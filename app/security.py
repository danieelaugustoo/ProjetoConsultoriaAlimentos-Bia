from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path

import bleach
from flask import Flask, Response, current_app, request
from werkzeug.utils import secure_filename

CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "script-src 'self' https://challenges.cloudflare.com; "
    "frame-src https://challenges.cloudflare.com; "
    "connect-src 'self' https://challenges.cloudflare.com; "
    "object-src 'none'"
)


def registrar_cabecalhos_seguranca(app: Flask) -> None:
    @app.after_request
    def _aplicar(resp: Response) -> Response:
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()"
        )
        resp.headers.setdefault("Content-Security-Policy", CSP)
        if request.is_secure or not app.debug:
            resp.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return resp


def hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    segredo = current_app.config["SECRET_KEY"].encode()
    return hashlib.sha256(segredo + ip.encode()).hexdigest()


def ip_do_cliente() -> str | None:
    return request.remote_addr


_TAGS = ["p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li",
         "h2", "h3", "h4", "blockquote", "a", "hr", "span"]
_ATTRS = {"a": ["href", "title", "target", "rel"]}


def sanitizar_html(bruto: str) -> str:
    limpo = bleach.clean(
        bruto or "", tags=_TAGS, attributes=_ATTRS,
        protocols=["http", "https", "mailto"], strip=True,
    )
    return bleach.linkify(limpo, skip_tags=["a"])


class ErroUpload(ValueError):
    pass


_PDF_MAGIC = b"%PDF-"
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _nome_unico(original: str) -> str:
    ext = Path(secure_filename(original)).suffix.lower()
    return f"{uuid.uuid4().hex}{ext}"


def salvar_pdf(file_storage, destino_dir: str, max_bytes: int) -> tuple[str, str]:
    if not file_storage or not file_storage.filename:
        raise ErroUpload("Nenhum PDF foi enviado.")
    nome_amigavel = secure_filename(file_storage.filename)
    if not nome_amigavel.lower().endswith(".pdf"):
        raise ErroUpload("O arquivo precisa ter extensão .pdf.")

    dados = file_storage.read()
    if not dados:
        raise ErroUpload("O PDF enviado está vazio.")
    if len(dados) > max_bytes:
        raise ErroUpload(f"O PDF excede o limite de {max_bytes // (1024 * 1024)} MB.")
    if not dados.startswith(_PDF_MAGIC):
        raise ErroUpload("O conteúdo do arquivo não é um PDF válido.")

    Path(destino_dir).mkdir(parents=True, exist_ok=True)
    nome_disco = _nome_unico(file_storage.filename)
    (Path(destino_dir) / nome_disco).write_bytes(dados)
    return nome_disco, nome_amigavel


def salvar_imagem(file_storage, destino_dir: str, max_bytes: int) -> str | None:
    if not file_storage or not file_storage.filename:
        return None
    ext = Path(secure_filename(file_storage.filename)).suffix.lower()
    if ext not in _IMG_EXTS:
        raise ErroUpload("A capa precisa ser .jpg, .png ou .webp.")

    dados = file_storage.read()
    if len(dados) > max_bytes:
        raise ErroUpload(f"A imagem excede o limite de {max_bytes // (1024 * 1024)} MB.")

    try:
        from PIL import Image

        Image.open(io.BytesIO(dados)).verify()
    except Exception as exc:
        raise ErroUpload("O arquivo de capa não é uma imagem válida.") from exc

    Path(destino_dir).mkdir(parents=True, exist_ok=True)
    nome_disco = _nome_unico(file_storage.filename)
    (Path(destino_dir) / nome_disco).write_bytes(dados)
    return nome_disco
