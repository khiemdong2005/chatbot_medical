"""
================================================================================
Unit tests for core/retry_policy.py
================================================================================
"""

import time
import pytest
from unittest.mock import Mock

from core.retry_policy import (
    RetryPolicy,
    ErrorClassification,
    classify_exception,
    extract_retry_after,
    execute_with_retry,
    MaxRetriesExceededError
)


class DummyHTTPError(Exception):
    def __init__(self, status_code: int, message: str, headers: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = status_code
        self.response = Mock(headers=headers or {})


def test_classify_exception_status_codes():
    assert classify_exception(DummyHTTPError(401, "Unauthorized")) == ErrorClassification.AUTH_ERROR
    assert classify_exception(DummyHTTPError(403, "Forbidden")) == ErrorClassification.AUTH_ERROR
    assert classify_exception(DummyHTTPError(429, "Too Many Requests")) == ErrorClassification.RATE_LIMIT
    assert classify_exception(DummyHTTPError(400, "Bad Request")) == ErrorClassification.BAD_REQUEST
    assert classify_exception(DummyHTTPError(500, "Internal Server Error")) == ErrorClassification.SERVER_ERROR
    assert classify_exception(DummyHTTPError(503, "Service Unavailable")) == ErrorClassification.SERVER_ERROR
    assert classify_exception(DummyHTTPError(504, "Gateway Timeout")) == ErrorClassification.SERVER_ERROR


def test_classify_exception_types():
    assert classify_exception(TimeoutError("Operation timed out")) == ErrorClassification.TIMEOUT
    assert classify_exception(ConnectionError("Connection refused")) == ErrorClassification.NETWORK_ERROR
    assert classify_exception(ConnectionResetError("Peer reset connection")) == ErrorClassification.NETWORK_ERROR


def test_classify_exception_messages():
    assert classify_exception(Exception("ACCESS_TOKEN_TYPE_UNSUPPORTED")) == ErrorClassification.AUTH_ERROR
    assert classify_exception(Exception("429 RESOURCE_EXHAUSTED")) == ErrorClassification.RATE_LIMIT
    assert classify_exception(Exception("503 UNAVAILABLE")) == ErrorClassification.SERVER_ERROR
    assert classify_exception(Exception("DEADLINE_EXCEEDED")) == ErrorClassification.TIMEOUT


def test_extract_retry_after_header():
    exc = DummyHTTPError(429, "Rate limit exceeded", headers={"Retry-After": "2.5"})
    assert extract_retry_after(exc) == 2.5


def test_extract_retry_after_message():
    exc = Exception("Rate limit exceeded. Please retry after 1.5s")
    assert extract_retry_after(exc) == 1.5

    exc2 = Exception("Quota exceeded, try again in 3 seconds")
    assert extract_retry_after(exc2) == 3.0


def test_calculate_delay_exponential_and_retry_after():
    policy = RetryPolicy(base_delay=0.5, max_delay=4.0, jitter=False)
    # Attempt 1: 0.5 * 2^0 = 0.5
    assert policy.calculate_delay(1) == 0.5
    # Attempt 2: 0.5 * 2^1 = 1.0
    assert policy.calculate_delay(2) == 1.0
    # Attempt 3: 0.5 * 2^2 = 2.0
    assert policy.calculate_delay(3) == 2.0
    # Attempt 4: 0.5 * 2^3 = 4.0 (capped at max_delay)
    assert policy.calculate_delay(4) == 4.0

    # With explicit retry_after
    assert policy.calculate_delay(1, retry_after=1.2) == 1.2
    assert policy.calculate_delay(1, retry_after=10.0) == 4.0  # capped by max_delay


def test_execute_with_retry_success_after_transient_failures():
    """Simulate: 503 -> 503 -> Success (3 attempts, final success)."""
    call_count = 0

    def mock_op():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise DummyHTTPError(503, "Service Unavailable")
        return {"status": "ok"}

    policy = RetryPolicy(max_attempts=3, base_delay=0.01, max_delay=0.05, jitter=False)
    retries = []

    def on_retry(attempt, delay, exc, classification):
        retries.append((attempt, classification))

    result = execute_with_retry(
        mock_op,
        policy=policy,
        stage="test_op",
        on_retry=on_retry
    )

    assert result == {"status": "ok"}
    assert call_count == 3
    assert len(retries) == 2
    assert retries[0][1] == ErrorClassification.SERVER_ERROR
    assert retries[1][1] == ErrorClassification.SERVER_ERROR


def test_execute_with_retry_non_retryable_error():
    """Simulate: 401 Unauthorized -> Should fail immediately in 1 attempt."""
    call_count = 0

    def mock_op():
        nonlocal call_count
        call_count += 1
        raise DummyHTTPError(401, "UNAUTHENTICATED")

    policy = RetryPolicy(max_attempts=3, base_delay=0.01, max_delay=0.05, jitter=False)

    with pytest.raises(DummyHTTPError) as exc_info:
        execute_with_retry(mock_op, policy=policy, stage="test_op")

    assert exc_info.value.status_code == 401
    assert call_count == 1  # Exactly 1 attempt, NO retry


def test_execute_with_retry_429_rate_limit():
    """Simulate: 429 Rate limit with Retry-After header -> retry succeeds."""
    call_count = 0

    def mock_op():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise DummyHTTPError(429, "Too Many Requests", headers={"Retry-After": "0.01"})
        return "recovered"

    policy = RetryPolicy(max_attempts=3, base_delay=0.01, max_delay=0.05, jitter=False)
    result = execute_with_retry(mock_op, policy=policy, stage="test_op")

    assert result == "recovered"
    assert call_count == 2


def test_execute_with_retry_exhaustion():
    """Simulate: 500 continuously -> exhausts max_attempts and raises."""
    call_count = 0

    def mock_op():
        nonlocal call_count
        call_count += 1
        raise DummyHTTPError(500, "Internal Server Error")

    policy = RetryPolicy(max_attempts=3, base_delay=0.01, max_delay=0.05, jitter=False)

    with pytest.raises(DummyHTTPError):
        execute_with_retry(mock_op, policy=policy, stage="test_op")

    assert call_count == 3

