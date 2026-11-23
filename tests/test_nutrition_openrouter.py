"""Offline contract tests for nutrition's OpenRouter-only inference path."""

import json
import urllib.error
from io import BytesIO
from unittest.mock import patch

import pytest

from core.ai_types import ErrorClassification
from core.circuit_breaker import reset_all_circuit_breakers
from core.llm_provider import LLMProvider, LLMProviderError, _OpenRouterModels
from core.nutrition_ai import NutritionAIError, select_recipes, validate_selection
from core.nutrition_options import DRINK, FOOD, get_nutrition_options


@pytest.fixture
def openrouter_nutrition(monkeypatch):
    reset_all_circuit_breakers()
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-offline-test-key")
    monkeypatch.setenv("OPENROUTER_NUTRITION_MODEL", "nvidia/nemotron-3.5-lightning:free")
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    # A leftover Gemini key must never take over this workload.
    monkeypatch.setenv("GEMINI_NUTRITION_API_KEY", "unused-test-gemini-key")
    yield
    reset_all_circuit_breakers()


def _selection(recipe_id):
    return {
        "needs_clarification": False,
        "clarification_question": "",
        "recommendations": [{
            "recipe_id": recipe_id,
            "reason": "Công thức trong kho có nguyên liệu đã khai báo.",
            "caution": "Chỉ là lựa chọn tham khảo.",
            "source_ids": [],
        }],
    }


def _provider_error(classification, status_code=None):
    original = Exception("redacted provider failure")
    if status_code is not None:
        original.status_code = status_code
    return LLMProviderError(
        message="Provider unavailable",
        classification=classification,
        operation="nutrition_ai",
        original_exception=original,
    )


def test_missing_openrouter_key_never_uses_gemini(openrouter_nutrition, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    with patch("google.genai.Client") as google_client:
        with pytest.raises(NutritionAIError, match="not_configured"):
            select_recipes("ho", "food", FOOD, [])
        google_client.assert_not_called()


@pytest.mark.parametrize("kind,catalog", [("food", FOOD), ("drink", DRINK)])
def test_openrouter_ranks_only_catalog_items(openrouter_nutrition, kind, catalog):
    with patch("core.llm_provider.llm_provider.generate_json", return_value=_selection(catalog[0]["id"])) as generate_json:
        result = select_recipes("ho", kind, catalog, [])
    assert result["recipes"][0]["id"] == catalog[0]["id"]
    assert result["model"] == "nvidia/nemotron-3.5-lightning:free"
    call = generate_json.call_args.kwargs
    assert call["provider"] == "openrouter"
    assert call["json_mode"] is False
    assert call["reasoning_enabled"] is False
    assert call["model"] == "nvidia/nemotron-3.5-lightning:free"
    assert call.get("candidate_models") is None


def test_openrouter_selection_keeps_valid_full_meal(openrouter_nutrition):
    payload = _selection("oat_porridge")
    payload["full_meal_set"] = {
        "title": "Mâm cơm tham khảo",
        "meal_time": "lunch",
        "rationale": "Ghép các món có nguyên liệu rõ ràng trong kho công thức.",
        "main_recipe_id": "tofu_pumpkin",
        "soup_recipe_id": "pumpkin_soup",
        "side_recipe_id": "soft_egg",
        "staple_text": "",
    }
    result = validate_selection(payload, FOOD, 0)
    assert result["full_meal_set"]["main_recipe_id"] == "tofu_pumpkin"
    assert result["full_meal_set"]["soup_recipe_id"] == "pumpkin_soup"


@pytest.mark.parametrize("payload", [None, {}, "", "not json", {"choices": []}])
def test_malformed_or_empty_model_response_uses_safe_error(openrouter_nutrition, payload):
    with patch("core.llm_provider.llm_provider.generate_json", return_value=payload):
        with pytest.raises(NutritionAIError, match="invalid_response"):
            select_recipes("ho", "food", FOOD, [])


@pytest.mark.parametrize("classification,status_code,expected", [
    (ErrorClassification.BAD_REQUEST, 404, "configuration"),
    (ErrorClassification.AUTH_ERROR, 401, "credentials_or_access"),
    (ErrorClassification.AUTH_ERROR, 403, "credentials_or_access"),
    (ErrorClassification.RATE_LIMIT, 429, "quota"),
    (ErrorClassification.SERVER_ERROR, 500, "unavailable"),
    (ErrorClassification.SERVER_ERROR, 503, "unavailable"),
    (ErrorClassification.TIMEOUT, None, "unavailable"),
])
def test_provider_failures_are_classified_without_gemini_fallback(
    openrouter_nutrition, classification, status_code, expected
):
    error = _provider_error(classification, status_code)
    with patch("core.llm_provider.llm_provider.generate_json", side_effect=error) as generate_json:
        with patch("google.genai.Client") as google_client:
            with pytest.raises(NutritionAIError, match=expected):
                select_recipes("ho", "food", FOOD, [])
            google_client.assert_not_called()
    generate_json.assert_called_once()


def test_unavailable_model_keeps_filtered_catalog_without_ai_label(openrouter_nutrition):
    error = _provider_error(ErrorClassification.BAD_REQUEST, 404)
    with patch("core.llm_provider.llm_provider.generate_json", side_effect=error):
        result = get_nutrition_options("sốt", "food")
    assert result["provider_status"] == "fallback_configuration"
    assert result["recommendation_scope"] == "filtered_catalog"
    assert result["gemini_used"] is False
    assert result["recipes"]


def test_openrouter_chat_completion_payload_and_text_parts(openrouter_nutrition):
    model = _OpenRouterModels("sk-or-offline-test-key")
    response = {"choices": [{"message": {"content": [
        {"type": "text", "text": json.dumps(_selection("oat_porridge"))}
    ]}}]}
    with patch.object(model, "_post_completion", return_value=response) as post:
        result = model.generate_content(
            model="nvidia/nemotron-3.5-lightning:free",
            contents='{"user_input":"ho"}',
            config={"system_instruction": "Return valid JSON", "temperature": 0.2,
                    "max_output_tokens": 2600, "reasoning_enabled": False},
        )
    payload = post.call_args.args[0]
    assert payload["model"] == "nvidia/nemotron-3.5-lightning:free"
    assert payload["messages"] == [
        {"role": "system", "content": "Return valid JSON"},
        {"role": "user", "content": '{"user_input":"ho"}'},
    ]
    assert "response_format" not in payload
    assert payload["reasoning"] == {"enabled": False}
    assert json.loads(result.text)["recommendations"][0]["recipe_id"] == "oat_porridge"


def test_reasoning_setting_is_not_added_to_other_model_calls(openrouter_nutrition):
    model = _OpenRouterModels("sk-or-offline-test-key")
    with patch.object(model, "_post_completion", return_value={"choices": []}) as post:
        model.generate_content(model="nvidia/nemotron-3.5-lightning:free", contents="hello")
    assert "reasoning" not in post.call_args.args[0]


def test_openrouter_request_uses_official_endpoint_and_bearer(openrouter_nutrition):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"choices":[]}'

    model = _OpenRouterModels("sk-or-offline-test-key")
    with patch("core.llm_provider.urllib.request.urlopen", return_value=Response()) as urlopen:
        assert model._post_completion({"model": "test", "messages": []}) == {"choices": []}
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://openrouter.ai/api/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer sk-or-offline-test-key"
    assert request.get_method() == "POST"


def test_openrouter_401_fails_without_retry(openrouter_nutrition):
    provider = LLMProvider()
    unauthorized = urllib.error.HTTPError(
        "https://openrouter.ai/api/v1/chat/completions", 401,
        "Unauthorized", {}, BytesIO(b'{"error":"invalid key"}'),
    )
    with patch("core.llm_provider.urllib.request.urlopen", side_effect=unauthorized) as urlopen:
        with pytest.raises(LLMProviderError) as captured:
            provider.generate_json(
                contents="{}", model="nvidia/nemotron-3.5-lightning:free",
                operation="nutrition_ai", profile="nutrition", provider="openrouter",
                json_mode=False,
            )
    assert captured.value.classification == ErrorClassification.AUTH_ERROR
    assert urlopen.call_count == 1


def test_length_limited_empty_completion_is_invalid_response(openrouter_nutrition):
    provider = LLMProvider()
    truncated = {"choices": [{"finish_reason": "length", "message": {"content": ""}}]}
    with patch.object(_OpenRouterModels, "_post_completion", return_value=truncated) as post:
        with pytest.raises(LLMProviderError) as captured:
            provider.generate_json(
                contents="{}", model="nvidia/nemotron-3.5-lightning:free",
                operation="nutrition_ai", profile="nutrition", provider="openrouter",
                json_mode=False, reasoning_enabled=False,
            )
    assert captured.value.classification == ErrorClassification.SCHEMA_ERROR
    assert post.call_count == 1

