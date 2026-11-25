"""
================================================================================
🩺 MEDIMIND PHASE 5.3 — UNIFIED AI PROVIDER UNIT TEST SUITE
================================================================================
Kiểm thử toàn diện cho core/llm_provider.py:
1. Lazy Client Initialization (không gọi mạng khi import).
2. Tái sử dụng Client dùng chung (Shared Client Reuse & Thread-Safe).
3. Phân giải cấu hình theo Workload Profile (Timeout, Retry, Circuit Breaker).
4. Kịch bản thành công (generate_text, generate_json, generate_multimodal).
5. Kịch bản lỗi tạm thời (Transient 503/429) -> Tự động thử lại (Retry) -> Thành công.
6. Kịch bản lỗi vĩnh viễn (Non-retryable 401/400) -> Fail-fast, không retry lặp vô hạn.
7. Xử lý thiếu API Key an toàn -> Không crash ứng dụng, trả về AUTH_ERROR.
8. Tính cách ly Circuit Breaker (Breaker Isolation: Nutrition trip không làm sập Chat).
9. Bảo vệ quyền riêng tư (Zero-PHI trong Exception và Logs).
10. Kiểm thử tải đồng thời đa luồng (Concurrent Calls).
================================================================================
"""

import os
import time
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

from core.llm_provider import LLMProvider, LLMProviderError, llm_provider
from core.retry_policy import ErrorClassification, RetryPolicy
from core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, get_circuit_breaker, reset_all_circuit_breakers
from core.observability import metrics_collector


@pytest.fixture(autouse=True)
def reset_state():
    """Reset trạng thái metrics và circuit breakers trước mỗi test."""
    reset_all_circuit_breakers()
    metrics_collector.reset()
    yield
    reset_all_circuit_breakers()


# ==============================================================================
# 1. KIỂM THỬ KHỞI TẠO LƯỜI (LAZY INITIALIZATION) & LIFECYCLE
# ==============================================================================

class TestLLMProviderLifecycle:
    """Kiểm tra vòng đời client và tính lười (Lazy Initialization)."""

    def test_import_makes_no_network_call(self):
        """Khởi tạo LLMProvider không thực hiện bất kỳ lệnh gọi mạng nào."""
        provider = LLMProvider()
        assert len(provider._clients) == 0

    def test_shared_client_reuse(self):
        """Các lần gọi cùng API key và timeout tái sử dụng đúng 1 client duy nhất."""
        provider = LLMProvider()
        with patch("google.genai.Client") as mock_client_cls:
            mock_inst = MagicMock()
            mock_client_cls.return_value = mock_inst

            c1 = provider.get_client("AIzaSyTestKey1234567890", timeout_seconds=15.0)
            c2 = provider.get_client("AIzaSyTestKey1234567890", timeout_seconds=15.0)

            assert c1 is c2
            assert mock_client_cls.call_count == 1

    def test_missing_or_invalid_api_key_raises_auth_error(self):
        """Khi không có API key hợp lệ, provider ném ra LLMProviderError với AUTH_ERROR."""
        provider = LLMProvider()
        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate_text(
                prompt="Hello",
                api_key="your_google_gemini_api_key_here",  # Placeholder key
                operation="chat_generation"
            )
        err = exc_info.value
        assert err.classification == ErrorClassification.AUTH_ERROR
        assert err.retryable is False
        assert "chưa được cấu hình" in err.message

    def test_resolve_api_key_prioritizes_nutrition_profile(self, monkeypatch):
        """Profile nutrition đọc đúng GEMINI_NUTRITION_API_KEY khi có cấu hình."""
        monkeypatch.setenv("AI_PROVIDER", "")
        monkeypatch.setenv("GROQ_API_KEY", "")
        monkeypatch.setenv("GEMINI_NUTRITION_API_KEY", "nutri_key_123456789")
        monkeypatch.setenv("GEMINI_API_KEY", "general_key_123456789")

        provider = LLMProvider()
        assert provider.resolve_api_key(profile="nutrition") == "nutri_key_123456789"
        assert provider.resolve_api_key(profile="chat") == "general_key_123456789"


# ==============================================================================
# 2. KIỂM THỬ THỰC THI THÀNH CÔNG & THẤT BẠI CÓ KIỂM SOÁT
# ==============================================================================

class TestLLMProviderExecution:
    """Kiểm tra thực thi các phương thức generate_text, generate_json, generate_multimodal."""

    def test_generate_text_success(self):
        """generate_text trả về nội dung chuỗi khi mô hình thành công."""
        provider = LLMProvider()
        mock_response = MagicMock()
        mock_response.text = "Đây là lời khuyên y tế chuẩn mực."

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = provider.generate_text(
                prompt="Tư vấn đau đầu",
                api_key="AIzaSyValidTestKey123456",
                operation="chat_generation"
            )

            assert result == "Đây là lời khuyên y tế chuẩn mực."
            metrics = metrics_collector.get_summary()["counters"]
            assert metrics["llm_request_total"] >= 1
            assert metrics["llm_success_total"] >= 1

    def test_generate_json_success(self):
        """generate_json bóc tách JSON chuẩn ngay cả khi phản hồi bọc trong code block."""
        provider = LLMProvider()
        mock_response = MagicMock()
        mock_response.text = '```json\n{"risk_level": "mild", "score": 25}\n```'

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = provider.generate_json(
                contents="Đánh giá mức độ",
                api_key="AIzaSyValidTestKey123456",
                operation="chat_generation"
            )

            assert isinstance(result, dict)
            assert result["risk_level"] == "mild"
            assert result["score"] == 25

    def test_retry_on_transient_503_recovers_successfully(self):
        """Gặp lỗi 503 ở lần 1, retry lần 2 thành công -> trả về kết quả."""
        provider = LLMProvider()
        mock_response = MagicMock()
        mock_response.text = "Khôi phục thành công sau retry."

        error_503 = Exception("503 Server Unavailable")
        setattr(error_503, "status_code", 503)

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.models.generate_content.side_effect = [error_503, mock_response]
            mock_get_client.return_value = mock_client

            with patch("time.sleep"):  # Không làm chậm thời gian test
                res = provider.generate_text(
                    prompt="Test query",
                    api_key="AIzaSyValidTestKey123456",
                    operation="query_expansion"
                )

            assert res == "Khôi phục thành công sau retry."
            metrics = metrics_collector.get_summary()["counters"]
            assert metrics["llm_retry_total"] >= 1
            assert metrics["server_error_5xx_total"] >= 1
            assert metrics["llm_success_total"] >= 1

    def test_non_retryable_400_fails_fast_without_retrying(self):
        """Lỗi 400 Bad Request không được retry lặp lại mà phải fail-fast ngay lập tức."""
        provider = LLMProvider()
        error_400 = Exception("400 Bad Request: Invalid parameter")
        setattr(error_400, "status_code", 400)

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.models.generate_content.side_effect = error_400
            mock_get_client.return_value = mock_client

            with pytest.raises(LLMProviderError) as exc_info:
                provider.generate_text(
                    prompt="Bad payload",
                    api_key="AIzaSyValidTestKey123456",
                    operation="chat_generation"
                )

            err = exc_info.value
            assert err.classification == ErrorClassification.BAD_REQUEST
            assert mock_client.models.generate_content.call_count == 1  # Chính xác 1 lần, không retry


# ==============================================================================
# 3. KIỂM THỬ TÍNH CÁCH LY CIRCUIT BREAKER (BREAKER ISOLATION)
# ==============================================================================

class TestCircuitBreakerIsolation:
    """Xác nhận sự cố ở Nutrition AI không làm sập Chat Lâm Sàng."""

    def test_nutrition_failures_do_not_trip_chat_circuit_breaker(self):
        """Nutrition breaker bị OPEN do 5 lần lỗi 503 liên tiếp, Chat breaker vẫn CLOSED 100%."""
        provider = LLMProvider()

        nutrition_breaker = get_circuit_breaker("nutrition")
        chat_breaker = get_circuit_breaker("chat")

        assert nutrition_breaker.state == "CLOSED"
        assert chat_breaker.state == "CLOSED"

        error_503 = Exception("503 Service Unavailable")
        setattr(error_503, "status_code", 503)

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.models.generate_content.side_effect = error_503
            mock_get_client.return_value = mock_client

            with patch("time.sleep"):
                # Gây lỗi liên tục trên nutrition workload cho tới khi ngắt mạch
                for _ in range(nutrition_breaker.failure_threshold + 1):
                    try:
                        provider.generate_text(
                            prompt="Thực đơn gút",
                            api_key="AIzaSyValidTestKey123456",
                            operation="nutrition_ai"
                        )
                    except LLMProviderError:
                        pass

        # Nutrition Circuit Breaker đã bị OPEN
        assert nutrition_breaker.state == "OPEN"

        # Chat Circuit Breaker vẫn CLOSED hoàn toàn
        assert chat_breaker.state == "CLOSED"
        assert chat_breaker.can_execute() is True


# ==============================================================================
# 4. KIỂM THỬ THREAD SAFETY VÀ ĐỒNG THỜI (CONCURRENCY)
# ==============================================================================

class TestLLMProviderConcurrency:
    """Kiểm tra thực thi đồng thời đa luồng qua Provider."""

    def test_multithreaded_provider_invocations(self):
        """Nhiều luồng gọi đồng thời không gây race condition khi khởi tạo client hay cập nhật metrics."""
        provider = LLMProvider()
        mock_response = MagicMock()
        mock_response.text = "OK"

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_response
            mock_get_client.return_value = mock_client

            errors = []

            def worker(w_id):
                try:
                    for _ in range(20):
                        res = provider.generate_text(
                            prompt=f"Worker {w_id}",
                            api_key="AIzaSyValidTestKey123456",
                            operation="chat_generation"
                        )
                        assert res == "OK"
                except Exception as e:
                    errors.append(e)

            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(worker, i) for i in range(8)]
                for f in as_completed(futures):
                    f.result()

            assert len(errors) == 0


# ==============================================================================
# 5. KIỂM THỬ MULTI-KEY GROQ FAILOVER & KHÔI PHỤC HTTP 400 (BẢO TOÀN OCR)
# ==============================================================================

class TestGroqMultiKeyAnd400Recovery:
    """Kiểm tra tách key theo tác vụ, xoay vòng 429 và xử lý lỗi 400 không làm lệch OCR."""

    def test_groq_workload_key_routing_and_cross_failover_pool(self, monkeypatch):
        """Chat ưu tiên Key 1 (backup Key 2); OCR/Nutrition ưu tiên Key 2 (backup Key 1)."""
        monkeypatch.setenv("AI_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_primary_chat_key_111111")
        monkeypatch.setenv("GROQ_API_KEY_2", "gsk_backup_heavy_key_222222")
        monkeypatch.setenv("GROQ_OCR_API_KEY", "gsk_backup_heavy_key_222222")
        monkeypatch.setenv("GROQ_NUTRITION_API_KEY", "gsk_backup_heavy_key_222222")

        provider = LLMProvider()
        assert provider._collect_groq_key_pool(profile="chat_generation") == [
            "gsk_primary_chat_key_111111",
            "gsk_backup_heavy_key_222222",
        ]
        assert provider._collect_groq_key_pool(profile="prescription_ocr") == [
            "gsk_backup_heavy_key_222222",
            "gsk_primary_chat_key_111111",
        ]
        assert provider._collect_groq_key_pool(profile="nutrition_ai") == [
            "gsk_backup_heavy_key_222222",
            "gsk_primary_chat_key_111111",
        ]

    def test_groq_429_fails_over_to_backup_key_preserving_same_model(self):
        """Khi Key 1 gặp 429, xoay sang Key 2 trên CÙNG model trước khi đổi model."""
        from core.ai.llm_provider import _GroqHTTPError, _GroqModels, _GROQ_RATE_LIMIT_COOLDOWNS
        _GROQ_RATE_LIMIT_COOLDOWNS.clear()

        models = _GroqModels(
            api_key="gsk_key_one_1234567890",
            fallback_api_keys=["gsk_key_two_1234567890"],
        )
        attempts = []

        def fake_post(payload, *, api_key=None):
            used_key = api_key or models._api_key
            attempts.append((used_key, payload["model"]))
            if used_key == "gsk_key_one_1234567890":
                raise _GroqHTTPError(429, "Groq HTTP 429")
            return {"choices": [{"message": {"content": '{"medications": [{"name": "Paracetamol"}]}'}}]}

        with patch.object(models, "_post_completion", side_effect=fake_post):
            resp = models.generate_content(
                model="qwen/qwen3.8-27b",
                contents=[
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}},
                    "Đọc đơn thuốc",
                ],
                config={"response_mime_type": "application/json"},
            )

        assert attempts == [
            ("gsk_key_one_1234567890", "qwen/qwen3.8-27b"),
            ("gsk_key_two_1234567890", "qwen/qwen3.8-27b"),
        ]
        assert resp.model == "qwen/qwen3.8-27b"
        assert "Paracetamol" in resp.text

    def test_groq_multimodal_never_downgrades_to_text_only_fallback_on_429(self):
        """Payload OCR có ảnh tuyệt đối không gửi sang gpt-oss text-only (tránh 400 và giữ chuẩn OCR)."""
        from core.ai.llm_provider import _GroqHTTPError, _GroqModels, _GROQ_RATE_LIMIT_COOLDOWNS
        _GROQ_RATE_LIMIT_COOLDOWNS.clear()

        models = _GroqModels(
            api_key="gsk_key_one_1234567890",
            fallback_api_keys=["gsk_key_two_1234567890"],
        )
        seen_models = []

        def fake_post(payload, *, api_key=None):
            seen_models.append(payload["model"])
            raise _GroqHTTPError(429, "Groq HTTP 429")

        with patch.object(models, "_post_completion", side_effect=fake_post):
            with pytest.raises(_GroqHTTPError) as exc_info:
                models.generate_content(
                    model="qwen/qwen3.8-27b",
                    contents=[
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}},
                        "Đọc đơn thuốc",
                    ],
                )

        assert exc_info.value.status_code == 429
        assert seen_models == ["qwen/qwen3.8-27b", "qwen/qwen3.8-27b"]

    def test_groq_400_compat_strips_response_format_and_max_tokens(self):
        """Khi gặp HTTP 400 do response_format/max_tokens, tự gỡ lần lượt để khôi phục ngay."""
        from core.ai.llm_provider import _GroqHTTPError, _GroqModels, _GROQ_RATE_LIMIT_COOLDOWNS
        _GROQ_RATE_LIMIT_COOLDOWNS.clear()

        models = _GroqModels(api_key="gsk_key_one_1234567890")
        seen_payloads = []

        def fake_post(payload, *, api_key=None):
            seen_payloads.append(dict(payload))
            if "response_format" in payload or "max_tokens" in payload:
                raise _GroqHTTPError(400, "Groq HTTP 400 (json_validate_failed)", error_code="json_validate_failed")
            return {"choices": [{"message": {"content": '{"ok": true}'}}]}

        with patch.object(models, "_post_completion", side_effect=fake_post):
            resp = models.generate_content(
                model="qwen/qwen3.8-27b",
                contents="Tra cứu sức khỏe",
                config={"response_mime_type": "application/json", "max_output_tokens": 2600, "temperature": 0.2},
            )

        assert len(seen_payloads) == 3
        assert "response_format" in seen_payloads[0] and "max_tokens" in seen_payloads[0]
        assert "response_format" not in seen_payloads[1] and "max_tokens" in seen_payloads[1]
        assert "response_format" not in seen_payloads[2] and "max_tokens" not in seen_payloads[2]
        assert resp.text == '{"ok": true}'
