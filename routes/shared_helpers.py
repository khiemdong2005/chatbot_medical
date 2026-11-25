"""Shared HTTP/session helpers for modular Flask route handlers."""

from datetime import datetime
import sys
import uuid

from flask import request, session

from core.shared.db_utils import commit_or_rollback as _default_commit_or_rollback
from core.shared.models import User, db
from core.shared.network_utils import get_trusted_client_ip
from core.shared.settings import PROJECT_ROOT, settings

DEFAULT_UPLOAD_FOLDER = str(PROJECT_ROOT / "uploads")


def resolve_app_attr(name: str, default):
    """Resolve an attribute from ``app`` module if loaded (preserves test monkeypatches)."""
    app_mod = sys.modules.get("app")
    if app_mod is not None and hasattr(app_mod, name):
        return getattr(app_mod, name)
    return default


def commit_or_rollback():
    """Delegate to ``app.commit_or_rollback`` when patched, else ``core.shared.db_utils``."""
    fn = resolve_app_attr("commit_or_rollback", _default_commit_or_rollback)
    return fn()


def get_request_client_ip() -> str:
    """Xác định Client IP từ Flask request tuân thủ chính sách Proxy tin cậy (Phase 8.3)."""
    return get_trusted_client_ip(
        request.remote_addr,
        dict(request.headers),
        trust_proxy=settings.security.trust_proxy_headers,
        trusted_proxy_count=settings.security.trusted_proxy_count,
    )


def valid_birth_date(value, formats=("%d/%m/%Y",)):
    for fmt in formats:
        try:
            if datetime.strptime(value, fmt).strftime(fmt) == value:
                return True
        except ValueError:
            continue
    return False


def find_login_user(identifier):
    if "@" in identifier:
        exact = User.query.filter_by(email=identifier).first()
        if exact:
            return exact
        matches = User.query.filter(db.func.lower(User.email) == identifier.lower()).limit(2).all()
        return matches[0] if len(matches) == 1 else None
    phone = "".join(filter(str.isdigit, identifier))
    if not phone:
        return None
    return User.query.filter(
        (User.phone_number == identifier)
        | (User.phone_number == phone)
        | (User.email == f"{phone}@phone.medimind")
    ).first()


def start_authenticated_session(user):
    guest_token = session.get("guest_token") if not session.get("user_id") else None
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    if guest_token:
        session["guest_token"] = guest_token


def get_request_identity():
    user_id = session.get("user_id")
    if "guest_token" not in session:
        session["guest_token"] = f"gst_{uuid.uuid4().hex[:12]}"
    return user_id, session.get("guest_token")
