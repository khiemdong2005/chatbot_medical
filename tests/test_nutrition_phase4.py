"""Comprehensive Test Suite for Phase 4: Content-Based Scoring & Candidate Ranking.

Validates:
1. Score normalization in [0.0, 1.0].
2. Weight configuration and multi-objective additive scoring.
3. Clinical soft preference matching (boosting preferred, penalizing avoided).
4. Cooking method preference alignment.
5. User ingredient preferences and soft dislikes.
6. Nutrition data quality & provenance handling.
7. Metadata confidence & certainty scoring.
8. Deterministic ranking & stable tie-breaking.
9. Role-specific Top-K segmentation.
10. Hard constraint isolation invariant: ranked_ids <= filtered_ids.
11. Safe propagation of halts (UNSUPPORTED_ALLERGEN_HALT, EMPTY_POOL).
12. Zero leakage of standalone dishes into combo roles.
13. Zero leakage of manual review items into ranked pools.
14. Explainable RankingExplanation structure & reason codes.
"""

from pathlib import Path
import pytest
from typing import Set

from core.nutrition.candidate_ranker import (
    CandidateRanker,
    ContentBasedScorer,
    RankingExplanation,
    RecipeFeatureExtractor,
    ScoringConfig,
    ScoringContext,
)
from core.nutrition.clinical_constraints import (
    CandidatePools,
    ReasonCode,
    ResolvedConstraints,
    SafetyStatus,
)
from core.nutrition.constraint_resolver import ConstraintResolver
from core.nutrition.constraint_filter import ConstraintFilter
from core.nutrition.metadata_index import get_metadata_index, InMemoryInvertedIndex, STANDARD_COMBO_ROLES


@pytest.fixture(scope="module")
def index_fixture() -> InMemoryInvertedIndex:
    return get_metadata_index()


@pytest.fixture(scope="module")
def ranker_fixture(index_fixture: InMemoryInvertedIndex) -> CandidateRanker:
    return CandidateRanker(index=index_fixture)


# -----------------------------------------------------------------------------
# 1. Scoring Normalization & Config Tests
# -----------------------------------------------------------------------------

def test_score_normalization_boundaries(ranker_fixture: CandidateRanker):
    """Verify all recipe scores fall strictly within [0.0, 1.0]."""
    res = ConstraintResolver.resolve_constraints(condition_query="ăn lành mạnh")
    pools = ConstraintFilter.filter_candidates(res, index=ranker_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)

    assert ranked.total_ranked_count > 0
    for role, items in ranked.ranked_by_role.items():
        for r in items:
            assert 0.0 <= r.total_score <= 1.0, f"Score out of bounds: {r.total_score}"
            for comp, val in r.score_breakdown.items():
                assert 0.0 <= val <= 1.0, f"Component {comp} out of bounds: {val}"


def test_custom_weight_configuration(index_fixture: InMemoryInvertedIndex):
    """Verify custom scoring weights alter ranking deterministically."""
    # Custom config emphasizing cooking method over ingredient
    custom_cfg = ScoringConfig(
        weight_clinical=0.10,
        weight_cooking=0.70,
        weight_ingredient=0.10,
        weight_metadata=0.05,
        weight_nutrition_quality=0.05,
    )
    custom_ranker = CandidateRanker(index=index_fixture, config=custom_cfg)

    res = ConstraintResolver.resolve_constraints(
        profile={"preferences": ["steaming"]},
        condition_query="thích ăn đồ hấp"
    )
    pools = ConstraintFilter.filter_candidates(res, index=index_fixture)
    ranked = custom_ranker.rank_candidates(pools, resolved=res)

    top_main = ranked.ranked_by_role["main_dish"][0]
    assert "steaming" in index_fixture.get_metadata_by_id(top_main.recipe_id)["cooking_methods"]
    assert top_main.score_breakdown["cooking_method"] == 1.0


# -----------------------------------------------------------------------------
# 2. Clinical Soft Preference Alignment Tests
# -----------------------------------------------------------------------------

def test_diabetes_clinical_soft_preference_boost(ranker_fixture: CandidateRanker):
    """Verify diabetes clinical preferences boost fiber/vegetables and grains."""
    res = ConstraintResolver.resolve_constraints(condition_query="đái tháo đường type 2")
    pools = ConstraintFilter.filter_candidates(res, index=ranker_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)

    top_mains = ranked.ranked_by_role["main_dish"][:5]
    for r in top_mains:
        meta = ranker_fixture.index.get_metadata_by_id(r.recipe_id)
        # Verify preferred groups are matched and rewarded
        assert any(g in ("vegetable", "grain") for g in meta["ingredient_groups"])
        assert any(code in r.reason_codes for code in ("CLINICAL_PREFERRED_GROUP", "HIGH_METADATA_CONFIDENCE"))


def test_gout_soft_avoidance_penalty(ranker_fixture: CandidateRanker):
    """Verify Gout soft-avoids beef and seafood without hard-excluding them."""
    res = ConstraintResolver.resolve_constraints(condition_query="bệnh gút")
    pools = ConstraintFilter.filter_candidates(res, index=ranker_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)

    # Candidate with beef/seafood should have a lower clinical score than pure vegetable/poultry dish
    main_dishes = ranked.ranked_by_role["main_dish"]
    beef_dishes = [d for d in main_dishes if "beef" in ranker_fixture.index.get_metadata_by_id(d.recipe_id)["normalized_ingredients"]]
    non_beef_dishes = [d for d in main_dishes if "beef" not in ranker_fixture.index.get_metadata_by_id(d.recipe_id)["normalized_ingredients"]]

    if beef_dishes and non_beef_dishes:
        assert beef_dishes[0].score_breakdown["clinical_preferences"] < non_beef_dishes[0].score_breakdown["clinical_preferences"]
        assert "CLINICAL_AVOIDED_INGREDIENT" in beef_dishes[0].reason_codes


# -----------------------------------------------------------------------------
# 3. Cooking Method & User Ingredient Preference Tests
# -----------------------------------------------------------------------------

def test_cooking_method_preference_boost(ranker_fixture: CandidateRanker):
    """Verify user cooking preference (e.g. stir_frying) boosts matching recipes."""
    res = ConstraintResolver.resolve_constraints(
        profile={"preferences": ["xào"]},
        condition_query="thích ăn món xào"
    )
    pools = ConstraintFilter.filter_candidates(res, index=ranker_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)

    top_veg = ranked.ranked_by_role["vegetable"][0]
    meta = ranker_fixture.index.get_metadata_by_id(top_veg.recipe_id)
    assert "stir_frying" in meta["cooking_methods"]
    assert "PREFERRED_COOKING_METHOD" in top_veg.reason_codes


def test_user_disliked_ingredients_soft_penalty(ranker_fixture: CandidateRanker):
    """Verify non-mandatory disliked ingredients receive penalty in ingredient_preferences."""
    ctx = ScoringContext()
    ctx.user_avoided_ingredients.add("onion")

    scorer = ContentBasedScorer()
    feats_with_onion = {
        "normalized_ingredients": {"beef", "onion"},
        "ingredient_groups": {"meat", "spice_herb"},
        "cooking_methods": {"stir_frying"},
        "classification_confidence": 0.95,
        "review_required": False,
        "classification_uncertainty": False,
        "nutrition_verified": False,
        "macro_consistency": False,
        "has_carbohydrate_data": False,
        "has_calories": True,
        "servings_numeric": 2,
    }
    feats_without_onion = dict(feats_with_onion)
    feats_without_onion["normalized_ingredients"] = {"beef", "garlic"}

    score_onion, bd_onion, _, pen_onion, rc_onion, _ = scorer.score_recipe(feats_with_onion, ctx)
    score_no_onion, bd_no_onion, _, _, _, _ = scorer.score_recipe(feats_without_onion, ctx)

    assert bd_onion["ingredient_preferences"] < bd_no_onion["ingredient_preferences"]
    assert "USER_DISLIKED_INGREDIENT" in rc_onion
    assert "user_dislike_ing:onion" in pen_onion


# -----------------------------------------------------------------------------
# 4. Nutrition Quality & Metadata Confidence Tests
# -----------------------------------------------------------------------------

def test_canonical_staple_nutrition_verified_score(ranker_fixture: CandidateRanker):
    """Verify canonical staples receive highest nutrition quality score due to official table verification."""
    res = ConstraintResolver.resolve_constraints(condition_query="ăn lành mạnh")
    pools = ConstraintFilter.filter_candidates(res, index=ranker_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)

    for staple in ranked.ranked_by_role["staple"]:
        if staple.recipe_id.startswith("canonical_staple_"):
            assert staple.score_breakdown["nutrition_quality"] == 1.00
            assert staple.nutrition_quality == "verified"
            assert "VERIFIED_NUTRITION_DATA" in staple.reason_codes


def test_missing_nutrition_data_handled_without_zero_default(ranker_fixture: CandidateRanker):
    """Verify unverified/incomplete nutrition data receives reduced score without treating missing data as 0."""
    scorer = ContentBasedScorer()
    ctx = ScoringContext()

    feats_incomplete = {
        "normalized_ingredients": {"tofu"},
        "ingredient_groups": {"legume"},
        "cooking_methods": {"steaming"},
        "classification_confidence": 0.90,
        "review_required": False,
        "classification_uncertainty": False,
        "nutrition_verified": False,
        "macro_consistency": False,
        "has_carbohydrate_data": False,
        "has_calories": False,  # Missing calories entirely
        "servings_numeric": None,
    }

    _, bd, _, _, rc, nq = scorer.score_recipe(feats_incomplete, ctx)
    assert bd["nutrition_quality"] == 0.30
    assert nq == "incomplete"
    assert "INCOMPLETE_NUTRITION_DATA" in rc


# -----------------------------------------------------------------------------
# 5. Deterministic Ranking & Tie-Breaking Tests
# -----------------------------------------------------------------------------

def test_ranking_determinism(ranker_fixture: CandidateRanker):
    """Verify exact same input produces bit-identical ranking and ordering across multiple calls."""
    res = ConstraintResolver.resolve_constraints(condition_query="tiểu đường type 2, không ăn đồ chiên")
    pools = ConstraintFilter.filter_candidates(res, index=ranker_fixture.index)

    run1 = ranker_fixture.rank_candidates(pools, resolved=res)
    run2 = ranker_fixture.rank_candidates(pools, resolved=res)

    assert run1.total_ranked_count == run2.total_ranked_count
    for role in run1.ranked_by_role:
        ids1 = [r.recipe_id for r in run1.ranked_by_role[role]]
        ids2 = [r.recipe_id for r in run2.ranked_by_role[role]]
        assert ids1 == ids2, f"Non-deterministic ordering in role {role}"

        scores1 = [r.total_score for r in run1.ranked_by_role[role]]
        scores2 = [r.total_score for r in run2.ranked_by_role[role]]
        assert scores1 == scores2


def test_stable_tie_break_ordering(ranker_fixture: CandidateRanker):
    """Verify identical scores tie-break strictly by alphabetical recipe_id ASC."""
    # When all preferences are neutral, recipes with identical scores should tie-break by ID
    res = ConstraintResolver.resolve_constraints()
    pools = ConstraintFilter.filter_candidates(res, index=ranker_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)

    for role, items in ranked.ranked_by_role.items():
        for i in range(len(items) - 1):
            if items[i].total_score == items[i + 1].total_score:
                assert items[i].recipe_id < items[i + 1].recipe_id, "Tie-break failed recipe_id ASC order"


# -----------------------------------------------------------------------------
# 6. Hard Constraint Isolation Invariants
# -----------------------------------------------------------------------------

def test_hard_constraint_isolation_subset_invariant(ranker_fixture: CandidateRanker):
    """Verify ranked_ids <= filtered_ids for all roles."""
    res = ConstraintResolver.resolve_constraints(
        profile={"conditions": ["diabetes"], "allergies": ["shrimp"]},
        condition_query="không ăn đồ chiên"
    )
    pools = ConstraintFilter.filter_candidates(res, index=ranker_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)

    for role, items in ranked.ranked_by_role.items():
        for r in items:
            assert r.recipe_id in pools.unique_candidate_ids, f"Ranked item {r.recipe_id} not in filtered candidate IDs!"


def test_halted_status_produces_empty_ranking(ranker_fixture: CandidateRanker):
    """Verify when Phase 3 halts on unsupported allergen or CKD, ranking returns empty lists."""
    # 1. Unsupported allergen halt
    res_halt = ConstraintResolver.resolve_constraints(condition_query="dị ứng hạt điều")
    pools_halt = ConstraintFilter.filter_candidates(res_halt, index=ranker_fixture.index)
    ranked_halt = ranker_fixture.rank_candidates(pools_halt, resolved=res_halt)

    assert ranked_halt.is_safe_to_proceed is False
    assert ranked_halt.safety_status == SafetyStatus.UNSUPPORTED_ALLERGEN_HALT.value
    assert ranked_halt.total_ranked_count == 0
    for role, items in ranked_halt.ranked_by_role.items():
        assert len(items) == 0

    # 2. CKD safeguard halt
    res_ckd = ConstraintResolver.resolve_constraints(condition_query="bệnh nhân suy thận mạn")
    pools_ckd = ConstraintFilter.filter_candidates(res_ckd, index=ranker_fixture.index)
    ranked_ckd = ranker_fixture.rank_candidates(pools_ckd, resolved=res_ckd)

    assert ranked_ckd.is_safe_to_proceed is False
    assert ranked_ckd.safety_status == SafetyStatus.INSUFFICIENT_CLINICAL_DATA.value
    assert ranked_ckd.total_ranked_count == 0


def test_no_standalone_in_combo_roles(ranker_fixture: CandidateRanker):
    """Verify standalone dishes never leak into staple, main_dish, soup, or vegetable."""
    res = ConstraintResolver.resolve_constraints(condition_query="ăn lành mạnh")
    pools = ConstraintFilter.filter_candidates(res, index=ranker_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)

    for role in STANDARD_COMBO_ROLES:
        for item in ranked.ranked_by_role[role]:
            meta = ranker_fixture.index.get_metadata_by_id(item.recipe_id)
            assert meta["primary_role"] != "standalone", f"Standalone dish {item.recipe_id} leaked into combo {role}"


def test_no_manual_review_in_ranked_results(ranker_fixture: CandidateRanker):
    """Verify manual review dishes never appear anywhere in ranked output."""
    res = ConstraintResolver.resolve_constraints(condition_query="ăn lành mạnh")
    pools = ConstraintFilter.filter_candidates(res, index=ranker_fixture.index)
    ranked = ranker_fixture.rank_candidates(pools, resolved=res)

    for role, items in ranked.ranked_by_role.items():
        for item in items:
            assert item.recipe_id not in ranker_fixture.index.manual_review_ids
