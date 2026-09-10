from __future__ import annotations

import base64
import smtplib
from dataclasses import dataclass, field
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests


@dataclass
class Anexo:
    filename: str
    content: bytes


@dataclass
class Mensagem:
    para_email: str
    para_nome: str
    assunto: str
    html: str
    texto: str
    de_email: str
    de_nome: str
    reply_to: str | None = None
    anexos: list[Anexo] = field(default_factory=list)


class ErroEnvioEmail(RuntimeError):
    pass


class ConsoleProvider:
    """Não envia nada; só registra. Usado em desenvolvimento."""

    def __init__(self, logger=None):
        self._logger = logger

    def enviar(self, msg: Mensagem) -> None:
        linha = f"[email:console] para={msg.para_email} assunto={msg.assunto!r} anexos={[a.filename for a in msg.anexos]}"
        (self._logger.info if self._logger else print)(linha)


class BrevoAPIProvider:
    URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, api_key: str, timeout: int = 15):
        if not api_key:
            raise ErroEnvioEmail("BREVO_API_KEY ausente.")
        self._api_key = api_key
        self._timeout = timeout

    def enviar(self, msg: Mensagem) -> None:
        payload = {
            "sender": {"email": msg.de_email, "name": msg.de_nome},
            "to": [{"email": msg.para_email, "name": msg.para_nome}],
            "subject": msg.assunto,
            "htmlContent": msg.html,
            "textContent": msg.texto,
        }
        if msg.reply_to:
            payload["replyTo"] = {"email": msg.reply_to}
        if msg.anexos:
            payload["attachment"] = [
                {"name": a.filename, "content": base64.b64encode(a.content).decode()}
                for a in msg.anexos
            ]

        try:
            resp = requests.post(
                self.URL, json=payload, timeout=self._timeout,
                headers={"api-key": self._api_key, "content-type": "application/json"},
            )
        except requests.RequestException as exc:
            raise ErroEnvioEmail(f"Falha de rede ao chamar a Brevo: {exc}") from exc

        if resp.status_code >= 300:
            raise ErroEnvioEmail(f"Brevo respondeu {resp.status_code}: {resp.text[:400]}")


class BrevoSMTPProvider:
    def __init__(self, host, port, user, password, timeout=20):
        if not (user and password):
            raise ErroEnvioEmail("Credenciais SMTP da Brevo ausentes.")
        self._host, self._port = host, port
        self._user, self._password = user, password
        self._timeout = timeout

    def enviar(self, msg: Mensagem) -> None:
        raiz = MIMEMultipart("mixed")
        raiz["Subject"] = msg.assunto
        raiz["From"] = f"{msg.de_nome} <{msg.de_email}>"
        raiz["To"] = f"{msg.para_nome} <{msg.para_email}>"
        if msg.reply_to:
            raiz["Reply-To"] = msg.reply_to

        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(msg.texto, "plain", "utf-8"))
        alt.attach(MIMEText(msg.html, "html", "utf-8"))
        raiz.attach(alt)

        for a in msg.anexos:
            parte = MIMEApplication(a.content, _subtype="pdf")
            parte.add_header("Content-Disposition", "attachment", filename=a.filename)
            raiz.attach(parte)

        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as srv:
                srv.starttls()
                srv.login(self._user, self._password)
                srv.send_message(raiz)
        except (smtplib.SMTPException, OSError) as exc:
            raise ErroEnvioEmail(f"Falha ao enviar via SMTP da Brevo: {exc}") from exc


def criar_provider(config, logger=None):
    nome = (config.get("EMAIL_PROVIDER") or "brevo_api").strip().lower()
    if nome == "console":
        return ConsoleProvider(logger)
    if nome == "brevo_smtp":
        return BrevoSMTPProvider(
            config["BREVO_SMTP_HOST"], config["BREVO_SMTP_PORT"],
            config["BREVO_SMTP_USER"], config["BREVO_SMTP_PASSWORD"],
        )
    return BrevoAPIProvider(config["BREVO_API_KEY"])
