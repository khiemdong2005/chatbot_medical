"""Offline tests for OpenRouter's clinical chat request contract."""

from unittest.mock import patch

import pytest
from google.genai import types

from core.llm_provider import LLMProvider, _OpenRouterHTTPError


MODEL = "baidu/ernie-4.5-21b-a3b-thinking"
SCHEMA = {
    "type": "object",
    "properties": {"accepted": {"type": "array", "items": {"type": "integer"}}},
    "required": ["accepted"],
    "additionalProperties": False,
}


@pytest.fixture
def chat_client(monkeypatch):
    for key in ("OPENROUTER_CHAT_JSON_SCHEMA", "OPENROUTER_CHAT_DATA_COLLECTION", "OPENROUTER_CHAT_ZDR"):
        monkeypatch.delenv(key, raising=False)
    return LLMProvider().get_client("sk-or-test-chat-adapter-key", profile="chat")


def test_strict_chat_sends_sdk_json_schema_and_selected_privacy_preferences(chat_client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_CHAT_JSON_SCHEMA", "1")
    monkeypatch.setenv("OPENROUTER_CHAT_DATA_COLLECTION", "deny")
    monkeypatch.setenv("OPENROUTER_CHAT_ZDR", "1")
    config = types.GenerateContentConfig(
        system_instruction="Return the accepted indices.",
        response_mime_type="application/json",
        response_json_schema=SCHEMA,
    )
    response = {"choices": [{"message": {"content": '{"accepted":[1]}'}}]}

    with patch.object(chat_client.models, "_post_completion", return_value=response) as post:
        result = chat_client.models.generate_content(model=MODEL, contents="synthetic text", config=config)

    payload = post.call_args.args[0]
    assert result.text == '{"accepted":[1]}'
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "medimind_chat", "strict": True, "schema": SCHEMA},
    }
    assert payload["provider"] == {"require_parameters": True, "data_collection": "deny", "zdr": True}


@pytest.mark.parametrize("status", [400, 429, 503])
def test_compatibility_chat_preserves_http_status_without_retransmitting(chat_client, status):
    config = types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=SCHEMA)
    error = _OpenRouterHTTPError(status, f"OpenRouter HTTP {status}")

    with patch.object(chat_client.models, "_post_completion", side_effect=error) as post:
        with pytest.raises(_OpenRouterHTTPError) as captured:
            chat_client.models.generate_content(model=MODEL, contents="synthetic text", config=config)

    assert captured.value.status_code == status
    post.assert_called_once()
    payload = post.call_args.args[0]
    assert "response_format" not in payload
    assert "provider" not in payload
    assert "valid raw JSON object" in payload["messages"][0]["content"]


def test_strict_chat_never_falls_back_to_unstructured_after_400(chat_client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_CHAT_JSON_SCHEMA", "true")
    config = types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=SCHEMA)
    error = _OpenRouterHTTPError(400, "OpenRouter HTTP 400")

    with patch.object(chat_client.models, "_post_completion", side_effect=error) as post:
        with pytest.raises(_OpenRouterHTTPError):
            chat_client.models.generate_content(model=MODEL, contents="synthetic text", config=config)

    post.assert_called_once()
    assert post.call_args.args[0]["response_format"]["type"] == "json_schema"


@pytest.mark.parametrize("code, status", [(429, 429), ("503", 503), ("provider_error", 502), (200, 502)])
@pytest.mark.parametrize("in_choice", [False, True])
def test_successful_http_response_with_explicit_error_is_an_upstream_failure(chat_client, code, status, in_choice):
    error = {"code": code, "message": "private echoed prompt"}
    response = {"choices": [{"message": {"content": '{"partial":true}'}}]}
    target = response["choices"][0] if in_choice else response
    target["error"] = error

    with patch.object(chat_client.models, "_post_completion", return_value=response) as post:
        with pytest.raises(_OpenRouterHTTPError) as captured:
            chat_client.models.generate_content(model=MODEL, contents="synthetic text")

    assert captured.value.status_code == status
    assert "private echoed prompt" not in str(captured.value)
    post.assert_called_once()


def test_chat_flags_do_not_affect_other_clients_using_the_same_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_CHAT_JSON_SCHEMA", "1")
    monkeypatch.setenv("OPENROUTER_CHAT_DATA_COLLECTION", "deny")
    monkeypatch.setenv("OPENROUTER_CHAT_ZDR", "1")
    provider = LLMProvider()
    key = "sk-or-test-shared-adapter-key"
    chat_client = provider.get_client(key, profile="chat")
    legacy_client = provider.get_client(key)
    assert provider.get_client(key, profile="chat_generation") is chat_client
    assert chat_client is not legacy_client

    config = types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=SCHEMA)
    with patch.object(legacy_client.models, "_post_completion", return_value={"choices": []}) as post:
        legacy_client.models.generate_content(model=MODEL, contents="synthetic text", config=config)

    payload = post.call_args.args[0]
    assert payload["response_format"] == {"type": "json_object"}
    assert "provider" not in payload
