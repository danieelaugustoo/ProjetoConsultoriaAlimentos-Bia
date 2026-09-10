from __future__ import annotations

from pathlib import Path

from flask import current_app, render_template, url_for

from .providers import Anexo, ErroEnvioEmail, Mensagem, criar_provider

__all__ = ["enviar_email_material", "ErroEnvioEmail"]

MAX_ANEXO_BYTES = 6 * 1024 * 1024


def _link_download(token: str) -> str:
    try:
        return url_for("public.baixar", token=token, _external=True)
    except RuntimeError:
        base = current_app.config["SITE_URL"].rstrip("/")
        return f"{base}/baixar/{token}"


def enviar_email_material(lead, material, token: str) -> None:
    cfg = current_app.config
    dados_pdf = (Path(cfg["UPLOAD_FOLDER"]) / material.pdf_path).read_bytes()

    ctx = {
        "lead": lead,
        "material": material,
        "link_download": _link_download(token),
        "contato_email": cfg["CONTATO_EMAIL"],
        "contato_whatsapp": cfg["CONTATO_WHATSAPP"],
        "contato_instagram": cfg["CONTATO_INSTAGRAM"],
        "contato_linkedin": cfg["CONTATO_LINKEDIN"],
    }

    anexos = []
    if len(dados_pdf) <= MAX_ANEXO_BYTES:
        anexos.append(Anexo(material.pdf_filename, dados_pdf))
    else:
        current_app.logger.warning(
            "PDF de %s tem %d bytes; enviando só o link.", material.slug, len(dados_pdf)
        )

    msg = Mensagem(
        para_email=lead.email,
        para_nome=lead.full_name,
        assunto=f"Seu material: {material.title}",
        html=render_template("email/material.html", **ctx),
        texto=render_template("email/material.txt", **ctx),
        de_email=cfg["MAIL_FROM"],
        de_nome=cfg["MAIL_FROM_NAME"],
        reply_to=cfg.get("MAIL_REPLY_TO") or None,
        anexos=anexos,
    )
    criar_provider(cfg, current_app.logger).enviar(msg)
