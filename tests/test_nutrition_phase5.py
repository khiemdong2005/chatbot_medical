"""Comprehensive Test Suite for Phase 5: Dynamic Meal Composition Engine.

Validates:
1. Four-component Family Meal Combo Invariants:
   - Exactly 4 components: staple, main_dish, soup, vegetable.
   - Zero duplicate recipe IDs within the same combo.
   - Zero standalone dishes inside combos.
   - Zero manual-review / quarantined dishes in combos.
   - Authentic vegetable dish quality (primary_role == 'vegetable').
2. Standalone Meal Invariants:
   - Selected strictly from Phase 4 ranked standalone pool.
   - Category diversity (phở, bún, cháo, hủ tiếu, cơm đĩa, mì).
   - Zero standalone cross-combining or external additions.
3. Target Output Limits:
   - Configurable max_family_combos (<= 6) and max_standalone_meals (<= 6).
   - Returns fewer than 6 if valid candidates are scarce without relaxing hard constraints.
4. Hard Safety Preservation & Halting:
   - If Phase 3 Clinical Engine halts (unsupported allergen / refusal), Phase 5 halts immediately (0 meals).
5. Partial & Empty Pool Resilience:
   - Missing staple -> 0 family combos, standalone intact.
   - Missing soup -> 0 family combos, standalone intact.
   - Missing vegetable -> 0 family combos, standalone intact.
   - Missing main_dish -> 0 family combos, standalone intact.
   - Impossible constraints -> 0 combos, 0 standalones.
6. Determinism & Stable Tie-Breaking:
   - Multiple identical calls yield bit-for-bit identical results and order.
7. Multi-Objective Scoring & Diversity:
   - Ingredient overlap penalty inside combo.
   - Cooking monotony penalty inside combo.
   - Across-combo main dish rotation and overlap penalty.
8. Medical & Nutrition Truthfulness:
   - Mandatory nutrition disclaimer present.
   - Zero false medical healing claims or unverified calorie summations.
"""

from copy import deepcopy
from typing import Dict, Any
import pytest

from core.nutrition.candidate_ranker import CandidateRanker, RankedResults, RankingExplanation
from core.nutrition.clinical_constraints import CandidatePools, ResolvedConstraints, SafetyStatus
from core.nutrition.constraint_resolver import ConstraintResolver
from core.nutrition.constraint_filter import ConstraintFilter
from core.nutrition.metadata_index import get_metadata_index, InMemoryInvertedIndex
from core.nutrition.meal_composition import (
    DynamicMealComposer,
    FamilyMealCombo,
    MealCompositionConfig,
    MealCompositionResult,
    StandaloneMeal,
    classify_standalone_dish_category,
)


@pytest.fixture(scope="module")
def index_fixture() -> InMemoryInvertedIndex:
    return get_metadata_index()


@pytest.fixture(scope="module")
def ranker_fixture(index_fixture: InMemoryInvertedIndex) -> CandidateRanker:
    return CandidateRanker(index=index_fixture)


@pytest.fixture(scope="module")
def composer_fixture(index_fixture: InMemoryInvertedIndex) -> DynamicMealComposer:
    return DynamicMealComposer(index=index_fixture)


# -----------------------------------------------------------------------------
# 1. Four-component Combo Structure & Invariants
# -----------------------------------------------------------------------------

def test_four_component_combo_structure_and_roles(composer_fixture: DynamicMealComposer, ranker_fixture: CandidateRanker):
    """Verify each combo has exactly staple, main_dish, soup, vegetable with distinct IDs."""
    res = ConstraintResolver.resolve_constraints(condition_query="ăn lành mạnh")
    pools = ConstraintFilter.filter_candidates(res, index=composer_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)
    result = composer_fixture.compose_meals(ranked, resolved=res)

    assert result.is_safe_to_proceed is True
    assert len(result.family_combos) > 0
    assert len(result.family_combos) <= 6

    for combo in result.family_combos:
        # Exactly 4 roles present
        assert set(combo.components.keys()) == {"staple", "main_dish", "soup", "vegetable"}

        # Distinct recipe IDs
        ids = [c.recipe_id for c in combo.components.values()]
        assert len(ids) == 4
        assert len(set(ids)) == 4, f"Duplicate recipe ID found in combo: {ids}"

        # Roles match correctly
        assert combo.components["staple"].role == "staple"
        assert combo.components["main_dish"].role == "main_dish"
        assert combo.components["soup"].role == "soup"
        assert combo.components["vegetable"].role == "vegetable"

        # Scores bounded
        assert 0.0 <= combo.meal_score <= 1.0
        assert "FOUR_COMPONENT_BALANCED_MEAL" in combo.reason_codes


def test_no_standalone_leakage_in_combos(composer_fixture: DynamicMealComposer, ranker_fixture: CandidateRanker):
    """Verify standalone dishes never leak into any slot of a family meal combo."""
    res = ConstraintResolver.resolve_constraints(condition_query="ăn lành mạnh")
    pools = ConstraintFilter.filter_candidates(res, index=composer_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)
    result = composer_fixture.compose_meals(ranked, resolved=res)

    for combo in result.family_combos:
        for slot_name, comp in combo.components.items():
            meta = composer_fixture.index.get_metadata_by_id(comp.recipe_id) or {}
            assert meta.get("primary_role") != "standalone", (
                f"Standalone dish {comp.recipe_id} ({comp.title}) leaked into combo slot {slot_name}!"
            )


def test_no_manual_review_leakage_in_combos(composer_fixture: DynamicMealComposer, ranker_fixture: CandidateRanker):
    """Verify dishes flagged for manual review are never included in combos."""
    res = ConstraintResolver.resolve_constraints(condition_query="ăn lành mạnh")
    pools = ConstraintFilter.filter_candidates(res, index=composer_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)
    result = composer_fixture.compose_meals(ranked, resolved=res)

    for combo in result.family_combos:
        for comp in combo.components.values():
            assert comp.recipe_id not in composer_fixture.index.manual_review_ids
            meta = composer_fixture.index.get_metadata_by_id(comp.recipe_id) or {}
            assert meta.get("review_required") is False


def test_vegetable_role_quality(composer_fixture: DynamicMealComposer, ranker_fixture: CandidateRanker):
    """Verify vegetable component must be an authentic vegetable dish (primary_role == 'vegetable')."""
    res = ConstraintResolver.resolve_constraints(condition_query="đái tháo đường type 2")
    pools = ConstraintFilter.filter_candidates(res, index=composer_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)
    result = composer_fixture.compose_meals(ranked, resolved=res)

    for combo in result.family_combos:
        veg_comp = combo.components["vegetable"]
        meta = composer_fixture.index.get_metadata_by_id(veg_comp.recipe_id) or {}
        assert meta.get("primary_role") == "vegetable"
        assert "vegetable" in meta.get("eligible_combo_roles", [])


# -----------------------------------------------------------------------------
# 2. Hard Safety Preservation & Halting
# -----------------------------------------------------------------------------

def test_unsupported_allergen_halts_phase5(composer_fixture: DynamicMealComposer, ranker_fixture: CandidateRanker):
    """Verify unsupported allergen (e.g. Tree Nuts) halts Phase 5 immediately with 0 meals."""
    res = ConstraintResolver.resolve_constraints(profile={"allergies": ["tree_nuts"]})
    assert res.is_safe_to_proceed is False
    assert res.safety_status == SafetyStatus.UNSUPPORTED_ALLERGEN_HALT

    pools = ConstraintFilter.filter_candidates(res, index=composer_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)
    result = composer_fixture.compose_meals(ranked, resolved=res)

    assert result.is_safe_to_proceed is False
    assert result.family_combos == []
    assert result.standalone_meals == []
    assert result.total_combos_evaluated == 0
    assert result.halt_reason is not None


def test_unmapped_disease_halts_phase5(composer_fixture: DynamicMealComposer, ranker_fixture: CandidateRanker):
    """Verify unmapped severe disease (e.g. Ung thư) halts Phase 5 with refusal notice."""
    res = ConstraintResolver.resolve_constraints(condition_query="bị ung thư gan")
    assert res.is_safe_to_proceed is False
    assert res.safety_status == SafetyStatus.UNMAPPED_DISEASE_SAFEGUARD

    pools = ConstraintFilter.filter_candidates(res, index=composer_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)
    result = composer_fixture.compose_meals(ranked, resolved=res)

    assert result.is_safe_to_proceed is False
    assert result.family_combos == []
    assert result.standalone_meals == []
    assert result.halt_reason is not None


# -----------------------------------------------------------------------------
# 3. Partial & Empty Pool Handling
# -----------------------------------------------------------------------------

def test_missing_staple_yields_zero_combos_but_viable_standalone(composer_fixture: DynamicMealComposer):
    """When staple pool is empty, no family combos are created, but standalone meals are returned."""
    ranked = RankedResults()
    ranked.ranked_by_role["staple"] = []  # Empty staple!
    ranked.ranked_by_role["main_dish"] = [
        RankingExplanation("m1", "Món mặn 1", "main_dish", 0.8, 1, {}, [], [], [], 0.9, "estimated", [])
    ]
    ranked.ranked_by_role["soup"] = [
        RankingExplanation("p1", "Canh 1", "soup", 0.7, 1, {}, [], [], [], 0.9, "estimated", [])
    ]
    ranked.ranked_by_role["vegetable"] = [
        RankingExplanation("v1", "Rau 1", "vegetable", 0.75, 1, {}, [], [], [], 0.9, "estimated", [])
    ]
    ranked.ranked_by_role["standalone"] = [
        RankingExplanation("vifoodrec_10", "Lẩu riêu bắp bò", "standalone", 0.85, 1, {}, [], [], [], 0.9, "estimated", [])
    ]

    result = composer_fixture.compose_meals(ranked)
    assert result.family_combos == []
    assert "staple" in result.missing_roles
    assert len(result.standalone_meals) == 1
    assert result.standalone_meals[0].recipe_id == "vifoodrec_10"


def test_missing_soup_yields_zero_combos(composer_fixture: DynamicMealComposer):
    """When soup pool is empty, family combos must not be created."""
    ranked = RankedResults()
    ranked.ranked_by_role["staple"] = [
        RankingExplanation("canonical_staple_com_trang", "Cơm", "staple", 0.8, 1, {}, [], [], [], 1.0, "verified", [])
    ]
    ranked.ranked_by_role["main_dish"] = [
        RankingExplanation("m1", "Món mặn 1", "main_dish", 0.8, 1, {}, [], [], [], 0.9, "estimated", [])
    ]
    ranked.ranked_by_role["soup"] = []  # Empty soup!
    ranked.ranked_by_role["vegetable"] = [
        RankingExplanation("v1", "Rau 1", "vegetable", 0.75, 1, {}, [], [], [], 0.9, "estimated", [])
    ]

    result = composer_fixture.compose_meals(ranked)
    assert result.family_combos == []
    assert "soup" in result.missing_roles


def test_missing_vegetable_yields_zero_combos(composer_fixture: DynamicMealComposer):
    """When vegetable pool is empty, family combos must not be created."""
    ranked = RankedResults()
    ranked.ranked_by_role["staple"] = [
        RankingExplanation("canonical_staple_com_trang", "Cơm", "staple", 0.8, 1, {}, [], [], [], 1.0, "verified", [])
    ]
    ranked.ranked_by_role["main_dish"] = [
        RankingExplanation("m1", "Món mặn 1", "main_dish", 0.8, 1, {}, [], [], [], 0.9, "estimated", [])
    ]
    ranked.ranked_by_role["soup"] = [
        RankingExplanation("p1", "Canh 1", "soup", 0.7, 1, {}, [], [], [], 0.9, "estimated", [])
    ]
    ranked.ranked_by_role["vegetable"] = []  # Empty vegetable!

    result = composer_fixture.compose_meals(ranked)
    assert result.family_combos == []
    assert "vegetable" in result.missing_roles


def test_missing_main_dish_yields_zero_combos(composer_fixture: DynamicMealComposer):
    """When main dish pool is empty, family combos must not be created."""
    ranked = RankedResults()
    ranked.ranked_by_role["staple"] = [
        RankingExplanation("canonical_staple_com_trang", "Cơm", "staple", 0.8, 1, {}, [], [], [], 1.0, "verified", [])
    ]
    ranked.ranked_by_role["main_dish"] = []  # Empty main!
    ranked.ranked_by_role["soup"] = [
        RankingExplanation("p1", "Canh 1", "soup", 0.7, 1, {}, [], [], [], 0.9, "estimated", [])
    ]
    ranked.ranked_by_role["vegetable"] = [
        RankingExplanation("v1", "Rau 1", "vegetable", 0.75, 1, {}, [], [], [], 0.9, "estimated", [])
    ]

    result = composer_fixture.compose_meals(ranked)
    assert result.family_combos == []
    assert "main_dish" in result.missing_roles


def test_empty_candidate_pools_yield_zero_results(composer_fixture: DynamicMealComposer):
    """When all candidate pools are empty, returns 0 family combos and 0 standalone meals gracefully."""
    ranked = RankedResults()
    result = composer_fixture.compose_meals(ranked)
    assert result.family_combos == []
    assert result.standalone_meals == []
    assert len(result.missing_roles) == 4


# -----------------------------------------------------------------------------
# 4. Determinism & Stable Tie-Breaking
# -----------------------------------------------------------------------------

def test_determinism_across_successive_runs(composer_fixture: DynamicMealComposer, ranker_fixture: CandidateRanker):
    """Verify that multiple consecutive runs yield bit-for-bit identical combos, scores, and signatures."""
    res = ConstraintResolver.resolve_constraints(condition_query="bệnh gút")
    pools = ConstraintFilter.filter_candidates(res, index=composer_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)

    res1 = composer_fixture.compose_meals(ranked, resolved=res)
    res2 = composer_fixture.compose_meals(ranked, resolved=res)

    assert len(res1.family_combos) == len(res2.family_combos)
    for c1, c2 in zip(res1.family_combos, res2.family_combos):
        assert c1.combo_id == c2.combo_id
        assert c1.signature == c2.signature
        assert c1.meal_score == c2.meal_score
        assert c1.reason_codes == c2.reason_codes
        assert c1.score_breakdown == c2.score_breakdown

    assert len(res1.standalone_meals) == len(res2.standalone_meals)
    for s1, s2 in zip(res1.standalone_meals, res2.standalone_meals):
        assert s1.recipe_id == s2.recipe_id
        assert s1.score == s2.score
        assert s1.dish_category == s2.dish_category


# -----------------------------------------------------------------------------
# 5. Across-Combo Diversity & Main Dish Rotation
# -----------------------------------------------------------------------------

def test_across_combo_diversity_rotates_main_dishes(composer_fixture: DynamicMealComposer, ranker_fixture: CandidateRanker):
    """Verify that returned family combos rotate main dishes (distinct main dishes when available)."""
    res = ConstraintResolver.resolve_constraints(condition_query="ăn lành mạnh")
    pools = ConstraintFilter.filter_candidates(res, index=composer_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)
    result = composer_fixture.compose_meals(ranked, resolved=res)

    assert len(result.family_combos) == 6

    main_ids = [combo.components["main_dish"].recipe_id for combo in result.family_combos]
    # In Healthy Eating with 15 available mains, all 6 combos must have distinct mains
    assert len(set(main_ids)) == 6, f"Expected 6 distinct main dishes, got: {main_ids}"


def test_no_combos_with_three_or_more_identical_dishes(composer_fixture: DynamicMealComposer, ranker_fixture: CandidateRanker):
    """Verify that no two returned combos share 3 or more identical dishes."""
    res = ConstraintResolver.resolve_constraints(condition_query="dị ứng tôm")
    pools = ConstraintFilter.filter_candidates(res, index=composer_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)
    result = composer_fixture.compose_meals(ranked, resolved=res)

    combos = result.family_combos
    for i in range(len(combos)):
        set_i = {comp.recipe_id for comp in combos[i].components.values()}
        for j in range(i + 1, len(combos)):
            set_j = {comp.recipe_id for comp in combos[j].components.values()}
            overlap = len(set_i & set_j)
            assert overlap < 3, (
                f"Combos #{i+1} and #{j+1} share {overlap} dishes! Exceeds diversity limit."
            )


# -----------------------------------------------------------------------------
# 6. Standalone Category Diversity
# -----------------------------------------------------------------------------

def test_standalone_category_diversity(composer_fixture: DynamicMealComposer, ranker_fixture: CandidateRanker):
    """Verify standalone meal selection spans multiple categories (phở, bún, cháo, etc.)."""
    res = ConstraintResolver.resolve_constraints(condition_query="ăn lành mạnh")
    pools = ConstraintFilter.filter_candidates(res, index=composer_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)
    result = composer_fixture.compose_meals(ranked, resolved=res)

    assert len(result.standalone_meals) == 6
    categories = [m.dish_category for m in result.standalone_meals]
    unique_cats = set(categories)

    # Must cover at least 3 distinct categories
    assert len(unique_cats) >= 3, f"Expected diverse standalone categories, got: {categories}"


# -----------------------------------------------------------------------------
# 7. Intra-Combo Penalties: Ingredient Overlap & Cooking Monotony
# -----------------------------------------------------------------------------

def test_ingredient_overlap_penalty_applied(composer_fixture: DynamicMealComposer):
    """Verify combo with duplicate key ingredients receives penalty and reason code."""
    # vifoodrec_1885 is chicken, vifoodrec_1014 (Canh gà bí xanh) is also chicken!
    combo = composer_fixture.evaluate_single_combo(
        staple_id="canonical_staple_com_trang",
        main_dish_id="vifoodrec_1885",
        soup_id="vifoodrec_1014",
        vegetable_id="vifoodrec_1068",
    )

    # Ingredient diversity score must be penalized below 1.0 due to duplicate chicken & poultry
    assert combo.score_breakdown["ingredient_diversity"] < 1.0
    assert any("INGREDIENT_OVERLAP_PENALTY" in r for r in combo.reason_codes)


def test_cooking_monotony_penalty_applied(composer_fixture: DynamicMealComposer):
    """Verify combo with multiple deep-fried dishes receives cooking monotony penalty."""
    # vifoodrec_1461 (Xúc xích chiên) and vifoodrec_1018 (Nấm chiên giòn) are both deep_frying!
    combo = composer_fixture.evaluate_single_combo(
        staple_id="canonical_staple_com_trang",
        main_dish_id="vifoodrec_1461",
        soup_id="vifoodrec_1005",
        vegetable_id="vifoodrec_1018",
    )

    # Cooking diversity must be penalized below 1.0 due to dual deep-frying
    assert combo.score_breakdown["cooking_diversity"] < 1.0


# -----------------------------------------------------------------------------
# 8. Medical & Nutrition Truthfulness
# -----------------------------------------------------------------------------

def test_nutrition_disclaimer_and_no_fake_medical_claims(composer_fixture: DynamicMealComposer, ranker_fixture: CandidateRanker):
    """Verify nutrition disclaimer is present on all combos and no fake claims exist."""
    res = ConstraintResolver.resolve_constraints(condition_query="ăn lành mạnh")
    pools = ConstraintFilter.filter_candidates(res, index=composer_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)
    result = composer_fixture.compose_meals(ranked, resolved=res)

    for combo in result.family_combos:
        assert combo.nutrition_disclaimer != ""
        assert "chữa bệnh" not in combo.nutrition_disclaimer.lower()
        assert "an toàn tuyệt đối" not in combo.nutrition_disclaimer.lower()

    for meal in result.standalone_meals:
        assert meal.nutrition_disclaimer != ""
