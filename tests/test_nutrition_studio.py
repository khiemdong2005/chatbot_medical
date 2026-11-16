import pytest
from app import create_app
from core.nutrition_service import get_nutrition_recommendation, find_preset_condition

@pytest.fixture
def client():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.test_client() as client:
        yield client

def test_preset_dau_bung_kinh_matches():
    res = find_preset_condition("đau bụng kinh")
    assert res is not None
    assert res["condition_name"] == "Đau bụng kinh"
    assert len(res["foods_to_eat"]) == 4
    assert len(res["foods_to_avoid"]) == 3
    assert res["recipe"]["title"] == "Canh khoai lang hạt dẻ hầm"

def test_preset_nhiet_mieng_matches():
    res = find_preset_condition("nhiệt miệng")
    assert res is not None
    assert res["condition_name"] == "Nhiệt miệng"
    assert "foods_to_eat" in res
    assert "recipe" in res

def test_api_nutrition_analyze_valid_preset(client):
    res = client.post("/api/nutrition/analyze", json={"condition": "Đau bụng kinh"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["data"]["condition_name"] == "Đau bụng kinh"
    assert data["data"]["recipe"]["title"] == "Canh khoai lang hạt dẻ hầm"

def test_api_nutrition_analyze_empty_input(client):
    res = client.post("/api/nutrition/analyze", json={"condition": "   "})
    assert res.status_code == 400
    data = res.get_json()
    assert data["success"] is False
    assert "Vui lòng nhập" in data["error"]

def test_api_nutrition_analyze_custom_fallback(client):
    res = client.post("/api/nutrition/analyze", json={"condition": "mỏi cơ vai gáy cấp"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "foods_to_eat" in data["data"]
    assert "foods_to_avoid" in data["data"]
    assert "recipe" in data["data"]

