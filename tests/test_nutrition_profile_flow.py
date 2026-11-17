import json
import pytest

from core.models import User, db
from core.nutrition_options import get_nutrition_options
from core.nutrition_rules import _ingredient_allergens, prepare_nutrition_candidates
from core.recipe_catalog import imported_recipes, retrieve_candidates


@pytest.mark.parametrize("dob", ["01/01/1990", "1990-01-01"])
def test_profile_food_allergy_excludes_every_displayed_dish(client, test_app, test_users, dob):
    with test_app.app_context():
        user = db.session.get(User, test_users["user_a_id"])
        user.clinical_profile = json.dumps({"allergies": "tôm, cua", "height": "170", "weight": "82"})
        user.dob = dob
        db.session.commit()
    with client.session_transaction() as session:
        session["user_id"] = test_users["user_a_id"]

    response = client.post("/api/nutrition/options", json={"condition": "gút, ít đường", "recipe_type": "food"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["query_preferences"] == ["Ít/không thêm đường"]
    assert data["profile_context"]["bmi"] == 28.4
    assert set(data["profile_context"]["allergies"]) == {"tôm/tép", "cua/ghẹ"}
    dishes = data["recipes"] + [item["recipe"] for item in (data.get("full_meal_set") or {}).get("dishes", [])]
    assert dishes
    assert all(not (_ingredient_allergens(recipe) & {"shrimp", "crab"}) for recipe in dishes)
    if data.get("full_meal_set"):
        meal = data["full_meal_set"]
        assert meal["total_calories"] == sum(item["recipe"]["calories"] for item in meal["dishes"])
        assert "chưa tính" in meal["calorie_note"]


def test_browser_cannot_inject_profile_into_guest_request(client):
    response = client.post("/api/nutrition/options", json={
        "condition": "ho", "recipe_type": "drink",
        "profile": {"allergies": "sữa", "height": "170", "weight": "82"},
    })
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["profile_context"]["used"] is False
    assert data["profile_context"]["bmi"] is None


def test_nutrition_page_exposes_compact_results_blocks(client):
    response = client.get("/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    for marker in ('id="nf-context"', 'id="nf-evidence"', 'id="nf-full-meal-wrap"', 'id="nf-detail-content"'):
        assert marker in page


def test_unresolved_profile_food_allergy_fails_closed():
    recipes = imported_recipes("food")[:12]
    result = prepare_nutrition_candidates("ho", recipes, profile_allergies="dị ứng thực phẩm không rõ")
    assert result["recipes"] == []
    assert len(result["excluded"]) == len(recipes)
    options = get_nutrition_options("ho", "food", profile={"allergies": "dị ứng thực phẩm không rõ"})
    assert options["recipes"] == []
    assert options["profile_context"]["allergy_needs_review"] is True


def test_low_sugar_preference_does_not_invent_nutrient_threshold():
    result = prepare_nutrition_candidates("ít đường", imported_recipes("food"))
    assert result["query_preferences"] == ["Ít/không thêm đường"]
    assert result["recipes"]
    assert all(not recipe.get("nutrition_verified") for recipe in result["recipes"])
    known = [recipe["sugar"] for recipe in result["recipes"] if isinstance(recipe.get("sugar"), (int, float))]
    assert known == sorted(known)
    shortlist = retrieve_candidates("ít đường", result["recipes"], sort_by_sugar=True)
    assert min(recipe["sugar"] for recipe in shortlist) == min(known)


def test_allergen_scan_includes_common_sauces():
    recipe = {"ingredients": [{"name": "Nước mắm"}, {"name": "Dầu hào"}, {"name": "Xì dầu"}]}
    assert {"fish", "shellfish", "seafood", "soy"} <= _ingredient_allergens(recipe)


def test_ambiguous_unaccented_food_allergy_is_not_guessed():
    assert prepare_nutrition_candidates("ho; dị ứng cá", imported_recipes("drink"))["allergies"] == ["fish"]
    assert prepare_nutrition_candidates("ho; dị ứng cà", imported_recipes("drink"))["recipes"] == []


@pytest.mark.parametrize("query", [
    "tiểu đường và bệnh thận", "gút, thận yếu", "ít đường, bệnh gan",
    "tiểu đường và tăng mỡ máu", "gút và bệnh tim", "bệnh celiac",
])
def test_unmapped_disease_or_comorbidity_blocks_automatic_suggestions(query):
    result = get_nutrition_options(query, "food")
    assert result["provider_status"] == "clinical_safeguard_refusal"
    assert result["recipes"] == []
    assert result["needs_clarification"] is True
