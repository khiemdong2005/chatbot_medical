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
from core.settings import settings
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
    def __init__(self, text: str, raw: Optional[Dict[str, Any]] = None, model: Optional[str] = None):
        self.text = text
        self.raw = raw or {}
        self.model = model


GROQ_FALLBACK_MODELS = ("qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b")


class _OpenRouterModels:
    """Mimics client.models.generate_content(...) via OpenAI-compatible Chat Completions API (Groq / OpenRouter)."""
    ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, timeout_seconds: float = 25.0, *, chat: bool = False, provider: str = "openrouter"):
        self._api_key = (api_key or "").strip()
        self._timeout = max(10.0, float(timeout_seconds))
        self._chat = chat
        self._provider = (provider or "openrouter").strip().lower()

    def _endpoint(self) -> str:
        if self._provider == "groq":
            base = (os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai/v1").strip().rstrip("/")
            parsed = urlsplit(base)
            if (parsed.scheme != "https" or parsed.netloc != "api.groq.com"
                    or parsed.path != "/openai/v1" or parsed.query or parsed.fragment):
                raise _OpenRouterHTTPError(400, "Invalid Groq base URL")
            return f"{base}/chat/completions"

        base = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip().rstrip("/")
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
                if "text" in item:
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
            "User-Agent": "MediMind-Clinical-AI/2.5",
        }
        if self._provider != "groq":
            headers["HTTP-Referer"] = "https://medimind.local"
            headers["X-Title"] = "MediMind Clinical AI"
        provider_label = "Groq" if self._provider == "groq" else "OpenRouter"
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
        if max_tokens is not None and int(max_tokens) >= 2048:
            payload["max_tokens"] = int(max_tokens)
        if self._provider == "groq":
            if want_json:
                payload["response_format"] = {"type": "json_object"}
        elif self._chat:
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
        if self._provider != "groq":
            if isinstance(reasoning_enabled, bool):
                payload["reasoning"] = {"enabled": reasoning_enabled}

        def _send_with_compat(req_payload: Dict[str, Any]) -> Dict[str, Any]:
            try:
                return self._post_completion(req_payload)
            except _OpenRouterHTTPError as err:
                # Preserve the legacy compatibility retry for workflows outside strict OpenRouter chat.
                if (self._provider == "groq" or not self._chat) and err.status_code == 400 and "response_format" in req_payload:
                    req_payload.pop("response_format", None)
                    return self._post_completion(req_payload)
                raise

        try:
            resp_json = _send_with_compat(payload)
        except _OpenRouterHTTPError as e:
            if self._provider == "groq" and e.status_code in (404, 413, 429):
                last_err = e
                resp_json = None
                for fallback_model in GROQ_FALLBACK_MODELS:
                    if fallback_model == payload.get("model"):
                        continue
                    payload["model"] = fallback_model
                    try:
                        resp_json = _send_with_compat(payload)
                        break
                    except _OpenRouterHTTPError as fb_err:
                        last_err = fb_err
                        if fb_err.status_code not in (404, 413, 429):
                            raise
                if resp_json is None:
                    raise last_err
            else:
                raise

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
        return _OpenRouterResponse(text=content, raw=resp_json, model=payload.get("model"))


class _OpenRouterClient:
    """Drop-in replacement for genai.Client exposing .models.generate_content() (Groq / OpenRouter)."""
    def __init__(self, api_key: str, timeout_seconds: float = 25.0, *, chat: bool = False, provider: str = "openrouter"):
        self.provider = (provider or "openrouter").strip().lower()
        self.models = _OpenRouterModels(api_key=api_key, timeout_seconds=timeout_seconds, chat=chat, provider=self.provider)


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

    # ==========================================================================
    # 1. API KEY RESOLUTION & VALIDATION
    # ==========================================================================

    def is_groq_active(self) -> bool:
        """Kiểm tra xem hệ thống có đang cấu hình chạy Groq API hay không."""
        provider = os.getenv("AI_PROVIDER", "").strip().lower()
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if provider == "groq":
            return bool(groq_key)
        if not provider and groq_key:
            return True
        return False

    def is_openrouter_active(self) -> bool:
        """Kiểm tra xem hệ thống có đang cấu hình chạy OpenRouter hay không."""
        if self.is_groq_active():
            return False
        provider = os.getenv("AI_PROVIDER", "").strip().lower()
        openrouter_key = (
            os.getenv("OPENROUTER_API_KEY", "").strip()
            or os.getenv("OPENROUTER_CHAT_API_KEY", "").strip()
            or os.getenv("OPENROUTER_OCR_API_KEY", "").strip()
            or os.getenv("OPENROUTER_NUTRITION_API_KEY", "").strip()
        )
        return provider == "openrouter" and bool(openrouter_key)

    def resolve_api_key(
        self,
        profile: Optional[str] = None,
        explicit_key: Optional[str] = None
    ) -> str:
        """
        Xác định API Key theo Profile một cách an toàn:
        - Nếu có explicit_key -> ưu tiên số 1.
        - Nếu AI_PROVIDER=groq (hoặc mặc định có GROQ_API_KEY) -> dùng GROQ_API_KEY.
        - Nếu AI_PROVIDER=openrouter -> ưu tiên key OpenRouter theo profile rồi tới OPENROUTER_API_KEY.
        - Profile 'nutrition' -> GEMINI_NUTRITION_API_KEY -> GEMINI_API_KEY.
        - Profile 'chat' -> GEMINI_CHAT_API_KEY -> GEMINI_API_KEY.
        - Mặc định -> GEMINI_API_KEY -> GOOGLE_API_KEY.
        """
        if explicit_key and isinstance(explicit_key, str) and explicit_key.strip():
            return explicit_key.strip()

        if self.is_groq_active():
            return os.getenv("GROQ_API_KEY", "").strip()

        prof = (profile or "").lower()
        if self.is_openrouter_active():
            if prof in ("chat", "chat_generation"):
                k = os.getenv("OPENROUTER_CHAT_API_KEY", "").strip()
                if k:
                    return k
            elif prof in ("ocr", "prescription", "interpretation"):
                k = os.getenv("OPENROUTER_OCR_API_KEY", "").strip()
                if k:
                    return k
            elif prof in ("nutrition", "nutrition_ai"):
                k = os.getenv("OPENROUTER_NUTRITION_API_KEY", "").strip()
                if k:
                    return k
            return (
                os.getenv("OPENROUTER_API_KEY", "").strip()
                or os.getenv("OPENROUTER_CHAT_API_KEY", "").strip()
                or os.getenv("OPENROUTER_OCR_API_KEY", "").strip()
                or os.getenv("OPENROUTER_NUTRITION_API_KEY", "").strip()
            )
        if prof in ("nutrition", "nutrition_ai"):
            key = os.getenv("GEMINI_NUTRITION_API_KEY") or settings.gemini.nutrition_api_key or ""
            if key:
                return key.strip()

        if prof in ("chat", "chat_generation"):
            key = os.getenv("GEMINI_CHAT_API_KEY") or settings.gemini.chat_api_key or ""
            if key:
                return key.strip()

        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or settings.gemini.api_key or ""
        return key.strip()

    def is_configured(
        self,
        profile: Optional[str] = None,
        explicit_key: Optional[str] = None
    ) -> bool:
        """Kiểm tra tính hợp lệ của API Key mà không thực hiện kết nối mạng."""
        key = self.resolve_api_key(profile=profile, explicit_key=explicit_key)
        return bool(
            key
            and not key.startswith("YOUR_")
            and key != "your_google_gemini_api_key_here"
            and len(key) > 10
        )

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
        Khởi tạo hoặc tái sử dụng AI Client (OpenRouter hoặc Gemini) một cách lười (Lazy) và an toàn đa luồng.
        Không thực hiện bất kỳ lệnh gọi mạng nào lúc khởi tạo.
        """
        key_clean = (api_key or "").strip()
        env_groq_key = os.getenv("GROQ_API_KEY", "").strip()
        use_groq = provider == "groq" or (
            provider is None and (
                key_clean.startswith("gsk_")
                or (self.is_groq_active() and bool(env_groq_key) and key_clean == env_groq_key)
            )
        )
        use_openrouter = (not use_groq) and (
            provider == "openrouter" or (
                provider is None and key_clean.startswith("sk-or-")
            )
        )
        chat = (use_groq or use_openrouter) and (profile or "").lower() in ("chat", "chat_generation")
        timeout_ms = max(10000, int(timeout_seconds * 1000))
        prefix = "gq" if use_groq else ("or" if use_openrouter else "gm")
        cache_key = f"{prefix}_{hash(key_clean)}_{timeout_ms}"
        if chat:
            cache_key += "_chat"

        with self._lock:
            if cache_key in self._clients:
                return self._clients[cache_key]

            if use_groq:
                client = _OpenRouterClient(api_key=key_clean, timeout_seconds=timeout_seconds, chat=chat, provider="groq")
                self._clients[cache_key] = client
                return client

            if use_openrouter:
                client = _OpenRouterClient(api_key=key_clean, timeout_seconds=timeout_seconds, chat=chat, provider="openrouter")
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
            val = os.getenv("OCR_AI_TIMEOUT_SECONDS")
            return float(val) if val else settings.gemini.timeout_ocr
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

    def get_default_model(self, operation: str) -> str:
        """Lấy model mặc định cho từng tác vụ."""
        op = operation.lower()
        if self.is_groq_active():
            default_groq = (os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
            if "chat" in op:
                return (os.getenv("GROQ_CHAT_MODEL") or default_groq).strip()
            if "expansion" in op:
                return (os.getenv("GROQ_EXPANSION_MODEL") or default_groq).strip()
            if "nutrition" in op:
                return (os.getenv("GROQ_NUTRITION_MODEL") or default_groq).strip()
            if "ocr" in op or "prescription" in op:
                return (os.getenv("GROQ_OCR_MODEL") or default_groq).strip()
            if "interpretation" in op:
                return (os.getenv("GROQ_INTERPRETATION_MODEL") or default_groq).strip()
            return default_groq

        if self.is_openrouter_active():
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

        valid_key = bool(effective_key and not effective_key.startswith("YOUR_")
                         and effective_key != "your_google_gemini_api_key_here"
                         and len(effective_key) > 10)
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

        if provider is None:
            client = self.get_client(effective_key, timeout_seconds=timeout)
        else:
            client = self.get_client(effective_key, timeout_seconds=timeout, provider=provider)

        last_error = None
        last_classification = ErrorClassification.UNKNOWN

        for current_model in models_to_try:
            try:
                def _do_call():
                    return call_fn(client, current_model)

                res = execute_with_retry(
                    _do_call,
                    policy=policy,
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
                # Đổi model chỉ khi model hiện tại không tồn tại hoặc lỗi tạm thời.
                # Lỗi tài khoản, payload, schema và ClientError UNKNOWN sẽ lặp lại
                # với mọi model nên phải trả về OCR cục bộ ngay.
                if model_unavailable or classification in policy.retryable_classes:
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
            # Many OpenAI-compatible endpoints do not accept Gemini SDK structured-output parameters.
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
            cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()
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
