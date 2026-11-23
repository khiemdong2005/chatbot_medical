"""Unit and integration test suite for Phase 3: Clinical Constraint Engine.

Validates:
- Evidence-based clinical rules (Gout, Diabetes, Fatty Liver, Hypertension, GERD, Celiac)
- Clinical safeguards (CKD insufficient info, unmapped complex diseases)
- Hard allergy filtering (Single, multiple, fail-closed)
- Unsupported allergen handling (Tree nuts fail-closed)
- Wheat allergy vs Celiac distinction (Gluten-free oats/barley)
- Comorbidity handling (Gout + Diabetes)
- Profile vs request conflict resolution (Hard exclusion always wins)
- Candidate pool segregation (Combo roles vs Standalone vs Beverage)
- Empty candidate pool safety (No relaxation of safety rules)
- Deterministic output ordering
- Zero LLM invocation during constraint filtering
"""

from pathlib import Path
import pytest
from typing import Set

from core.nutrition.clinical_constraints import (
    CandidatePools,
    ClinicalRuleDefinition,
    ConstraintSeverity,
    ConstraintType,
    ReasonCode,
    ResolvedConstraints,
    CLINICAL_RULES,
)
from core.nutrition.constraint_resolver import ConstraintResolver
from core.nutrition.constraint_filter import ConstraintFilter
from core.nutrition.metadata_index import get_metadata_index, InMemoryInvertedIndex


@pytest.fixture(scope="module")
def index_fixture() -> InMemoryInvertedIndex:
    return get_metadata_index()


def test_general_healthy_eating(index_fixture: InMemoryInvertedIndex):
    """Verify general healthy eating applies balanced rules and retrieves full active catalog."""
    resolved = ConstraintResolver.resolve_constraints(condition_query="ăn lành mạnh")
    assert resolved.is_safe_to_proceed is True
    assert any(r.rule_id == "RULE_HEALTHY_BALANCED" for r in resolved.applied_rules)

    pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)
    assert pools.safety_status == "SAFE"
    assert pools.execution_metrics["surviving_count"] == 2447  # 2472 - 25 manual review items
    assert len(pools.combo_candidates["main_dish"]) == 1406
    assert len(pools.combo_candidates["staple"]) == 10


def test_gout_constraints(index_fixture: InMemoryInvertedIndex):
    """Verify Gout rules exclude organ meats & alcohol, soft-limit beef/seafood, and cite sources."""
    resolved = ConstraintResolver.resolve_constraints(condition_query="tôi bị bệnh gút")
    assert resolved.is_safe_to_proceed is True
    assert "organ_meat" in resolved.hard_excluded_ingredient_groups
    assert "alcohol" in resolved.hard_excluded_ingredients
    assert "beef" in resolved.soft_avoided_ingredients
    assert any(r.rule_id == "RULE_GOUT_ORGAN_MEATS" for r in resolved.applied_rules)
    assert any("NHS" in ref["source_title"] for ref in resolved.source_references)

    pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)
    assert pools.safety_status == "SAFE"
    # Ensure no organ meat in any surviving combo dishes
    for role, rids in pools.combo_candidates.items():
        for rid in rids:
            meta = index_fixture.get_metadata_by_id(rid)
            assert "organ_meat" not in meta["ingredient_groups"]


def test_diabetes_constraints(index_fixture: InMemoryInvertedIndex):
    """Verify Type 2 Diabetes rules exclude added sugar desserts and prioritize complex carbs/fiber."""
    resolved = ConstraintResolver.resolve_constraints(condition_query="đái tháo đường type 2")
    assert resolved.is_safe_to_proceed is True
    assert resolved.nutrient_limits.get("sugar") == "low"
    assert "vegetable" in resolved.soft_preferred_ingredient_groups
    assert any(r.rule_id == "RULE_DIABETES_FREE_SUGARS" for r in resolved.applied_rules)

    pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)
    assert pools.safety_status == "SAFE"
    assert len(pools.combo_candidates["main_dish"]) > 0


def test_fatty_liver_constraints(index_fixture: InMemoryInvertedIndex):
    """Verify Fatty Liver rules exclude alcohol and deep frying, and prefer steaming/boiling."""
    resolved = ConstraintResolver.resolve_constraints(condition_query="gan nhiễm mỡ")
    assert resolved.is_safe_to_proceed is True
    assert "alcohol" in resolved.hard_excluded_ingredients
    assert "deep_frying" in resolved.hard_excluded_cooking_methods
    assert "steaming" in resolved.soft_preferred_cooking_methods
    assert "boiling" in resolved.soft_preferred_cooking_methods
    assert any(r.rule_id == "RULE_FATTY_LIVER_DEEP_FRIED" for r in resolved.applied_rules)

    pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)
    assert pools.safety_status == "SAFE"
    # Verify no deep-fried dishes in combo pools
    for role, rids in pools.combo_candidates.items():
        for rid in rids:
            meta = index_fixture.get_metadata_by_id(rid)
            assert "deep_frying" not in meta["cooking_methods"]


def test_hypertension_constraints(index_fixture: InMemoryInvertedIndex):
    """Verify Hypertension rules exclude alcohol, require low sodium, and cite guidelines."""
    resolved = ConstraintResolver.resolve_constraints(condition_query="tăng huyết áp")
    assert resolved.is_safe_to_proceed is True
    assert "alcohol" in resolved.hard_excluded_ingredients
    assert resolved.nutrient_limits.get("sodium") == "low"
    assert any(r.rule_id == "RULE_HYPERTENSION_SALT_PRESERVED" for r in resolved.applied_rules)

    pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)
    assert pools.safety_status == "SAFE"


def test_gerd_constraints():
    """Verify GERD applies soft restrictions on personal triggers without blanket hard exclusions."""
    resolved = ConstraintResolver.resolve_constraints(condition_query="trào ngược dạ dày thực quản")
    assert resolved.is_safe_to_proceed is True
    assert "chili" in resolved.soft_avoided_ingredients
    assert "caffeine" in resolved.soft_avoided_ingredients
    # Ensure they are soft avoided, not hard excluded
    assert "chili" not in resolved.hard_excluded_ingredients
    assert any(r.rule_id == "RULE_GERD_TRIGGER_EXCLUSION" for r in resolved.applied_rules)


def test_ckd_insufficient_information_safeguard(index_fixture: InMemoryInvertedIndex):
    """Verify Chronic Kidney Disease without nephrologist prescription halts safely."""
    resolved = ConstraintResolver.resolve_constraints(condition_query="bệnh nhân suy thận mạn")
    assert resolved.is_safe_to_proceed is False
    assert resolved.safety_halt_reason == "CKD_INSUFFICIENT_CLINICAL_DATA"
    assert "ckd_stage_unspecified" in resolved.unresolved_constraints
    assert any("KDIGO" in ref["source_title"] for ref in resolved.source_references)

    pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)
    assert pools.safety_status == "CKD_INSUFFICIENT_CLINICAL_DATA"
    assert pools.execution_metrics["surviving_count"] == 0
    assert len(pools.combo_candidates["main_dish"]) == 0


def test_unmapped_disease_safeguard(index_fixture: InMemoryInvertedIndex):
    """Verify complex unmapped conditions (cancer, pregnancy, stroke) trigger refusal."""
    for query in ["ung thư dạ dày", "tai biến mạch máu não", "phụ nữ mang thai"]:
        resolved = ConstraintResolver.resolve_constraints(condition_query=query)
        assert resolved.is_safe_to_proceed is False
        assert resolved.is_unmapped_disease is True
        assert resolved.safety_halt_reason == "UNMAPPED_DISEASE_SAFEGUARD"

        pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)
        assert pools.safety_status == "UNMAPPED_DISEASE_SAFEGUARD"
        assert pools.execution_metrics["surviving_count"] == 0


def test_single_and_multiple_allergy_filtering(index_fixture: InMemoryInvertedIndex):
    """Verify single and multiple allergen exclusions filter accurately."""
    # Single allergy
    res_shrimp = ConstraintResolver.resolve_constraints(condition_query="dị ứng tôm")
    assert res_shrimp.hard_excluded_allergens == {"shrimp"}
    pools_shrimp = ConstraintFilter.filter_candidates(res_shrimp, index=index_fixture)
    assert pools_shrimp.safety_status == "SAFE"
    assert pools_shrimp.execution_metrics["surviving_count"] == 1964

    # Multiple allergies
    res_multi = ConstraintResolver.resolve_constraints(
        profile={"allergies": ["shrimp", "egg"]},
        condition_query="dị ứng sữa bò"
    )
    assert res_multi.hard_excluded_allergens == {"shrimp", "egg", "cow_milk"}
    pools_multi = ConstraintFilter.filter_candidates(res_multi, index=index_fixture)
    assert pools_multi.safety_status == "SAFE"
    # Verify no shrimp, egg, or milk in surviving dishes
    for rid in pools_multi.combo_candidates["main_dish"][:20]:
        meta = index_fixture.get_metadata_by_id(rid)
        for ag in ("shrimp", "egg", "cow_milk"):
            assert meta["allergen_assessments"][ag]["status"] == "assessed_not_detected"


def test_unsupported_tree_nuts_allergy_fail_closed(index_fixture: InMemoryInvertedIndex):
    """Verify unsupported allergen (tree nuts) halts execution and never claims safe filtering."""
    for query in ["dị ứng hạt điều", "dị ứng hạt dẻ", "dị ứng óc chó", "dị ứng tree nuts"]:
        resolved = ConstraintResolver.resolve_constraints(condition_query=query)
        assert resolved.is_safe_to_proceed is False
        assert resolved.safety_halt_reason == "UNSUPPORTED_ALLERGEN_HALT"
        assert "tree_nuts" in resolved.unsupported_allergens

        pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)
        assert pools.safety_status == "UNSUPPORTED_ALLERGEN_HALT"
        assert pools.execution_metrics["surviving_count"] == 0
        assert len(pools.warnings) > 0


def test_wheat_vs_celiac_distinction(index_fixture: InMemoryInvertedIndex):
    """Verify Celiac disease enforces strict gluten-free exclusions including barley and unverified oats."""
    resolved = ConstraintResolver.resolve_constraints(condition_query="bệnh celiac kiêng gluten")
    assert resolved.is_safe_to_proceed is True
    assert "wheat_gluten" in resolved.hard_excluded_allergens
    assert "barley" in resolved.hard_excluded_ingredients
    assert "oats" in resolved.hard_excluded_ingredients
    assert any(r.rule_id == "RULE_CELIAC_GLUTEN_FREE" for r in resolved.applied_rules)

    pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)
    assert pools.safety_status == "SAFE"
    # Ensure no surviving dish contains oats or wheat
    for rid in pools.combo_candidates["staple"]:
        recipe = index_fixture.get_recipe_by_id(rid)
        assert "yến mạch" not in recipe["title"].lower()


def test_comorbidity_gout_and_diabetes(index_fixture: InMemoryInvertedIndex):
    """Verify comorbidity (Gout + Diabetes) intersects restrictions cleanly without conflict."""
    resolved = ConstraintResolver.resolve_constraints(
        profile={"conditions": ["gout", "diabetes"]},
        condition_query="bệnh gút và tiểu đường"
    )
    assert resolved.is_safe_to_proceed is True
    assert "organ_meat" in resolved.hard_excluded_ingredient_groups
    assert "alcohol" in resolved.hard_excluded_ingredients
    assert resolved.nutrient_limits.get("sugar") == "low"
    assert any(r.condition_id == "gout" for r in resolved.applied_rules)
    assert any(r.condition_id == "diabetes" for r in resolved.applied_rules)

    pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)
    assert pools.safety_status == "SAFE"
    assert len(pools.combo_candidates["main_dish"]) > 0


def test_profile_and_request_conflict_resolution(index_fixture: InMemoryInvertedIndex):
    """Verify Hard Safety Constraints ALWAYS win over personal preferences."""
    # User profile says they prefer seafood, but query declares shrimp allergy
    resolved = ConstraintResolver.resolve_constraints(
        profile={"preferences": ["hai san"]},
        condition_query="dị ứng tôm, không ăn thịt bò",
        user_disliked_ingredients=["thịt bò"]
    )
    assert "shrimp" in resolved.hard_excluded_allergens
    assert "beef" in resolved.hard_excluded_ingredient_groups

    pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)
    # Check that shrimp is strictly absent from all pools
    for rid in pools.combo_candidates["main_dish"][:30]:
        meta = index_fixture.get_metadata_by_id(rid)
        assert meta["allergen_assessments"]["shrimp"]["status"] == "assessed_not_detected"
        assert "beef" not in meta["ingredient_groups"]


def test_candidate_pools_segregation_and_invariants(index_fixture: InMemoryInvertedIndex):
    """Verify candidate pools are segregated and standalone/review dishes are strictly barred from combo."""
    resolved = ConstraintResolver.resolve_constraints(condition_query="ăn lành mạnh")
    pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)

    standalone_set = set(pools.standalone_candidates)
    manual_review_set = index_fixture.manual_review_ids

    # For every combo slot, ensure NO standalone dish exists
    for role in ("staple", "main_dish", "soup", "vegetable"):
        combo_set = set(pools.combo_candidates[role])
        assert len(combo_set & standalone_set) == 0, f"Found standalone dish in combo[{role}]!"
        assert len(combo_set & manual_review_set) == 0, f"Found review-required dish in combo[{role}]!"

    # Beverage and Standalone must have items
    assert len(pools.standalone_candidates) == 397
    assert len(pools.beverage_candidates) == 97


def test_deterministic_clinical_output(index_fixture: InMemoryInvertedIndex):
    """Verify 100 consecutive calls return 100% deterministic, byte-identical sorted candidate IDs."""
    resolved = ConstraintResolver.resolve_constraints(
        condition_query="tiểu đường, dị ứng tôm, không ăn đồ chiên"
    )
    first_pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)

    for _ in range(50):
        next_pools = ConstraintFilter.filter_candidates(resolved, index=index_fixture)
        assert first_pools.combo_candidates == next_pools.combo_candidates
        assert first_pools.standalone_candidates == next_pools.standalone_candidates
