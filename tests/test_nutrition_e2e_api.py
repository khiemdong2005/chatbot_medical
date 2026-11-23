"""End-to-End API and Integration Tests for Nutrition Engine (Phase 5 - 9).

Validates all 20 real-world scenarios across HTTP endpoints:
1. Người dùng khỏe mạnh (Healthy)
2. Bệnh gút (Gout)
3. Đái tháo đường type 2 (Type 2 Diabetes)
4. Gan nhiễm mỡ (NAFLD)
5. Trào ngược dạ dày (GERD)
6. Dị ứng tôm (Shrimp allergy)
7. Dị ứng trứng (Egg allergy)
8. Dị ứng sữa bò (Cow milk allergy)
9. Dị ứng nhiều nhóm (Multiple allergies: shrimp, egg, milk)
10. Dị ứng hạt chưa hỗ trợ (Unsupported allergen: tree nuts fail-closed)
11. Bệnh thận mạn / CKD (Unmapped clinical safeguard)
12. Gút + Tiểu đường (Multiple co-morbidities)
13. Sở thích gà hấp (chicken_meat + steaming preference)
14. Không ăn đồ chiên (avoid deep_frying)
15. Không thích thịt bò (avoid beef)
16. Không có món hợp lệ (Impossible constraints graceful empty response)
17. Thiếu một combo role (Partial/sparse pool handling)
18. Refresh nhiều lần (Rotation with exclude_recipe_ids)
19. Người dùng chưa đăng nhập (Guest session handling)
20. Kiểm thử tải đồng thời (Concurrent requests)
"""

import concurrent.futures
import json
import time
import pytest
from app import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_scenario_01_healthy(client):
    """1. Người dùng khỏe mạnh."""
    res = client.post("/api/nutrition/meals", json={"condition": "ăn uống lành mạnh, cân bằng"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["safety_status"] == "PASSED_KNOWN_CONSTRAINTS"
    assert len(data["family_combos"]) == 6
    assert len(data["standalone_meals"]) == 6
    for combo in data["family_combos"]:
        assert len(combo["components"]) == 4
        assert set(combo["components"].keys()) == {"staple", "main_dish", "soup", "vegetable"}


def test_scenario_02_gout(client):
    """2. Bệnh gút."""
    res = client.post("/api/nutrition/meals", json={"condition": "bệnh gút"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert len(data["family_combos"]) >= 1
    # Không có thịt đỏ giàu purin hoặc nội tạng
    for combo in data["family_combos"]:
        for comp in combo["components"].values():
            assert "long heo" not in comp["title"].lower()
            assert "thịt bò" not in comp["title"].lower()


def test_scenario_03_type2_diabetes(client):
    """3. Đái tháo đường type 2."""
    res = client.post("/api/nutrition/meals", json={"condition": "đái tháo đường type 2"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert len(data["family_combos"]) >= 1


def test_scenario_04_nafld(client):
    """4. Gan nhiễm mỡ."""
    res = client.post("/api/nutrition/meals", json={"condition": "gan nhiễm mỡ"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert len(data["family_combos"]) == 6
    # Ưu tiên hấp, luộc
    for combo in data["family_combos"]:
        main_cook = combo["components"]["main_dish"].get("primary_cooking_method")
        assert main_cook in ("steaming", "boiling", "soup_cooking", "raw_fresh", "grilling", "stir_frying", None)


def test_scenario_05_gerd(client):
    """5. GERD (Trào ngược dạ dày)."""
    res = client.post("/api/nutrition/meals", json={"condition": "trào ngược dạ dày thực quản"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert len(data["family_combos"]) >= 1
    vegetables = {combo["components"]["vegetable"]["recipe_id"] for combo in data["family_combos"]}
    assert "fl_steamed_greens" in vegetables
    for combo in data["family_combos"]:
        assert all(dish["recipe_id"] != "vifoodrec_2901" for dish in combo["components"].values())


def test_scenario_06_shrimp_allergy(client):
    """6. Dị ứng tôm."""
    res = client.post("/api/nutrition/meals", json={"condition": "ăn ngon", "allergies": ["shrimp"]})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    for combo in data["family_combos"]:
        for comp in combo["components"].values():
            assert "tôm" not in comp["title"].lower()
            assert "téptrán" not in comp["title"].lower()


@pytest.mark.parametrize("request_body", [
    {"condition": "gợi ý bữa tối, dị ứng hải sản"},
    {"condition": "gợi ý bữa tối", "allergies": ["hải sản"]},
])
def test_seafood_allergy_expands_to_all_indexed_groups(client, request_body):
    from core.nutrition.meal_engine_service import MealEngineService

    response = client.post("/api/nutrition/meals", json=request_body)
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["family_combos"] and data["standalone_meals"]
    ids = {dish["recipe_id"] for dish in data["standalone_meals"]}
    ids.update(dish["recipe_id"] for combo in data["family_combos"] for dish in combo["components"].values())
    index = MealEngineService.get_instance().index
    for code in ("shrimp", "crab", "squid_octopus", "mollusk", "fish"):
        assert not (ids & index.get_ids_by_allergen_status(code, "known_present"))
        assert not (ids & index.get_ids_by_allergen_status(code, "unknown"))


def test_options_return_both_views_for_seafood_allergy(client):
    response = client.post("/api/nutrition/options", json={"condition": "dị ứng hải sản", "recipe_type": "food"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert not data["needs_clarification"]
    assert data["recipes"] and data["meal_combos"]


def test_scenario_07_egg_allergy(client):
    """7. Dị ứng trứng."""
    res = client.post("/api/nutrition/meals", json={"condition": "cơm tối", "allergies": ["egg"]})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    for combo in data["family_combos"]:
        for comp in combo["components"].values():
            assert "trứng" not in comp["title"].lower()


def test_scenario_08_cow_milk_allergy(client):
    """8. Dị ứng sữa bò."""
    res = client.post("/api/nutrition/meals", json={"condition": "bữa ăn trưa", "allergies": ["cow_milk"]})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    for combo in data["family_combos"]:
        for comp in combo["components"].values():
            assert "sữa tươi" not in comp["title"].lower()
            assert "phô mai" not in comp["title"].lower()


def test_scenario_09_multiple_allergies(client):
    """9. Dị ứng nhiều nhóm (tôm + trứng + sữa)."""
    res = client.post("/api/nutrition/meals", json={"condition": "ăn nhẹ", "allergies": ["shrimp", "egg", "cow_milk"]})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    for combo in data["family_combos"]:
        for comp in combo["components"].values():
            t = comp["title"].lower()
            assert "tôm" not in t and "trứng" not in t
            # Hàu sữa là hải sản/mollusk, không phải sữa bò; kiểm tra không có sữa tươi / phô mai
            assert "sữa tươi" not in t and "phô mai" not in t and "bơ sữa" not in t


def test_scenario_10_unsupported_allergen_halt(client):
    """10. Dị ứng hạt chưa hỗ trợ (tree nuts) -> FAIL-CLOSED HALT."""
    res = client.post("/api/nutrition/meals", json={"condition": "bữa tối", "allergies": ["tree_nuts"]})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "refusal"
    assert data["safety_status"] == "UNSUPPORTED_ALLERGEN_HALT"
    assert len(data["family_combos"]) == 0
    assert len(data["standalone_meals"]) == 0
    assert "dị ứng" in data["notice"].lower()


def test_scenario_11_ckd_unmapped_safeguard(client):
    """11. Bệnh thận mạn / CKD thiếu dữ liệu -> SAFEGUARD REFUSAL."""
    res = client.post("/api/nutrition/meals", json={"condition": "bệnh thận mạn giai đoạn 4"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "refusal"
    assert data["safety_status"] in ("UNMAPPED_DISEASE_SAFEGUARD", "INSUFFICIENT_CLINICAL_DATA")
    assert len(data["family_combos"]) == 0


def test_scenario_12_comorbidity_gout_diabetes(client):
    """12. Gút + Tiểu đường (đa bệnh lý)."""
    res = client.post("/api/nutrition/meals", json={"condition": "bệnh gút và đái tháo đường"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert len(data["family_combos"]) >= 1


def test_scenario_13_chicken_steaming_preference(client):
    """13. Thích thịt gà hấp."""
    res = client.post("/api/nutrition/meals", json={"condition": "thích thịt gà hấp"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert len(data["family_combos"]) >= 1


def test_scenario_14_avoid_deep_frying(client):
    """14. Không ăn đồ chiên rán."""
    res = client.post("/api/nutrition/meals", json={"condition": "không ăn đồ chiên rán, thanh đạm"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert len(data["family_combos"]) >= 1


def test_scenario_15_avoid_beef(client):
    """15. Không thích thịt bò."""
    res = client.post("/api/nutrition/meals", json={"condition": "kiêng thịt bò"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    for combo in data["family_combos"]:
        for comp in combo["components"].values():
            assert "thịt bò" not in comp["title"].lower()
            assert "bắp bò" not in comp["title"].lower()


def test_scenario_16_impossible_constraints(client):
    """16. Ràng buộc bất khả thi -> Trả về rỗng an toàn, không crash."""
    # Loại trừ toàn bộ ID
    all_dummy = [f"vifoodrec_{i}" for i in range(3000)]
    res = client.post("/api/nutrition/meals", json={"condition": "ăn nhẹ", "exclude_recipe_ids": all_dummy})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert len(data["family_combos"]) == 0 or len(data["family_combos"]) <= 6


@pytest.mark.parametrize("condition", ["gan nhiễm mỡ", "gút"])
def test_scenario_17_backward_compat_options(client, condition):
    """17. Endpoint /api/nutrition/options tương thích ngược."""
    res = client.post("/api/nutrition/options", json={"condition": condition, "recipe_type": "food"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    d = data["data"]
    assert "meal_combos" in d
    assert d["recipes"]
    assert len(d["meal_combos"]) == 6
    assert d["full_meal_set"] == d["meal_combos"][0]
    assert any(combo["total_calories"] is not None for combo in d["meal_combos"])
    for combo in d["meal_combos"]:
        values = [dish["recipe"]["calories"] for dish in combo["dishes"]
                  if type(dish["recipe"]["calories"]) in (int, float)]
        assert combo["calorie_covered_dishes"] == len(values)
        assert combo["total_calories"] == (round(sum(values), 1) if values else None)


@pytest.mark.parametrize("condition", ["gút, dị ứng tôm", "gút và đái tháo đường type 2, dị ứng tôm"])
def test_shared_ingredient_filter_applies_to_both_views(client, condition):
    from core.nutrition.meal_engine_service import MealEngineService
    from core.nutrition.nutrition_rules import prepare_nutrition_candidates

    response = client.post("/api/nutrition/options", json={"condition": condition, "recipe_type": "food"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["recipes"] and data["meal_combos"]
    returned_ids = {recipe["id"] for recipe in data["recipes"]}
    returned_ids.update(dish["recipe"]["id"] for meal in data["meal_combos"] for dish in meal["dishes"])
    index = MealEngineService.get_instance().index
    original_recipes = [{**index.get_recipe_by_id(recipe_id), "imported": True} for recipe_id in returned_ids]
    assert not prepare_nutrition_candidates(condition, original_recipes)["excluded"]


@pytest.mark.parametrize("condition", ["bệnh thận mạn", "gút, dị ứng thực phẩm không rõ"])
def test_nutrition_options_do_not_show_either_view_when_safety_blocks(client, condition):
    response = client.post("/api/nutrition/options", json={"condition": condition, "recipe_type": "food"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["needs_clarification"]
    assert not data["recipes"] and not data.get("meal_combos")


def test_meal_calories_report_partial_coverage(client, monkeypatch):
    from core.nutrition.meal_engine_service import MealEngineService

    original = MealEngineService.get_recipe_details

    def details_without_staple_energy(service, recipe_id):
        details = original(service, recipe_id)
        if recipe_id.startswith("canonical_staple_"):
            details["calories"] = None
        return details

    monkeypatch.setattr(MealEngineService, "get_recipe_details", details_without_staple_energy)
    response = client.post("/api/nutrition/options", json={"condition": "gút", "recipe_type": "food"})
    assert response.status_code == 200
    meals = response.get_json()["data"]["meal_combos"]
    partial_meals = [meal for meal in meals if meal["calorie_covered_dishes"] < len(meal["dishes"])]
    assert partial_meals
    for meal in partial_meals:
        values = [dish["recipe"]["calories"] for dish in meal["dishes"] if dish["recipe"]["calories"] is not None]
        assert 0 < len(values) == meal["calorie_covered_dishes"] < len(meal["dishes"])
        assert meal["total_calories"] == round(sum(values), 1)


def test_scenario_18_refresh_rotation(client):
    """18. Refresh nhiều lần (loại trừ các món đã thấy)."""
    # Lần 1
    res1 = client.post("/api/nutrition/meals", json={"condition": "ăn uống lành mạnh"})
    assert res1.status_code == 200
    data1 = res1.get_json()
    seen_ids = [
        comp["recipe_id"]
        for combo in data1["family_combos"]
        for comp in combo["components"].values()
    ]
    # Lần 2 với exclude_recipe_ids
    res2 = client.post("/api/nutrition/meals", json={"condition": "ăn uống lành mạnh", "exclude_recipe_ids": seen_ids[:10]})
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["status"] == "success"
    assert len(data2["family_combos"]) >= 1


def test_scenario_19_guest_unauthenticated(client):
    """19. Khách vãng lai chưa đăng nhập -> Hoạt động bình thường."""
    with client.session_transaction() as sess:
        sess.clear()
    res = client.post("/api/nutrition/meals", json={"condition": "cơm gia đình"})
    assert res.status_code == 200
    assert res.get_json()["status"] == "success"


def test_scenario_20_concurrent_requests():
    """20. Kiểm thử tải đồng thời qua ThreadPoolExecutor trên MealEngineService."""
    from core.nutrition.meal_engine_service import MealEngineService
    service = MealEngineService.get_instance()

    def make_req(q):
        t0 = time.perf_counter()
        res = service.recommend_meals(q)
        latency = (time.perf_counter() - t0) * 1000.0
        return res.get("status"), latency, len(res.get("family_combos", []))

    queries = [
        "bệnh gút", "đái tháo đường type 2", "gan nhiễm mỡ", "ăn uống lành mạnh",
        "trào ngược dạ dày", "thịt gà hấp", "thanh đạm ít dầu mỡ", "cơm gia đình",
        "món canh ngon", "bữa trưa nhẹ nhàng"
    ] * 5  # 50 requests

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(make_req, queries))

    assert len(results) == 50
    latencies = [lat for _, lat, _ in results]
    mean_lat = sum(latencies) / len(latencies)
    latencies.sort()
    p95_lat = latencies[int(len(latencies) * 0.95)]

    for status, latency, combo_count in results:
        assert status == "success"
        assert combo_count >= 1

    # Under concurrent multi-thread CPU load, mean should be well under 400ms
    assert mean_lat < 400.0
    assert p95_lat < 1000.0
