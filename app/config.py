from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
PASTA_INSTANCE = RAIZ_PROJETO / "instance"
PASTA_UPLOADS = PASTA_INSTANCE / "uploads" / "materiais"
PASTA_LOGS = PASTA_INSTANCE / "logs"


def _bool_env(nome: str, padrao: bool = False) -> bool:
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "yes", "on", "sim"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-inseguro-troque-no-env")
    WTF_CSRF_TIME_LIMIT = 60 * 60

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool_env("SESSION_COOKIE_SECURE", True)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    REMEMBER_COOKIE_SECURE = _bool_env("SESSION_COOKIE_SECURE", True)
    REMEMBER_COOKIE_HTTPONLY = True

    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 8 * 1024 * 1024))

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{(PASTA_INSTANCE / 'app.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = str(PASTA_UPLOADS)
    MAX_PDF_BYTES = int(os.environ.get("MAX_PDF_BYTES", 8 * 1024 * 1024))
    MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_BYTES", 2 * 1024 * 1024))

    DOWNLOAD_TOKEN_TTL_DIAS = int(os.environ.get("DOWNLOAD_TOKEN_TTL_DIAS", 7))
    DOWNLOAD_TOKEN_MAX_USOS = int(os.environ.get("DOWNLOAD_TOKEN_MAX_USOS", 5))

    EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "brevo_api")
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
    BREVO_SMTP_HOST = os.environ.get("BREVO_SMTP_HOST", "smtp-relay.brevo.com")
    BREVO_SMTP_PORT = int(os.environ.get("BREVO_SMTP_PORT", 587))
    BREVO_SMTP_USER = os.environ.get("BREVO_SMTP_USER", "")
    BREVO_SMTP_PASSWORD = os.environ.get("BREVO_SMTP_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "contato@bvconsultora.com")
    MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", "Beatriz Vasconcelos - Consultora de Alimentos")
    MAIL_REPLY_TO = os.environ.get("MAIL_REPLY_TO", "beatriz.consultoradealimentos@gmail.com")

    CONTATO_EMAIL = os.environ.get("CONTATO_EMAIL", "beatriz.consultoradealimentos@gmail.com")
    CONTATO_WHATSAPP = os.environ.get(
        "CONTATO_WHATSAPP", "https://api.whatsapp.com/send?phone=5511945097739"
    )
    CONTATO_INSTAGRAM = os.environ.get(
        "CONTATO_INSTAGRAM", "https://www.instagram.com/beatriz.consultoradealimentos/"
    )
    CONTATO_LINKEDIN = os.environ.get(
        "CONTATO_LINKEDIN", "https://www.linkedin.com/in/beatrizvasconcelosconsultora/"
    )

    SITE_URL = os.environ.get("SITE_URL", "https://bvconsultora.com")

    TURNSTILE_ENABLED = _bool_env("TURNSTILE_ENABLED", False)
    TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "")
    TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET", "")
    TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_PUBLICO = os.environ.get("RATELIMIT_PUBLICO", "5 per hour")
    RATELIMIT_LOGIN = os.environ.get("RATELIMIT_LOGIN", "5 per minute")

    PREFERRED_URL_SCHEME = "https"
    DEBUG = False
    TESTING = False


class DevConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    PREFERRED_URL_SCHEME = "http"
    EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "console")


class ProdConfig(Config):
    @staticmethod
    def validar() -> None:
        problemas = []
        if os.environ.get("SECRET_KEY", "") in ("", "dev-inseguro-troque-no-env"):
            problemas.append("SECRET_KEY não definida")
        provider = os.environ.get("EMAIL_PROVIDER", "brevo_api")
        if provider == "brevo_api" and not os.environ.get("BREVO_API_KEY"):
            problemas.append("BREVO_API_KEY não definida")
        if provider == "brevo_smtp" and not os.environ.get("BREVO_SMTP_PASSWORD"):
            problemas.append("BREVO_SMTP_PASSWORD não definida")
        if problemas:
            raise RuntimeError("Configuração de produção incompleta: " + "; ".join(problemas))


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SESSION_COOKIE_SECURE = False
    EMAIL_PROVIDER = "console"
    RATELIMIT_ENABLED = False


CONFIGS = {"development": DevConfig, "production": ProdConfig, "testing": TestConfig}


def escolher_config(nome: str | None = None):
    nome = (
        nome or os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or "production"
    ).strip().lower()
    return CONFIGS.get(nome, ProdConfig)
