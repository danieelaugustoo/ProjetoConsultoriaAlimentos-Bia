from __future__ import annotations

import re

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    BooleanField,
    HiddenField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, Optional, Regexp, ValidationError

from .antispam import carimbo_valido, email_descartavel
from .models import ORIGENS

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _strip(v):
    return v.strip() if isinstance(v, str) else v


def _strip_lower(v):
    return v.strip().lower() if isinstance(v, str) else v


class LeadForm(FlaskForm):
    full_name = StringField(
        "Nome completo",
        validators=[DataRequired("Informe seu nome completo."), Length(min=3, max=160)],
        filters=[_strip],
    )
    email = StringField(
        "E-mail",
        validators=[DataRequired("Informe seu e-mail."), Email("E-mail inválido."), Length(max=190)],
        filters=[_strip_lower],
    )
    company = StringField(
        "Nome da empresa",
        validators=[DataRequired("Informe o nome da empresa."), Length(min=2, max=160)],
        filters=[_strip],
    )
    role = StringField(
        "Cargo",
        validators=[DataRequired("Informe seu cargo."), Length(min=2, max=120)],
        filters=[_strip],
    )
    referral_source = SelectField(
        "Como você conheceu a Beatriz Vasconcelos?",
        choices=[("", "Selecione uma opção")] + ORIGENS,
        validators=[DataRequired("Escolha uma opção.")],
    )
    referral_other = StringField(
        "Conte um pouco mais", validators=[Optional(), Length(max=160)], filters=[_strip]
    )
    consent_lgpd = BooleanField(
        "Autorizo o tratamento dos meus dados conforme a Política de Privacidade.",
        validators=[DataRequired("É necessário aceitar a Política de Privacidade.")],
    )
    website = HiddenField()  # honeypot
    ts = HiddenField()       # carimbo de tempo assinado (honeypot temporal)
    submit = SubmitField("Receber material")

    def validate_referral_source(self, field):
        if field.data == "outro" and not (self.referral_other.data or "").strip():
            raise ValidationError('Descreva como conheceu a Beatriz (você escolheu "Outro").')

    def validate_email(self, field):
        if email_descartavel(field.data or ""):
            raise ValidationError("Use um e-mail permanente, não um endereço temporário.")

    def validate_ts(self, field):
        if not carimbo_valido(field.data or ""):
            raise ValidationError("Envio inválido. Recarregue a página e tente de novo.")


class LoginForm(FlaskForm):
    email = StringField("E-mail", validators=[DataRequired(), Email(), Length(max=190)], filters=[_strip_lower])
    password = PasswordField("Senha", validators=[DataRequired(), Length(max=200)])
    submit = SubmitField("Entrar")


class MaterialForm(FlaskForm):
    title = StringField(
        "Título",
        validators=[DataRequired("Informe o título."), Length(min=3, max=180)],
        filters=[_strip],
    )
    slug = StringField(
        "Slug (endereço)",
        validators=[Optional(), Length(max=180),
                    Regexp(SLUG_RE, message="Use apenas letras minúsculas, números e hífens.")],
        filters=[_strip_lower],
    )
    summary = TextAreaField(
        "Chamada curta",
        validators=[DataRequired("Escreva uma chamada curta."), Length(min=10, max=300)],
        filters=[_strip],
    )
    body_html = TextAreaField("Conteúdo (texto do post)", validators=[Optional(), Length(max=20000)])
    pdf = FileField("Arquivo PDF do material", validators=[Optional(), FileAllowed(["pdf"], "Envie um arquivo .pdf.")])
    cover = FileField(
        "Imagem de capa",
        validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Imagem .jpg, .png ou .webp.")],
    )
    is_published = BooleanField("Publicado (visível no site)")
    submit = SubmitField("Salvar material")

    def __init__(self, *args, exige_pdf: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        if exige_pdf:
            self.pdf.validators = [FileRequired("Envie o PDF do material."), *self.pdf.validators]
