"""
tests/test_settings.py
Kiểm thử bộ phận Quản lý Cấu hình Tập trung (Central Settings).
Đảm bảo thẩm định schema, bảo vệ thông tin nhạy cảm, giải quyết đường dẫn bền vững
và hành vi SECRET_KEY giữa môi trường Development vs Production.
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch

from core.settings import Settings, get_settings, reset_settings, _mask_secret


def test_settings_default_values():
    """Kiểm tra các giá trị mặc định của Settings khi không có env override (đã clear env)."""
    clean_env = {
        "FLASK_ENV": "development",
        "GEMINI_API_KEY": "test-mock-gemini-key-123456"
    }
    with patch.dict(os.environ, clean_env, clear=True):
        s = Settings(_env_file=None)
        assert s.server.env == "development"
        assert s.server.is_production is False

        # Models: Code default trước Phase 5.4 là gemini-flash-lite-latest
        assert s.gemini.chat_model == "gemini-flash-lite-latest"
        assert s.gemini.expansion_model == "gemini-flash-lite-latest"
        assert s.gemini.nutrition_model == "gemini-flash-lite-latest"
        assert s.gemini.ocr_model == "gemini-flash-lite-latest"
        assert s.gemini.interpretation_model == "gemini-flash-lite-latest"

        # Timeouts & Retries
        assert s.gemini.timeout_chat == 25.0
        assert s.gemini.timeout_expansion == 3.0
        assert s.gemini.timeout_ocr == 30.0
        assert s.retry.max_attempts == 3
        assert s.retry.base_delay_seconds == 0.5
        assert s.retry.max_delay_seconds == 4.0

        # Circuit Breaker
        assert s.circuit_breaker.enabled is True
        assert s.circuit_breaker.failure_threshold == 5
        assert s.circuit_breaker.cooldown_seconds == 30.0

        # RAG Settings: Bảo toàn quyết định Phase 3.1
        assert s.rag.query_expansion_enabled is False
        assert s.rag.query_expansion_timeout_seconds == 3.0
        assert s.rag.vector_search_enabled is False
        assert s.rag.rerank_enabled is False

        assert s.paths.project_root.exists()
        assert s.paths.database_url.startswith("sqlite:///")


def test_settings_explicit_env_override():
    """Kiểm tra việc ghi đè cấu hình qua biến môi trường hoạt động chính xác."""
    s = Settings(
        RAG_QUERY_EXPANSION_ENABLED="true",
        RAG_VECTOR_SEARCH_ENABLED="1",
        RAG_RERANK_ENABLED="true",
        QUERY_EXPANSION_TIMEOUT_SECONDS="5.5",
        AI_CIRCUIT_COOLDOWN_SECONDS="45.0",
        GEMINI_CHAT_MODEL="gemini-3.1-flash-lite",
        _env_file=None
    )
    assert s.rag.query_expansion_enabled is True
    assert s.rag.vector_search_enabled is True
    assert s.rag.rerank_enabled is True
    assert s.rag.query_expansion_timeout_seconds == 5.5
    assert s.gemini.timeout_expansion == 5.5
    assert s.circuit_breaker.cooldown_seconds == 45.0
    assert s.gemini.chat_model == "gemini-3.1-flash-lite"


def test_settings_numeric_and_bool_parsing():
    """Kiểm tra parse đúng kiểu dữ liệu số thực, số nguyên và boolean."""
    s = Settings(
        AI_RETRY_MAX_ATTEMPTS="5",
        AI_RETRY_BASE_DELAY_SECONDS="1.5",
        AI_CIRCUIT_BREAKER_ENABLED="false",
        SESSION_COOKIE_SECURE="1",
        PORT="9000",
        _env_file=None
    )
    assert s.retry.max_attempts == 5
    assert s.retry.base_delay_seconds == 1.5
    assert s.circuit_breaker.enabled is False
    assert s.security.session_cookie_secure is True
    assert s.server.port == 9000


def test_missing_optional_configs_do_not_fail():
    """Ứng dụng vẫn khởi tạo thành công khi thiếu các cấu hình tùy chọn."""
    s = Settings(
        GEMINI_API_KEY=None,
        GOOGLE_API_KEY=None,
        GOOGLE_CLIENT_ID=None,
        TWILIO_ACCOUNT_SID=None,
        SMTP_SERVER=None,
        _env_file=None
    )
    assert s.gemini.api_key is None
    assert s.security.google_client_id is None
    assert s.messaging.twilio_account_sid is None
    assert s.messaging.smtp_server is None


def test_secret_key_development_fallback():
    """Khi thiếu SECRET_KEY ở môi trường Development, trả về stable dev fallback và không raise."""
    s = Settings(
        FLASK_ENV="development",
        ENV="development",
        SECRET_KEY=None,
        _env_file=None
    )
    with patch.dict(os.environ, {"SECRET_KEY": "", "FLASK_ENV": "development", "ENV": "development"}):
        dev_key = s.get_effective_secret_key(testing=False)
        assert dev_key == "dev-insecure-secret-key-change-in-production-medimind-2026"


def test_secret_key_production_missing_raises_error():
    """Khi thiếu SECRET_KEY ở môi trường Production và không phải testing, bắt buộc raise RuntimeError."""
    s = Settings(
        FLASK_ENV="production",
        ENV="production",
        SECRET_KEY=None,
        _env_file=None
    )
    with patch.dict(os.environ, {"SECRET_KEY": "", "FLASK_ENV": "production", "ENV": "production"}):
        with pytest.raises(RuntimeError) as exc_info:
            s.get_effective_secret_key(testing=False)
        assert "Yêu cầu cấu hình SECRET_KEY an toàn" in str(exc_info.value)


def test_secret_key_explicit_takes_precedence():
    """Khi cấu hình explicit SECRET_KEY, giá trị đó được ưu tiên sử dụng."""
    s = Settings(
        SECRET_KEY="super-secret-custom-key-12345",
        _env_file=None
    )
    assert s.get_effective_secret_key(testing=False) == "super-secret-custom-key-12345"


def test_secret_masking_never_leaks_in_repr():
    """Đảm bảo các phương thức __repr__ không bao giờ in lộ raw secrets."""
    raw_api_key = "AIzaSyABC1234567890XYZSecretKey"
    raw_secret_key = "TopSecretFlaskSessionKey123456"

    s = Settings(
        GEMINI_API_KEY=raw_api_key,
        SECRET_KEY=raw_secret_key,
        _env_file=None
    )

    gemini_repr = repr(s.gemini)
    security_repr = repr(s.security)
    settings_repr = repr(s)

    assert raw_api_key not in gemini_repr
    assert raw_secret_key not in security_repr
    assert raw_api_key not in settings_repr
    assert raw_secret_key not in settings_repr

    # Kiểm tra hàm _mask_secret
    assert _mask_secret(None) == "<EMPTY>"
    assert _mask_secret("") == "<EMPTY>"
    assert _mask_secret("12345") == "***"
    assert _mask_secret("1234567890") == "123...7890"


def test_path_resolution_and_database_persistence():
    """Kiểm tra đường dẫn CSDL và thư mục dữ liệu đồng nhất với kiến trúc Docker volume."""
    s = Settings(_env_file=None)
    root = s.paths.project_root
    assert root.exists()
    assert (root / "core").exists()

    # Đường dẫn instance và database
    assert s.paths.data_dir == root / "instance"
    assert s.paths.database_path == root / "instance" / "medimind.db"
    assert s.paths.database_url.startswith("sqlite:///")
    assert "medimind.db" in s.paths.database_url


def test_singleton_reset():
    """Kiểm tra hàm get_settings và reset_settings cho phép làm mới singleton khi test."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2

    s3 = reset_settings()
    assert s3 is not None
