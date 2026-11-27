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


def test_browser_cannot_inject_profile_into_guest_request(client, test_users):
    guest_response = client.post("/api/nutrition/options", json={
        "condition": "ho", "recipe_type": "food",
        "profile": {"allergies": "sữa", "height": "170", "weight": "82"},
    })
    assert guest_response.status_code == 401
    assert guest_response.get_json()["auth_required"] is True

    with client.session_transaction() as sess:
        sess["user_id"] = test_users["user_a_id"]
    drink_response = client.post("/api/nutrition/options", json={
        "condition": "ho", "recipe_type": "drink",
    })
    assert drink_response.status_code == 400

    response = client.post("/api/nutrition/options", json={
        "condition": "ho", "recipe_type": "food",
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
    sample = [
        {**result["recipes"][0], "id": "s1", "sugar": 8.0},
        {**result["recipes"][1], "id": "s2", "sugar": 1.5},
        {**result["recipes"][2], "id": "s3", "sugar": 4.0},
    ]
    shortlist = retrieve_candidates("ít đường", sample, sort_by_sugar=True)
    assert min(recipe["sugar"] for recipe in shortlist) == 1.5


def test_allergen_scan_includes_common_sauces():
    recipe = {"ingredients": [{"name": "Nước mắm"}, {"name": "Dầu hào"}, {"name": "Xì dầu"}]}
    assert {"fish", "shellfish", "seafood", "soy"} <= _ingredient_allergens(recipe)


def test_ambiguous_unaccented_food_allergy_is_not_guessed():
    assert prepare_nutrition_candidates("ho; dị ứng cá", imported_recipes("food")[:20])["allergies"] == ["fish"]
    assert prepare_nutrition_candidates("ho; dị ứng cà", imported_recipes("food")[:20])["recipes"] == []


@pytest.mark.parametrize("query", [
    "tiểu đường và bệnh thận", "gút, thận yếu", "ít đường, bệnh gan",
    "tiểu đường và tăng mỡ máu", "gút và bệnh tim", "bệnh celiac",
])
def test_unmapped_disease_or_comorbidity_blocks_automatic_suggestions(query):
    result = get_nutrition_options(query, "food")
    assert result["provider_status"] == "clinical_safeguard_refusal"
    assert result["recipes"] == []
    assert result["needs_clarification"] is True


def test_nutrition_survey_syncs_height_weight_age_gender_and_allergies_from_profile(client, test_users):
    from pathlib import Path

    with client.session_transaction() as sess:
        sess["user_id"] = test_users["user_a_id"]

    save_res = client.post(
        "/api/auth/profile",
        headers={"Origin": "http://localhost"},
        json={
            "name": "Nguyen Van Dinh Duong",
            "dob": "15/08/1998",
            "gender": "Nữ",
            "height": "162",
            "weight": "54.5",
            "allergies": "hải sản, đậu phộng",
        },
    )
    assert save_res.status_code == 200
    me_user = client.get("/api/auth/me").get_json()["user"]
    assert me_user["height"] == "162"
    assert me_user["weight"] == "54.5"
    assert me_user["dob"] == "15/08/1998"
    assert me_user["gender"] == "Nữ"
    assert me_user["allergies"] == "hải sản, đậu phộng"

    root = Path(__file__).resolve().parent.parent
    nf_js = (root / "frontend" / "static" / "js" / "nutrition-flow.js").read_text(encoding="utf-8")
    app_js = (root / "frontend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    html = (root / "frontend" / "templates" / "index.html").read_text(encoding="utf-8")

    assert "_applyProfileToSurveyFields" in nf_js
    assert "_computeAgeFromDob" in nf_js
    assert "medimind:profile-updated" in nf_js
    assert "medimind:auth-logout" in nf_js
    assert "medimind:profile-updated" in app_js
    assert "medimind:auth-logout" in app_js
    assert "window.currentUser = currentUser" in app_js
    assert "_getScopedMedReminderStorageKey" in app_js
    assert "document.getElementById('p-height')?.value.trim()" in app_js
    assert "document.getElementById('p-weight')?.value.trim()" in app_js
    assert "currentUser.blood_type || 'Chưa rõ'" in app_js
    assert 'id="nf-sv-weight" type="number" step="any"' in html
    assert "nutrition-flow.js') }}?v=26.2.8" in html
    assert "nutrition-catalog.js') }}?v=11" in html
