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
import logging
import threading
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

    def resolve_api_key(
        self,
        profile: Optional[str] = None,
        explicit_key: Optional[str] = None
    ) -> str:
        """
        Xác định API Key theo Profile một cách an toàn:
        - Nếu có explicit_key -> ưu tiên số 1.
        - Profile 'nutrition' -> GEMINI_NUTRITION_API_KEY -> GEMINI_API_KEY.
        - Profile 'chat' -> GEMINI_CHAT_API_KEY -> GEMINI_API_KEY.
        - Mặc định -> GEMINI_API_KEY -> GOOGLE_API_KEY.
        """
        if explicit_key and isinstance(explicit_key, str) and explicit_key.strip():
            return explicit_key.strip()

        prof = (profile or "").lower()
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
        timeout_seconds: float = 15.0
    ) -> Any:
        """
        Khởi tạo hoặc tái sử dụng Gemini Client một cách lười (Lazy) và an toàn đa luồng.
        Không thực hiện bất kỳ lệnh gọi mạng nào lúc khởi tạo.
        """
        timeout_ms = max(10000, int(timeout_seconds * 1000))
        cache_key = f"{hash(api_key)}_{timeout_ms}"

        with self._lock:
            if cache_key in self._clients:
                return self._clients[cache_key]

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
        profile: Optional[str] = None
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
        effective_key = self.resolve_api_key(profile=profile or operation, explicit_key=api_key)

        if not self.is_configured(profile=profile or operation, explicit_key=effective_key):
            metrics_collector.increment("llm_failure_total")
            metrics_collector.record_error("AUTH_ERROR")
            metrics_collector.log_event(operation, req_id, 0.0, "FALLBACK", error_class="AUTH_ERROR")
            logger.info("[%s][REQ-%s] GEMINI_API_KEY chưa cấu hình hoặc không hợp lệ.", operation, req_id)
            raise LLMProviderError(
                message="Khóa xác thực Gemini API chưa được cấu hình.",
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

        client = self.get_client(effective_key, timeout_seconds=timeout)

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
                last_error = e
                last_classification = classification
                logger.warning(
                    "[%s][REQ-%s] Lỗi khi gọi model %s (%s).",
                    operation, req_id, current_model, classification.value
                )
                # Nếu còn candidate models khác và lỗi không phải do Circuit Open, thử model tiếp theo
                continue

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
        circuit_breaker: Optional[CircuitBreaker] = None
    ) -> Dict[str, Any]:
        """Sinh và parse cấu trúc dữ liệu JSON có bảo chứng schema."""
        from google.genai import types

        config_kwargs: Dict[str, Any] = {
            "response_mime_type": "application/json"
        }
        if schema:
            config_kwargs["response_json_schema"] = schema
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if max_output_tokens is not None:
            config_kwargs["max_output_tokens"] = max_output_tokens

        config = types.GenerateContentConfig(**config_kwargs)

        def _call(client, m):
            res = client.models.generate_content(
                model=m,
                contents=contents,
                config=config
            )
            raw = res.text or "" if res else ""
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
                profile=profile
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
