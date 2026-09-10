from __future__ import annotations

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template  # noqa: E402
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

from .config import PASTA_INSTANCE, PASTA_LOGS, PASTA_UPLOADS, escolher_config  # noqa: E402
from .extensions import csrf, db, limiter, login_manager  # noqa: E402
from .security import registrar_cabecalhos_seguranca  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


def _preparar_pastas() -> None:
    for pasta in (PASTA_INSTANCE, PASTA_UPLOADS, PASTA_LOGS):
        pasta.mkdir(parents=True, exist_ok=True)


def _configurar_logs(app: Flask) -> None:
    if app.debug or app.testing:
        return
    handler = RotatingFileHandler(
        PASTA_LOGS / "app.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)


def _registrar_erros(app: Flask) -> None:
    for codigo in (400, 403, 404, 413, 429):
        app.register_error_handler(
            codigo, lambda e, c=codigo: (render_template(f"errors/{c}.html"), c)
        )

    @app.errorhandler(500)
    def _500(e):
        app.logger.exception("Erro interno não tratado")
        return render_template("errors/500.html"), 500


def create_app(config_nome: str | None = None) -> Flask:
    _preparar_pastas()

    app = Flask(
        __name__,
        template_folder=str(RAIZ / "templates"),
        static_folder=str(RAIZ / "static"),
        instance_path=str(PASTA_INSTANCE),
    )
    Config = escolher_config(config_nome)
    app.config.from_object(Config)
    if hasattr(Config, "validar"):
        Config.validar()

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    @login_manager.user_loader
    def carregar_admin(user_id: str):
        from .models import AdminUser

        return db.session.get(AdminUser, int(user_id))

    from .blueprints.public import bp as public_bp
    from .blueprints.admin import bp as admin_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    from .cli import registrar_cli

    registrar_cli(app)

    registrar_cabecalhos_seguranca(app)
    _configurar_logs(app)
    _registrar_erros(app)

    @app.context_processor
    def _globais_template():
        return {
            "ano_atual": datetime.now().year,
            "turnstile_enabled": app.config["TURNSTILE_ENABLED"],
            "turnstile_site_key": app.config["TURNSTILE_SITE_KEY"],
            "contato": {
                "email": app.config["CONTATO_EMAIL"],
                "whatsapp": app.config["CONTATO_WHATSAPP"],
                "instagram": app.config["CONTATO_INSTAGRAM"],
                "linkedin": app.config["CONTATO_LINKEDIN"],
            },
        }

    with app.app_context():
        db.create_all()

    return app
