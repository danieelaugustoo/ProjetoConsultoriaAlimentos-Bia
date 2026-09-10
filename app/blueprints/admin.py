from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from ..emailer import enviar_email_material
from ..emailer.sender import ErroEnvioEmail
from ..extensions import db, limiter
from ..forms import LoginForm, MaterialForm
from ..models import AdminUser, DownloadToken, Lead, Material, agora
from ..security import ErroUpload, salvar_imagem, salvar_pdf, sanitizar_html

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _upload_dir():
    return current_app.config["UPLOAD_FOLDER"]


def _limite_login():
    return current_app.config["RATELIMIT_LOGIN"]


def _slugify(texto: str) -> str:
    txt = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    txt = re.sub(r"[^a-zA-Z0-9]+", "-", txt).strip("-").lower()
    return txt or "material"


def _slug_unico(base: str, ignorar_id: int | None = None) -> str:
    slug, i = base, 2
    while True:
        q = Material.query.filter_by(slug=slug)
        if ignorar_id is not None:
            q = q.filter(Material.id != ignorar_id)
        if q.first() is None:
            return slug
        slug, i = f"{base}-{i}", i + 1


def _remover_arquivo(nome: str | None) -> None:
    if not nome:
        return
    try:
        (Path(_upload_dir()) / nome).unlink(missing_ok=True)
    except OSError as exc:
        current_app.logger.warning("Não removi %s: %s", nome, exc)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit(_limite_login, methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = AdminUser.query.filter_by(email=form.email.data).first()
        if user is None or not user.check_password(form.password.data):
            current_app.logger.warning("Login admin falhou: %s", form.email.data)
            flash("E-mail ou senha incorretos.", "erro")
            return render_template("admin/login.html", form=form), 401

        login_user(user, remember=False)
        user.last_login_at = agora()
        db.session.commit()
        current_app.logger.info("Login admin OK: %s", user.email)

        destino = request.args.get("next")
        if not destino or not destino.startswith("/") or destino.startswith("//"):
            destino = url_for("admin.dashboard")
        return redirect(destino)

    return render_template("admin/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Sessão encerrada.", "ok")
    return redirect(url_for("admin.login"))


@bp.route("/")
@login_required
def dashboard():
    return render_template(
        "admin/dashboard.html",
        total_materiais=Material.query.count(),
        total_publicados=Material.query.filter_by(is_published=True).count(),
        total_leads=Lead.query.count(),
        falhas_email=Lead.query.filter_by(email_status="failed").count(),
        ultimos=Lead.query.order_by(Lead.created_at.desc()).limit(5).all(),
    )


@bp.route("/materiais")
@login_required
def materiais_listar():
    itens = Material.query.order_by(Material.created_at.desc()).all()
    return render_template("admin/materiais.html", materiais=itens)


@bp.route("/materiais/novo", methods=["GET", "POST"])
@login_required
def material_novo():
    form = MaterialForm(exige_pdf=True)
    if form.validate_on_submit():
        try:
            nome_disco, nome_amigavel = salvar_pdf(
                form.pdf.data, _upload_dir(), current_app.config["MAX_PDF_BYTES"]
            )
            capa = salvar_imagem(form.cover.data, _upload_dir(), current_app.config["MAX_IMAGE_BYTES"])
        except ErroUpload as exc:
            flash(str(exc), "erro")
            return render_template("admin/material_form.html", form=form, modo="novo"), 400

        material = Material(
            title=form.title.data,
            slug=_slug_unico(_slugify(form.slug.data or form.title.data)),
            summary=form.summary.data,
            body_html=sanitizar_html(form.body_html.data),
            pdf_path=nome_disco,
            pdf_filename=nome_amigavel,
            cover_path=capa,
            is_published=form.is_published.data,
        )
        db.session.add(material)
        db.session.commit()
        current_app.logger.info("Material criado: %s", material.slug)
        flash("Material criado com sucesso.", "ok")
        return redirect(url_for("admin.materiais_listar"))

    return render_template("admin/material_form.html", form=form, modo="novo")


@bp.route("/materiais/<int:material_id>/editar", methods=["GET", "POST"])
@login_required
def material_editar(material_id: int):
    material = db.session.get(Material, material_id) or abort(404)
    form = MaterialForm(obj=material)

    if form.validate_on_submit():
        try:
            if form.pdf.data:
                novo_disco, novo_amigavel = salvar_pdf(
                    form.pdf.data, _upload_dir(), current_app.config["MAX_PDF_BYTES"]
                )
                _remover_arquivo(material.pdf_path)
                material.pdf_path, material.pdf_filename = novo_disco, novo_amigavel
            if form.cover.data:
                nova_capa = salvar_imagem(
                    form.cover.data, _upload_dir(), current_app.config["MAX_IMAGE_BYTES"]
                )
                _remover_arquivo(material.cover_path)
                material.cover_path = nova_capa
        except ErroUpload as exc:
            flash(str(exc), "erro")
            return render_template(
                "admin/material_form.html", form=form, modo="editar", material=material
            ), 400

        material.title = form.title.data
        if form.slug.data:
            material.slug = _slug_unico(_slugify(form.slug.data), ignorar_id=material.id)
        material.summary = form.summary.data
        material.body_html = sanitizar_html(form.body_html.data)
        material.is_published = form.is_published.data
        db.session.commit()
        current_app.logger.info("Material editado: %s", material.slug)
        flash("Material atualizado.", "ok")
        return redirect(url_for("admin.materiais_listar"))

    if request.method == "GET":
        form.body_html.data = material.body_html
    return render_template("admin/material_form.html", form=form, modo="editar", material=material)


@bp.route("/materiais/<int:material_id>/excluir", methods=["POST"])
@login_required
def material_excluir(material_id: int):
    material = db.session.get(Material, material_id) or abort(404)
    _remover_arquivo(material.pdf_path)
    _remover_arquivo(material.cover_path)
    db.session.delete(material)
    db.session.commit()
    current_app.logger.info("Material excluído: %s", material.slug)
    flash("Material excluído.", "ok")
    return redirect(url_for("admin.materiais_listar"))


@bp.route("/leads")
@login_required
def leads_listar():
    material_id = request.args.get("material", type=int)
    busca = (request.args.get("q") or "").strip()

    query = Lead.query.order_by(Lead.created_at.desc())
    if material_id:
        query = query.filter(Lead.material_id == material_id)
    if busca:
        termo = f"%{busca}%"
        query = query.filter(
            db.or_(Lead.full_name.ilike(termo), Lead.email.ilike(termo), Lead.company.ilike(termo))
        )

    return render_template(
        "admin/leads.html",
        leads=query.limit(500).all(),
        materiais=Material.query.order_by(Material.title).all(),
        material_id=material_id,
        busca=busca,
    )


@bp.route("/leads.csv")
@login_required
def leads_csv():
    material_id = request.args.get("material", type=int)
    query = Lead.query.order_by(Lead.created_at.desc())
    if material_id:
        query = query.filter(Lead.material_id == material_id)

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Data", "Nome", "E-mail", "Empresa", "Cargo", "Como conheceu", "Material", "Status e-mail"])
    for lead in query.all():
        writer.writerow([
            lead.created_at.strftime("%d/%m/%Y %H:%M"),
            lead.full_name, lead.email, lead.company, lead.role,
            lead.origem_label,
            lead.material.title if lead.material else "",
            lead.email_status,
        ])

    return Response(
        buffer.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@bp.route("/leads/<int:lead_id>/excluir", methods=["POST"])
@login_required
def lead_excluir(lead_id: int):
    lead = db.session.get(Lead, lead_id) or abort(404)
    DownloadToken.query.filter_by(lead_id=lead.id).update({"lead_id": None})
    db.session.delete(lead)
    db.session.commit()
    current_app.logger.info("Lead %s excluído", lead_id)
    flash("Lead excluído.", "ok")
    return redirect(request.referrer or url_for("admin.leads_listar"))


@bp.route("/leads/<int:lead_id>/reenviar", methods=["POST"])
@login_required
def lead_reenviar(lead_id: int):
    lead = db.session.get(Lead, lead_id) or abort(404)
    token = DownloadToken.gerar(
        lead.material_id, lead.id,
        current_app.config["DOWNLOAD_TOKEN_TTL_DIAS"],
        current_app.config["DOWNLOAD_TOKEN_MAX_USOS"],
    )
    db.session.add(token)
    db.session.commit()
    try:
        enviar_email_material(lead, lead.material, token.token)
        lead.email_status = "sent"
        flash("E-mail reenviado.", "ok")
    except (ErroEnvioEmail, OSError) as exc:
        lead.email_status = "failed"
        current_app.logger.error("Reenvio falhou para %s: %s", lead.email, exc)
        flash("Não foi possível reenviar o e-mail. Verifique a configuração de envio.", "erro")
    db.session.commit()
    return redirect(request.referrer or url_for("admin.leads_listar"))
