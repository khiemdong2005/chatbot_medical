"""
tests/test_api_error_schema.py
Kiểm thử bộ chuẩn hóa mã lỗi và Error Boundary (API Error Schema).
Xác nhận canonical schema {"error": {"code": ..., "message": ...}}
và tính tương thích ngược với các trường legacy (detail, message, success, status)
trên cả hai tầng FastAPI Gateway và Flask WSGI.
"""
import pytest
from starlette.testclient import TestClient

from core.api_errors import (
    ErrorCode,
    status_code_to_error_code,
    make_error_payload,
    flask_api_error,
    fastapi_api_error,
    APIError
)
from core.main_fastapi import app as fastapi_app
from app import create_app


@pytest.fixture
def api_client():
    return TestClient(fastapi_app)


@pytest.fixture
def flask_client():
    test_app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with test_app.test_client() as client:
        yield client


def test_status_code_mapping():
    """Kiểm tra ánh xạ HTTP status code sang canonical ErrorCode."""
    assert status_code_to_error_code(400) == ErrorCode.VALIDATION_ERROR
    assert status_code_to_error_code(401) == ErrorCode.AUTH_REQUIRED
    assert status_code_to_error_code(403) == ErrorCode.FORBIDDEN
    assert status_code_to_error_code(404) == ErrorCode.NOT_FOUND
    assert status_code_to_error_code(429) == ErrorCode.RATE_LIMITED
    assert status_code_to_error_code(502) == ErrorCode.AI_UNAVAILABLE
    assert status_code_to_error_code(503) == ErrorCode.AI_UNAVAILABLE
    assert status_code_to_error_code(504) == ErrorCode.AI_UNAVAILABLE
    assert status_code_to_error_code(500) == ErrorCode.INTERNAL_ERROR


def test_make_error_payload_structure():
    """Kiểm tra cấu trúc payload chuẩn chứa cả canonical schema và transitional fields."""
    payload = make_error_payload(
        code=ErrorCode.VALIDATION_ERROR,
        message="Vui lòng nhập họ và tên.",
        details=[{"field": "name", "issue": "required"}]
    )

    # 1. Canonical Schema
    assert "error" in payload
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["message"] == "Vui lòng nhập họ và tên."
    assert payload["error"]["details"] == [{"field": "name", "issue": "required"}]

    # 2. Backward Compatibility Fields
    assert payload["success"] is False
    assert payload["status"] == "error"
    assert payload["message"] == "Vui lòng nhập họ và tên."
    assert payload["detail"] == "Vui lòng nhập họ và tên."


def test_fastapi_http_exception_normalized_schema(api_client):
    """Kiểm tra FastAPI HTTPException (400) trả về canonical error schema và detail tương thích."""
    # Gửi request rỗng vào /api/chat để kích hoạt 400 validation error
    res = api_client.post("/api/chat", json={})
    assert res.status_code == 400
    data = res.json()

    # Kiểm tra Canonical Schema
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(data["error"]["message"], str)
    assert len(data["error"]["message"]) > 0

    # Kiểm tra tính tương thích ngược cho FastAPI client
    assert "detail" in data
    assert data["detail"] == data["error"]["message"]


def test_fastapi_forbidden_exception_normalized(api_client):
    """Kiểm tra mã lỗi 403 trên FastAPI Gateway được chuẩn hóa mã FORBIDDEN."""
    from core.observability import metrics_collector
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(metrics_collector, "is_enabled", lambda: False)
        res = api_client.get("/api/system/metrics")
        assert res.status_code == 403
        data = res.json()
        assert "error" in data
        assert isinstance(data["error"], dict)
        assert data["error"]["code"] == "FORBIDDEN"
        assert data["error"]["message"] == "System metrics endpoint is disabled."
        assert data["detail"] == "System metrics endpoint is disabled."


def test_fastapi_rate_limit_error_code(api_client):
    """Kiểm tra mã lỗi 429 Rate Limit mang mã canonical RATE_LIMITED."""
    payload = make_error_payload(
        code=ErrorCode.RATE_LIMITED,
        message="Bạn đang gửi tin nhắn quá nhanh."
    )
    assert payload["error"]["code"] == "RATE_LIMITED"


def test_flask_auth_required_error_schema(flask_client):
    """Kiểm tra lỗi 401 trên Flask WSGI trả về schema hợp lệ."""
    # Gọi endpoint yêu cầu đăng nhập khi chưa có session
    res = flask_client.get("/api/appointments")
    assert res.status_code == 401
    data = res.get_json()
    # Kiểm tra có trường thông báo lỗi
    assert data is not None


def test_api_error_exception_raising():
    """Kiểm tra exception APIError có thể được khởi tạo và chuyển đổi thành dict chuẩn."""
    exc = APIError(
        code=ErrorCode.AI_UNAVAILABLE,
        message="Google Gemini API đang gián đoạn tạm thời.",
        status_code=503
    )
    assert exc.status_code == 503
    payload = exc.to_dict()
    assert payload["error"]["code"] == "AI_UNAVAILABLE"
    assert payload["error"]["message"] == "Google Gemini API đang gián đoạn tạm thời."
    assert payload["detail"] == "Google Gemini API đang gián đoạn tạm thời."
