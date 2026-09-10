from __future__ import annotations

from pathlib import Path

from flask import current_app, render_template, url_for

from .providers import Anexo, ErroEnvioEmail, Mensagem, criar_provider

__all__ = [
    "enviar_email_confirmacao",
    "enviar_email_material",
    "enviar_email_boas_vindas",
    "ErroEnvioEmail",
]

MAX_ANEXO_BYTES = 6 * 1024 * 1024


def _url_externa(endpoint: str, **kw) -> str:
    try:
        return url_for(endpoint, _external=True, **kw)
    except RuntimeError:
        base = current_app.config["SITE_URL"].rstrip("/")
        cam = url_for(endpoint, **kw)
        return f"{base}{cam}"


def _contatos() -> dict:
    cfg = current_app.config
    return {
        "contato_email": cfg["CONTATO_EMAIL"],
        "contato_whatsapp": cfg["CONTATO_WHATSAPP"],
        "contato_instagram": cfg["CONTATO_INSTAGRAM"],
        "contato_linkedin": cfg["CONTATO_LINKEDIN"],
    }


def _remetente() -> dict:
    cfg = current_app.config
    return {
        "de_email": cfg["MAIL_FROM"],
        "de_nome": cfg["MAIL_FROM_NAME"],
        "reply_to": cfg.get("MAIL_REPLY_TO") or None,
    }


def _enviar(lead, assunto: str, template: str, ctx: dict, anexos: list[Anexo] | None = None) -> None:
    ctx = {"lead": lead, **_contatos(), **ctx}
    msg = Mensagem(
        para_email=lead.email,
        para_nome=lead.full_name,
        assunto=assunto,
        html=render_template(f"{template}.html", **ctx),
        texto=render_template(f"{template}.txt", **ctx),
        anexos=anexos or [],
        **_remetente(),
    )
    criar_provider(current_app.config, current_app.logger).enviar(msg)


def enviar_email_confirmacao(lead) -> None:
    link = _url_externa("public.confirmar", token=lead.confirm_token)
    assunto = "Confirme seu e-mail"
    if lead.source == "material" and lead.material:
        assunto = f"Confirme para receber: {lead.material.title}"
    _enviar(lead, assunto, "email/confirmar", {"link_confirmar": link})


def enviar_email_material(lead, material, download_token: str) -> None:
    caminho = Path(current_app.config["UPLOAD_FOLDER"]) / material.pdf_path
    dados = caminho.read_bytes()

    anexos: list[Anexo] = []
    if len(dados) <= MAX_ANEXO_BYTES:
        anexos.append(Anexo(material.pdf_filename, dados))
    else:
        current_app.logger.warning(
            "PDF de %s tem %d bytes; enviando só o link.", material.slug, len(dados)
        )

    _enviar(
        lead,
        f"Seu material: {material.title}",
        "email/material",
        {
            "material": material,
            "link_download": _url_externa("public.baixar", token=download_token),
        },
        anexos,
    )


def enviar_email_boas_vindas(lead) -> None:
    _enviar(
        lead,
        "Cadastro confirmado",
        "email/boas_vindas",
        {"link_materiais": _url_externa("public.materiais")},
    )
