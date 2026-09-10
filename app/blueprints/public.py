from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

import requests
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)

from ..emailer import (
    ErroEnvioEmail,
    enviar_email_boas_vindas,
    enviar_email_confirmacao,
    enviar_email_material,
)
from ..extensions import db, limiter
from ..forms import LeadForm
from ..models import DownloadToken, Lead, Material, agora
from ..security import hash_ip, ip_do_cliente

bp = Blueprint("public", __name__)

NOME_CAPA_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|jpeg|png|webp)$", re.IGNORECASE)
MAX_PEDIDOS_POR_EMAIL_DIA = 3


def _limite_publico():
    return current_app.config["RATELIMIT_PUBLICO"]


def _turnstile_ok() -> bool:
    cfg = current_app.config
    if not cfg.get("TURNSTILE_ENABLED"):
        return True
    token = request.form.get("cf-turnstile-response", "")
    if not token:
        return False
    try:
        resp = requests.post(
            cfg["TURNSTILE_VERIFY_URL"],
            data={"secret": cfg["TURNSTILE_SECRET"], "response": token,
                  "remoteip": ip_do_cliente() or ""},
            timeout=8,
        )
        return bool(resp.json().get("success"))
    except (requests.RequestException, ValueError):
        current_app.logger.warning("Turnstile não pôde ser validado; recusando envio.")
        return False


def _excedeu_limite_email(email: str) -> bool:
    desde = agora() - timedelta(days=1)
    n = Lead.query.filter(Lead.email == email, Lead.created_at >= desde).count()
    return n >= MAX_PEDIDOS_POR_EMAIL_DIA


def _registrar_lead(form: LeadForm, source: str, material: Material | None) -> Lead:
    eh_outro = form.referral_source.data == "outro"
    lead = Lead(
        full_name=form.full_name.data,
        email=form.email.data,
        company=form.company.data,
        role=form.role.data,
        referral_source=form.referral_source.data,
        referral_other=(form.referral_other.data or None) if eh_outro else None,
        material=material,
        source=source,
        consent_lgpd=True,
        consent_at=agora(),
        confirm_token=Lead.novo_confirm_token(),
        ip_hash=hash_ip(ip_do_cliente()),
        user_agent=(request.user_agent.string or "")[:255],
    )
    db.session.add(lead)
    db.session.commit()

    try:
        enviar_email_confirmacao(lead)
        lead.email_status = "sent"
    except (ErroEnvioEmail, OSError) as exc:
        lead.email_status = "failed"
        current_app.logger.error("Falha no e-mail de confirmação para %s: %s", lead.email, exc)
    db.session.commit()
    return lead


@bp.route("/")
def home():
    return render_template("index.html")


@bp.route("/privacidade")
def privacidade():
    return render_template("privacidade.html")


@bp.route("/materiais/capa/<nome>")
def capa(nome: str):
    if not NOME_CAPA_RE.match(nome):
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], nome, max_age=86400)


@bp.route("/materiais")
def materiais():
    itens = (
        Material.query.filter_by(is_published=True)
        .order_by(Material.created_at.desc())
        .all()
    )
    return render_template("materiais.html", materiais=itens)


@bp.route("/materiais/<slug>")
def material_detalhe(slug: str):
    material = Material.query.filter_by(slug=slug, is_published=True).first_or_404()
    return render_template("material_detail.html", material=material, form=LeadForm())


@bp.route("/materiais/<slug>/solicitar", methods=["POST"])
@limiter.limit(_limite_publico)
def solicitar_material(slug: str):
    material = Material.query.filter_by(slug=slug, is_published=True).first_or_404()
    form = LeadForm()

    if (form.website.data or "").strip():
        current_app.logger.info("Honeypot acionado em %s", slug)
        return redirect(url_for("public.material_sucesso", slug=slug))

    valido = form.validate_on_submit()
    if not _turnstile_ok():
        flash("Não conseguimos confirmar que você não é um robô. Tente novamente.", "erro")
        valido = False
    if not valido:
        for erros in form.errors.values():
            for erro in erros:
                flash(erro, "erro")
        return render_template("material_detail.html", material=material, form=form), 400

    if _excedeu_limite_email(form.email.data):
        flash("Já registramos várias solicitações para este e-mail hoje. Tente amanhã.", "erro")
        return render_template("material_detail.html", material=material, form=form), 429

    _registrar_lead(form, "material", material)
    return redirect(url_for("public.material_sucesso", slug=slug))


@bp.route("/materiais/<slug>/sucesso")
def material_sucesso(slug: str):
    material = Material.query.filter_by(slug=slug, is_published=True).first_or_404()
    return render_template("material_sucesso.html", material=material)


@bp.route("/cadastro", methods=["POST"])
@limiter.limit(_limite_publico)
def cadastro():
    form = LeadForm()

    if (form.website.data or "").strip():
        current_app.logger.info("Honeypot acionado no cadastro")
        return redirect(url_for("public.cadastro_sucesso"))

    if not form.validate_on_submit() or not _turnstile_ok():
        flash("Não foi possível concluir o cadastro. Confira os campos e tente de novo.", "erro")
        return render_template("cadastro.html", form=form), 400

    if _excedeu_limite_email(form.email.data):
        flash("Já registramos várias solicitações para este e-mail hoje. Tente amanhã.", "erro")
        return render_template("cadastro.html", form=form), 429

    _registrar_lead(form, "popup", None)
    return redirect(url_for("public.cadastro_sucesso"))


@bp.route("/cadastro/sucesso")
def cadastro_sucesso():
    return render_template("cadastro_sucesso.html")


@bp.route("/confirmar/<token>")
@limiter.limit("20 per hour")
def confirmar(token: str):
    lead = Lead.query.filter_by(confirm_token=token).first()
    if lead is None:
        abort(404)

    if lead.confirmed:
        return render_template("cadastro_confirmado.html", lead=lead, repetido=True)

    lead.confirmed = True
    lead.confirmed_at = agora()

    try:
        if lead.source == "material" and lead.material:
            dt = DownloadToken.gerar(
                lead.material_id, lead.id,
                current_app.config["DOWNLOAD_TOKEN_TTL_DIAS"],
                current_app.config["DOWNLOAD_TOKEN_MAX_USOS"],
            )
            db.session.add(dt)
            db.session.flush()
            enviar_email_material(lead, lead.material, dt.token)
        else:
            enviar_email_boas_vindas(lead)
        lead.email_status = "sent"
    except (ErroEnvioEmail, OSError) as exc:
        lead.email_status = "failed"
        current_app.logger.error("Falha no envio pós-confirmação para %s: %s", lead.email, exc)

    db.session.commit()
    return render_template("cadastro_confirmado.html", lead=lead, repetido=False)


@bp.route("/baixar/<token>")
@limiter.limit("30 per hour")
def baixar(token: str):
    registro = DownloadToken.query.filter_by(token=token).first()
    if registro is None:
        abort(404)
    if not registro.valido:
        return render_template("download_expirado.html"), 410

    material = registro.material
    caminho = Path(current_app.config["UPLOAD_FOLDER"]) / material.pdf_path
    if not caminho.is_file():
        current_app.logger.error("PDF ausente no disco: %s", caminho)
        abort(404)

    registro.uses += 1
    material.download_count += 1
    db.session.commit()

    return send_file(
        caminho, mimetype="application/pdf", as_attachment=True,
        download_name=material.pdf_filename, max_age=0,
    )
