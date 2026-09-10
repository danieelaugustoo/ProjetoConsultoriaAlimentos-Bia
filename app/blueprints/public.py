from __future__ import annotations

import re
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

from ..emailer import enviar_email_material
from ..emailer.sender import ErroEnvioEmail
from ..extensions import db, limiter
from ..forms import LeadForm
from ..models import DownloadToken, Lead, Material, agora
from ..security import hash_ip, ip_do_cliente

bp = Blueprint("public", __name__)

NOME_CAPA_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|jpeg|png|webp)$", re.IGNORECASE)


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

    if not form.validate_on_submit():
        for erros in form.errors.values():
            for erro in erros:
                flash(erro, "erro")
        return render_template("material_detail.html", material=material, form=form), 400

    if not _turnstile_ok():
        flash("Não conseguimos confirmar que você não é um robô. Tente novamente.", "erro")
        return render_template("material_detail.html", material=material, form=form), 400

    eh_outro = form.referral_source.data == "outro"
    lead = Lead(
        full_name=form.full_name.data,
        email=form.email.data,
        company=form.company.data,
        role=form.role.data,
        referral_source=form.referral_source.data,
        referral_other=(form.referral_other.data or None) if eh_outro else None,
        material=material,
        consent_lgpd=True,
        consent_at=agora(),
        ip_hash=hash_ip(ip_do_cliente()),
        user_agent=(request.user_agent.string or "")[:255],
    )
    token = DownloadToken.gerar(
        material.id, None,
        current_app.config["DOWNLOAD_TOKEN_TTL_DIAS"],
        current_app.config["DOWNLOAD_TOKEN_MAX_USOS"],
    )
    db.session.add(lead)
    db.session.flush()
    token.lead_id = lead.id
    db.session.add(token)
    db.session.commit()

    try:
        enviar_email_material(lead, material, token.token)
        lead.email_status = "sent"
    except (ErroEnvioEmail, OSError) as exc:
        lead.email_status = "failed"
        current_app.logger.error("Falha ao enviar %s para %s: %s", slug, lead.email, exc)
    db.session.commit()

    return redirect(url_for("public.material_sucesso", slug=slug))


@bp.route("/materiais/<slug>/sucesso")
def material_sucesso(slug: str):
    material = Material.query.filter_by(slug=slug, is_published=True).first_or_404()
    return render_template("material_sucesso.html", material=material)


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
