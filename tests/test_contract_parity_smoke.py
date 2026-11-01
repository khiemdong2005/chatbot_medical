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
    assert isinstance(flask_data["risk_score"], int)
    assert isinstance(fastapi_data["risk_score"], int)
    assert 0 <= flask_data["risk_score"] <= 100
    assert 0 <= fastapi_data["risk_score"] <= 100
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

