import pytest
from starlette.testclient import TestClient
from main_fastapi import app as fastapi_app


def test_flask_and_fastapi_chat_contract_parity(client):
    """Kiểm thử 8: Smoke test backend chính & kiểm thử contract tương đương giữa Flask và FastAPI."""
    test_payload = {
        "message": "Tôi bị sốt 38 độ và ngạt mũi từ hôm qua",
        "history": [],
        "lang": "vi"
    }

    # 1. Gọi Flask Backend
    flask_res = client.post("/api/chat", json=test_payload)
    assert flask_res.status_code == 200
    flask_data = flask_res.get_json()

    # 2. Gọi FastAPI Gateway
    fastapi_client = TestClient(fastapi_app)
    fastapi_res = fastapi_client.post("/api/chat", json=test_payload)
    assert fastapi_res.status_code == 200
    fastapi_data = fastapi_res.json()

    # 3. Đối chiếu Contract tương đương
    required_keys = [
        "answer",
        "risk_level",
        "risk_score",
        "symptoms",
        "specialist",
        "visual_findings",
        "differential_diagnosis",
        "is_emergency",
        "degraded",
        "sources"
    ]

    for k in required_keys:
        assert k in flask_data, f"Flask thiếu trường hợp đồng: {k}"
        assert k in fastapi_data, f"FastAPI thiếu trường hợp đồng: {k}"

    # Kiểm tra loại dữ liệu
    for data in (flask_data, fastapi_data):
        assert data["risk_score"] is None or (type(data["risk_score"]) is int and 0 <= data["risk_score"] <= 100)
    assert isinstance(flask_data["sources"], list)
    assert isinstance(fastapi_data["sources"], list)


def test_emergency_parity_across_backends(client):
    """Kiểm thử 8b: Đánh giá cấp cứu nhất quán giữa Flask và FastAPI."""
    emergency_payload = {
        "message": "Bác tôi bị đau thắt ngực dữ dội và ngất xỉu",
        "history": [],
        "lang": "vi"
    }

    # Flask
    flask_res = client.post("/api/chat", json=emergency_payload)
    assert flask_res.status_code == 200
    assert flask_res.get_json()["is_emergency"] is True
    assert flask_res.get_json()["risk_score"] == 90

    # FastAPI
    fastapi_client = TestClient(fastapi_app)
    fastapi_res = fastapi_client.post("/api/chat", json=emergency_payload)
    assert fastapi_res.status_code == 200
    assert fastapi_res.json()["is_emergency"] is True
    assert fastapi_res.json()["risk_score"] == 90


def test_fastapi_gateway_security_headers_and_csrf_protection():
    """Kiểm thử 8c: FastAPI Gateway áp dụng đầy đủ Security Headers & chặn Cross-Origin / Cross-Site CSRF."""
    fastapi_client = TestClient(fastapi_app)

    idx_res = fastapi_client.get("/")
    assert idx_res.status_code == 200
    assert idx_res.headers.get("X-Content-Type-Options") == "nosniff"
    assert idx_res.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert idx_res.headers.get("Server") == "MediMind-Clinical-Engine"
    csp = idx_res.headers.get("Content-Security-Policy", "")
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'self'" in csp
    assert "form-action 'self'" in csp

    cross_origin_res = fastapi_client.post(
        "/api/chat",
        json={"message": "Sốt nhẹ", "history": []},
        headers={"Origin": "https://attacker.evil.example"},
    )
    assert cross_origin_res.status_code == 403

    cross_site_fetch = fastapi_client.post(
        "/api/chat",
        json={"message": "Sốt nhẹ", "history": []},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert cross_site_fetch.status_code == 403


