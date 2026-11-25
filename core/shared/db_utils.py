"""
================================================================================
🩺 MEDIMIND CLINICAL AI - DATABASE TRANSACTION UTILITIES
================================================================================
Cung cấp các tiện ích quản lý giao dịch CSDL an toàn:
- commit_or_rollback: Đảm bảo luôn rollback khi commit gặp sự cố, chống dirty session.
- transactional_session: Context manager tự động quản lý commit/rollback theo khối lệnh.
================================================================================
"""

import logging
from contextlib import contextmanager
from typing import Optional, Any
from core.shared.models import db

logger = logging.getLogger("DBUtils")

_shared_flask_app = None


def set_flask_app(app: Any) -> None:
    """Đăng ký Flask application instance cho DB context dùng chung."""
    global _shared_flask_app
    _shared_flask_app = app


def get_flask_app() -> Optional[Any]:
    """Lấy Flask application instance hiện tại một cách an toàn."""
    global _shared_flask_app
    if _shared_flask_app is not None:
        return _shared_flask_app
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            _shared_flask_app = current_app._get_current_object()
            return _shared_flask_app
    except Exception:
        pass
    try:
        from app import app as flask_app
        _shared_flask_app = flask_app
        return _shared_flask_app
    except Exception:
        return None


@contextmanager
def app_db_context():
    """Context manager đảm bảo luôn có application context hợp lệ cho SQLAlchemy session."""
    from flask import has_app_context
    if has_app_context():
        yield db.session
    else:
        app_inst = get_flask_app()
        if app_inst is not None:
            with app_inst.app_context():
                yield db.session
        else:
            raise RuntimeError("Không tìm thấy Flask application instance để truy cập CSDL.")


def commit_or_rollback(session=None) -> None:
    """
    Thực hiện commit giao dịch CSDL một cách an toàn.
    Nếu commit phát sinh ngoại lệ, tự động thực hiện rollback ngay lập tức
    để ngăn chặn việc session bị bẩn (dirty/poisoned) gây lỗi cho các request tiếp theo.
    """
    sess = session or db.session
    try:
        sess.commit()
    except Exception as e:
        try:
            sess.rollback()
        except Exception:
            pass
        logger.error("Giao dịch CSDL thất bại, đã thực hiện rollback an toàn (%s).", type(e).__name__)
        raise


@contextmanager
def transactional_session(session=None):
    """
    Context manager bọc một khối giao dịch:
    - Đảm bảo app_context hợp lệ.
    - yield session để thực thi các lệnh ORM (add, delete, query).
    - Tự động gọi commit khi hoàn tất khối lệnh.
    - Tự động gọi rollback khi có bất kỳ ngoại lệ nào xảy ra trước khi ném lại lỗi.
    """
    with app_db_context() as default_sess:
        sess = session or default_sess
        try:
            yield sess
            sess.commit()
        except Exception as e:
            try:
                sess.rollback()
            except Exception:
                pass
            logger.error("Ngoại lệ trong transactional_session, đã thực hiện rollback (%s).", type(e).__name__)
            raise


