import os
import pytest
from unittest.mock import patch, MagicMock
from scripts.check_gemini_connection import (
    check_gemini_connection,
    validate_credential_format,
    classify_gemini_error
)
from core.gemini_service import GeminiMedicalService
from scripts.evaluate_answer_quality import check_deterministic_guardrails, classify_error_taxonomy


def test_missing_credential_is_rejected():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=True):
        valid, code, reason = validate_credential_format("")
        assert valid is False
        assert code == "MISSING_KEY"
        assert "missing or empty" in reason.lower()

        res = check_gemini_connection()
        assert res["auth_ok"] is False
        assert res["classification"] == "MISSING_KEY"


def test_placeholder_credential_is_rejected():
    placeholder = "your_google_gemini_api_key_here"
    valid, code, reason = validate_credential_format(placeholder)
    assert valid is False
    assert code == "PLACEHOLDER_KEY"

    placeholder_prefix = "YOUR_API_KEY_HERE"
    valid2, code2, _ = validate_credential_format(placeholder_prefix)
    assert valid2 is False
    assert code2 == "PLACEHOLDER_KEY"


def test_aq_prefixed_credential_not_rejected_locally():
    """AQ-prefixed keys must NOT be rejected by local format checks."""
    aq_key = "AQ.SampleNewGoogleAIStudioKeyFormat1234567890abcdef"
    valid, code, reason = validate_credential_format(aq_key)
    assert valid is True
    assert code == "VALID_FORMAT"

    # Also test GeminiMedicalService.is_configured()
    svc = GeminiMedicalService(api_key=aq_key)
    assert svc.is_configured() is True


def test_unsupported_auth_method_401_classified_correctly():
    """401 ACCESS_TOKEN_TYPE_UNSUPPORTED must be classified as UNSUPPORTED_AUTH_METHOD, not generic 401."""
    exc = Exception("401 UNAUTHENTICATED. ACCESS_TOKEN_TYPE_UNSUPPORTED: generativelanguage.googleapis.com")
    status, msg = classify_gemini_error(exc)
    assert status == "UNSUPPORTED_AUTH_METHOD"
    assert "ACCESS_TOKEN_TYPE_UNSUPPORTED" in msg


def test_invalid_api_key_401_classified():
    exc = Exception("401 UNAUTHENTICATED: API key not valid. Please pass a valid API key.")
    status, msg = classify_gemini_error(exc)
    assert status == "INVALID_API_KEY"


def test_secret_never_logged_or_exposed():
    sensitive_token = "AQ.SuperSecretApiKey1234567890Secret"
    with patch.dict(os.environ, {"GEMINI_API_KEY": sensitive_token}, clear=True):
        with patch("google.genai.Client", side_effect=Exception(f"401 UNAUTHENTICATED on key {sensitive_token}")):
            res = check_gemini_connection()
            assert res["auth_ok"] is False
            # Ensure the raw secret is NEVER exposed in the sanitized message
            assert sensitive_token not in res["message"]


def test_model_not_found_is_distinct_from_auth_failure():
    """MODEL_NOT_FOUND must be separated from authentication failure."""
    exc = Exception("404 NOT_FOUND: models/gemini-invalid-model is not found")
    status, msg = classify_gemini_error(exc)
    assert status == "MODEL_NOT_FOUND"
    assert "Model not found" in msg


def test_fallback_not_treated_as_successful_generation():
    case = {"relevant_sources": ["https://medlineplus.gov/fatigue.html"]}
    rag_docs = [{"source_url": "https://medlineplus.gov/fatigue.html"}]
    known_sources = {"https://medlineplus.gov/fatigue.html"}

    # Degraded fallback response
    fallback_result = {
        "answer": "Mình tạm chưa kết nối được dịch vụ AI nên chưa thể đánh giá tình trạng.",
        "degraded": True,
        "sources": []
    }
    checks = check_deterministic_guardrails(case, fallback_result, rag_docs, known_sources)
    assert checks["is_degraded"] is True

    # Error taxonomy must classify as MODEL_FAILURE
    fact_cov = {"coverage": 0.0, "matched_facts": [], "missing_facts": ["fact1"]}
    forbid = {"violated": False, "violated_claims": []}
    reasons = classify_error_taxonomy(checks, fact_cov, forbid, is_auth_blocked=True)
    assert "MODEL_FAILURE" in reasons
