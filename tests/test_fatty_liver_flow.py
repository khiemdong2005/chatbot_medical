"""Fatty-liver suggestions stay useful without claiming clinical validation."""

from core.nutrition_options import FATTY_LIVER_FOOD, get_nutrition_options
from core.nutrition_rules import prepare_nutrition_candidates
from core.recipe_features import analyze_imported_recipe


def _visible_ids(data):
    meal = (data.get("full_meal_set") or {}).get("dishes", [])
    return {recipe["id"] for recipe in data["recipes"]} | {dish["recipe"]["id"] for dish in meal}


def test_fatty_liver_api_returns_reference_dishes_without_model(client, monkeypatch):
    def unexpected_model_call(*_args, **_kwargs):
        raise AssertionError("curated suggestions must not call a model")

    monkeypatch.setattr("core.nutrition_ai.select_recipes", unexpected_model_call)
    response = client.post("/api/nutrition/options", json={"condition": "Gan nhiễm mỡ", "recipe_type": "food"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["provider_status"] == "guided_catalog"
    assert data["matched"] is True
    assert data["needs_clarification"] is False
    assert data["gemini_used"] is False
    assert data["eligible_count"] == len(FATTY_LIVER_FOOD)
    assert _visible_ids(data) == {recipe["id"] for recipe in FATTY_LIVER_FOOD}
    meal_recipes = {dish["recipe"]["id"]: dish["recipe"] for dish in data["full_meal_set"]["dishes"]}
    fish_ingredients = {item["name"] for item in meal_recipes["fl_steamed_fish"]["ingredients"]}
    greens_ingredients = {item["name"] for item in meal_recipes["fl_steamed_greens"]["ingredients"]}
    assert (fish_ingredients & greens_ingredients) == {"Nước lọc"}
    assert any("niddk.nih.gov" in source["source_url"] for source in data["sources"])
    assert "chưa xác nhận từng món" in data["notice"]


def test_fatty_liver_filters_declared_allergies_from_dishes_and_meal():
    data = get_nutrition_options("gan nhiễm mỡ; dị ứng cá", "food", profile={"allergies": "đậu nành"})
    shown = _visible_ids(data)
    assert data["provider_status"] == "guided_catalog"
    assert "fl_steamed_fish" not in shown
    assert "fl_tofu_tomato" not in shown
    assert "fl_chicken_vegetables" in shown
    assert data["eligible_count"] == len(FATTY_LIVER_FOOD) - 2


def test_fatty_liver_aliases_are_exact_and_unmapped_comorbidity_stays_guarded():
    for query in ("gan nhiễm mỡ", "bệnh gan nhiễm mỡ", "fatty liver", "NAFLD", "MASLD"):
        parsed = prepare_nutrition_candidates(query, FATTY_LIVER_FOOD)
        assert parsed["contexts"] == ["fatty_liver"]
        assert parsed["is_unmapped_disease"] is False
    assert prepare_nutrition_candidates("không bị gan nhiễm mỡ", FATTY_LIVER_FOOD)["recognized"] is False
    blocked = get_nutrition_options("gan nhiễm mỡ và bệnh thận", "food")
    assert blocked["provider_status"] == "clinical_safeguard_refusal"
    assert blocked["recipes"] == []


def test_curated_recipe_translations_cover_all_displayed_fields():
    for recipe in FATTY_LIVER_FOOD:
        english = recipe["translations"]["en"]
        assert english["title"] and english["subtitle"] and english["benefit"]
        assert len(english["ingredients"]) == len(recipe["ingredients"])
        assert len(english["steps"]) == len(recipe["steps"])
        assert len(english["avoid"]) == len(recipe["avoid"])


def test_plain_added_sugar_is_detected_without_flagging_unsweetened_milk():
    recipe = {
        "id": "sample_sugary_oats", "title": "Cháo yến mạch ngọt", "recipe_type": "food",
        "language": "vi", "imported": True, "categories": [],
        "ingredients": [{"name": "Yến mạch 40g"}, {"name": "Đường 1 muỗng"}, {"name": "Nước lọc 200ml"}],
        "steps": ["Nấu chín yến mạch với nước, cho đường vào."],
    }
    assert analyze_imported_recipe(recipe)["sugar_high"] is True
    assert prepare_nutrition_candidates("gan nhiễm mỡ", [recipe])["recipes"] == []
    unsweetened = {**recipe, "ingredients": [{"name": "Sữa đậu nành không đường"}]}
    assert analyze_imported_recipe(unsweetened)["sugar_high"] is False
