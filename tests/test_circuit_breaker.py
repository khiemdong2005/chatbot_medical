"""
================================================================================
Unit tests for core/circuit_breaker.py
================================================================================
"""

import time
import pytest
from core.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerOpenError
from core.retry_policy import ErrorClassification, RetryPolicy, execute_with_retry


def test_circuit_breaker_initial_state():
    cb = CircuitBreaker(name="test_cb", failure_threshold=3, cooldown_seconds=0.1)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True


def test_circuit_breaker_trips_to_open_on_threshold():
    cb = CircuitBreaker(name="test_cb", failure_threshold=3, cooldown_seconds=0.1)

    # 1st failure
    cb.record_failure(ErrorClassification.SERVER_ERROR)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # 2nd failure
    cb.record_failure(ErrorClassification.RATE_LIMIT)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # 3rd failure -> Trips to OPEN
    cb.record_failure(ErrorClassification.TIMEOUT)
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False


def test_circuit_breaker_rejects_immediately_when_open():
    cb = CircuitBreaker(name="test_cb", failure_threshold=2, cooldown_seconds=10.0)
    cb.record_failure(ErrorClassification.SERVER_ERROR)
    cb.record_failure(ErrorClassification.SERVER_ERROR)
    assert cb.state == CircuitState.OPEN

    call_count = 0

    def mock_op():
        nonlocal call_count
        call_count += 1
        return "success"

    policy = RetryPolicy(max_attempts=3, base_delay=0.01)

    with pytest.raises(CircuitBreakerOpenError):
        execute_with_retry(mock_op, policy=policy, circuit_breaker=cb, stage="test_call")

    assert call_count == 0  # Provider was NEVER called! Fail fast 0ms.


def test_circuit_breaker_half_open_recovery():
    """After cooldown, transitions to HALF_OPEN. Trial request success -> CLOSED."""
    cb = CircuitBreaker(name="test_cb", failure_threshold=2, cooldown_seconds=0.05)
    cb.record_failure(ErrorClassification.SERVER_ERROR)
    cb.record_failure(ErrorClassification.SERVER_ERROR)
    assert cb.state == CircuitState.OPEN

    # Wait for cooldown to expire (giving sufficient margin for Windows 15.6ms timer resolution)
    time.sleep(0.1)

    # Should transition to HALF_OPEN and allow trial request
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Record success -> Circuit fully recovers to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True


def test_circuit_breaker_half_open_failure_reopens():
    """Trial request in HALF_OPEN fails -> immediately reopens for another cooldown."""
    cb = CircuitBreaker(name="test_cb", failure_threshold=2, cooldown_seconds=0.05)
    cb.record_failure(ErrorClassification.SERVER_ERROR)
    cb.record_failure(ErrorClassification.SERVER_ERROR)
    assert cb.state == CircuitState.OPEN

    time.sleep(0.1)
    assert cb.can_execute() is True  # Enters HALF_OPEN

    # Trial request fails
    cb.record_failure(ErrorClassification.SERVER_ERROR)
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False


def test_non_transient_errors_do_not_trip_circuit():
    """AUTH_ERROR (401) and BAD_REQUEST (400) should NOT trip circuit breaker."""
    cb = CircuitBreaker(name="test_cb", failure_threshold=3, cooldown_seconds=1.0)

    for _ in range(5):
        cb.record_failure(ErrorClassification.AUTH_ERROR)
        cb.record_failure(ErrorClassification.BAD_REQUEST)

    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True


def test_circuit_breaker_reset():
    cb = CircuitBreaker(name="test_cb", failure_threshold=1, cooldown_seconds=10.0)
    cb.record_failure(ErrorClassification.SERVER_ERROR)
    assert cb.state == CircuitState.OPEN

    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

