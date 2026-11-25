"""
================================================================================
🩺 MEDIMIND UNIFIED AI / LLM PROVIDER LAYER
================================================================================
Cung cấp cổng giao tiếp LLM tập trung (Single Responsibility) cho toàn bộ
các tác vụ gọi Google Gemini AI trong hệ thống MediMind:
- Quản lý vòng đời Client: Lazy singleton, khởi tạo an toàn đa luồng, không gọi mạng lúc import.
- Phân giải API Key an toàn: Tách biệt key Chat / Nutrition / OCR theo Profile.
- Cấu hình Timeout theo Stage (chat, expansion, ocr, nutrition, interpretation).
- Tích hợp Retry Policy có Exponential Backoff & Jitter từ core/retry_policy.py.
- Circuit Breaker cách ly theo từng Workload (Chat không bị ảnh hưởng khi Nutrition lỗi).
- Quan sát & Đo lường thống nhất qua core/observability.py.
- Bảo mật quyền riêng tư tuyệt đối (Zero-PHI trong log và exception).
================================================================================
"""

import os
import re
import json
import time
import uuid
import base64
import logging
import threading
import urllib.request
import urllib.error
from urllib.parse import urlsplit
from typing import Dict, Any, List, Optional, Union, Callable

from core.retry_policy import (
    RetryPolicy,
    ErrorClassification,
    classify_exception,
    execute_with_retry,
    MaxRetriesExceededError
)
from core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    get_circuit_breaker
)
try:
    from core.settings import settings, is_configured_secret
except ImportError:
    from core.settings import settings
    def is_configured_secret(val: Any) -> bool:
        if not val or not isinstance(val, str):
            return False
        clean = val.strip().lower()
        return clean not in ("", "placeholder", "none", "null", "your_api_key_here") and not clean.startswith("your_")
from core.observability import metrics_collector

logger = logging.getLogger("LLMProvider")


def _openrouter_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _is_model_unavailable_error(exc: Exception) -> bool:
    """A missing model is the one deterministic client error worth trying elsewhere."""
    code = (getattr(exc, "status_code", None) or getattr(exc, "code", None)
            or getattr(exc, "http_status", None))
    if code == 404:
        return True
    status = str(getattr(exc, "status", "") or "").upper()
    if status in ("NOT_FOUND", "MODEL_NOT_FOUND"):
        return True
    message = str(exc).upper()
    return ("MODEL_NOT_FOUND" in message or
            ("NOT_FOUND" in message and "MODEL" in message))


class _OpenRouterHTTPError(Exception):
    """HTTP error carrying status_code for RetryPolicy / classify_exception."""
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = status_code


class _OpenRouterResponse:
    """Mimics google-genai GenerateContentResponse with .text attribute."""
    def __init__(self, text: str, raw: Optional[Dict[str, Any]] = None):
        self.text = text
        self.raw = raw or {}


class _OpenRouterModels:
    """Mimics client.models.generate_content(...) via OpenRouter Chat Completions API."""
    ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
    GROQ_OCR_FALLBACK_MODELS = ("qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b")

    def __init__(self, api_key: str, timeout_seconds: float = 25.0, *, chat: bool = False,
                 ocr: bool = False, groq: bool = False, provider: str = ""):
        self._api_key = api_key
        self._timeout = max(10.0, float(timeout_seconds))
        self._chat = chat
        self._ocr = ocr
        self._groq = groq or (str(provider).lower() == "groq")

    def _endpoint(self) -> str:
        if self._groq:
            return _groq_completion_endpoint()
        base = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        if self._ocr:
            base = base.strip().rstrip("/")
        parsed = urlsplit(base)
        if (parsed.scheme != "https" or parsed.netloc != "openrouter.ai"
                or parsed.path != "/api/v1" or parsed.query or parsed.fragment):
            raise _OpenRouterHTTPError(400, "Invalid OpenRouter base URL")
        return f"{base}/chat/completions"

    def _convert_contents(self, contents: Any) -> Any:
        if isinstance(contents, str):
            return contents
        items = contents if isinstance(contents, list) else [contents]
        parts: List[Dict[str, Any]] = []
        for item in items:
            if isinstance(item, str):
                parts.append({"type": "text", "text": item})
            elif isinstance(item, dict):
                if item.get("type") == "image_bytes" and item.get("data"):
                    mime = item.get("mime_type") or "image/jpeg"
                    raw_bytes = item["data"]
                    b64 = base64.b64encode(raw_bytes).decode("ascii") if isinstance(raw_bytes, (bytes, bytearray)) else str(raw_bytes)
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"}
                    })
                elif "text" in item:
                    parts.append({"type": "text", "text": str(item["text"])})
                else:
                    parts.append(item)
            else:
                inline = getattr(item, "inline_data", None)
                if inline is not None and getattr(inline, "data", None):
                    mime = getattr(inline, "mime_type", None) or "image/jpeg"
                    raw_bytes = inline.data
                    b64 = base64.b64encode(raw_bytes).decode("ascii") if isinstance(raw_bytes, (bytes, bytearray)) else str(raw_bytes)
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"}
                    })
                elif getattr(item, "text", None) is not None:
                    parts.append({"type": "text", "text": str(item.text)})
                else:
                    parts.append({"type": "text", "text": str(item)})
        if parts and all(p.get("type") == "text" for p in parts):
            return "\n\n".join(p["text"] for p in parts)
        return parts

    def _post_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MediMind-Clinical-AI/1.0",
        }
        if not self._groq:
            headers["HTTP-Referer"] = "https://medimind.local"
            headers["X-Title"] = "MediMind Clinical AI"
        provider_label = "Groq" if self._groq else "OpenRouter"
        req = urllib.request.Request(
            self._endpoint(),
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            # Provider error bodies can echo request content. Never retain them
            # in exceptions, retry logs, or API responses.
            raise _OpenRouterHTTPError(he.code, f"{provider_label} HTTP {he.code}") from None
        except urllib.error.URLError as ue:
            raise TimeoutError(f"{provider_label} connection error: {ue.reason}") from None

    def _post_with_json_compatibility(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._post_completion(payload)
        except _OpenRouterHTTPError as error:
            retry_statuses = (400,) if self._ocr else (400, 422)
            if self._chat or error.status_code not in retry_statuses or "response_format" not in payload:
                raise
            payload.pop("response_format")
            return self._post_completion(payload)

    def generate_content(self, model: str, contents: Any, config: Optional[Any] = None) -> _OpenRouterResponse:
        def get_config(key: str) -> Any:
            if isinstance(config, dict):
                return config.get(key)
            return getattr(config, key, None)

        messages: List[Dict[str, Any]] = []
        sys_inst = get_config("system_instruction")
        temperature = get_config("temperature")
        max_tokens = get_config("max_output_tokens")
        want_json = get_config("response_mime_type") == "application/json"
        reasoning_enabled = get_config("reasoning_enabled")

        if sys_inst:
            if want_json:
                sys_inst = f"{sys_inst}\n\nIMPORTANT: Respond ONLY with a valid raw JSON object (no markdown fences, no extra text)."
            messages.append({"role": "system", "content": str(sys_inst)})
        elif want_json:
            messages.append({"role": "system", "content": "Respond ONLY with a valid raw JSON object (no markdown fences, no extra text)."})

        messages.append({"role": "user", "content": self._convert_contents(contents)})

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            output_tokens = int(max_tokens)
            if self._ocr and output_tokens >= 2048:
                payload["max_tokens"] = output_tokens
            elif not self._ocr and output_tokens > 0:
                payload["max_tokens"] = max(output_tokens, 4096)
        if self._chat:
            routing: Dict[str, Any] = {}
            if os.getenv("OPENROUTER_CHAT_DATA_COLLECTION", "").strip().lower() == "deny":
                routing["data_collection"] = "deny"
            if _openrouter_flag("OPENROUTER_CHAT_ZDR"):
                routing["zdr"] = True
            if want_json and _openrouter_flag("OPENROUTER_CHAT_JSON_SCHEMA"):
                schema = get_config("response_json_schema")
                if not isinstance(schema, dict) or not schema:
                    raise _OpenRouterHTTPError(400, "OpenRouter chat JSON Schema is missing or invalid")
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "medimind_chat", "strict": True, "schema": schema},
                }
                routing["require_parameters"] = True
            if routing:
                payload["provider"] = routing
        elif want_json:
            payload["response_format"] = {"type": "json_object"}
        if not self._groq and isinstance(reasoning_enabled, bool):
            payload["reasoning"] = {"enabled": reasoning_enabled}

        fallback_statuses = (404, 413, 429)
        try:
            resp_json = self._post_with_json_compatibility(payload)
        except _OpenRouterHTTPError as error:
            if not self._groq or error.status_code not in fallback_statuses:
                raise
            has_image = any(
                isinstance(msg.get("content"), list)
                and any(isinstance(part, dict) and part.get("type") == "image_url" for part in msg["content"])
                for msg in (payload.get("messages") or [])
                if isinstance(msg, dict)
            )
            if has_image:
                raise
            last_error = error
            for fallback_model in self.GROQ_OCR_FALLBACK_MODELS:
                if fallback_model == model:
                    continue
                payload["model"] = fallback_model
                try:
                    resp_json = self._post_with_json_compatibility(payload)
                    break
                except _OpenRouterHTTPError as fallback_error:
                    if fallback_error.status_code not in fallback_statuses:
                        raise
                    last_error = fallback_error
            else:
                raise last_error

        response = resp_json if isinstance(resp_json, dict) else {}
        choices = response.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        error = response.get("error")
        if not isinstance(error, dict):
            error = choice.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            if isinstance(code, str) and re.fullmatch(r"[45][0-9]{2}", code):
                code = int(code)
            status = code if type(code) is int and 400 <= code <= 599 else 502
            raise _OpenRouterHTTPError(status, f"OpenRouter completion error ({status})")

        message = choice.get("message")
        content = message.get("content", "") if isinstance(message, dict) else ""
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content
                              if isinstance(part, dict) and isinstance(part.get("text"), str))
        if not isinstance(content, str):
            content = ""
        if not self._ocr and not content.strip() and isinstance(message, dict):
            reasoning = message.get("reasoning", "")
            if isinstance(reasoning, str) and reasoning.strip():
                content = reasoning
        return _OpenRouterResponse(text=content, raw=resp_json)


class _OpenRouterClient:
    """Drop-in replacement for genai.Client exposing .models.generate_content()."""
    def __init__(self, api_key: str, timeout_seconds: float = 25.0, *, chat: bool = False,
                 ocr: bool = False, groq: bool = False):
        self.models = _OpenRouterModels(api_key, timeout_seconds, chat=chat, ocr=ocr, groq=groq)


# ==============================================================================
# GROQ PROVIDER — OpenAI-compatible, free tier 30 req/min (10x OpenRouter free)
# Models: llama-3.3-70b-versatile, gemma2-9b-it, llama-3.1-8b-instant, ...
# Endpoint: https://api.groq.com/openai/v1/chat/completions
# Key format: gsk_...
# ==============================================================================

class _GroqHTTPError(_OpenRouterHTTPError):
    """Dedicated HTTP error for Groq so logs clearly distinguish Groq from OpenRouter."""


def _groq_completion_endpoint() -> str:
    base = (os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai/v1").strip().rstrip("/")
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or parsed.netloc != "api.groq.com"
            or parsed.path != "/openai/v1" or parsed.query or parsed.fragment):
        raise _GroqHTTPError(400, "Invalid Groq base URL")
    return f"{base}/chat/completions"


class _GroqModels:
    """Mimics _OpenRouterModels via Groq's OpenAI-compatible Chat Completions API."""
    ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, timeout_seconds: float = 25.0):
        self._api_key = api_key
        self._timeout = max(10.0, float(timeout_seconds))

    def _convert_contents(self, contents: Any) -> str:
        """Groq không hỗ trợ image input trên free tier — chỉ nhận text."""
        if isinstance(contents, str):
            return contents
        items = contents if isinstance(contents, list) else [contents]
        parts: List[str] = []
        for item in items:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item["text"]))
                # bỏ qua image_bytes — Groq free không hỗ trợ vision
            else:
                text = getattr(item, "text", None)
                if text is not None:
                    parts.append(str(text))
        return "\n\n".join(parts)

    def _endpoint(self) -> str:
        return _groq_completion_endpoint()

    def _post_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = urllib.request.Request(
            self._endpoint(),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "MediMind-Clinical-AI/1.0",
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            if he.code == 429:
                headers = he.headers or {}
                logger.warning(
                    "Groq rate limit: model=%s retry_after=%s remaining_requests=%s remaining_tokens=%s",
                    payload.get("model"),
                    headers.get("Retry-After"),
                    headers.get("x-ratelimit-remaining-requests"),
                    headers.get("x-ratelimit-remaining-tokens"),
                )
            raise _GroqHTTPError(he.code, f"Groq HTTP {he.code}") from None
        except urllib.error.URLError as ue:
            raise TimeoutError(f"Groq connection error: {ue.reason}") from None

    def generate_content(self, model: str, contents: Any, config: Optional[Any] = None) -> _OpenRouterResponse:
        def get_config(key: str) -> Any:
            if isinstance(config, dict):
                return config.get(key)
            return getattr(config, key, None)

        messages: List[Dict[str, Any]] = []
        sys_inst = get_config("system_instruction")
        temperature = get_config("temperature")
        max_tokens = get_config("max_output_tokens")
        want_json = get_config("response_mime_type") == "application/json"

        if sys_inst:
            if want_json:
                sys_inst = (f"{sys_inst}\n\n"
                            "IMPORTANT: Respond ONLY with a valid raw JSON object "
                            "(no markdown fences, no extra text).")
            messages.append({"role": "system", "content": str(sys_inst)})
        elif want_json:
            messages.append({
                "role": "system",
                "content": "Respond ONLY with a valid raw JSON object (no markdown fences, no extra text)."
            })

        messages.append({"role": "user", "content": self._convert_contents(contents)})

        payload: Dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = float(temperature)
        # Groq reasoning models (gpt-oss-*) consume tokens for internal reasoning —
        # enforce a minimum of 1024 so content tokens remain after the reasoning budget.
        effective_max = int(max_tokens) if (max_tokens is not None and int(max_tokens) > 0) else 1024
        payload["max_tokens"] = max(effective_max, 1024)
        if want_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp_json = self._post_completion(payload)
        except _OpenRouterHTTPError as e:
            # Retry without response_format nếu model không hỗ trợ JSON mode
            if e.status_code in (400, 422) and "response_format" in payload:
                payload.pop("response_format", None)
                resp_json = self._post_completion(payload)
            elif e.status_code == 404:
                fallback_model = (os.getenv("GROQ_FALLBACK_MODEL") or "qwen/qwen3.8-27b").strip()
                if fallback_model and payload.get("model") != fallback_model:
                    payload["model"] = fallback_model
                    resp_json = self._post_completion(payload)
                else:
                    raise
            else:
                raise

        response = resp_json if isinstance(resp_json, dict) else {}
        # Handle Groq error field
        error = response.get("error")
        if isinstance(error, dict):
            code = error.get("code") or 502
            if isinstance(code, str) and re.fullmatch(r"[45][0-9]{2}", code):
                code = int(code)
            status = code if isinstance(code, int) and 400 <= code <= 599 else 502
            raise _GroqHTTPError(status, f"Groq completion error ({status})")

        choices = response.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = choice.get("message")
        content = message.get("content", "") if isinstance(message, dict) else ""
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
        if not isinstance(content, str):
            content = ""
        if not content.strip() and isinstance(message, dict):
            reasoning = message.get("reasoning", "")
            if isinstance(reasoning, str) and reasoning.strip():
                content = reasoning
        # Groq reasoning models (openai/gpt-oss-*) may put output only in "reasoning"
        # when max_tokens is too small — fall back to reasoning field if content is empty.
        if not content.strip() and isinstance(message, dict):
            reasoning = message.get("reasoning", "")
            if isinstance(reasoning, str) and reasoning.strip():
                content = reasoning.strip()
                logger.debug("Groq: content empty, falling back to reasoning field (%d chars)", len(content))
        return _OpenRouterResponse(text=content, raw=resp_json)


class _GroqClient:
    """Drop-in replacement for genai.Client — wraps _GroqModels."""
    def __init__(self, api_key: str, timeout_seconds: float = 25.0):
        self.models = _GroqModels(api_key=api_key, timeout_seconds=timeout_seconds)


class LLMProviderError(Exception):
    """Ngoại lệ có cấu trúc của LLM Provider, bảo đảm an toàn quyền riêng tư (Zero-PHI)."""
    def __init__(
        self,
        message: str,
        classification: ErrorClassification,
        operation: str,
        retryable: bool = False,
        original_exception: Optional[Exception] = None
    ):
        self.message = message
        self.classification = classification
        self.operation = operation
        self.retryable = retryable
        self.original_exception = original_exception
        super().__init__(f"[{operation}] {classification.value}: {message}")


class LLMProvider:
    """
    Unified Gemini AI Provider:
    Quản lý Client lifecycle, Retry, Circuit Breaker, Timeout, Metrics và Safe Logging.
    """

    def __init__(self):
        self._clients: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._groq_rr_idx = 0

    def _groq_key_pool(self, primary_key: str) -> List[str]:
        """Collect configured Groq API keys (primary + backup + GROQ_API_KEYS) and rotate round-robin."""
        candidates: List[str] = []
        for raw in (
            primary_key,
            os.getenv("GROQ_API_KEY", ""),
            os.getenv("GROQ_BACKUP_API_KEY", ""),
        ):
            clean = (raw or "").strip()
            if clean and is_configured_secret(clean) and clean not in candidates:
                candidates.append(clean)
        for part in (os.getenv("GROQ_API_KEYS") or "").split(","):
            clean = part.strip()
            if clean and is_configured_secret(clean) and clean not in candidates:
                candidates.append(clean)
        if len(candidates) > 1:
            with self._lock:
                start = self._groq_rr_idx % len(candidates)
                self._groq_rr_idx += 1
            return candidates[start:] + candidates[:start]
        return candidates

    # ==========================================================================
    # 1. API KEY RESOLUTION & VALIDATION
    # ==========================================================================

    def is_groq_active(self) -> bool:
        """Kiểm tra Groq có được cấu hình làm primary provider không."""
        provider = os.getenv("AI_PROVIDER", "").strip().lower()
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        return provider == "groq" and is_configured_secret(groq_key)

    def is_openrouter_active(self) -> bool:
        """Kiểm tra xem hệ thống có đang cấu hình chạy OpenRouter hay không."""
        provider = os.getenv("AI_PROVIDER", "").strip().lower()
        if provider == "openrouter":
            return True
        openrouter_key = (
            os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPENROUTER_CHAT_API_KEY")
            or os.getenv("OPENROUTER_OCR_API_KEY")
            or os.getenv("OPENROUTER_NUTRITION_API_KEY")
            or ""
        ).strip()
        return provider == "openrouter" and is_configured_secret(openrouter_key)

    def _prescription_ocr_credentials(self) -> tuple[str, str]:
        provider = os.getenv("OCR_AI_PROVIDER", "").strip().lower()
        if not provider:
            provider = os.getenv("AI_PROVIDER", "").strip().lower()
        # Groq không hỗ trợ multimodal vision cho đơn thuốc (text-only).
        # Nếu có OPENROUTER_OCR_API_KEY hoặc GEMINI_API_KEY, tự động ưu tiên cho OCR vision.
        if provider == "openrouter" or (provider in ("", "groq") and os.getenv("OCR_AI_PROVIDER", "").strip().lower() != "groq"):
            for name in ("OPENROUTER_OCR_API_KEY", "OPENROUTER_API_KEY",
                         "OPENROUTER_CHAT_API_KEY", "OPENROUTER_NUTRITION_API_KEY"):
                key = os.getenv(name, "").strip()
                if is_configured_secret(key):
                    return "openrouter", key
        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or settings.gemini.api_key or ""
        if is_configured_secret(gemini_key):
            return "gemini", gemini_key.strip()
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if provider in ("", "groq") and is_configured_secret(groq_key):
            return "groq", groq_key
        return "gemini", gemini_key.strip()

    def resolve_api_key(
        self,
        profile: Optional[str] = None,
        explicit_key: Optional[str] = None
    ) -> str:
        """
        Xác định API Key theo Profile một cách an toàn:
        - Nếu AI_PROVIDER=groq      -> ưu tiên GROQ_API_KEY (gsk_...).
        - Nếu AI_PROVIDER=openrouter -> ưu tiên OPENROUTER_*_API_KEY (sk-or-...).
        - Nếu có explicit_key        -> ưu tiên số 1.
        - Profile 'nutrition' -> OPENROUTER_NUTRITION_API_KEY -> GEMINI_NUTRITION_API_KEY -> GEMINI_API_KEY.
        - Profile 'chat'      -> OPENROUTER_CHAT_API_KEY -> GEMINI_CHAT_API_KEY -> GEMINI_API_KEY.
        - Profile 'ocr'       -> OPENROUTER_OCR_API_KEY -> OCR_MODEL / GEMINI_API_KEY.
        - Mặc định            -> GEMINI_API_KEY -> GOOGLE_API_KEY.
        """
        if explicit_key and isinstance(explicit_key, str) and explicit_key.strip():
            return explicit_key.strip()

        prof = (profile or "").lower()
        if prof in ("ocr", "prescription_ocr", "prescription", "interpretation"):
            return self._prescription_ocr_credentials()[1]
        is_vision_ocr = any(tag in prof for tag in ("ocr", "prescription", "vision"))

        # Groq primary provider (text-only: không hỗ trợ vision/OCR -> bỏ qua cho tác vụ OCR/Vision)
        if self.is_groq_active() and not is_vision_ocr:
            groq_key = os.getenv("GROQ_API_KEY", "").strip()
            if groq_key:
                return groq_key

        if self.is_openrouter_active():
            if prof in ("nutrition", "nutrition_ai"):
                or_nutri_key = (os.getenv("OPENROUTER_NUTRITION_API_KEY") or "").strip()
                if is_configured_secret(or_nutri_key):
                    return or_nutri_key
            if prof in ("chat", "chat_generation"):
                or_chat_key = (os.getenv("OPENROUTER_CHAT_API_KEY") or "").strip()
                if is_configured_secret(or_chat_key):
                    return or_chat_key
            if is_vision_ocr or prof in ("ocr", "prescription", "vision", "interpretation"):
                or_ocr_key = (os.getenv("OPENROUTER_OCR_API_KEY") or "").strip()
                if is_configured_secret(or_ocr_key):
                    return or_ocr_key
                return or_ocr_key

        if self.is_openrouter_active():
            for env_name in (
                "OPENROUTER_API_KEY",
                "OPENROUTER_CHAT_API_KEY",
                "OPENROUTER_OCR_API_KEY",
                "OPENROUTER_NUTRITION_API_KEY",
            ):
                candidate = (os.getenv(env_name) or "").strip()
                if is_configured_secret(candidate):
                    return candidate
            return ""

        or_general_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        if is_configured_secret(or_general_key):
            return or_general_key

        if prof in ("nutrition", "nutrition_ai"):
            key = (os.getenv("GEMINI_NUTRITION_API_KEY") or settings.gemini.nutrition_api_key or "").strip()
            if is_configured_secret(key):
                return key

        if prof in ("chat", "chat_generation"):
            key = (os.getenv("GEMINI_CHAT_API_KEY") or settings.gemini.chat_api_key or "").strip()
            if is_configured_secret(key):
                return key

        for candidate in (
            os.getenv("GEMINI_API_KEY"),
            os.getenv("GOOGLE_API_KEY"),
            settings.gemini.api_key,
        ):
            clean = (candidate or "").strip()
            if is_configured_secret(clean):
                return clean
        return ""

    def is_configured(
        self,
        profile: Optional[str] = None,
        explicit_key: Optional[str] = None
    ) -> bool:
        """Kiểm tra tính hợp lệ của API Key mà không thực hiện kết nối mạng."""
        key = self.resolve_api_key(profile=profile, explicit_key=explicit_key)
        return bool(is_configured_secret(key) and len(key) > 10)

    # ==========================================================================
    # 2. CLIENT LIFECYCLE (LAZY SINGLETON & THREAD-SAFE)
    # ==========================================================================

    def get_client(
        self,
        api_key: str,
        timeout_seconds: float = 15.0,
        provider: Optional[str] = None,
        *,
        profile: Optional[str] = None,
    ) -> Any:
        """
        Khởi tạo hoặc tái sử dụng AI Client (Groq / OpenRouter / Gemini) một cách lười (Lazy) và an toàn đa luồng.
        Không thực hiện bất kỳ lệnh gọi mạng nào lúc khởi tạo.
        Priority: Groq (gsk_...) > OpenRouter (sk-or-...) > Gemini
        """
        use_groq = provider == "groq" or (
            provider is None and isinstance(api_key, str) and api_key.startswith("gsk_"))
        use_openrouter = (not use_groq) and (
            provider == "openrouter" or (
                provider is None and isinstance(api_key, str) and api_key.startswith("sk-or-")))
        chat = use_openrouter and (profile or "").lower() in ("chat", "chat_generation")
        ocr = (use_groq or use_openrouter) and profile in ("prescription_ocr", "interpretation")
        timeout_ms = max(10000, int(timeout_seconds * 1000))

        if use_groq:
            cache_key = f"groq_{hash(api_key)}_{timeout_ms}"
        elif use_openrouter:
            cache_key = f"or_{hash(api_key)}_{timeout_ms}"
            if chat:
                cache_key += "_chat"
        else:
            cache_key = f"gm_{hash(api_key)}_{timeout_ms}"
        if ocr:
            cache_key += "_ocr"

        with self._lock:
            if cache_key in self._clients:
                return self._clients[cache_key]

            if ocr:
                client = _OpenRouterClient(api_key, timeout_seconds, ocr=True, groq=use_groq)
                self._clients[cache_key] = client
                return client

            if use_groq:
                client = _GroqClient(api_key=api_key, timeout_seconds=timeout_seconds)
                self._clients[cache_key] = client
                return client

            if use_openrouter:
                client = _OpenRouterClient(api_key=api_key, timeout_seconds=timeout_seconds, chat=chat)
                self._clients[cache_key] = client
                return client

            try:
                from google import genai
                from google.genai import types

                http_options = types.HttpOptions(
                    timeout=timeout_ms,
                    retry_options=types.HttpRetryOptions(attempts=1)
                )
                client = genai.Client(api_key=api_key, http_options=http_options)
                self._clients[cache_key] = client
                return client
            except Exception as e:
                logger.error("Không thể khởi tạo Gemini Client (%s).", type(e).__name__)
                raise LLMProviderError(
                    message=f"Không thể khởi tạo Gemini Client: {type(e).__name__}",
                    classification=ErrorClassification.AUTH_ERROR,
                    operation="client_initialization",
                    original_exception=e
                ) from None

    # ==========================================================================
    # 3. STAGE-SPECIFIC DEFAULTS (TIMEOUT, RETRY, CIRCUIT BREAKER, MODEL)
    # ==========================================================================

    def get_stage_timeout(self, operation: str) -> float:
        """Lấy cấu hình timeout theo từng stage/workload."""
        op = operation.lower()
        if "chat" in op:
            val = os.getenv("LLM_CHAT_TIMEOUT_SECONDS") or os.getenv("GEMINI_GENERATION_TIMEOUT_SECONDS")
            return float(val) if val else settings.gemini.timeout_chat
        if "expansion" in op:
            val = os.getenv("LLM_EXPANSION_TIMEOUT_SECONDS") or os.getenv("QUERY_EXPANSION_TIMEOUT_SECONDS")
            return float(val) if val else settings.gemini.timeout_expansion
        if "ocr" in op or "prescription" in op:
            val = os.getenv("OCR_AI_TIMEOUT_SECONDS") or os.getenv("OPENROUTER_OCR_TIMEOUT_SECONDS")
            return float(val) if val else max(60.0, float(settings.gemini.timeout_ocr))
        if "nutrition" in op:
            val = os.getenv("GEMINI_NUTRITION_TIMEOUT_SECONDS")
            return float(val) if val else settings.gemini.timeout_nutrition
        if "interpretation" in op:
            val = os.getenv("LLM_INTERPRETATION_TIMEOUT_SECONDS") or os.getenv("GEMINI_INTERPRETATION_TIMEOUT_SECONDS")
            return float(val) if val else settings.gemini.timeout_interpretation
        val = os.getenv("LLM_DEFAULT_TIMEOUT_SECONDS")
        return float(val) if val else settings.gemini.timeout_default

    def get_stage_retry_policy(self, operation: str) -> RetryPolicy:
        """Lấy cấu hình Retry Policy theo từng stage."""
        op = operation.lower()
        if "expansion" in op:
            return RetryPolicy(max_attempts=2, base_delay=0.2, max_delay=1.0, jitter=True)
        if "ocr" in op or "prescription" in op:
            return RetryPolicy(max_attempts=2, base_delay=0.5, max_delay=2.0, jitter=True)
        # Chat, Nutrition và mặc định
        max_att = int(os.getenv("AI_RETRY_MAX_ATTEMPTS", str(settings.retry.max_attempts)))
        base_d = float(os.getenv("AI_RETRY_BASE_DELAY_SECONDS", str(settings.retry.base_delay_seconds)))
        max_d = float(os.getenv("AI_RETRY_MAX_DELAY_SECONDS", str(settings.retry.max_delay_seconds)))
        return RetryPolicy(max_attempts=max_att, base_delay=base_d, max_delay=max_d, jitter=settings.retry.jitter)

    def get_stage_circuit_breaker(self, operation: str) -> CircuitBreaker:
        """Lấy Circuit Breaker độc lập theo từng workload."""
        op = operation.lower()
        if "chat" in op:
            return get_circuit_breaker("chat")
        if "expansion" in op:
            return get_circuit_breaker("query_expansion")
        if "nutrition" in op:
            return get_circuit_breaker("nutrition")
        if "ocr" in op or "prescription" in op:
            return get_circuit_breaker("ocr")
        if "interpretation" in op:
            return get_circuit_breaker("interpretation")
        return get_circuit_breaker("gemini_main")

    def get_default_model(self, operation: str, api_key: Optional[str] = None) -> str:
        """Lấy model mặc định cho từng tác vụ. Priority: Groq > OpenRouter > Gemini."""
        op = operation.lower()

        if op == "prescription_ocr":
            provider, _ = self._prescription_ocr_credentials()
            if provider == "groq":
                return (os.getenv("GROQ_OCR_MODEL") or os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
            if provider == "openrouter":
                return os.getenv("OPENROUTER_OCR_MODEL", "nvidia/nemotron-3.5-super-vl:free").strip()
            return (os.getenv("OCR_MODEL") or settings.gemini.ocr_model).strip()

        if op == "interpretation" and api_key:
            if api_key.startswith("gsk_"):
                return (os.getenv("GROQ_INTERPRETATION_MODEL") or os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
            if api_key.startswith("sk-or-"):
                return os.getenv("OPENROUTER_INTERPRETATION_MODEL", "openrouter/free").strip()
            return (os.getenv("INTERPRETATION_MODEL") or settings.gemini.interpretation_model).strip()

        # Groq priority
        use_groq = (
            self.is_groq_active()
            or (isinstance(api_key, str) and api_key.strip().startswith("gsk_"))
        )
        if use_groq:
            # Groq không hỗ trợ vision — OCR fallback sang OpenRouter hoặc Gemini
            if "ocr" in op or "prescription" in op or "vision" in op:
                or_key = (
                    os.getenv("OPENROUTER_OCR_API_KEY", "").strip()
                    or os.getenv("OPENROUTER_API_KEY", "").strip()
                )
                if is_configured_secret(or_key) or (isinstance(api_key, str) and api_key.startswith("sk-or-")):
                    return os.getenv("OPENROUTER_OCR_MODEL", "nvidia/nemotron-3.5-super-vl:free").strip()
                return (os.getenv("OCR_MODEL") or settings.gemini.ocr_model).strip()
            if "chat" in op:
                return (os.getenv("GROQ_CHAT_MODEL") or os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
            if "expansion" in op:
                return (os.getenv("GROQ_EXPANSION_MODEL") or os.getenv("GROQ_MODEL") or "openai/gpt-oss-20b").strip()
            if "nutrition" in op:
                return (os.getenv("GROQ_NUTRITION_MODEL") or os.getenv("GROQ_MODEL") or "openai/gpt-oss-20b").strip()
            if "interpretation" in op:
                return (os.getenv("GROQ_INTERPRETATION_MODEL") or os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b").strip()
            return (os.getenv("GROQ_CHAT_MODEL") or os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()

        use_openrouter = (
            self.is_openrouter_active()
            or (isinstance(api_key, str) and api_key.strip().startswith("sk-or-"))
        )
        if use_openrouter:
            if "chat" in op:
                return os.getenv("OPENROUTER_CHAT_MODEL", "openrouter/free").strip()
            if "expansion" in op:
                return os.getenv("OPENROUTER_EXPANSION_MODEL", "openrouter/free").strip()
            if "nutrition" in op:
                return os.getenv("OPENROUTER_NUTRITION_MODEL", "openrouter/free").strip()
            if "ocr" in op or "prescription" in op:
                return os.getenv("OPENROUTER_OCR_MODEL", "nvidia/nemotron-3.5-super-vl:free").strip()
            if "interpretation" in op:
                return os.getenv("OPENROUTER_INTERPRETATION_MODEL", "openrouter/free").strip()
            return os.getenv("OPENROUTER_CHAT_MODEL", "openrouter/free").strip()

        if "chat" in op:
            return (os.getenv("GEMINI_CHAT_MODEL") or os.getenv("GEMINI_MODEL") or settings.gemini.chat_model).strip()
        if "expansion" in op:
            return (os.getenv("GEMINI_EXPANSION_MODEL") or settings.gemini.expansion_model).strip()
        if "nutrition" in op:
            return (os.getenv("GEMINI_NUTRITION_MODEL") or settings.gemini.nutrition_model).strip()
        if "ocr" in op or "prescription" in op:
            return (os.getenv("OCR_MODEL") or settings.gemini.ocr_model).strip()
        if "interpretation" in op:
            return (os.getenv("INTERPRETATION_MODEL") or settings.gemini.interpretation_model).strip()
        return settings.gemini.chat_model

    # ==========================================================================
    # 4. CORE EXECUTION ENGINE (WITH RETRY, BREAKER, METRICS & PRIVACY LOGS)
    # ==========================================================================

    def _execute_model_call(
        self,
        call_fn: Callable[[Any, str], Any],
        operation: str,
        model: Optional[str] = None,
        candidate_models: Optional[List[str]] = None,
        timeout_seconds: Optional[float] = None,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        request_id: Optional[str] = None,
        api_key: Optional[str] = None,
        profile: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Any:
        """
        Thực thi cuộc gọi mô hình Gemini với đầy đủ các tầng bảo vệ:
        - Kiểm tra cấu hình API Key
        - Cấp phát / Tái sử dụng Client
        - Bọc trong Circuit Breaker cách ly
        - Thực thi Retry với Exponential Backoff & Jitter
        - Ghi nhận Metrics chính xác (Không double-count)
        - Ghi Log bảo mật Zero-PHI
        """
        req_id = request_id or uuid.uuid4().hex[:8]
        if provider == "groq":
            effective_key = (api_key or os.getenv("GROQ_API_KEY") or "").strip()
        elif provider == "openrouter":
            # An absent OpenRouter key must never resolve to a legacy Gemini key.
            effective_key = (api_key or os.getenv("OPENROUTER_API_KEY") or "").strip()
        else:
            effective_key = self.resolve_api_key(profile=profile or operation, explicit_key=api_key)

        valid_key = bool(is_configured_secret(effective_key) and len(effective_key) > 10)
        if not valid_key:
            metrics_collector.increment("llm_failure_total")
            metrics_collector.record_error("AUTH_ERROR")
            metrics_collector.log_event(operation, req_id, 0.0, "FALLBACK", error_class="AUTH_ERROR")
            logger.info("[%s][REQ-%s] API key chưa cấu hình hoặc không hợp lệ.", operation, req_id)
            raise LLMProviderError(
                message="Khóa xác thực AI chưa được cấu hình.",
                classification=ErrorClassification.AUTH_ERROR,
                operation=operation,
                retryable=False
            )

        timeout = timeout_seconds or self.get_stage_timeout(operation)
        policy = retry_policy or self.get_stage_retry_policy(operation)
        breaker = circuit_breaker or self.get_stage_circuit_breaker(operation)

        models_to_try = candidate_models or [model or self.get_default_model(operation)]

        metrics_collector.increment("llm_request_total")
        start_time = time.time()
        retries_count = 0

        def _on_retry(attempt, delay, exc, classification):
            nonlocal retries_count
            retries_count += 1
            metrics_collector.increment("llm_retry_total")
            if classification == ErrorClassification.RATE_LIMIT:
                metrics_collector.increment("rate_limit_429_total")
            elif classification == ErrorClassification.SERVER_ERROR:
                metrics_collector.increment("server_error_5xx_total")
            elif classification == ErrorClassification.TIMEOUT:
                metrics_collector.increment("timeout_total")

        document_ai = operation in ("prescription_ocr", "interpretation")
        is_groq_key = effective_key.startswith("gsk_") or provider == "groq"
        key_pool = self._groq_key_pool(effective_key) if is_groq_key else [effective_key]
        if not key_pool:
            key_pool = [effective_key]

        def _make_client(key_str: str):
            if document_ai:
                return self.get_client(key_str, timeout_seconds=timeout, provider=provider, profile=operation)
            if provider is None:
                return self.get_client(key_str, timeout_seconds=timeout)
            return self.get_client(key_str, timeout_seconds=timeout, provider=provider)

        client = _make_client(key_pool[0])
        is_groq_client = isinstance(client, _GroqClient) or (
            isinstance(client, _OpenRouterClient) and getattr(client.models, "_groq", False)
        )

        # Nếu client là Groq, loại bỏ các fallback model của Gemini/OpenRouter
        if is_groq_client:
            groq_models = [
                m for m in models_to_try
                if not m.startswith("gemini-") and m != "default" and not m.endswith(":free")
            ]
            if groq_models:
                models_to_try = list(dict.fromkeys(groq_models))
        # Nếu client là OpenRouter, chuẩn hóa các model Gemini sang OpenRouter model hợp lệ
        elif isinstance(client, _OpenRouterClient):
            mapped_models = []
            default_or_ocr = os.getenv("OPENROUTER_OCR_MODEL", "openrouter/free").strip()
            default_or_chat = os.getenv("OPENROUTER_CHAT_MODEL", "openrouter/free").strip()
            for m in models_to_try:
                if m.startswith("gemini-") or "flash" in m or m == "default":
                    mapped_models.append(default_or_ocr if "ocr" in operation or "prescription" in operation else default_or_chat)
                else:
                    mapped_models.append(m)
            if "ocr" in operation or "prescription" in operation:
                mapped_models.extend(["nvidia/nemotron-3.5-super-vl:free", "google/gemma-4-26b-a4b-it:free"])
            models_to_try = list(dict.fromkeys(mapped_models))

        last_error = None
        last_classification = ErrorClassification.UNKNOWN

        for current_model in models_to_try:
            rotated_on_rate_limit = False
            model_unavailable = False
            for key_idx, active_key in enumerate(key_pool):
                active_client = client if key_idx == 0 else _make_client(active_key)
                active_policy = (
                    RetryPolicy(max_attempts=1, base_delay=0.1, max_delay=0.5, jitter=False)
                    if len(key_pool) > 1 and key_idx < len(key_pool) - 1
                    else policy
                )
                try:
                    def _do_call():
                        return call_fn(active_client, current_model)

                    res = execute_with_retry(
                        _do_call,
                        policy=active_policy,
                        circuit_breaker=breaker,
                        stage=operation,
                        request_id=req_id,
                        on_retry=_on_retry
                    )

                    latency_ms = (time.time() - start_time) * 1000.0
                    metrics_collector.increment("llm_success_total")
                    metrics_collector.record_latency(f"{operation}_latency_ms", latency_ms)
                    metrics_collector.record_attempts(retries_count + 1)
                    metrics_collector.log_event(operation, req_id, latency_ms, "SUCCESS", retry_count=retries_count)

                    logger.info(
                        "[%s][REQ-%s] Hoàn tất thành công qua model %s trong %.1fms (lượt thử: %d).",
                        operation, req_id, current_model, latency_ms, retries_count + 1
                    )
                    return res

                except CircuitBreakerOpenError as cbe:
                    latency_ms = (time.time() - start_time) * 1000.0
                    metrics_collector.increment("llm_failure_total")
                    metrics_collector.increment("circuit_breaker_open_total")
                    metrics_collector.record_error("CIRCUIT_OPEN")
                    metrics_collector.log_event(operation, req_id, latency_ms, "CIRCUIT_OPEN", error_class="CIRCUIT_OPEN")
                    logger.warning("[%s][REQ-%s] Circuit Breaker '%s' đang MỞ. Từ chối thực thi.", operation, req_id, breaker.name)
                    raise LLMProviderError(
                        message=f"Circuit Breaker '{breaker.name}' đang mở.",
                        classification=ErrorClassification.CIRCUIT_OPEN,
                        operation=operation,
                        retryable=False,
                        original_exception=cbe
                    ) from None

                except Exception as e:
                    classification = classify_exception(e)
                    model_unavailable = _is_model_unavailable_error(e)
                    if classification == ErrorClassification.UNKNOWN and type(e).__name__ == "ClientError":
                        classification = ErrorClassification.BAD_REQUEST
                    last_error = e
                    last_classification = classification
                    logger.warning(
                        "[%s][REQ-%s] Lỗi khi gọi model %s (%s).",
                        operation, req_id, current_model, classification.value
                    )
                    if classification == ErrorClassification.RATE_LIMIT and key_idx < len(key_pool) - 1:
                        logger.info("[%s][REQ-%s] Key Groq #%d dính 429, xoay sang key dự phòng #%d.", operation, req_id, key_idx + 1, key_idx + 2)
                        rotated_on_rate_limit = True
                        continue
                    rotated_on_rate_limit = False
                    break

            if not rotated_on_rate_limit:
                if model_unavailable or last_classification in policy.retryable_classes:
                    continue
                break

        # Đã thử hết candidate models hoặc hết lượt retry
        latency_ms = (time.time() - start_time) * 1000.0
        metrics_collector.increment("llm_failure_total")
        metrics_collector.record_error(last_classification.value)
        metrics_collector.log_event(
            operation, req_id, latency_ms, "FAILURE",
            error_class=last_classification.value, retry_count=retries_count
        )

        raise LLMProviderError(
            message=f"Thực thi tác vụ {operation} thất bại qua toàn bộ mô hình: {last_classification.value}",
            classification=last_classification,
            operation=operation,
            retryable=False,
            original_exception=last_error
        )

    # ==========================================================================
    # 5. PUBLIC API METHODS
    # ==========================================================================

    def generate_text(
        self,
        prompt: Union[str, List[Any]],
        model: Optional[str] = None,
        candidate_models: Optional[List[str]] = None,
        system_instruction: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        operation: str = "chat_generation",
        request_id: Optional[str] = None,
        api_key: Optional[str] = None,
        profile: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[CircuitBreaker] = None
    ) -> str:
        """Sinh văn bản tự do (Plain Text / Markdown / Query Expansion)."""
        from google.genai import types

        config_kwargs: Dict[str, Any] = {}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if max_output_tokens is not None:
            config_kwargs["max_output_tokens"] = max_output_tokens

        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        def _call(client, m):
            res = client.models.generate_content(
                model=m,
                contents=prompt,
                config=config
            )
            return res.text or "" if res else ""

        return self._execute_model_call(
            call_fn=_call,
            operation=operation,
            model=model,
            candidate_models=candidate_models,
            timeout_seconds=timeout_seconds,
            retry_policy=retry_policy,
            circuit_breaker=circuit_breaker,
            request_id=request_id,
            api_key=api_key,
            profile=profile
        )

    def generate_json(
        self,
        contents: Union[str, List[Any]],
        schema: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        candidate_models: Optional[List[str]] = None,
        system_instruction: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        operation: str = "chat_generation",
        request_id: Optional[str] = None,
        api_key: Optional[str] = None,
        profile: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        provider: Optional[str] = None,
        json_mode: bool = True,
        reasoning_enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Sinh và parse cấu trúc dữ liệu JSON có bảo chứng schema."""
        config_kwargs: Dict[str, Any] = {}
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
        if schema and provider not in ("openrouter", "groq"):
            config_kwargs["response_json_schema"] = schema
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if max_output_tokens is not None:
            config_kwargs["max_output_tokens"] = max_output_tokens
        if provider == "openrouter" and reasoning_enabled is not None:
            config_kwargs["reasoning_enabled"] = reasoning_enabled

        if provider in ("openrouter", "groq"):
            # Many free/OpenAI-compatible models do not accept Gemini structured-output params.
            # The caller's prompt describes the schema; validation remains local.
            config = config_kwargs
        else:
            from google.genai import types
            config = types.GenerateContentConfig(**config_kwargs)

        def _call(client, m):
            res = client.models.generate_content(
                model=m,
                contents=contents,
                config=config
            )
            raw = res.text or "" if res else ""
            if not isinstance(raw, str):
                raw = ""
            if operation == "prescription_ocr":
                raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(r"\s*```$", "", cleaned).strip()
            match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1).strip()
            return json.loads(cleaned)

        try:
            return self._execute_model_call(
                call_fn=_call,
                operation=operation,
                model=model,
                candidate_models=candidate_models,
                timeout_seconds=timeout_seconds,
                retry_policy=retry_policy,
                circuit_breaker=circuit_breaker,
                request_id=request_id,
                api_key=api_key,
                profile=profile,
                provider=provider,
            )
        except json.JSONDecodeError as jde:
            raise LLMProviderError(
                message="Dữ liệu trả về từ Gemini không đúng định dạng JSON.",
                classification=ErrorClassification.SCHEMA_ERROR,
                operation=operation,
                retryable=False,
                original_exception=jde
            ) from None

    def generate_multimodal(
        self,
        contents: List[Any],
        config: Optional[Any] = None,
        model: Optional[str] = None,
        candidate_models: Optional[List[str]] = None,
        timeout_seconds: Optional[float] = None,
        operation: str = "prescription_ocr",
        request_id: Optional[str] = None,
        api_key: Optional[str] = None,
        profile: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[CircuitBreaker] = None
    ) -> Any:
        """Thực thi tác vụ Đa phương thức (Multimodal OCR / Vision / PDF)."""
        def _call(client, m):
            return client.models.generate_content(
                model=m,
                contents=contents,
                config=config
            )

        return self._execute_model_call(
            call_fn=_call,
            operation=operation,
            model=model,
            candidate_models=candidate_models,
            timeout_seconds=timeout_seconds,
            retry_policy=retry_policy,
            circuit_breaker=circuit_breaker,
            request_id=request_id,
            api_key=api_key,
            profile=profile
        )


# Thể hiện Singleton dùng chung toàn hệ thống
llm_provider = LLMProvider()
