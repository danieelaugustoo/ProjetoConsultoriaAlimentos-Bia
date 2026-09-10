from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def agora() -> datetime:
    return datetime.now(timezone.utc)


ORIGENS = [
    ("instagram", "Instagram"),
    ("linkedin", "LinkedIn"),
    ("indicacao", "Indicação de amigo ou colega"),
    ("google", "Google / busca"),
    ("evento", "Evento ou palestra"),
    ("cliente", "Já sou cliente"),
    ("outro", "Outro"),
]
ORIGENS_LABEL = dict(ORIGENS)


class AdminUser(UserMixin, db.Model):
    __tablename__ = "admin_user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(190), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=agora, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True))

    def set_password(self, senha: str) -> None:
        self.password_hash = generate_password_hash(senha, method="scrypt")

    def check_password(self, senha: str) -> bool:
        return check_password_hash(self.password_hash, senha)


class Material(db.Model):
    __tablename__ = "material"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    summary = db.Column(db.String(300), nullable=False, default="")
    body_html = db.Column(db.Text, nullable=False, default="")

    cover_path = db.Column(db.String(255))
    pdf_path = db.Column(db.String(255), nullable=False)
    pdf_filename = db.Column(db.String(180), nullable=False, default="material.pdf")

    is_published = db.Column(db.Boolean, nullable=False, default=False, index=True)
    download_count = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), default=agora, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=agora, onupdate=agora, nullable=False)

    leads = db.relationship("Lead", back_populates="material", cascade="all, delete-orphan")
    tokens = db.relationship("DownloadToken", back_populates="material", cascade="all, delete-orphan")


class Lead(db.Model):
    __tablename__ = "lead"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(190), nullable=False, index=True)
    company = db.Column(db.String(160), nullable=False)
    role = db.Column(db.String(120), nullable=False)
    referral_source = db.Column(db.String(30), nullable=False)
    referral_other = db.Column(db.String(160))

    material_id = db.Column(db.Integer, db.ForeignKey("material.id"), nullable=False, index=True)
    material = db.relationship("Material", back_populates="leads")

    consent_lgpd = db.Column(db.Boolean, nullable=False, default=False)
    consent_at = db.Column(db.DateTime(timezone=True))

    ip_hash = db.Column(db.String(64))
    user_agent = db.Column(db.String(255))
    email_status = db.Column(db.String(20), nullable=False, default="pending")

    created_at = db.Column(db.DateTime(timezone=True), default=agora, nullable=False, index=True)

    @property
    def origem_label(self) -> str:
        if self.referral_source == "outro" and self.referral_other:
            return f"Outro: {self.referral_other}"
        return ORIGENS_LABEL.get(self.referral_source, self.referral_source)


class DownloadToken(db.Model):
    __tablename__ = "download_token"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)

    material_id = db.Column(db.Integer, db.ForeignKey("material.id"), nullable=False)
    material = db.relationship("Material", back_populates="tokens")
    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"))

    created_at = db.Column(db.DateTime(timezone=True), default=agora, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    uses = db.Column(db.Integer, nullable=False, default=0)
    max_uses = db.Column(db.Integer, nullable=False, default=5)

    @classmethod
    def gerar(cls, material_id, lead_id, ttl_dias, max_uses) -> "DownloadToken":
        return cls(
            token=secrets.token_urlsafe(32),
            material_id=material_id,
            lead_id=lead_id,
            expires_at=agora() + timedelta(days=ttl_dias),
            max_uses=max_uses,
        )

    @property
    def valido(self) -> bool:
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return agora() <= exp and self.uses < self.max_uses
