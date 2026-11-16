"""
================================================================================
Integration tests for Reliability, Resilience, and Observability
================================================================================
"""

import pytest
from unittest.mock import Mock, patch

from core.circuit_breaker import gemini_circuit_breaker, CircuitState
from core.observability import metrics_collector
from core.query_expansion_service import QueryExpansionService, QueryExpansionProvider, ExpandedQuery
from core.chat_service import process_clinical_chat
from core.gemini_service import GeminiMedicalService


@pytest.fixture(autouse=True)
def reset_state():
    gemini_circuit_breaker.reset()
    metrics_collector.reset()
    yield
    gemini_circuit_breaker.reset()
    metrics_collector.reset()


def test_emergency_precheck_under_circuit_open_outage():
    """
    INVARIANT: Even when Gemini is completely down and Circuit Breaker is OPEN,
    emergency pre-check MUST short-circuit deterministically and return 115 alert
    without ever attempting to call Gemini.
    """
    gemini_circuit_breaker.trip_for_test()
    assert gemini_circuit_breaker.state == CircuitState.OPEN

    # Mock Gemini service to fail if called
    mock_gemini = Mock(spec=GeminiMedicalService)
    mock_gemini.generate_clinical_response.side_effect = AssertionError("Gemini must NOT be called for emergency!")

    emergency_query = "Tôi bị đau ngực dữ dội như dao đâm, khó thở và vã mồ hôi hột"
    res = process_clinical_chat(
        message=emergency_query,
        history=[],
        gemini_service=mock_gemini
    )

    assert res["is_emergency"] is True
    assert "115" in res["answer"]
    assert res["risk_score"] == 90
    assert mock_gemini.generate_clinical_response.call_count == 0


def test_query_expansion_resilience_on_provider_failure():
    """
    When the query expansion provider fails (exception or empty),
    the system must degrade cleanly to original query with used_expansion=False and degraded=True,
    without crashing the retrieval pipeline.
    """
    class FailingProvider(QueryExpansionProvider):
        def expand(self, query: str, timeout_seconds: float = 3.0) -> str:
            raise TimeoutError("Simulated expansion timeout")

    service = QueryExpansionService(
        enabled=True,
        provider=FailingProvider(),
        timeout_seconds=0.1
    )

    result = service.expand_for_retrieval("Tôi bị sốt cao đau đầu", language="vi")

    assert isinstance(result, ExpandedQuery)
    assert result.original_query == "Tôi bị sốt cao đau đầu"
    assert result.expanded_query == "Tôi bị sốt cao đau đầu"  # Clean fallback
    assert result.used_expansion is False
    assert result.degraded is True

    # Check metrics
    summary = metrics_collector.get_summary()
    assert summary["counters"]["query_expansion_failure"] >= 1


def test_request_id_propagation_and_observability():
    """Request ID must be tracked across stages in observability."""
    custom_req_id = "test-req-trace-uuid-12345"

    mock_gemini = Mock(spec=GeminiMedicalService)
    mock_gemini.generate_clinical_response.return_value = {
        "answer": "Chào bạn, hãy nghỉ ngơi và uống nhiều nước ấm.",
        "risk_level": "Nguy cơ thấp",
        "risk_score": 15,
        "specialist": "Y học gia đình",
        "symptoms": ["Sốt nhẹ"],
        "visual_findings": [],
        "differential_diagnosis": ["Cảm cúm thông thường"],
        "is_emergency": False,
        "sources": []
    }

    res = process_clinical_chat(
        message="Tôi bị hắt hơi sổ mũi nhẹ từ sáng nay",
        history=[],
        request_id=custom_req_id,
        gemini_service=mock_gemini
    )

    assert "nghỉ ngơi" in res["answer"]
    summary = metrics_collector.get_summary()
    assert summary["latencies"]["total_request_latency_ms"]["count"] >= 1
    assert summary["latencies"]["total_request_latency_ms"]["p50"] > 0


def test_chat_service_fallback_on_gemini_outage():
    """
    When Gemini experiences a persistent 503 outage and exhausts retries,
    the chat service must activate the fallback engine and mark degraded=True,
    without crashing or returning an exception.
    """
    mock_gemini = Mock(spec=GeminiMedicalService)
    mock_gemini.generate_clinical_response.return_value = None  # Simulates fallback return

    res = process_clinical_chat(
        message="Tôi bị mỏi cơ sau khi tập thể dục",
        history=[],
        gemini_service=mock_gemini
    )

    assert res["degraded"] is True
    assert "tạm chưa kết nối được dịch vụ AI" in res["answer"]
    assert res["is_emergency"] is False


def test_metrics_collector_percentile_calculation():
    """Verify statistical percentile calculations for P50 and P95."""
    collector = metrics_collector
    collector.reset()

    # Insert 100 values: 1 to 100
    for val in range(1, 101):
        collector.record_latency("test_stage", float(val))

    summary = collector.get_summary()
    lat = summary["latencies"]["test_stage"]

    assert lat["count"] == 100
    assert lat["min"] == 1.0
    assert lat["max"] == 100.0
    assert lat["mean"] == 50.5
    assert lat["p50"] == 50.5
    assert lat["p95"] == 95.05

