from __future__ import annotations

from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address)

login_manager.login_view = "admin.login"
login_manager.login_message = "Faça login para acessar o painel."
login_manager.login_message_category = "aviso"
login_manager.session_protection = "strong"
