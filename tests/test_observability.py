import time
import threading
import pytest
from core.observability import LocalMetricsRegistry
from core.circuit_breaker import CircuitBreaker, CircuitState
from core.retry_policy import ErrorClassification


def test_metric_increments_and_aliases():
    reg = LocalMetricsRegistry()
    reg.reset()

    reg.increment("requests_total", 5)
    reg.increment("requests_success", 4)
    reg.increment("requests_fallback", 1)
    reg.increment("emergency_short_circuit_total", 2)

    # Legacy alias test
    reg.increment("ai_429_count", 3)
    reg.increment("server_error_5xx_total", 2)

    summary = reg.get_summary()
    assert summary["requests"]["total"] == 5
    assert summary["requests"]["success"] == 4
    assert summary["requests"]["fallback"] == 1
    assert summary["requests"]["emergency_short_circuit"] == 2
    assert summary["ai"]["rate_limit_429"] == 3
    assert summary["ai"]["server_error_5xx"] == 2
    assert summary["errors"]["RATE_LIMIT"] >= 3
    assert summary["errors"]["SERVER_ERROR"] >= 2


def test_latency_rolling_window_bounded():
    reg = LocalMetricsRegistry(window_size=200)
    reg.reset()

    # Record 500 latencies (exceeding window_size 200)
    for i in range(1, 501):
        reg.record_latency("generation_latency_ms", float(i))

    summary = reg.get_summary()
    gen_lat = summary["latency"]["generation_latency_ms"]

    # Must be bounded to 200 items max
    assert gen_lat["count"] == 200
    # Values should be the last 200: 301 to 500
    assert gen_lat["min"] == 301.0
    assert gen_lat["max"] == 500.0
    # P50 should be around 400.5
    assert 395.0 <= gen_lat["p50"] <= 405.0
    # P95 should be around 490
    assert 485.0 <= gen_lat["p95"] <= 500.0


def test_thread_safety_concurrent_increments():
    reg = LocalMetricsRegistry()
    reg.reset()

    def worker():
        for _ in range(100):
            reg.increment("requests_total", 1)
            reg.record_latency("triage_latency_ms", 1.5)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    summary = reg.get_summary()
    assert summary["requests"]["total"] == 1000
    assert summary["latency"]["triage_latency_ms"]["count"] == 1000


def test_circuit_state_exposure():
    reg = LocalMetricsRegistry()
    summary = reg.get_summary()
    cb = summary["circuit_breaker"]

    assert "state" in cb
    assert cb["state"] in ("CLOSED", "OPEN", "HALF_OPEN")
    assert "failure_count" in cb
    assert "failure_threshold" in cb
    assert "cooldown_remaining" in cb


def test_zero_phi_privacy_boundary(caplog):
    import logging
    caplog.set_level(logging.INFO)
    reg = LocalMetricsRegistry()
    reg.reset()

    # Log an event
    reg.log_event(
        stage="generation",
        request_id="req-test-1234",
        latency_ms=124.5,
        status="SUCCESS",
        query_hash="sensitive_query_sha256_hash"
    )

    summary = reg.get_summary()
    summary_str = str(summary)

    # Verify no private clinical keywords or user content in summary
    for forbidden in ["patient_name", "cancer", "diabetes", "prescription", "api_key", "password"]:
        assert forbidden not in summary_str

    # Verify structured logging output format
    assert "req-test-1234" in caplog.text
    assert "stage=generation" in caplog.text
    assert "status=SUCCESS" in caplog.text


def test_metrics_disabled_behavior():
    reg = LocalMetricsRegistry()
    reg.enabled = False

    reg.increment("requests_total", 10)
    reg.record_latency("retrieval_latency_ms", 50.0)

    # When disabled, counters stay 0 and buffers stay empty
    assert reg._counters["requests_total"] == 0
    assert len(reg._latencies["retrieval_latency_ms"]) == 0


def test_reset_functionality():
    reg = LocalMetricsRegistry()
    reg.increment("requests_total", 42)
    reg.record_latency("total_request_latency_ms", 150.0)

    reg.reset()
    summary = reg.get_summary()

    assert summary["requests"]["total"] == 0
    assert summary["latency"]["total_request_latency_ms"]["count"] == 0


def test_health_and_readiness_status_computation(monkeypatch):
    monkeypatch.setattr("core.rag_service.medical_rag_service.is_available", lambda: True)
    reg = LocalMetricsRegistry()
    reg.reset()

    from core.circuit_breaker import gemini_circuit_breaker
    gemini_circuit_breaker.reset()

    # Case 1: Healthy & Ready
    reg.increment("requests_total", 10)
    reg.increment("requests_success", 10)
    summary = reg.get_summary()
    assert summary["status"] == "READY"
    assert summary["components"]["circuit_breaker"] == "CLOSED"

    # Case 2: Degraded due to high fallback rate (>20%)
    reg.reset()
    reg.increment("requests_total", 10)
    reg.increment("requests_fallback", 5)  # 50% fallback rate
    summary_degraded = reg.get_summary()
    assert summary_degraded["status"] == "DEGRADED"

    # Case 3: Degraded due to Circuit Breaker OPEN
    reg.reset()
    gemini_circuit_breaker.trip_for_test()
    try:
        summary_cb_open = reg.get_summary()
        assert summary_cb_open["status"] == "DEGRADED"
        assert summary_cb_open["components"]["circuit_breaker"] == "OPEN"
        assert summary_cb_open["components"]["gemini"] == "DEGRADED"
    finally:
        gemini_circuit_breaker.reset()


def test_full_reliability_and_observability_pipeline_integration():
    from unittest.mock import Mock
    from core.chat_service import process_clinical_chat
    from core.gemini_service import GeminiMedicalService
    from core.observability import metrics_collector
    from core.circuit_breaker import gemini_circuit_breaker

    metrics_collector.reset()
    gemini_circuit_breaker.reset()

    # 1. Normal Request
    mock_gemini = Mock(spec=GeminiMedicalService)
    mock_gemini.generate_clinical_response.return_value = {
        "answer": "Bác sĩ khuyên bạn uống nhiều nước ấm.",
        "risk_level": "Nguy cơ thấp",
        "risk_score": 10,
        "specialist": "Nội khoa",
        "symptoms": ["Ho"],
        "visual_findings": [],
        "differential_diagnosis": [],
        "is_emergency": False,
        "sources": []
    }

    res_normal = process_clinical_chat("Tôi bị ho rát cổ họng", [], gemini_service=mock_gemini)
    assert res_normal["degraded"] is False

    # 2. Emergency Request
    res_emg = process_clinical_chat("Tôi bị đau thắt ngực dữ dội toát mồ hôi khó thở", [], gemini_service=mock_gemini)
    assert res_emg["is_emergency"] is True

    # 3. Simulate Fallback on Gemini 503
    mock_gemini.generate_clinical_response.return_value = None
    res_fallback = process_clinical_chat("Tôi bị đầy bụng khó tiêu", [], gemini_service=mock_gemini)
    assert res_fallback["degraded"] is True

    # Verify metrics accurately reflect all 3 requests
    summary = metrics_collector.get_summary()
    assert summary["requests"]["total"] >= 3
    assert summary["requests"]["success"] >= 2
    assert summary["requests"]["fallback"] >= 1
    assert summary["requests"]["emergency_short_circuit"] >= 1
    assert summary["latency"]["triage_latency_ms"]["count"] >= 3
    assert summary["latency"]["total_request_latency_ms"]["count"] >= 3

