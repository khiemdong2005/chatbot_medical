# ==============================================================
# MEDIMIND CLINICAL AI - STATELESS JWT AUTHENTICATION ENGINE
# ==============================================================

import os
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Dict, Any, Optional, Tuple, List
from flask import request, jsonify, session

SECRET_KEY = os.getenv("SECRET_KEY", "medimind-clinical-session-secret-2026")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 2
REFRESH_TOKEN_EXPIRE_DAYS = 7


def generate_tokens(user_id: int, role: str, name: Optional[str] = None) -> Dict[str, str]:
    """
    Sinh cặp Access Token (ngắn hạn) và Refresh Token (dài hạn).
    """
    now = datetime.now(timezone.utc)

    # 1. Access Token: 2 giờ
    access_payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "role": role,
        "name": name or "",
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    }
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

    # 2. Refresh Token: 7 ngày
    refresh_payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    }
    refresh_token = jwt.encode(refresh_payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_HOURS * 3600
    }


def decode_token(token: str, expected_type: str = "access") -> Optional[Dict[str, Any]]:
    """
    Giải mã và kiểm tra tính toàn vẹn của JWT Token.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != expected_type:
            return None
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def get_token_from_request() -> Optional[str]:
    """
    Trích xuất JWT từ Header Authorization (Bearer <token>) hoặc Cookie dự phòng.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return request.cookies.get("access_token")


def jwt_required(optional: bool = False, roles: Optional[List[str]] = None):
    """
    Decorator bảo vệ Endpoint bằng JWT.
    Hỗ trợ cả fallback sang session nếu người dùng đăng nhập qua web truyền thống.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = get_token_from_request()
            payload = decode_token(token, expected_type="access") if token else None

            if payload:
                request.current_user_id = payload.get("user_id")
                request.current_user_role = payload.get("role")
            elif session.get("user_id"):
                # Fallback tương thích ngược với Flask Session
                request.current_user_id = session.get("user_id")
                request.current_user_role = session.get("user_role", "patient")
            else:
                if not optional:
                    return jsonify({
                        "success": False,
                        "error": "Yêu cầu xác thực JWT. Vui lòng gửi kèm 'Authorization: Bearer <token>' hoặc đăng nhập.",
                        "code": "AUTH_REQUIRED"
                    }), 401
                request.current_user_id = None
                request.current_user_role = None

            # Kiểm tra phân quyền vai trò (Role-Based Access Control)
            if roles and request.current_user_role not in roles:
                return jsonify({
                    "success": False,
                    "error": f"Từ chối truy cập. Vai trò của bạn ({request.current_user_role}) không có quyền thực hiện thao tác này.",
                    "code": "FORBIDDEN"
                }), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator
