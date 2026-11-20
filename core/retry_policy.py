"""
================================================================================
🩺 MEDIMIND AI RETRY POLICY & ERROR CLASSIFICATION
================================================================================
Mục đích:
  - Cung cấp tiện ích retry tập trung (Single Responsibility) cho toàn bộ
    các lệnh gọi Google Gemini AI / Cloud Provider.
  - Phân loại lỗi chuẩn hóa (ErrorClassification):
      + RETRYABLE: 429 Rate Limit, 500/502/503/504 Server Error, Network Timeout,
                   Connection Reset.
      + NON-RETRYABLE: 400 Bad Request, 401 Auth Error, 403 Forbidden,
                       Schema Decoding Error, Client Deterministic Bugs.
  - Exponential Backoff có Jitter và tôn trọng header 'Retry-After'.
  - Giới hạn số lần thử và thời gian chờ tối đa (No Infinite Loops).
================================================================================
"""

import re
import time
import random
import logging
from dataclasses import dataclass, field
from typing import Callable, Any, Optional, Set

from core.ai_types import ErrorClassification
from core.circuit_breaker import CircuitBreakerOpenError

logger = logging.getLogger("RetryPolicy")


def redact_provider_error(exc: Optional[Exception]) -> str:
    """Format an upstream HTTP/AI error with safe status_code only (Zero-PHI / Zero-Secret)."""
    if exc is None:
        return ""
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None) or getattr(exc, "http_status", None)
    name = type(exc).__name__
    if isinstance(code, int):
        return f"{name} status={code}"
    return name


def classify_exception(exc: Exception) -> ErrorClassification:
    """
    Phân loại exception thành ErrorClassification chuẩn hóa mà không parse string tùy tiện.
    Kiểm tra thuộc tính HTTP status code trước, sau đó đối chiếu type và message.
    """
    if exc is None:
        return ErrorClassification.UNKNOWN

    exc_type_name = type(exc).__name__
    if exc_type_name == "CircuitBreakerOpenError":
        return ErrorClassification.CIRCUIT_OPEN

    # 1. Kiểm tra mã lỗi số (HTTP status_code / code)
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None) or getattr(exc, "http_status", None)
    if isinstance(code, int):
        if code in (401, 402, 403):
            return ErrorClassification.AUTH_ERROR
        if code == 429:
            return ErrorClassification.RATE_LIMIT
        if code == 408:
            return ErrorClassification.TIMEOUT
        if code in (400, 404, 422):
            return ErrorClassification.BAD_REQUEST
        if code in (500, 502, 503, 504):
            return ErrorClassification.SERVER_ERROR

    # 2. Kiểm tra theo Exception Type
    if isinstance(exc, (TimeoutError,)):
        return ErrorClassification.TIMEOUT
    if isinstance(exc, (ConnectionError, ConnectionResetError, ConnectionRefusedError)):
        return ErrorClassification.NETWORK_ERROR

    # 3. Phân tích tên lớp và thông báo lỗi đặc trưng của Google GenAI / HTTP Client
    msg = str(exc).upper()

    # Auth errors
    if any(k in msg for k in ("UNAUTHENTICATED", "ACCESS_TOKEN_TYPE_UNSUPPORTED", "API_KEY_INVALID", "PERMISSION_DENIED")):
        return ErrorClassification.AUTH_ERROR
    if "401" in msg and "UNAUTHENTICATED" in msg:
        return ErrorClassification.AUTH_ERROR
    if "403" in msg and ("FORBIDDEN" in msg or "PERMISSION" in msg):
        return ErrorClassification.AUTH_ERROR

    # Rate limit
    if any(k in msg for k in ("429", "RESOURCE_EXHAUSTED", "RATE_LIMIT", "QUOTA_EXCEEDED", "TOO MANY REQUESTS")):
        return ErrorClassification.RATE_LIMIT

    # Server errors
    if any(k in msg for k in ("503", "500", "502", "504", "UNAVAILABLE", "INTERNAL_SERVER_ERROR", "BAD_GATEWAY")):
        return ErrorClassification.SERVER_ERROR
    if "SERVERERROR" in exc_type_name.upper():
        return ErrorClassification.SERVER_ERROR

    # Timeout
    if any(k in msg for k in ("DEADLINE_EXCEEDED", "TIMED OUT", "TIMEOUT", "DEADLINE EXCEEDED")):
        return ErrorClassification.TIMEOUT

    # Network
    if any(k in msg for k in ("CONNECTION REFUSED", "CONNECTION RESET", "REMOTE DISCONNECTED", "FAILED TO ESTABLISH")):
        return ErrorClassification.NETWORK_ERROR

    # Bad request / Invalid argument
    if any(k in msg for k in ("INVALID_ARGUMENT", "400 BAD REQUEST", "BAD_REQUEST")):
        return ErrorClassification.BAD_REQUEST

    # Schema error
    if "JSONDECODEERROR" in exc_type_name.upper() or "INVALID JSON" in msg:
        return ErrorClassification.SCHEMA_ERROR

    return ErrorClassification.UNKNOWN


def extract_retry_after(exc: Exception) -> Optional[float]:
    """
    Trích xuất gợi ý Retry-After từ response header hoặc error message nếu có.
    """
    if exc is None:
        return None

    # Kiểm tra response headers
    response = getattr(exc, "response", None)
    if response and hasattr(response, "headers") and response.headers:
        retry_header = response.headers.get("retry-after") or response.headers.get("Retry-After")
        if retry_header:
            try:
                return max(0.0, float(retry_header))
            except (ValueError, TypeError):
                pass

    # Kiểm tra error message pattern: e.g. "retry after 2.5s" or "try again in 3 seconds"
    msg = str(exc).lower()
    match = re.search(r"(?:retry after|try again in|wait)\s+([0-9]+(?:\.[0-9]+)?)\s*(?:s|sec|seconds)?", msg)
    if match:
        try:
            return max(0.0, float(match.group(1)))
        except (ValueError, TypeError):
            pass

    return None


@dataclass
class RetryPolicy:
    """Chính sách Retry với Exponential Backoff & Jitter."""
    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 4.0
    jitter: bool = True
    retryable_classes: Set[ErrorClassification] = field(default_factory=lambda: {
        ErrorClassification.RATE_LIMIT,
        ErrorClassification.SERVER_ERROR,
        ErrorClassification.TIMEOUT,
        ErrorClassification.NETWORK_ERROR
    })

    def calculate_delay(self, attempt: int, retry_after: Optional[float] = None) -> float:
        """
        Tính thời gian chờ:
        - Nếu có retry_after hợp lệ: ưu tiên dùng retry_after (giới hạn bởi max_delay).
        - Ngược lại: exponential backoff = base_delay * (2 ** (attempt - 1)).
        - Thêm jitter nhỏ (tối đa 10% delay) để tránh thundering herd.
        """
        if retry_after is not None and retry_after > 0:
            delay = min(self.max_delay, retry_after)
        else:
            delay = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))

        if self.jitter and delay > 0:
            jitter_amount = random.uniform(0.0, min(0.25, delay * 0.1))
            delay = min(self.max_delay, delay + jitter_amount)

        return delay


class MaxRetriesExceededError(Exception):
    """Ngoại lệ khi đã dùng hết số lần thử lại cho phép."""
    def __init__(self, last_exception: Exception, classification: ErrorClassification, attempts: int):
        self.last_exception = last_exception
        self.classification = classification
        self.attempts = attempts
        super().__init__(f"Max retries ({attempts}) exceeded for {classification.value}: {last_exception}")


def execute_with_retry(
    operation: Callable[[], Any],
    policy: Optional[RetryPolicy] = None,
    circuit_breaker: Optional[Any] = None,
    stage: str = "ai_operation",
    request_id: Optional[str] = None,
    on_retry: Optional[Callable[[int, float, Exception, ErrorClassification], None]] = None
) -> Any:
    """
    Thực thi hàm operation() với cơ chế Retry Policy và Circuit Breaker dùng chung.
    
    Quy trình:
      1. Kiểm tra Circuit Breaker (nếu có). Nếu OPEN -> raise CircuitBreakerOpenError.
      2. Gọi operation().
      3. Nếu thành công -> báo circuit_breaker.record_success() -> trả kết quả.
      4. Nếu lỗi -> classify_exception(exc).
      5. Nếu lỗi KHÔNG nằm trong retryable_classes hoặc hết số lần thử ->
         báo circuit_breaker.record_failure(classification) -> re-raise.
      6. Nếu lỗi RETRYABLE và còn lượt thử ->
         tính delay (exponential backoff / retry-after) -> chờ -> thử lại.
    """
    policy = policy or RetryPolicy()
    req_tag = f"[REQ-{request_id}]" if request_id else "[RETRY]"

    # 1. Kiểm tra Circuit Breaker trước khi thực thi
    if circuit_breaker is not None and not circuit_breaker.can_execute():
        logger.warning("%s Circuit breaker '%s' is OPEN. Fast-failing stage '%s'.",
                       req_tag, circuit_breaker.name, stage)
        raise CircuitBreakerOpenError(f"Circuit breaker '{circuit_breaker.name}' is OPEN")

    last_exception = None
    last_classification = ErrorClassification.UNKNOWN

    for attempt in range(1, policy.max_attempts + 1):
        try:
            result = operation()
            if circuit_breaker is not None:
                circuit_breaker.record_success()
            return result
        except Exception as exc:
            last_exception = exc
            last_classification = classify_exception(exc)

            # Ghi nhận thất bại vào Circuit Breaker nếu là lỗi transient
            if circuit_breaker is not None:
                circuit_breaker.record_failure(last_classification)

            # Kiểm tra xem lỗi có được phép thử lại không
            err_detail = redact_provider_error(exc)
            if last_classification not in policy.retryable_classes:
                logger.warning(
                    "%s Stage '%s' encountered non-retryable error %s (%s). Failing immediately.",
                    req_tag, stage, last_classification.value, err_detail
                )
                raise exc

            # Kiểm tra nếu đã hết lượt thử
            if attempt >= policy.max_attempts:
                logger.warning(
                    "%s Stage '%s' exhausted max attempts (%d/%d) on %s (%s).",
                    req_tag, stage, attempt, policy.max_attempts,
                    last_classification.value, err_detail
                )
                raise exc

            # Tính toán thời gian backoff
            retry_after = extract_retry_after(exc)
            delay = policy.calculate_delay(attempt, retry_after)

            logger.info(
                "%s Stage '%s' attempt %d/%d failed with %s (%s). Retrying in %.2fs...",
                req_tag, stage, attempt, policy.max_attempts,
                last_classification.value, err_detail, delay
            )

            if on_retry is not None:
                try:
                    on_retry(attempt, delay, exc, last_classification)
                except Exception:
                    pass

            time.sleep(delay)

    raise last_exception or RuntimeError(f"Retry loop failed without exception for {stage}")

