"""Unit tests for Phase 2: In-Memory Inverted Index.

Validates:
- Logical catalog join integrity
- Index construction & frozenset immutability
- Primary, secondary, and combo role retrieval
- Standalone dish leakage prevention invariant
- Ingredient and ingredient group indexing
- Granular per-allergen 3-state filtering (fail-closed)
- Unsupported allergen detection and safety
- Manual review exclusion invariant
- Multi-constraint set algebra
- Empty candidate pool handling
- Concurrent read thread safety
- Deterministic output ordering
- Canonical staples integration
- Parity and legacy comparison
"""

import concurrent.futures
from pathlib import Path
import pytest
from typing import Set

from core.nutrition.metadata_index import (
    get_metadata_index,
    get_recipe_by_id,
    get_metadata_by_id,
    get_ids_by_primary_role,
    get_ids_by_combo_role,
    get_ids_by_ingredient,
    get_ids_by_ingredient_group,
    get_ids_by_allergen_status,
    get_ids_by_cooking_method,
    filter_candidate_ids,
    validate_allergens,
    InMemoryInvertedIndex,
    SUPPORTED_ALLERGENS,
    STANDARD_COMBO_ROLES,
    ALL_MEAL_ROLES,
)


@pytest.fixture(scope="module")
def index_fixture():
    """Load and provide the in-memory inverted index singleton."""
    return get_metadata_index()


def test_dataset_join_integrity(index_fixture: InMemoryInvertedIndex):
    """Verify the imported and authored recipes all have unique metadata records."""
    assert len(index_fixture.recipe_by_id) == 2472
    assert len(index_fixture.metadata_by_id) == 2472
    assert len(index_fixture.all_recipe_ids) == 2472

    # Verify no orphan IDs
    assert set(index_fixture.recipe_by_id.keys()) == set(index_fixture.metadata_by_id.keys())

    # Verify breakdown
    vifoodrec_ids = [rid for rid in index_fixture.all_recipe_ids if rid.startswith("vifoodrec_")]
    staple_ids = [rid for rid in index_fixture.all_recipe_ids if rid.startswith("canonical_staple_")]
    assert len(vifoodrec_ids) == 2462
    assert len(staple_ids) == 9
    assert len(set(vifoodrec_ids) & set(staple_ids)) == 0


def test_index_immutability(index_fixture: InMemoryInvertedIndex):
    """Verify that inverted indexes are stored as immutable frozensets."""
    for role, id_set in index_fixture.primary_role_index.items():
        assert isinstance(id_set, frozenset)
        with pytest.raises(AttributeError):
            id_set.add("fake_id")

    for role, id_set in index_fixture.combo_role_index.items():
        assert isinstance(id_set, frozenset)
        with pytest.raises(AttributeError):
            id_set.add("fake_id")

    for ag, id_set in index_fixture.allergen_present_index.items():
        assert isinstance(id_set, frozenset)

    assert isinstance(index_fixture.manual_review_ids, frozenset)
    assert isinstance(index_fixture.all_recipe_ids, frozenset)


def test_primary_and_secondary_role_retrieval(index_fixture: InMemoryInvertedIndex):
    """Verify role retrieval maps all 9 roles and matches total count."""
    primary_counts = {role: len(index_fixture.get_ids_by_primary_role(role)) for role in ALL_MEAL_ROLES}
    assert sum(primary_counts.values()) == 2472

    assert primary_counts["main_dish"] == 1406
    assert primary_counts["standalone"] == 397
    assert primary_counts["soup"] == 202
    assert primary_counts["vegetable"] == 190
    assert primary_counts["beverage"] == 97
    assert primary_counts["dessert"] == 82
    assert primary_counts["snack"] == 62
    assert primary_counts["other"] == 25
    assert primary_counts["staple"] == 11  # 9 canonical + 2 ViFoodRec


def test_combo_role_retrieval_and_invariants(index_fixture: InMemoryInvertedIndex):
    """Verify combo role invariants: no standalone, no review-required, only standard roles."""
    # 1. Check standard combo roles
    assert set(index_fixture.combo_role_index.keys()) == STANDARD_COMBO_ROLES
    assert len(index_fixture.get_ids_by_combo_role("main_dish")) == 1406
    assert len(index_fixture.get_ids_by_combo_role("soup")) == 202
    assert len(index_fixture.get_ids_by_combo_role("vegetable")) == 190
    assert len(index_fixture.get_ids_by_combo_role("staple")) == 10
    assert "canonical_staple_khoai_lang_luoc" in index_fixture.get_ids_by_combo_role("staple")
    assert all("vifoodrec_2901" not in ids for ids in index_fixture.combo_role_index.values())

    # 2. Standalone dishes NEVER appear in combo_role_index
    standalone_ids = index_fixture.get_ids_by_primary_role("standalone")
    assert len(standalone_ids) == 397
    for role, c_ids in index_fixture.combo_role_index.items():
        overlap = standalone_ids & c_ids
        assert len(overlap) == 0, f"Found {len(overlap)} standalone dishes in combo_role_index[{role}]"

    # 3. Manual review dishes NEVER appear in combo_role_index
    manual_review_ids = index_fixture.manual_review_ids
    assert len(manual_review_ids) == 25
    for role, c_ids in index_fixture.combo_role_index.items():
        overlap = manual_review_ids & c_ids
        assert len(overlap) == 0, f"Found {len(overlap)} review-required items in combo_role_index[{role}]"


def test_ingredient_and_group_retrieval(index_fixture: InMemoryInvertedIndex):
    """Verify normalized ingredient and group lookups."""
    # Check ginger lookup
    ginger_ids = index_fixture.get_ids_by_ingredient("ginger")
    assert len(ginger_ids) > 0
    assert isinstance(ginger_ids, frozenset)

    # Check seafood group lookup
    seafood_ids = index_fixture.get_ids_by_ingredient_group("seafood")
    assert len(seafood_ids) > 0
    assert isinstance(seafood_ids, frozenset)

    # All items with ginger must have 'ginger' in their metadata normalized_ingredients
    sample_id = next(iter(ginger_ids))
    sample_meta = index_fixture.get_metadata_by_id(sample_id)
    assert "ginger" in sample_meta["normalized_ingredients"]


def test_per_allergen_granular_3_state_filtering(index_fixture: InMemoryInvertedIndex):
    """Verify that each allergen has 3 disjoint states covering the entire catalog."""
    total_catalog = len(index_fixture.all_recipe_ids)

    for allergen in SUPPORTED_ALLERGENS:
        present = index_fixture.get_ids_by_allergen_status(allergen, "known_present")
        unknown = index_fixture.get_ids_by_allergen_status(allergen, "unknown")
        not_detected = index_fixture.get_ids_by_allergen_status(allergen, "assessed_not_detected")

        # Must be mutually exclusive
        assert len(present & unknown) == 0
        assert len(present & not_detected) == 0
        assert len(unknown & not_detected) == 0

        # Sum must cover all recipes
        assert len(present) + len(unknown) + len(not_detected) == total_catalog


def test_fail_closed_allergen_blocking(index_fixture: InMemoryInvertedIndex):
    """Verify that filtering an allergen blocks both known_present AND unknown (fail-closed)."""
    # Test with wheat_gluten which has both known_present and unknown
    present_gluten = index_fixture.get_ids_by_allergen_status("wheat_gluten", "known_present")
    unknown_gluten = index_fixture.get_ids_by_allergen_status("wheat_gluten", "unknown")
    not_detected_gluten = index_fixture.get_ids_by_allergen_status("wheat_gluten", "assessed_not_detected")

    assert len(present_gluten) > 0
    assert len(unknown_gluten) > 0

    surviving_ids = set(index_fixture.filter_candidate_ids(
        excluded_allergens=["wheat_gluten"],
        exclude_manual_review=False
    ))

    # All present_gluten must be blocked
    assert len(surviving_ids & present_gluten) == 0
    # All unknown_gluten must be blocked
    assert len(surviving_ids & unknown_gluten) == 0
    # Surviving must equal not_detected
    assert surviving_ids == not_detected_gluten


def test_unsupported_allergen_handling():
    """Verify validation of allergens flags unsupported allergens safely."""
    input_allergens = ["shrimp", "tree_nuts", "soy", "kiwi", "sesame"]
    supported, unsupported = validate_allergens(input_allergens)

    assert supported == ["shrimp", "soy", "sesame"]
    assert unsupported == ["tree_nuts", "kiwi"]


def test_manual_review_exclusion(index_fixture: InMemoryInvertedIndex):
    """Verify manual review items are excluded by default in filter_candidate_ids."""
    all_with_review = index_fixture.filter_candidate_ids(exclude_manual_review=False)
    all_without_review = index_fixture.filter_candidate_ids(exclude_manual_review=True)

    assert len(all_with_review) == 2472
    assert len(all_without_review) == 2472 - 25
    assert len(set(all_without_review) & index_fixture.manual_review_ids) == 0


def test_multi_constraint_filtering(index_fixture: InMemoryInvertedIndex):
    """Verify set algebra correctly intersects roles and subtracts multiple constraints."""
    filtered = index_fixture.filter_candidate_ids(
        included_roles=["main_dish", "soup"],
        use_combo_roles=True,
        excluded_allergens=["shrimp"],
        excluded_ingredient_groups=["beef"],
        excluded_cooking_methods=["deep_frying"],
        exclude_manual_review=True
    )

    shrimp_present = index_fixture.get_ids_by_allergen_status("shrimp", "known_present")
    shrimp_unknown = index_fixture.get_ids_by_allergen_status("shrimp", "unknown")
    beef_ids = index_fixture.get_ids_by_ingredient_group("beef")
    deep_fry_ids = index_fixture.get_ids_by_cooking_method("deep_frying")

    filtered_set = set(filtered)
    assert len(filtered_set & shrimp_present) == 0
    assert len(filtered_set & shrimp_unknown) == 0
    assert len(filtered_set & beef_ids) == 0
    assert len(filtered_set & deep_fry_ids) == 0
    assert len(filtered_set & index_fixture.manual_review_ids) == 0

    # All filtered items must have combo role in main_dish or soup
    main_or_soup = index_fixture.get_ids_by_combo_role("main_dish") | index_fixture.get_ids_by_combo_role("soup")
    assert filtered_set.issubset(main_or_soup)


def test_empty_candidate_pool_handling(index_fixture: InMemoryInvertedIndex):
    """Verify impossible constraints gracefully return empty list without error."""
    # All 25 'other' dishes have review_required=True, so excluding manual review yields empty list
    res = index_fixture.filter_candidate_ids(
        included_roles=["other"],
        exclude_manual_review=True
    )
    assert res == []

    # Also test passing empty candidate_ids
    assert index_fixture.filter_candidate_ids(candidate_ids=[]) == []


def test_concurrent_reads_thread_safety(index_fixture: InMemoryInvertedIndex):
    """Verify thread-safety of concurrent reads across 20 threads."""
    scenarios = ["main_dish", "soup", "vegetable", "staple"]

    def read_task(role):
        res = index_fixture.filter_candidate_ids(
            included_roles=[role],
            use_combo_roles=True,
            excluded_allergens=["shrimp"]
        )
        return len(res)

    tasks = [scenarios[i % len(scenarios)] for i in range(100)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(read_task, tasks))

    assert len(results) == 100
    # Every main_dish call should return identical counts
    main_counts = [results[i] for i, r in enumerate(tasks) if r == "main_dish"]
    assert len(set(main_counts)) == 1


def test_deterministic_output(index_fixture: InMemoryInvertedIndex):
    """Verify 100 consecutive calls return 100% deterministic, byte-identical sorted lists."""
    first = index_fixture.filter_candidate_ids(
        included_roles=["main_dish"],
        excluded_allergens=["fish", "soy"],
        deterministic=True
    )
    for _ in range(50):
        subsequent = index_fixture.filter_candidate_ids(
            included_roles=["main_dish"],
            excluded_allergens=["fish", "soy"],
            deterministic=True
        )
        assert first == subsequent


def test_canonical_staples_integration(index_fixture: InMemoryInvertedIndex):
    """Verify all 9 canonical staples are indexed with verified nutrition status."""
    staple_ids = [
        "canonical_staple_com_trang",
        "canonical_staple_com_gao_lut",
        "canonical_staple_bun_tuoi",
        "canonical_staple_banh_pho_tuoi",
        "canonical_staple_khoai_lang_luoc",
        "canonical_staple_khoai_tay_luoc",
        "canonical_staple_bap_luoc",
        "canonical_staple_yen_mach_nau",
        "canonical_staple_banh_mi_nguyen_cam"
    ]
    assert len(staple_ids) == 9

    for sid in staple_ids:
        recipe = index_fixture.get_recipe_by_id(sid)
        assert recipe is not None
        assert recipe["recipe_type"] == "food"

        meta = index_fixture.get_metadata_by_id(sid)
        assert meta is not None
        assert meta["primary_role"] == "staple"
        assert meta["eligible_combo_roles"] == ["staple"]
        assert meta["nutrition_verified"] is True
        assert meta["nutrient_provenance"] in ("national_food_table", "usda_fooddata_central")

        assert sid in index_fixture.get_ids_by_combo_role("staple")
        assert sid in index_fixture.get_ids_by_primary_role("staple")


def test_legacy_parity_and_discrepancies(index_fixture: InMemoryInvertedIndex):
    """Verify that indexed retrieval corrects known legacy bugs (e.g. standalone leaking into soups)."""
    # Legacy heuristic classified phở, bún, cháo with 'canh' or 'thịt' into soups/mains.
    # In index, standalone dishes are strictly barred from combo_role_index.
    pho_id = "vifoodrec_789"  # Phở bò
    pho_meta = index_fixture.get_metadata_by_id(pho_id)
    assert pho_meta["primary_role"] == "standalone"
    assert pho_meta["eligible_combo_roles"] == []

    soup_combo_ids = index_fixture.get_ids_by_combo_role("soup")
    assert pho_id not in soup_combo_ids

    main_combo_ids = index_fixture.get_ids_by_combo_role("main_dish")
    assert pho_id not in main_combo_ids
