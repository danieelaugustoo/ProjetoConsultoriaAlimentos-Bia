from __future__ import annotations

import getpass
from datetime import timedelta

import click
from flask import Flask

from .emailer import enviar_email_material
from .emailer.sender import ErroEnvioEmail
from .extensions import db
from .models import AdminUser, DownloadToken, Lead, agora


def registrar_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--senha", default=None)
    def create_admin(email: str, senha: str | None):
        """Cria o administrador ou redefine a senha dele."""
        email = email.strip().lower()
        if not senha:
            senha = getpass.getpass("Senha: ")
            if senha != getpass.getpass("Confirme a senha: "):
                raise click.ClickException("As senhas não conferem.")
        if len(senha) < 10:
            raise click.ClickException("Use uma senha com pelo menos 10 caracteres.")

        user = AdminUser.query.filter_by(email=email).first()
        if user is None:
            user = AdminUser(email=email)
            db.session.add(user)
            acao = "criado"
        else:
            acao = "atualizado"
        user.set_password(senha)
        db.session.commit()
        click.echo(f"Administrador {acao}: {email}")

    @app.cli.command("purge-leads")
    @click.option("--dias", default=365, show_default=True)
    @click.confirmation_option(prompt="Confirmar exclusão dos leads antigos?")
    def purge_leads(dias: int):
        """Remove leads mais antigos que N dias (retenção LGPD)."""
        limite = agora() - timedelta(days=dias)
        antigos = Lead.query.filter(Lead.created_at < limite).all()
        for lead in antigos:
            DownloadToken.query.filter_by(lead_id=lead.id).update({"lead_id": None})
            db.session.delete(lead)
        db.session.commit()
        click.echo(f"{len(antigos)} lead(s) removido(s).")

    @app.cli.command("resend-email")
    @click.argument("lead_id", type=int)
    def resend_email(lead_id: int):
        """Reenvia o material para um lead."""
        lead = db.session.get(Lead, lead_id)
        if lead is None:
            raise click.ClickException(f"Lead {lead_id} não encontrado.")
        token = DownloadToken.gerar(
            lead.material_id, lead.id,
            app.config["DOWNLOAD_TOKEN_TTL_DIAS"], app.config["DOWNLOAD_TOKEN_MAX_USOS"],
        )
        db.session.add(token)
        db.session.commit()
        try:
            enviar_email_material(lead, lead.material, token.token)
            lead.email_status = "sent"
            db.session.commit()
            click.echo(f"E-mail reenviado para {lead.email}.")
        except (ErroEnvioEmail, OSError) as exc:
            lead.email_status = "failed"
            db.session.commit()
            raise click.ClickException(f"Falha no envio: {exc}")
