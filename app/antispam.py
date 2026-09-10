from __future__ import annotations

import time
from pathlib import Path

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

_DOMINIOS_DESCARTAVEIS: set[str] | None = None
_TEMPO_MINIMO_S = 2
_TEMPO_MAXIMO_S = 2 * 60 * 60


def _carregar_dominios() -> set[str]:
    global _DOMINIOS_DESCARTAVEIS
    if _DOMINIOS_DESCARTAVEIS is None:
        arq = Path(__file__).parent / "data" / "disposable_domains.txt"
        linhas = arq.read_text(encoding="utf-8").splitlines() if arq.is_file() else []
        _DOMINIOS_DESCARTAVEIS = {
            l.strip().lower() for l in linhas if l.strip() and not l.startswith("#")
        }
    return _DOMINIOS_DESCARTAVEIS


def email_descartavel(email: str) -> bool:
    dominio = (email or "").rsplit("@", 1)[-1].strip().lower()
    return dominio in _carregar_dominios()


def _signer() -> TimestampSigner:
    return TimestampSigner(current_app.config["SECRET_KEY"], salt="form-ts")


def carimbo_agora() -> str:
    """Valor para o campo oculto de tempo do formulário."""
    return _signer().sign(str(int(time.time()))).decode()


def carimbo_valido(valor: str) -> bool:
    """True se o carimbo é autêntico e o formulário ficou aberto tempo de gente."""
    if not valor:
        return False
    try:
        bruto = _signer().unsign(valor, max_age=_TEMPO_MAXIMO_S)
    except (BadSignature, SignatureExpired):
        return False
    try:
        emitido = int(bruto)
    except ValueError:
        return False
    return (int(time.time()) - emitido) >= _TEMPO_MINIMO_S
