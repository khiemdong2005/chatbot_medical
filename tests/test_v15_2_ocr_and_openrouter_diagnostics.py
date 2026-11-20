"""
PROMAX V15.2 Regression Tests:
- Optional EasyOCR missing info logging & WinRT local fallback truthfulness
- Honest failure when both local OCR engine and AI Vision fail
- Mandatory PII masking guard blocking external AI upload when unmasked
- OpenRouter HTTP error classification (401/402/404/408/422/429/500/502/503/HTTP-200 error body)
- Sanitized status_code logging (Zero-Secret / Zero-PHI) & honest degraded chat payload
"""

import io
import json
import logging
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import core.ocr_extractor as ocr_ext
import core.ocr_parallel_service as ocr_parallel
import core.pipeline_orchestrator as pipe
from core.ai_types import ErrorClassification
from core.chat_service import process_clinical_chat
from core.circuit_breaker import reset_all_circuit_breakers
from core.gemini_service import GeminiMedicalService
from core.llm_provider import _OpenRouterHTTPError, _OpenRouterModels
from core.retry_policy import RetryPolicy, classify_exception, redact_provider_error


@pytest.fixture(autouse=True)
def _reset_breakers():
    reset_all_circuit_breakers()
    yield
    reset_all_circuit_breakers()


def _make_urllib_http_error(code: int, body: dict | str) -> urllib.error.HTTPError:
    raw = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body.encode("utf-8")
    return urllib.error.HTTPError(
        url="https://openrouter.ai/api/v1/chat/completions",
        code=code,
        msg="Error",
        hdrs={},
        fp=io.BytesIO(raw),
    )


def test_missing_easyocr_logs_once_without_error_spam(monkeypatch, capsys):
    monkeypatch.setattr(ocr_ext, "_OCR_READER", None)
    monkeypatch.setattr(ocr_ext, "_EASYOCR_UNAVAILABLE", False)

    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "easyocr":
            raise ModuleNotFoundError("No module named 'easyocr'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert ocr_ext.get_ocr_reader() is None
    assert ocr_ext.get_ocr_reader() is None
    captured = capsys.readouterr().out
    assert "[OCR ENGINE ERROR]" not in captured
    assert captured.count("EasyOCR") == 1


def test_extract_ocr_parallel_reports_failure_when_winrt_fails(tmp_path, monkeypatch):
    img = tmp_path / "rx.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    monkeypatch.setattr(ocr_parallel, "get_ocr_reader", lambda: None)
    monkeypatch.setattr(ocr_parallel.os, "name", "nt", raising=False)

    fake_proc = SimpleNamespace(returncode=2, stdout="", stderr="WINRT_ENGINE_UNAVAILABLE\n")
    monkeypatch.setattr(ocr_parallel.subprocess, "run", lambda *a, **kw: fake_proc)

    res = ocr_parallel.extract_ocr_parallel(str(img), doc_type="prescription")
    assert res["success"] is False
    assert res["engine"] == "winrt"
    assert "WinRT" in res["error"]


def test_pipeline_fails_honestly_when_both_ocr_engine_and_vision_fail(tmp_path, monkeypatch):
    img = tmp_path / "rx.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    monkeypatch.setattr(pipe, "check_image_quality", lambda *a, **kw: {"passed": True})
    monkeypatch.setattr(pipe, "preprocess_lightweight", lambda p, **kw: {"processed_path": p})
    monkeypatch.setattr(
        pipe,
        "extract_ocr_parallel",
        lambda *a, **kw: {"success": False, "engine": "none", "error": "No OCR engine", "lines": [], "rows": [], "raw_text": ""},
    )
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: None)

    res = pipe.process_medical_document_pipeline(str(img), "rx.png", doc_type_hint="prescription")
    assert res["status"] == "failed"
    assert res["error_code"] == "OCR_OR_AI_ANALYSIS_FAILED"
    assert res["ocr_engine"] == "none"


def test_pipeline_blocks_external_ai_when_mandatory_pii_masking_fails(tmp_path, monkeypatch):
    img = tmp_path / "rx_pii.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    vision_called = {"count": 0}
    monkeypatch.setattr(pipe, "check_image_quality", lambda *a, **kw: {"passed": True})
    monkeypatch.setattr(pipe, "preprocess_lightweight", lambda p, **kw: {"processed_path": p})
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda *a, **kw: {"success": True, "engine": "winrt", "lines": [], "rows": [], "raw_text": ""})
    monkeypatch.setattr(pipe, "mask_pii_on_image", lambda p, boxes: p)
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: vision_called.__setitem__("count", 1))

    res = pipe.process_medical_document_pipeline(str(img), "rx_pii.png", mask_pii=True)
    assert res["status"] == "blocked"
    assert res["error_code"] == "PII_MASKING_UNAVAILABLE"
    assert res["pii_protection"]["blocked_external_ai"] is True
    assert vision_called["count"] == 0


def test_openrouter_http_status_classification_and_secret_redaction():
    assert classify_exception(_OpenRouterHTTPError(401, "Unauthorized")) == ErrorClassification.AUTH_ERROR
    assert classify_exception(_OpenRouterHTTPError(402, "Insufficient credits")) == ErrorClassification.AUTH_ERROR
    assert classify_exception(_OpenRouterHTTPError(403, "Forbidden")) == ErrorClassification.AUTH_ERROR
    assert classify_exception(_OpenRouterHTTPError(404, "Model is currently unavailable")) == ErrorClassification.BAD_REQUEST
    assert classify_exception(_OpenRouterHTTPError(408, "Request timeout")) == ErrorClassification.TIMEOUT
    assert classify_exception(_OpenRouterHTTPError(422, "Invalid response_format")) == ErrorClassification.BAD_REQUEST
    assert classify_exception(_OpenRouterHTTPError(429, "Rate limit exceeded")) == ErrorClassification.RATE_LIMIT
    assert classify_exception(_OpenRouterHTTPError(502, "Bad Gateway")) == ErrorClassification.SERVER_ERROR
    assert classify_exception(_OpenRouterHTTPError(503, "Provider unavailable")) == ErrorClassification.SERVER_ERROR

    redacted = redact_provider_error(_OpenRouterHTTPError(401, "Invalid key sk-or-v1-abc123SECRET999"))
    assert "sk-or-v1-abc123SECRET999" not in redacted
    assert "status=401" in redacted


def test_openrouter_models_surfaces_http_200_error_and_strips_422_response_format():
    class _FakeResp:
        def __init__(self, raw_bytes: bytes):
            self._raw = raw_bytes

        def read(self) -> bytes:
            return self._raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    models = _OpenRouterModels(api_key="sk-or-v1-test-key-123456")

    err_200 = json.dumps({"error": {"code": 502, "message": "Upstream model overloaded"}}).encode("utf-8")
    with patch("core.llm_provider.urllib.request.urlopen", return_value=_FakeResp(err_200)):
        with pytest.raises(_OpenRouterHTTPError) as exc:
            models.generate_content("meta-llama/llama-3.1-8b-instruct:free", "hello")
    assert exc.value.status_code == 502

    calls = []
    ok_body = json.dumps({"choices": [{"message": {"content": '{"answer":"ok"}'}}]}).encode("utf-8")

    def fake_urlopen(req, timeout=25.0):
        payload = json.loads(req.data.decode("utf-8"))
        calls.append(payload)
        if "response_format" in payload:
            raise _make_urllib_http_error(422, {"error": {"message": "response_format unsupported"}})
        return _FakeResp(ok_body)

    with patch("core.llm_provider.urllib.request.urlopen", side_effect=fake_urlopen):
        resp = models.generate_content(
            "meta-llama/llama-3.1-8b-instruct:free",
            "hello",
            config={"response_mime_type": "application/json"},
        )
    assert len(calls) == 2
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]
    assert resp.text == '{"answer":"ok"}'


@pytest.mark.parametrize(
    "http_code,expected_cls,expected_attempts",
    [
        (401, ErrorClassification.AUTH_ERROR, 1),
        (402, ErrorClassification.AUTH_ERROR, 1),
        (404, ErrorClassification.BAD_REQUEST, 1),
        (429, ErrorClassification.RATE_LIMIT, 2),
        (502, ErrorClassification.SERVER_ERROR, 2),
    ],
)
def test_chat_openrouter_error_branches_and_sanitized_logs(http_code, expected_cls, expected_attempts, caplog):
    caplog.set_level(logging.WARNING)
    svc = GeminiMedicalService(api_key="sk-or-v1-test-key-secret-value", model="meta-llama/llama-3.1-8b-instruct:free")
    svc.retry_policy = RetryPolicy(max_attempts=2, base_delay=0.0, max_delay=0.0, jitter=False)

    attempts = {"count": 0}

    def failing_urlopen(*args, **kwargs):
        attempts["count"] += 1
        raise _make_urllib_http_error(http_code, {"error": {"message": f"Mock HTTP {http_code} from provider"}})

    with patch("core.llm_provider.urllib.request.urlopen", side_effect=failing_urlopen):
        res = process_clinical_chat(message="Tôi bị đau đầu nhẹ", history=[], gemini_service=svc)

    assert attempts["count"] == expected_attempts
    assert res["degraded"] is True
    assert res["ai_status"] == "unavailable"
    assert res["ai_error_code"] == expected_cls.value
    assert svc.last_error_info["status_code"] == http_code
    assert str(http_code) in caplog.text
    assert "sk-or-v1-test-key-secret-value" not in caplog.text


def test_frontend_degraded_notice_does_not_claim_home_followup():
    js = Path("static/js/app.js").read_text(encoding="utf-8")
    assert "Chế độ dự phòng: Theo dõi tại nhà" not in js
    assert "Backup Mode: Follow up at home" not in js
    assert "ai_error_code" in js


def test_fastapi_chat_endpoint_returns_honest_degraded_contract_on_openrouter_502():
    from starlette.testclient import TestClient
    from core.main_fastapi import app as fastapi_app
    import core.main_fastapi as mf

    mock_svc = GeminiMedicalService(api_key="sk-or-v1-test-key-secret-value", model="meta-llama/llama-3.1-8b-instruct:free")
    mock_svc.retry_policy = RetryPolicy(max_attempts=1, base_delay=0.0, max_delay=0.0, jitter=False)

    def raise_502(*args, **kwargs):
        raise _make_urllib_http_error(502, {"error": {"message": "Upstream OpenRouter 502 Bad Gateway"}})

    with patch.object(mf, "gemini_service", mock_svc), \
         patch("core.llm_provider.urllib.request.urlopen", side_effect=raise_502):
        client = TestClient(fastapi_app, headers={"origin": "http://localhost:8000"})
        resp = client.post("/api/chat", json={"message": "Tôi bị đau họng nhẹ", "history": [], "lang": "vi"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["degraded"] is True
    assert data["ai_status"] == "unavailable"
    assert data["ai_error_code"] == "SERVER_ERROR"
    assert "sk-or-" not in resp.text
