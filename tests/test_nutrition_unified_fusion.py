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


def test_meal_plan_returns_single_meals_combos_and_drinks_preserving_vifoodrec():
    # Ensure ViFoodRec drinks remain intact
    assert len(imported_recipes("drink")) > 0

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
    assert len(result["drinks"]) >= 1

    # Verify 100% real local photos exist on disk and ZERO .svg icons are returned
    from core.nutrition.nutrition_options import _CURATED_EXACT_IMAGES
    for _rid, img_url in _CURATED_EXACT_IMAGES.items():
        assert not img_url.endswith(".svg"), f"Curated image still SVG: {img_url}"
        assert (REPO_ROOT / img_url.split("?", 1)[0].lstrip("/")).exists(), f"Missing curated image: {img_url}"
    for combo in result["food_combos"]:
        for dish in combo["dishes"]:
            img = dish.get("image_link") or ""
            assert img.startswith("/static/images/recipes/"), f"Non-real combo image: {dish.get('title')} -> {img}"
            assert (REPO_ROOT / img.split("?", 1)[0].lstrip("/")).exists(), f"Missing combo image: {img}"

    # Verify shuffle with exclude_recipe_ids rotates dishes instead of repeating identical meals
    shown_ids = [m["items"][0]["food_id"] for m in result["daily_plan"]["meals"] if m.get("items")]
    payload_shuffle = dict(payload, preferences={"meals_per_day": 3, "exclude_recipe_ids": shown_ids})
    with patch("core.ai.llm_provider.llm_provider.is_groq_active", return_value=False):
        result2 = build_production_meal_plan(payload_shuffle)
    next_ids = [m["items"][0]["food_id"] for m in result2["daily_plan"]["meals"] if m.get("items")]
    assert set(next_ids) != set(shown_ids)


def test_nutrition_flask_routes_meal_plan_and_recipe_catalog(client):
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
    assert plan_data["drinks"]


def test_frontend_nutrition_fusion_security_and_hooks():
    flow_js = (REPO_ROOT / "static/js/nutrition-flow.js").read_text(encoding="utf-8")
    cat_js = (REPO_ROOT / "static/js/nutrition-catalog.js").read_text(encoding="utf-8")
    html = (REPO_ROOT / "templates/index.html").read_text(encoding="utf-8")

    # XSS protection & user-scoped sessionStorage in nutrition-flow.js
    assert "${safe(src)}" in flow_js
    assert "${safe(item.name" in flow_js
    assert "userScope" in flow_js
    assert "openNutritionRecipePopup" in flow_js

    # Typo fix 'ghe' (not 'ghep') in nutrition-catalog.js
    assert "'ghep'" not in cat_js
    assert "'ghe'" in cat_js

    # Both Survey + 2500+ Catalog + Popup Drawer mounted in index.html
    for hook in ('id="nf-start-survey-btn"', 'id="nf-open-catalog"', 'id="nf-catalog"', 'id="nf-recipe-drawer"', 'id="nf-survey-modal"', 'js/nutrition-catalog.js'):
        assert hook in html
