"""Comprehensive Test Suite for Phase 4.1: Ranking Quality & Scoring Correctness.

Validates:
1. Strict Preference Isolation:
   - Clinical soft preferences NEVER leak into user personal preferences.
   - When no user preferences are supplied, zero USER_PREFERRED_* reason codes are emitted.
2. Pairwise Relevance Evaluation:
   - Steaming preference: Steamed dish strictly outranks fried dish (all else equal).
   - Chicken preference: Chicken dish strictly outranks non-chicken dish.
   - Gout clinical avoidance: Purine/beef dish is strictly penalized compared to poultry/vegetable.
   - Missing cooking method: Receives neutral 0.50 without unjustified bonus.
3. Specific Recipe Root Cause Corrections:
   - vifoodrec_114 (Lươn nướng sả) is primary_role 'main_dish', NOT 'soup'.
   - vifoodrec_3199 (Cơm Gà Xối Mỡ) is NOT 'steaming'.
   - vifoodrec_1217 (Bún Mắm Chay) and vifoodrec_1310 (Miến Xào Chay) do NOT contain chicken/poultry.
   - vifoodrec_2170 (Nước Ép Táo Và Bắp Cải) does NOT contain corn/grain.
   - vifoodrec_1461 (Xúc Xích Chiên Bơ Khoai Tây Nghiền) recognizes sausage/meat and receives avoidance in Gout.
4. Score Bounding & Saturation Prevention:
   - Multiple matching ingredients do not cause runaway saturation.
"""

from typing import Dict, Any
import pytest

from core.nutrition.candidate_ranker import (
    CandidateRanker,
    ContentBasedScorer,
    ScoringConfig,
    ScoringContext,
)
from core.nutrition.clinical_constraints import SafetyStatus
from core.nutrition.constraint_resolver import ConstraintResolver
from core.nutrition.constraint_filter import ConstraintFilter
from core.nutrition.metadata_index import get_metadata_index, InMemoryInvertedIndex


@pytest.fixture(scope="module")
def index_fixture() -> InMemoryInvertedIndex:
    return get_metadata_index()


@pytest.fixture(scope="module")
def ranker_fixture(index_fixture: InMemoryInvertedIndex) -> CandidateRanker:
    return CandidateRanker(index=index_fixture)


# -----------------------------------------------------------------------------
# 1. Preference Isolation Tests
# -----------------------------------------------------------------------------

def test_preference_isolation_no_user_preferences_emits_no_user_reasons(ranker_fixture: CandidateRanker):
    """Verify that when the user specifies NO personal preferences, no USER_PREFERRED_* codes are emitted."""
    res = ConstraintResolver.resolve_constraints(condition_query="đái tháo đường type 2")
    pools = ConstraintFilter.filter_candidates(res, index=ranker_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)

    assert ranked.total_ranked_count > 0
    for role, items in ranked.ranked_by_role.items():
        for item in items:
            assert "USER_PREFERRED_GROUP" not in item.reason_codes, (
                f"Item {item.recipe_id} in role {role} emitted USER_PREFERRED_GROUP despite no user preferences!"
            )
            assert "USER_PREFERRED_INGREDIENT" not in item.reason_codes
            # When user has no preferences, ingredient_preferences score must be neutral 0.50
            assert item.score_breakdown["ingredient_preferences"] == 0.50


def test_user_preferences_strictly_separated_from_clinical(ranker_fixture: CandidateRanker):
    """Verify user preferences are only populated from user profile/query, not clinical directives."""
    res = ConstraintResolver.resolve_constraints(
        profile={"preferences": ["thịt gà"]},
        condition_query="đái tháo đường type 2"
    )
    # Clinical rules for diabetes prefer vegetable & grain
    assert "vegetable" in res.soft_preferred_ingredient_groups
    assert "grain" in res.soft_preferred_ingredient_groups

    # User preferences only contain poultry
    assert "poultry" in res.user_preferred_ingredient_groups or "chicken" in res.user_preferred_ingredients
    assert "vegetable" not in res.user_preferred_ingredient_groups

    pools = ConstraintFilter.filter_candidates(res, index=ranker_fixture.index)
    ctx = ScoringContext.from_resolved(resolved=res, pools=pools)

    assert "poultry" in ctx.user_preferred_ingredient_groups or "chicken" in ctx.user_preferred_ingredients
    assert "vegetable" not in ctx.user_preferred_ingredient_groups


# -----------------------------------------------------------------------------
# 2. Pairwise Relevance Evaluation Tests
# -----------------------------------------------------------------------------

def test_pairwise_steaming_preferred_over_deep_frying():
    """Pairwise test: A steamed chicken dish strictly outranks a deep-fried chicken dish when user prefers steaming."""
    scorer = ContentBasedScorer()
    ctx = ScoringContext()
    ctx.user_preferred_cooking_methods.add("steaming")
    ctx.all_preferred_methods.add("steaming")

    steamed_dish = {
        "normalized_ingredients": {"chicken", "ginger"},
        "ingredient_groups": {"poultry", "spice_herb"},
        "cooking_methods": {"steaming"},
        "static_meta_score": 0.95,
        "static_nutrition_score": 0.50,
        "nutrition_quality_label": "estimated"
    }

    fried_dish = {
        "normalized_ingredients": {"chicken", "ginger"},
        "ingredient_groups": {"poultry", "spice_herb"},
        "cooking_methods": {"deep_frying"},
        "static_meta_score": 0.95,
        "static_nutrition_score": 0.50,
        "nutrition_quality_label": "estimated"
    }

    score_steamed, bd_steamed, _, _, rc_steamed, _ = scorer.score_recipe(steamed_dish, ctx)
    score_fried, bd_fried, _, _, rc_fried, _ = scorer.score_recipe(fried_dish, ctx)

    assert score_steamed > score_fried
    assert bd_steamed["cooking_method"] > bd_fried["cooking_method"]
    assert "PREFERRED_COOKING_METHOD" in rc_steamed
    assert "PREFERRED_COOKING_METHOD" not in rc_fried


def test_pairwise_chicken_preference_requires_actual_chicken():
    """Pairwise test: User prefers chicken -> Dish with real chicken gets bonus; dish without chicken does not."""
    scorer = ContentBasedScorer()
    ctx = ScoringContext()
    ctx.user_preferred_ingredient_groups.add("poultry")

    chicken_dish = {
        "normalized_ingredients": {"chicken", "mushroom"},
        "ingredient_groups": {"poultry", "vegetable"},
        "cooking_methods": {"boiling"},
        "static_meta_score": 0.90,
        "static_nutrition_score": 0.50,
        "nutrition_quality_label": "estimated"
    }

    mushroom_dish = {
        "normalized_ingredients": {"mushroom", "tofu"},
        "ingredient_groups": {"vegetable", "legume"},
        "cooking_methods": {"boiling"},
        "static_meta_score": 0.90,
        "static_nutrition_score": 0.50,
        "nutrition_quality_label": "estimated"
    }

    score_chk, bd_chk, _, _, rc_chk, _ = scorer.score_recipe(chicken_dish, ctx)
    score_msh, bd_msh, _, _, rc_msh, _ = scorer.score_recipe(mushroom_dish, ctx)

    assert score_chk > score_msh
    assert bd_chk["ingredient_preferences"] > bd_msh["ingredient_preferences"]
    assert "USER_PREFERRED_GROUP" in rc_chk
    assert "USER_PREFERRED_GROUP" not in rc_msh


def test_pairwise_gout_clinical_soft_avoidance():
    """Pairwise test: In Gout, a beef dish is strictly penalized compared to poultry/vegetable dish."""
    scorer = ContentBasedScorer()
    ctx = ScoringContext()
    ctx.clinical_avoided_ingredients.add("beef")
    ctx.clinical_avoided_ingredient_groups.add("seafood")
    ctx.clinical_preferred_ingredient_groups.add("vegetable")

    poultry_dish = {
        "normalized_ingredients": {"chicken", "cabbage_greens"},
        "ingredient_groups": {"poultry", "vegetable"},
        "cooking_methods": {"boiling"},
        "static_meta_score": 0.95,
        "static_nutrition_score": 0.50,
        "nutrition_quality_label": "estimated"
    }

    beef_dish = {
        "normalized_ingredients": {"beef", "cabbage_greens"},
        "ingredient_groups": {"meat", "vegetable"},
        "cooking_methods": {"boiling"},
        "static_meta_score": 0.95,
        "static_nutrition_score": 0.50,
        "nutrition_quality_label": "estimated"
    }

    score_poultry, bd_poultry, _, _, rc_poultry, _ = scorer.score_recipe(poultry_dish, ctx)
    score_beef, bd_beef, _, _, rc_beef, _ = scorer.score_recipe(beef_dish, ctx)

    assert score_poultry > score_beef
    assert bd_poultry["clinical_preferences"] > bd_beef["clinical_preferences"]
    assert "CLINICAL_AVOIDED_INGREDIENT" in rc_beef
    assert "CLINICAL_AVOIDED_INGREDIENT" not in rc_poultry


def test_missing_cooking_method_remains_neutral():
    """Verify that a recipe with empty cooking methods receives neutral 0.50 cooking score."""
    scorer = ContentBasedScorer()
    ctx = ScoringContext()
    ctx.all_preferred_methods.add("steaming")

    dish_no_methods = {
        "normalized_ingredients": {"cabbage_greens"},
        "ingredient_groups": {"vegetable"},
        "cooking_methods": set(),
        "static_meta_score": 0.90,
        "static_nutrition_score": 0.50,
        "nutrition_quality_label": "estimated"
    }

    _, bd, _, _, rc, _ = scorer.score_recipe(dish_no_methods, ctx)
    assert bd["cooking_method"] == 0.50
    assert "PREFERRED_COOKING_METHOD" not in rc
    assert "AVOIDED_COOKING_METHOD" not in rc


# -----------------------------------------------------------------------------
# 3. Specific Recipe Root Cause Corrections
# -----------------------------------------------------------------------------

def test_vifoodrec_114_is_main_dish_not_soup(index_fixture: InMemoryInvertedIndex):
    """Verify vifoodrec_114 (Lươn nướng sả) is classified as main_dish, NOT soup."""
    meta = index_fixture.get_metadata_by_id("vifoodrec_114")
    assert meta["primary_role"] == "main_dish"
    assert "soup" not in meta["eligible_combo_roles"]
    assert "grilling" in meta["cooking_methods"]


def test_vifoodrec_3199_xoi_mo_not_steaming(index_fixture: InMemoryInvertedIndex):
    """Verify vifoodrec_3199 (Cơm Gà Xối Mỡ) is NOT tagged with steaming."""
    meta = index_fixture.get_metadata_by_id("vifoodrec_3199")
    assert "steaming" not in meta["cooking_methods"]
    assert "deep_frying" in meta["cooking_methods"]


def test_vifoodrec_1217_and_1310_vegetarian_dishes_not_chicken(index_fixture: InMemoryInvertedIndex):
    """Verify vegetarian dishes (Bún Mắm Chay, Miến Xào Chay) do NOT contain chicken/poultry."""
    m_1217 = index_fixture.get_metadata_by_id("vifoodrec_1217")
    assert "chicken" not in m_1217["normalized_ingredients"]
    assert "poultry" not in m_1217["ingredient_groups"]
    assert "steaming" not in m_1217["cooking_methods"]

    m_1310 = index_fixture.get_metadata_by_id("vifoodrec_1310")
    assert "chicken" not in m_1310["normalized_ingredients"]
    assert "poultry" not in m_1310["ingredient_groups"]
    assert "steaming" not in m_1310["cooking_methods"]


def test_vifoodrec_2170_cabbage_juice_not_corn(index_fixture: InMemoryInvertedIndex):
    """Verify vifoodrec_2170 (Nước Ép Táo Và Bắp Cải) does NOT contain corn or grain."""
    meta = index_fixture.get_metadata_by_id("vifoodrec_2170")
    assert "corn" not in meta["normalized_ingredients"]
    assert "grain" not in meta["ingredient_groups"]
    assert "cabbage_greens" in meta["normalized_ingredients"]


def test_vifoodrec_1461_sausage_detected_and_penalized_in_gout(
    index_fixture: InMemoryInvertedIndex,
    ranker_fixture: CandidateRanker
):
    """Verify vifoodrec_1461 detects sausage and is penalized in Gout."""
    meta = index_fixture.get_metadata_by_id("vifoodrec_1461")
    assert "sausage" in meta["normalized_ingredients"]
    assert "meat" in meta["ingredient_groups"]
    assert "steaming" not in meta["cooking_methods"]

    # In Gout query, vifoodrec_1461 must receive clinical avoidance penalty
    res = ConstraintResolver.resolve_constraints(condition_query="bệnh gút")
    pools = ConstraintFilter.filter_candidates(res, index=index_fixture)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)

    main_items = {it.recipe_id: it for it in ranked.ranked_by_role["main_dish"]}
    if "vifoodrec_1461" in main_items:
        it = main_items["vifoodrec_1461"]
        assert "CLINICAL_AVOIDED_INGREDIENT" in it.reason_codes
        assert it.score_breakdown["clinical_preferences"] <= 0.35


# -----------------------------------------------------------------------------
# 4. Score Saturation & Bounding Tests
# -----------------------------------------------------------------------------

def test_score_saturation_prevented():
    """Verify that dishes with multiple matched items don't saturate past bounded maximum."""
    scorer = ContentBasedScorer()
    ctx = ScoringContext()
    ctx.clinical_preferred_ingredients = {"broccoli", "carrot", "spinach", "gourd", "pumpkin"}
    ctx.clinical_preferred_ingredient_groups = {"vegetable", "grain"}

    dish_many_matches = {
        "normalized_ingredients": {"broccoli", "carrot", "spinach", "gourd", "pumpkin"},
        "ingredient_groups": {"vegetable", "grain"},
        "cooking_methods": {"boiling"},
        "static_meta_score": 0.90,
        "static_nutrition_score": 0.50,
        "nutrition_quality_label": "estimated"
    }

    _, bd, _, _, _, _ = scorer.score_recipe(dish_many_matches, ctx)
    # Base 0.50 + max bonus 0.35 = 0.85 (bounded, not 0.50 + 7 * 0.25 = 2.25)
    assert bd["clinical_preferences"] == 0.85


# -----------------------------------------------------------------------------
# 5. Final Quality Gate: Specificity, Cooking Hierarchy, & Clinical Truthfulness
# -----------------------------------------------------------------------------

def test_vifoodrec_197_egg_not_chicken_and_no_user_chicken_bonus(index_fixture: InMemoryInvertedIndex, ranker_fixture: CandidateRanker):
    """Verify vifoodrec_197 (Trứng hấp hàu rong biển) has chicken_egg, NOT chicken meat, and gets no chicken bonus."""
    meta = index_fixture.get_metadata_by_id("vifoodrec_197")
    assert "chicken" not in meta["normalized_ingredients"]
    assert "poultry" not in meta["ingredient_groups"]
    assert "chicken_egg" in meta["normalized_ingredients"]
    assert "egg" in meta["ingredient_groups"]
    assert "oyster" in meta["normalized_ingredients"]
    assert "seafood" in meta["ingredient_groups"]

    # When user likes "gà" (chicken meat), vifoodrec_197 must NOT receive user ingredient bonus
    res_chicken = ConstraintResolver.resolve_constraints(profile={"preferences": ["thịt gà"]})
    ctx_chicken = ScoringContext.from_resolved(res_chicken)
    feat197 = ranker_fixture.feature_extractor.extract_features("vifoodrec_197", index_fixture)
    score, bd, matched, _, rc, _ = ranker_fixture.scorer.score_recipe(feat197, ctx_chicken)

    assert "USER_PREFERRED_INGREDIENT" not in rc
    assert "user_pref_ing:chicken" not in matched
    assert bd["ingredient_preferences"] == 0.50  # Neutral

    # But when user likes "trứng" (egg), vifoodrec_197 must receive user group bonus
    res_egg = ConstraintResolver.resolve_constraints(profile={"preferences": ["trứng"]})
    ctx_egg = ScoringContext.from_resolved(res_egg)
    score_egg, bd_egg, matched_egg, _, rc_egg, _ = ranker_fixture.scorer.score_recipe(feat197, ctx_egg)

    assert "USER_PREFERRED_GROUP" in rc_egg
    assert "user_pref_group:egg" in matched_egg
    assert bd_egg["ingredient_preferences"] > 0.50


def test_specific_ingredient_vs_group_preference():
    """Verify resolver cleanly distinguishes specific ingredient ('gà') vs ingredient group ('gia cầm')."""
    res_specific = ConstraintResolver.resolve_constraints(condition_query="thích ăn thịt gà")
    assert "chicken" in res_specific.user_preferred_ingredients
    assert "poultry" not in res_specific.user_preferred_ingredient_groups

    res_group = ConstraintResolver.resolve_constraints(condition_query="thích ăn thịt gia cầm")
    assert "poultry" in res_group.user_preferred_ingredient_groups
    assert "chicken" not in res_group.user_preferred_ingredients

    res_egg = ConstraintResolver.resolve_constraints(condition_query="thích ăn trứng")
    assert "egg" in res_egg.user_preferred_ingredient_groups

    res_seafood = ConstraintResolver.resolve_constraints(condition_query="thích ăn hải sản")
    assert "seafood" in res_seafood.user_preferred_ingredient_groups


def test_primary_vs_secondary_cooking_methods_steaming(index_fixture: InMemoryInvertedIndex, ranker_fixture: CandidateRanker):
    """Verify primary cooking method receives full bonus while secondary receives partial bonus."""
    # vifoodrec_1885 (Chả Lụa Gà) is primarily steamed
    m1885 = index_fixture.get_metadata_by_id("vifoodrec_1885")
    assert m1885["primary_cooking_method"] == "steaming"
    assert "steaming" in m1885["cooking_methods"]

    # vifoodrec_1057 (Gà cuộn xôi xoài) is primarily pan-seared/stir-fried, secondary steamed
    m1057 = index_fixture.get_metadata_by_id("vifoodrec_1057")
    assert m1057["primary_cooking_method"] == "stir_frying"
    assert "steaming" in m1057["secondary_cooking_methods"]

    # vifoodrec_2232 (Cơm Saffron Cà Ri Gà) is primarily braised, secondary steamed
    m2232 = index_fixture.get_metadata_by_id("vifoodrec_2232")
    assert m2232["primary_cooking_method"] == "braising"
    assert "steaming" in m2232["secondary_cooking_methods"]

    # Evaluate all three under steaming preference
    res_steam = ConstraintResolver.resolve_constraints(user_preferences=["hấp"])
    ctx_steam = ScoringContext.from_resolved(res_steam)

    feat1885 = ranker_fixture.feature_extractor.extract_features("vifoodrec_1885", index_fixture)
    feat1057 = ranker_fixture.feature_extractor.extract_features("vifoodrec_1057", index_fixture)
    feat2232 = ranker_fixture.feature_extractor.extract_features("vifoodrec_2232", index_fixture)

    _, bd1885, _, _, rc1885, _ = ranker_fixture.scorer.score_recipe(feat1885, ctx_steam)
    _, bd1057, _, _, rc1057, _ = ranker_fixture.scorer.score_recipe(feat1057, ctx_steam)
    _, bd2232, _, _, rc2232, _ = ranker_fixture.scorer.score_recipe(feat2232, ctx_steam)

    # Primary steaming receives full 1.0 cooking score
    assert bd1885["cooking_method"] == 1.00
    assert "PREFERRED_COOKING_METHOD" in rc1885

    # Secondary steaming receives partial 0.70 cooking score
    assert bd1057["cooking_method"] == 0.70
    assert "SECONDARY_PREFERRED_COOKING_METHOD" in rc1057
    assert bd2232["cooking_method"] == 0.70
    assert "SECONDARY_PREFERRED_COOKING_METHOD" in rc2232

    # Chả lụa gà strictly receives higher cooking suitability than dishes where steaming is only a side-step
    assert bd1885["cooking_method"] > bd1057["cooking_method"]
    assert bd1885["cooking_method"] > bd2232["cooking_method"]


def test_vifoodrec_2411_no_fake_steaming_from_ot_chung(index_fixture: InMemoryInvertedIndex, ranker_fixture: CandidateRanker):
    """Verify vifoodrec_2411 (Cơm Gà Chính Gốc Hội An) is NOT tagged with steaming from ớt chưng."""
    meta = index_fixture.get_metadata_by_id("vifoodrec_2411")
    assert "steaming" not in meta["cooking_methods"]
    assert meta["primary_cooking_method"] == "boiling"

    res_steam = ConstraintResolver.resolve_constraints(user_preferences=["hấp"])
    ctx_steam = ScoringContext.from_resolved(res_steam)
    feat2411 = ranker_fixture.feature_extractor.extract_features("vifoodrec_2411", index_fixture)
    _, bd, matched, _, rc, _ = ranker_fixture.scorer.score_recipe(feat2411, ctx_steam)

    assert bd["cooking_method"] == 0.50  # Neutral
    assert "PREFERRED_COOKING_METHOD" not in rc
    assert "SECONDARY_PREFERRED_COOKING_METHOD" not in rc

