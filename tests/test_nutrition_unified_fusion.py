"""Tests for Unified Nutrition Fusion: BMR/TDEE Meal Planner (Food+Combo+Drinks) + 2,500+ Recipe Catalog."""

from pathlib import Path
from unittest.mock import patch

from core.nutrition.monngonmoingay_catalog import search_recipes
from core.nutrition.nutrition_meal_planner import build_production_meal_plan
from core.nutrition.recipe_catalog import imported_recipes

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_monngonmoingay_catalog_search_pagination_and_allergy_filter():
    base = search_recipes({"page": "1", "per_page": "12"})
    assert base["catalog_total"] == 2500
    assert len(base["items"]) == 12
    assert base["pages"] > 100

    # Accent-insensitive search + allergy exclusion
    filtered = search_recipes({"q": "canh", "exclude": ["Hải sản"], "page": "1", "per_page": "18"})
    assert filtered["total"] > 0
    for item in filtered["items"]:
        blob = (item["ten_mon"] + " " + " ".join(item["nguyen_lieu"])).lower()
        assert "tôm" not in blob


def test_meal_plan_returns_single_meals_and_combos_without_drinks():
    # Drinks feature and dataset have been removed completely
    assert imported_recipes("drink") == []

    payload = {
        "user_metrics": {
            "height": 170,
            "weight": 68,
            "age": 26,
            "gender": "Nam",
            "activity_level": "Vận động vừa",
            "goal": "Duy trì cân nặng",
        },
        "medical_conditions": ["Rối loạn mỡ máu", "Gút"],
        "allergies": "tôm, cua, hải sản, đậu phộng",
        "preferences": {"meals_per_day": 3},
    }
    with patch("core.ai.llm_provider.llm_provider.is_groq_active", return_value=False):
        result = build_production_meal_plan(payload)

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["daily_plan"]["bmr"] > 0
    assert result["daily_plan"]["tdee"] >= result["daily_plan"]["bmr"]
    assert len(result["daily_plan"]["meals"]) == 3
    assert len(result["food_combos"]) >= 1
    assert "drinks" not in result

    # Verify Mon Ngon Moi Ngay is the sole recipe dataset (ViFoodRec & Wikibooks removed)
    assert not (REPO_ROOT / "data/recipes/vifoodrec").exists()
    assert not (REPO_ROOT / "data/recipes/wikibooks").exists()
    all_foods = imported_recipes("food")
    assert len(all_foods) >= 2400
    assert all(r["id"].startswith("mnnm-") for r in all_foods)

    # Verify 100% real photos (local canonical staples or trusted monngonmoingay.com) and ZERO .svg icons
    for combo in result["food_combos"]:
        for dish in combo["dishes"]:
            img = dish.get("image_link") or ""
            assert not img.endswith(".svg"), f"SVG icon returned for combo dish: {dish.get('title')} -> {img}"
            if img.startswith("/static/"):
                assert (REPO_ROOT / "frontend" / img.split("?", 1)[0].lstrip("/")).exists(), f"Missing local combo image: {img}"
            else:
                assert img.startswith("https://monngonmoingay.com/"), f"Unexpected combo image URL: {dish.get('title')} -> {img}"

    # Verify shuffle with exclude_recipe_ids rotates dishes instead of repeating identical meals
    gout_payload = dict(payload, medical_conditions=["Gút"])
    with patch("core.ai.llm_provider.llm_provider.is_groq_active", return_value=False):
        gout_res1 = build_production_meal_plan(gout_payload)
    shown_ids = [m["items"][0]["food_id"] for m in gout_res1["daily_plan"]["meals"] if m.get("items")]
    payload_shuffle = dict(gout_payload, preferences={"meals_per_day": 3, "exclude_recipe_ids": shown_ids})
    with patch("core.ai.llm_provider.llm_provider.is_groq_active", return_value=False):
        result2 = build_production_meal_plan(payload_shuffle)
    next_ids = [m["items"][0]["food_id"] for m in result2["daily_plan"]["meals"] if m.get("items")]
    assert set(next_ids) != set(shown_ids)


def test_nutrition_flask_routes_meal_plan_and_recipe_catalog(client, test_users):
    # Unauthenticated guests must be blocked with 401 on every nutrition endpoint
    for method, url, kwargs in (
        ("GET", "/api/nutrition/recipe-catalog?q=ga&per_page=6&page=1", {}),
        ("POST", "/api/nutrition/meal-plan", {"json": {"user_metrics": {}}}),
        ("POST", "/api/nutrition/options", {"json": {"condition": "ho", "recipe_type": "food"}}),
        ("POST", "/api/nutrition/analyze", {"json": {"condition": "nhiệt miệng"}}),
    ):
        resp_unauth = client.open(url, method=method, **kwargs)
        assert resp_unauth.status_code == 401, f"{method} {url} should require login"
        assert resp_unauth.get_json().get("auth_required") is True

    with client.session_transaction() as sess:
        sess["user_id"] = test_users["user_a_id"]

    resp_cat = client.get("/api/nutrition/recipe-catalog?q=ga&per_page=6&page=1")
    assert resp_cat.status_code == 200
    cat_data = resp_cat.get_json()
    assert cat_data["catalog_total"] == 2500
    assert len(cat_data["items"]) <= 6

    with patch("core.ai.llm_provider.llm_provider.is_groq_active", return_value=False):
        resp_plan = client.post(
            "/api/nutrition/meal-plan",
            json={
                "user_metrics": {"height": 165, "weight": 58, "age": 24, "gender": "Nữ", "activity_level": "Ít vận động"},
                "medical_conditions": [],
                "allergies": "",
                "preferences": {"meals_per_day": 3},
            },
        )
    assert resp_plan.status_code == 200
    plan_data = resp_plan.get_json()
    assert plan_data["success"] is True
    assert plan_data["daily_plan"]["meals"]
    assert "drinks" not in plan_data


def test_frontend_nutrition_fusion_security_and_hooks():
    app_js = (REPO_ROOT / "frontend/static/js/app.js").read_text(encoding="utf-8")
    flow_js = (REPO_ROOT / "frontend/static/js/nutrition-flow.js").read_text(encoding="utf-8")
    cat_js = (REPO_ROOT / "frontend/static/js/nutrition-catalog.js").read_text(encoding="utf-8")
    html = (REPO_ROOT / "frontend/templates/index.html").read_text(encoding="utf-8")

    # Nutrition tab requires login in SPA router & handles 401 on API calls
    assert "const protectedTabs = ['profile-tab', 'admin-tab', 'doctor-tab'];" in app_js
    assert "response.status === 401" in flow_js
    assert "resp.status === 401" in flow_js
    assert "response.status === 401" in cat_js

    # XSS protection & user-scoped sessionStorage in nutrition-flow.js
    assert "${safe(src)}" in flow_js
    assert "${safe(item.name" in flow_js
    assert "userScope" in flow_js
    assert "openNutritionRecipePopup" in flow_js

    # Typo fix 'ghe' (not 'ghep') in nutrition-catalog.js
    assert "'ghep'" not in cat_js
    assert "'ghe'" in cat_js

    # Original external recipe link button removed from recipe detail drawer
    cat_css = (REPO_ROOT / "frontend/static/css/nutrition-flow.css").read_text(encoding="utf-8")
    assert "Mở công thức gốc" not in cat_js
    assert "Open original recipe" not in cat_js
    assert "nf-recipe-source-link" not in cat_js
    assert "nf-recipe-source-link" not in cat_css

    # Both Survey + 2500+ Catalog + Popup Drawer mounted in index.html
    for hook in ('id="nf-start-survey-btn"', 'id="nf-open-catalog"', 'id="nf-catalog"', 'id="nf-recipe-drawer"', 'id="nf-survey-modal"', 'js/nutrition-catalog.js'):
        assert hook in html
