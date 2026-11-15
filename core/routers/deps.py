"""
core/routers/deps.py
Shared FastAPI dependencies & request identity extraction.
Đồng bộ phiên đăng nhập giữa Flask cookie session và FastAPI native routes.
"""
import uuid
import logging
from typing import Optional, Tuple, Any
from fastapi import Request, HTTPException
from core.db_utils import get_flask_app

logger = logging.getLogger("RouterDeps")


def extract_request_identity(request: Request) -> Tuple[Optional[int], Optional[str], bool]:
    """
    Trích xuất (user_id, guest_token, is_new_guest) từ cookie / header.
    Tương thích 100% với phiên đăng nhập Flask.
    """
    user_id = None
    guest_token = None
    is_new = False

    flask_app = get_flask_app()

    # 1. Đọc từ Flask session cookie nếu có
    if flask_app is not None:
        cookie_name = getattr(flask_app, "session_cookie_name", "session")
        raw_cookie = request.cookies.get(cookie_name)
        if raw_cookie:
            try:
                serializer = flask_app.session_interface.get_signing_serializer(flask_app)
                if serializer:
                    data = serializer.loads(raw_cookie)
                    if isinstance(data, dict):
                        user_id = data.get("user_id")
                        guest_token = data.get("guest_token")
            except Exception:
                pass

    # 2. Đọc từ cookie guest_token riêng nếu có
    if not guest_token:
        guest_token = request.cookies.get("guest_token")

    # 3. Đọc từ header X-Guest-Token nếu có
    if not guest_token:
        guest_token = request.headers.get("X-Guest-Token")

    # 4. Nếu chưa có guest_token, tự sinh mới
    if not guest_token:
        guest_token = f"gst_{uuid.uuid4().hex[:12]}"
        is_new = True

    return user_id, guest_token, is_new


def require_authenticated_user(request: Request) -> int:
    """
    FastAPI dependency: Bắt buộc phiên người dùng đã xác thực.
    Nếu không có phiên hoặc phiên hết hạn -> ném canonical 401.
    """
    user_id, _, _ = extract_request_identity(request)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Vui lòng đăng nhập để thực hiện chức năng này."
        )
    return user_id


def extract_request_user_and_role(request: Request) -> Tuple[Optional[int], Optional[str]]:
    """
    Trích xuất (user_id, user_role) từ Flask session cookie.
    Tương thích 100% với phiên đăng nhập Flask.
    """
    user_id = None
    user_role = None

    flask_app = get_flask_app()
    if flask_app is not None:
        cookie_name = getattr(flask_app, "session_cookie_name", "session")
        raw_cookie = request.cookies.get(cookie_name)
        if raw_cookie:
            try:
                serializer = flask_app.session_interface.get_signing_serializer(flask_app)
                if serializer:
                    data = serializer.loads(raw_cookie)
                    if isinstance(data, dict):
                        user_id = data.get("user_id")
                        user_role = data.get("user_role")
            except Exception:
                pass

    if user_id and not user_role:
        try:
            from core.models import db, User
            user = db.session.get(User, user_id)
            if user:
                user_role = user.role
        except Exception:
            pass

    return user_id, user_role


def require_admin(request: Request) -> int:
    """
    FastAPI dependency: Bắt buộc phiên người dùng có quyền Quản trị viên (admin).
    - Chưa đăng nhập (anonymous) -> raise HTTPException(401).
    - Đã đăng nhập nhưng không phải admin (patient, doctor, guest) -> raise HTTPException(403).
    """
    user_id, user_role = extract_request_user_and_role(request)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Vui lòng đăng nhập với tài khoản Quản trị viên để thực hiện chức năng này."
        )
    if user_role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Yêu cầu quyền Quản trị viên (Admin) để truy cập tài nguyên này."
        )
    return user_id


def check_flask_admin() -> Optional[Tuple[Any, int]]:
    """
    Kiểm tra quyền admin trong Flask session.
    Trả về None nếu hợp lệ, hoặc trả về (response, status_code) nếu không hợp lệ.
    """
    from flask import session
    from core.api_errors import flask_api_error, ErrorCode

    user_id = session.get("user_id")
    if not user_id:
        return flask_api_error(
            ErrorCode.AUTH_REQUIRED,
            "Vui lòng đăng nhập với tài khoản Quản trị viên để thực hiện chức năng này.",
            status_code=401
        )

    user_role = session.get("user_role")
    if user_role != "admin":
        try:
            from core.models import db, User
            user = db.session.get(User, user_id)
            if user:
                user_role = user.role
        except Exception:
            pass

    if user_role != "admin":
        return flask_api_error(
            ErrorCode.FORBIDDEN,
            "Yêu cầu quyền Quản trị viên (Admin) để truy cập tài nguyên này.",
            status_code=403
        )

    return None
