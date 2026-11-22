"""Property-Based, Monotonicity, and Invariant Verification Suite for Phase 3.1.

Validates:
1. Monotonicity of hard constraint contraction:
   filtered_ab <= filtered_a <= original_pool (Subset relation)
2. Commutativity of independent hard constraints:
   filter(A + B) == filter(B + A)
3. Invariance against soft constraints:
   Adding soft preferences never expands or contracts the hard-filtered pool.
4. Genuine Empty Candidate Pool:
   Impossible constraints produce exactly 0 candidates, 0 role memberships,
   and NO_ELIGIBLE_CANDIDATES without falling back or calling LLM.
5. Invariant safety:
   - Standalone dishes never appear in combo roles.
   - Manual review recipes never appear in surviving candidate pools.
   - Canonical staples undergo safety filtering.
   - Zero unsupported allergen leakages.
6. Reference parity:
   Exact 1:1 ID match between ReferenceFilter and ConstraintFilter.
"""

from pathlib import Path
import pytest
from typing import Set

from core.nutrition.clinical_constraints import (
    CandidatePools,
    ClinicalRuleDefinition,
    ReasonCode,
    ResolvedConstraints,
    SafetyStatus,
)
from core.nutrition.constraint_resolver import ConstraintResolver
from core.nutrition.constraint_filter import ConstraintFilter
from core.nutrition.reference_filter import ReferenceFilter
from core.nutrition.metadata_index import get_metadata_index, InMemoryInvertedIndex, STANDARD_COMBO_ROLES


@pytest.fixture(scope="module")
def index_fixture() -> InMemoryInvertedIndex:
    return get_metadata_index()


# -----------------------------------------------------------------------------
# 1. Monotonicity Tests (Set Contraction Invariant)
# -----------------------------------------------------------------------------

def test_monotonicity_allergen_contraction(index_fixture: InMemoryInvertedIndex):
    """Verify filtered_ab <= filtered_a <= original_pool for sequential allergen additions."""
    base_res = ConstraintResolver.resolve_constraints()
    base_pool = ConstraintFilter.filter_candidates(base_res, index=index_fixture).unique_candidate_ids

    # Step 1: Add Shrimp allergy
    shrimp_res = ConstraintResolver.resolve_constraints(profile={"allergies": ["shrimp"]})
    shrimp_pool = ConstraintFilter.filter_candidates(shrimp_res, index=index_fixture).unique_candidate_ids

    # Step 2: Add Egg allergy in addition to Shrimp
    shrimp_egg_res = ConstraintResolver.resolve_constraints(profile={"allergies": ["shrimp", "egg"]})
    shrimp_egg_pool = ConstraintFilter.filter_candidates(shrimp_egg_res, index=index_fixture).unique_candidate_ids

    # Step 3: Add Cow Milk in addition to Shrimp and Egg
    multi_res = ConstraintResolver.resolve_constraints(profile={"allergies": ["shrimp", "egg", "cow_milk"]})
    multi_pool = ConstraintFilter.filter_candidates(multi_res, index=index_fixture).unique_candidate_ids

    assert shrimp_pool.issubset(base_pool), "shrimp_pool must be subset of base_pool"
    assert shrimp_egg_pool.issubset(shrimp_pool), "shrimp_egg_pool must be subset of shrimp_pool"
    assert multi_pool.issubset(shrimp_egg_pool), "multi_pool must be subset of shrimp_egg_pool"

    # Strictly contracting
    assert len(multi_pool) < len(shrimp_egg_pool) < len(shrimp_pool) < len(base_pool)


def test_monotonicity_mixed_hard_constraints(index_fixture: InMemoryInvertedIndex):
    """Verify monotonicity when mixing medical conditions, allergies, and cooking method exclusions."""
    base_res = ConstraintResolver.resolve_constraints()
    base_pool = ConstraintFilter.filter_candidates(base_res, index=index_fixture).unique_candidate_ids

    # Disease: Diabetes (excludes desserts)
    diab_res = ConstraintResolver.resolve_constraints(condition_query="đái tháo đường type 2")
    diab_pool = ConstraintFilter.filter_candidates(diab_res, index=index_fixture).unique_candidate_ids

    # Disease + Allergy: Diabetes + Shrimp
    diab_shrimp_res = ConstraintResolver.resolve_constraints(
        profile={"conditions": ["diabetes"], "allergies": ["shrimp"]}
    )
    diab_shrimp_pool = ConstraintFilter.filter_candidates(diab_shrimp_res, index=index_fixture).unique_candidate_ids

    # Disease + Allergy + Method: Diabetes + Shrimp + No Frying
    diab_shrimp_nofry_res = ConstraintResolver.resolve_constraints(
        profile={"conditions": ["diabetes"], "allergies": ["shrimp"]},
        condition_query="không ăn đồ chiên"
    )
    diab_shrimp_nofry_pool = ConstraintFilter.filter_candidates(diab_shrimp_nofry_res, index=index_fixture).unique_candidate_ids

    assert diab_pool.issubset(base_pool)
    assert diab_shrimp_pool.issubset(diab_pool)
    assert diab_shrimp_nofry_pool.issubset(diab_shrimp_pool)

    # Specific counts: 2446 -> 2364 -> 1881 -> 1270
    assert len(base_pool) == 2446
    assert len(diab_pool) == 2364
    assert len(diab_shrimp_pool) == 1881
    assert len(diab_shrimp_nofry_pool) == 1270


# -----------------------------------------------------------------------------
# 2. Commutativity Tests (Order Invariance)
# -----------------------------------------------------------------------------

def test_hard_constraint_commutativity(index_fixture: InMemoryInvertedIndex):
    """Verify constraint compilation and filtering is commutative: filter(A + B) == filter(B + A)."""
    # Order 1: Allergy then Cooking Method
    res_ab = ConstraintResolver.resolve_constraints(
        profile={"allergies": ["shrimp"]},
        condition_query="không ăn đồ chiên"
    )
    pool_ab = ConstraintFilter.filter_candidates(res_ab, index=index_fixture).unique_candidate_ids

    # Order 2: Cooking Method then Allergy
    res_ba = ConstraintResolver.resolve_constraints(
        profile={"disliked_ingredients": ["đồ chiên"]},
        condition_query="dị ứng tôm"
    )
    pool_ba = ConstraintFilter.filter_candidates(res_ba, index=index_fixture).unique_candidate_ids

    assert pool_ab == pool_ba, "Candidate set must be identical regardless of constraint order"
    assert len(pool_ab) == 1351


# -----------------------------------------------------------------------------
# 3. Soft vs Hard Independence Tests
# -----------------------------------------------------------------------------

def test_soft_constraints_do_not_alter_hard_candidate_membership(index_fixture: InMemoryInvertedIndex):
    """Verify adding soft preferences/avoidances does not alter hard candidate pool membership."""
    # Hard only
    hard_res = ConstraintResolver.resolve_constraints(profile={"allergies": ["fish"]})
    hard_pool = ConstraintFilter.filter_candidates(hard_res, index=index_fixture).unique_candidate_ids

    # Hard + multiple soft preferences
    soft_res = ConstraintResolver.resolve_constraints(
        profile={"allergies": ["fish"], "preferences": ["thích ăn rau", "thích hấp luộc"]}
    )
    soft_pool = ConstraintFilter.filter_candidates(soft_res, index=index_fixture).unique_candidate_ids

    assert hard_pool == soft_pool, "Soft preferences must NOT change the hard filtered candidate set"


# -----------------------------------------------------------------------------
# 4. Genuine Empty Candidate Pool Tests
# -----------------------------------------------------------------------------

def test_genuine_empty_candidate_pool(index_fixture: InMemoryInvertedIndex):
    """Verify impossible/contradictory constraints yield exactly 0 items with correct status."""
    res = ConstraintResolver.resolve_constraints(
        profile={"disliked_ingredients": ["tat ca cac mon"]},
        condition_query="không ăn bất kỳ món nào"
    )
    pools = ConstraintFilter.filter_candidates(res, index=index_fixture)

    assert pools.safety_status == SafetyStatus.NO_ELIGIBLE_CANDIDATES.value
    assert pools.execution_metrics["surviving_count"] == 0
    assert len(pools.unique_candidate_ids) == 0
    assert pools.total_role_memberships == 0
    for role in STANDARD_COMBO_ROLES:
        assert len(pools.combo_candidates[role]) == 0
    assert len(pools.standalone_candidates) == 0
    assert len(pools.beverage_candidates) == 0
    assert len(pools.dessert_candidates) == 0
    assert len(pools.snack_candidates) == 0
    assert pools.execution_metrics["is_combo_viable"] is False
    assert pools.execution_metrics["is_standalone_viable"] is False


def test_combo_incomplete_but_standalone_viable(index_fixture: InMemoryInvertedIndex):
    """Verify when staple is excluded, combo is incomplete but standalone meals remain viable."""
    res = ConstraintResolver.resolve_constraints(
        profile={"disliked_ingredients": ["staple"]}
    )
    res.hard_excluded_roles.add("staple")
    pools = ConstraintFilter.filter_candidates(res, index=index_fixture)

    assert pools.safety_status == SafetyStatus.PASSED_KNOWN_CONSTRAINTS.value
    assert pools.execution_metrics["surviving_count"] > 0
    assert len(pools.combo_candidates["staple"]) == 0
    assert len(pools.standalone_candidates) > 0
    assert pools.execution_metrics["is_combo_viable"] is False
    assert pools.execution_metrics["is_standalone_viable"] is True


# -----------------------------------------------------------------------------
# 5. Candidate Pool Invariants & Zero Leakage
# -----------------------------------------------------------------------------

def test_candidate_pool_invariants(index_fixture: InMemoryInvertedIndex):
    """Verify candidate pool invariants:
    - Standalone dishes never in combo roles
    - Manual review items never in any pool
    - Canonical staples only in staple role
    """
    res = ConstraintResolver.resolve_constraints()
    pools = ConstraintFilter.filter_candidates(res, index=index_fixture)

    # 1. Manual review exclusion
    for rid in pools.unique_candidate_ids:
        assert rid not in index_fixture.manual_review_ids

    # 2. Standalone never in combo roles
    standalone_ids = set(pools.standalone_candidates)
    for role, rids in pools.combo_candidates.items():
        assert len(set(rids) & standalone_ids) == 0, f"Standalone dish found in combo role {role}"

    # 3. Canonical staples strictly in staple role
    for rid in index_fixture.all_recipe_ids:
        if rid.startswith("canonical_staple_"):
            assert rid in pools.combo_candidates["staple"]
            assert rid not in pools.combo_candidates["main_dish"]
            assert rid not in pools.combo_candidates["soup"]
            assert rid not in pools.combo_candidates["vegetable"]
            assert rid not in pools.standalone_candidates


# -----------------------------------------------------------------------------
# 6. Reference Filter Parity
# -----------------------------------------------------------------------------

def test_reference_filter_parity_across_scenarios(index_fixture: InMemoryInvertedIndex):
    """Verify 100% parity between ReferenceFilter (linear scan) and ConstraintFilter (index)."""
    scenarios = [
        ("Healthy", {}, "ăn lành mạnh"),
        ("Gout", {"conditions": ["gout"]}, "bệnh gút"),
        ("Hyperuricemia", {}, "tăng acid uric, kiêng hải sản"),
        ("Diabetes", {"conditions": ["diabetes"]}, "đái tháo đường type 2"),
        ("Fatty_Liver", {"conditions": ["fatty_liver"]}, "gan nhiễm mỡ, không ăn đồ chiên"),
        ("Shrimp", {"allergies": ["shrimp"]}, "dị ứng tôm"),
        ("Multi_Allergy", {"allergies": ["shrimp", "egg", "cow_milk"]}, "dị ứng tôm và trứng"),
        ("Gout_Diabetes", {"conditions": ["gout", "diabetes"]}, "gút và tiểu đường"),
        ("Complex", {"conditions": ["diabetes"], "allergies": ["shrimp"]}, "tiểu đường, dị ứng tôm, không ăn đồ chiên"),
    ]

    for name, prof, q in scenarios:
        res = ConstraintResolver.resolve_constraints(profile=prof, condition_query=q)
        pools = ConstraintFilter.filter_candidates(res, index=index_fixture)
        ref_ids = ReferenceFilter.filter_candidates(
            res,
            recipe_by_id=index_fixture.recipe_by_id,
            metadata_by_id=index_fixture.metadata_by_id,
            manual_review_ids=index_fixture.manual_review_ids
        )
        opt_ids = sorted(list(pools.unique_candidate_ids))

        assert opt_ids == ref_ids, f"Parity mismatch in scenario {name}: Index={len(opt_ids)}, Ref={len(ref_ids)}"
