import pytest
from starlette.testclient import TestClient
from core.main_fastapi import app as fastapi_app
from core.observability import metrics_collector
from core.circuit_breaker import gemini_circuit_breaker


@pytest.fixture
def client():
    return TestClient(fastapi_app)


def test_health_endpoint_liveness(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}


def test_ready_endpoint_readiness(client):
    gemini_circuit_breaker.reset()
    response = client.get("/ready")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "rag" in data
    assert "gemini" in data
    assert "circuit_breaker" in data
    assert data["status"] in ("ready", "degraded", "not_ready")


def test_ready_endpoint_degraded_when_circuit_open(client):
    gemini_circuit_breaker.trip_for_test()
    try:
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["gemini"] == "degraded"
        assert data["circuit_breaker"] == "OPEN"
    finally:
        gemini_circuit_breaker.reset()


def test_metrics_endpoint_structure(client):
    metrics_collector.reset()
    metrics_collector.increment("requests_total", 3)
    metrics_collector.increment("requests_success", 3)

    response = client.get("/api/system/metrics")
    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert "requests" in data
    assert data["requests"]["total"] >= 3
    assert "ai" in data
    assert "retrieval" in data
    assert "query_expansion" in data
    assert "latency" in data
    assert "circuit_breaker" in data
    assert "errors" in data
    assert "safety" in data

    # Verify zero-phi: no user prompt or sensitive data
    raw_text = response.text.lower()
    for forbidden in ["patient", "password", "api_key", "secret"]:
        assert forbidden not in raw_text


def test_metrics_reset_endpoint(client):
    metrics_collector.increment("requests_total", 10)
    response = client.post("/api/system/metrics/reset")
    assert response.status_code == 200
    assert response.json() == {"status": "reset_successful"}

    check_res = client.get("/api/system/metrics")
    assert check_res.json()["requests"]["total"] == 0


def test_metrics_disabled_returns_403(client, monkeypatch):
    metrics_collector.enabled = False
    try:
        response = client.get("/api/system/metrics")
        assert response.status_code == 403
        post_response = client.post("/api/system/metrics/reset")
        assert post_response.status_code == 403
    finally:
        metrics_collector.enabled = True


def test_system_dashboard_html_page(client):
    res1 = client.get("/system")
    assert res1.status_code == 200
    assert "text/html" in res1.headers.get("content-type", "")
    assert "MediMind Local Observability" in res1.text

    res2 = client.get("/admin/system")
    assert res2.status_code == 200
    assert "MediMind Local Observability" in res2.text


def test_flask_parity_endpoints():
    from app import app as flask_app
    with flask_app.test_client() as flask_client:
        h = flask_client.get("/health")
        assert h.status_code == 200
        assert h.get_json() == {"status": "ok"}

        r = flask_client.get("/ready")
        assert r.status_code in (200, 503)
        assert "status" in r.get_json()

        m = flask_client.get("/api/system/metrics")
        assert m.status_code == 200
        assert "requests" in m.get_json()

        s = flask_client.get("/system")
        assert s.status_code == 200
        assert b"MediMind Local Observability" in s.data

