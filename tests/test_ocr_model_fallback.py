"""Model fallback must not multiply OCR latency for deterministic API errors."""

from unittest.mock import patch

import pytest

from core.ai_types import ErrorClassification
from core.llm_provider import LLMProvider, LLMProviderError, llm_provider
from core.gemini_schema_service import extract_with_gemini_schema


def test_unclassified_deterministic_error_does_not_try_every_model():
    provider = LLMProvider()
    attempted = []

    def call(_client, model):
        attempted.append(model)
        raise ValueError("bad payload")

    with patch.object(provider, "get_client", return_value=object()):
        with pytest.raises(LLMProviderError) as failure:
            provider._execute_model_call(
                call, operation="prescription_ocr", api_key="valid-test-key-12345",
                candidate_models=["first", "second", "third"],
            )

    assert attempted == ["first"]
    assert failure.value.classification == ErrorClassification.UNKNOWN


def test_auth_error_does_not_try_another_model():
    provider = LLMProvider()
    attempted = []

    def call(_client, model):
        attempted.append(model)
        error = Exception("permission denied")
        error.status_code = 403
        raise error

    with patch.object(provider, "get_client", return_value=object()):
        with pytest.raises(LLMProviderError) as failure:
            provider._execute_model_call(
                call, operation="prescription_ocr", api_key="valid-test-key-12345",
                candidate_models=["first", "second"],
            )

    assert attempted == ["first"]
    assert failure.value.classification == ErrorClassification.AUTH_ERROR


def test_unknown_client_error_stops_after_one_model():
    class ClientError(Exception):
        pass

    provider = LLMProvider()
    attempted = []

    def call(_client, model):
        attempted.append(model)
        raise ClientError("UNKNOWN")

    with patch.object(provider, "get_client", return_value=object()):
        with pytest.raises(LLMProviderError) as failure:
            provider._execute_model_call(
                call, operation="prescription_ocr", api_key="valid-test-key-12345",
                candidate_models=["first", "second", "third"],
            )

    assert attempted == ["first"]
    assert failure.value.classification == ErrorClassification.BAD_REQUEST


def test_missing_model_tries_next_candidate():
    provider = LLMProvider()
    attempted = []

    def call(_client, model):
        attempted.append(model)
        if model == "missing":
            error = Exception("model not found")
            error.status_code = 404
            raise error
        return "ok"

    with patch.object(provider, "get_client", return_value=object()):
        result = provider._execute_model_call(
            call, operation="prescription_ocr", api_key="valid-test-key-12345",
            candidate_models=["missing", "available"],
        )

    assert result == "ok"
    assert attempted == ["missing", "available"]


def test_ocr_schema_uses_configured_model_and_one_fallback(tmp_path):
    image = tmp_path / "prescription.jpg"
    image.write_bytes(b"test-image")

    with (patch.object(llm_provider, "resolve_api_key", return_value="valid-test-key-12345"),
          patch.object(llm_provider, "is_configured", return_value=True),
          patch.object(llm_provider, "get_default_model", return_value="gemini-flash-lite-latest"),
          patch.object(llm_provider, "generate_json", return_value={}) as generate):
        extract_with_gemini_schema(str(image))

    assert generate.call_args.kwargs["candidate_models"] == [
        "gemini-flash-lite-latest", "inclusionai/ling-3.2-flash:free"
    ]
