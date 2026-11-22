"""Unit tests for Phase 1 & 1.1: Data Engineering, Metadata Normalization & Quality Assurance."""

import hashlib
import json
from pathlib import Path
import pytest

from core.nutrition.recipe_metadata import (
    get_recipe_metadata,
    load_canonical_staples,
    load_recipe_metadata_map,
    clear_metadata_cache
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "recipes"
RAW_RECIPES_PATH = DATA_DIR / "vifoodrec" / "recipes.json"
METADATA_PATH = DATA_DIR / "vifoodrec" / "recipes_metadata.json"
CANONICAL_STAPLES_PATH = DATA_DIR / "canonical_staples.json"
GT_EVAL_PATH = DATA_DIR / "vifoodrec" / "ground_truth_eval_250.json"

EXPECTED_RAW_SHA256 = "3f9cfe8f97a7522ebd47d88358dfbe7d03ba7f938924c168da1da9f7560d14f4"
ALLOWED_MEAL_ROLES = {
    "staple", "main_dish", "soup", "vegetable", "standalone",
    "beverage", "dessert", "snack", "other"
}
ALLOWED_ALLERGEN_STATUSES = {"known_present", "assessed_not_detected", "unknown"}
BIG_11_ALLERGENS = {
    "shrimp", "crab", "squid_octopus", "fish", "mollusk",
    "peanut", "sesame", "egg", "cow_milk", "soy", "wheat_gluten"
}


def test_original_dataset_integrity():
    """Verify that original recipes.json dataset was NOT modified or corrupted."""
    assert RAW_RECIPES_PATH.exists(), "Raw recipes.json must exist"
    content = RAW_RECIPES_PATH.read_bytes()
    current_sha256 = hashlib.sha256(content).hexdigest().lower()
    assert current_sha256 == EXPECTED_RAW_SHA256, (
        f"Raw recipes.json has been mutated! Expected {EXPECTED_RAW_SHA256}, got {current_sha256}"
    )
    with open(RAW_RECIPES_PATH, "r", encoding="utf-8") as f:
        recipes = json.load(f)
    assert len(recipes) == 2462, f"Expected 2462 recipes, found {len(recipes)}"


def test_metadata_coverage_and_schema():
    """Verify that recipes_metadata.json completely covers all 2462 recipes with Phase 1.1 schema."""
    assert METADATA_PATH.exists(), "recipes_metadata.json must exist"
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    assert len(metadata) == 2462, f"Metadata must cover exactly 2462 recipes, got {len(metadata)}"

    ids = set()
    for item in metadata:
        rec_id = item.get("id")
        assert rec_id, "Every item must have an id"
        assert rec_id not in ids, f"Duplicate id in metadata: {rec_id}"
        ids.add(rec_id)

        # Check required fields
        assert "meal_role" in item
        assert "primary_role" in item
        assert item["primary_role"] in ALLOWED_MEAL_ROLES, f"Invalid primary_role: {item['primary_role']}"
        assert isinstance(item.get("secondary_roles"), list)
        assert isinstance(item.get("eligible_combo_roles"), list)
        assert isinstance(item.get("normalized_ingredients"), list)
        assert isinstance(item.get("ingredient_groups"), list)
        assert isinstance(item.get("allergen_tags"), list)
        assert isinstance(item.get("allergen_unknown_tags"), list)
        assert item.get("allergen_status") in ALLOWED_ALLERGEN_STATUSES
        assert "allergen_assessments" in item
        assert isinstance(item["allergen_assessments"], dict)
        assert set(item["allergen_assessments"].keys()) == BIG_11_ALLERGENS

        # Check per-allergen structure
        for ag, assess in item["allergen_assessments"].items():
            assert assess["status"] in ALLOWED_ALLERGEN_STATUSES
            assert "evidence" in assess
            assert "uncertainty_reason" in assess

        assert isinstance(item.get("cooking_methods"), list)
        assert item.get("nutrition_verified") is False, "ViFoodRec nutrition must be marked unverified"
        assert "review_required" in item
        assert "classification_confidence" in item


def test_meal_role_classification_standalone_dishes():
    """Verify standalone one-dish meals are classified as standalone and CANNOT be combo components."""
    meta_map = load_recipe_metadata_map()

    test_cases = [
        ("vifoodrec_7", "standalone"),    # Cơm hến trộn
        ("vifoodrec_19", "standalone"),   # Cháo hàu sữa đậu xanh
        ("vifoodrec_38", "standalone"),   # Bún giò heo nấu giấm
        ("vifoodrec_40", "standalone"),   # Lẩu cháo chim cút
        ("vifoodrec_46", "standalone"),   # Mì Quảng xào lươn
        ("vifoodrec_590", "standalone"),  # Bánh canh cá lóc
        ("vifoodrec_789", "standalone"),  # Phở bò
    ]

    for rec_id, expected_role in test_cases:
        item = meta_map.get(rec_id)
        assert item is not None, f"Item {rec_id} not found in metadata"
        assert item["primary_role"] == expected_role, (
            f"Expected {expected_role} for {item['title']} ({rec_id}), got {item['primary_role']}"
        )
        # CRITICAL PROTOCOL CHECK: Standalone dishes must have EMPTY eligible_combo_roles!
        assert item["eligible_combo_roles"] == [], (
            f"Standalone dish {item['title']} ({rec_id}) must have empty eligible_combo_roles, got {item['eligible_combo_roles']}"
        )


def test_meal_role_classification_meat_in_vegetables():
    """Verify meat-heavy vegetable dishes (Rau muống xào bò, Thịt bê xào cải rổ, Gỏi ngó sen tôm thịt)."""
    meta_map = load_recipe_metadata_map()

    # Thịt bê xào cải rổ: vifoodrec_23
    be_xao = meta_map.get("vifoodrec_23")
    assert be_xao is not None
    assert be_xao["primary_role"] == "main_dish"
    assert "vegetable" in be_xao["secondary_roles"]
    assert be_xao["eligible_combo_roles"] == ["main_dish"]

    # Gỏi ngó sen tôm thịt: vifoodrec_4
    goi_sen = meta_map.get("vifoodrec_4")
    assert goi_sen is not None
    assert goi_sen["primary_role"] == "main_dish"
    assert goi_sen["eligible_combo_roles"] == ["main_dish"]

    # Rau Muống Xào Bò: vifoodrec_3952
    rau_muong_bo = meta_map.get("vifoodrec_3952")
    assert rau_muong_bo is not None
    assert rau_muong_bo["primary_role"] == "main_dish"
    assert rau_muong_bo["eligible_combo_roles"] == ["main_dish"]


def test_false_positive_deceptions_handling():
    """Verify tricky edge cases (cải bó xôi vs xôi, mì căn vs mì, tép tỏi vs tép, bánh xoắn ốc vs ốc)."""
    meta_map = load_recipe_metadata_map()

    # vifoodrec_1173: Bánh Mì Xoắn Ốc Nhân Kem Trứng -> should NOT contain 'mollusk'
    item_1173 = meta_map.get("vifoodrec_1173")
    assert item_1173 is not None
    assert item_1173["allergen_assessments"]["mollusk"]["status"] == "assessed_not_detected"
    assert "mollusk" not in item_1173["allergen_tags"]

    # Check dishes with 'cải bó xôi' are not classified as 'staple' (xôi)
    spinach_items = [m for m in meta_map.values() if "cải bó xôi" in m["title"].lower()]
    for item in spinach_items:
        assert item["primary_role"] != "staple", f"Spinach dish {item['title']} must not be staple"


def test_per_allergen_assessments_granularity():
    """Verify that per-allergen assessments accurately distinguish known_present vs unknown vs assessed_not_detected."""
    meta_map = load_recipe_metadata_map()

    # vifoodrec_0: Mực ống hấp củ đậu -> squid_octopus is known_present
    rec_0 = meta_map.get("vifoodrec_0")
    assert rec_0 is not None
    assert rec_0["allergen_assessments"]["squid_octopus"]["status"] == "known_present"
    assert rec_0["allergen_assessments"]["crab"]["status"] == "assessed_not_detected"


def test_canonical_staples_verified_provenance():
    """Verify canonical_staples.json has exact individual citations, FDC/NIN codes, and reference portion phrasing."""
    assert CANONICAL_STAPLES_PATH.exists(), "canonical_staples.json must exist"
    staples = load_canonical_staples()
    assert len(staples) == 9, f"Expected exactly 9 canonical staples, got {len(staples)}"

    staple_ids = [s["id"] for s in staples]
    assert "canonical_staple_com_trang" in staple_ids
    assert "canonical_staple_com_gao_lut" in staple_ids
    assert "canonical_staple_bun_tuoi" in staple_ids

    for staple in staples:
        assert staple["primary_role"] == "staple"
        assert staple["eligible_combo_roles"] == ["staple"]
        assert staple["nutrition_verified"] is True
        assert staple["calories"] > 0
        assert staple["protein"] > 0
        assert staple["carbohydrates"] > 0
        assert staple["source_name"]
        assert staple["source_record_id"]
        assert staple["original_nutrient_values"]
        assert staple["conversion_formula"]
        assert "reference_portion_note" in staple
        assert "tham chiếu" in staple["reference_portion_note"].lower(), "Must use 'khẩu phần tham chiếu'"
        assert "allergen_assessments" in staple


def test_ground_truth_eval_dataset_and_accuracy():
    """Verify ground truth 250 dataset exists and classifier meets benchmark accuracy."""
    assert GT_EVAL_PATH.exists(), "ground_truth_eval_250.json must exist"
    with open(GT_EVAL_PATH, "r", encoding="utf-8") as f:
        gt_list = json.load(f)
    assert len(gt_list) == 250, f"Expected 250 ground truth items, got {len(gt_list)}"

    meta_map = load_recipe_metadata_map()
    correct = 0
    for gt in gt_list:
        rid = gt["id"]
        true_role = gt["ground_truth_primary_role"]
        pred_meta = meta_map.get(rid)
        assert pred_meta is not None
        if pred_meta["primary_role"] == true_role:
            correct += 1

    accuracy = (correct / len(gt_list)) * 100
    assert accuracy >= 80.0, f"Classification accuracy must be >= 80%, got {accuracy:.2f}%"


def test_recipe_metadata_module_api():
    """Verify core.nutrition.recipe_metadata module functions work correctly."""
    clear_metadata_cache()

    # 1. Query existing vifoodrec recipe
    meta_0 = get_recipe_metadata("vifoodrec_0")
    assert meta_0 is not None
    assert meta_0["id"] == "vifoodrec_0"
    assert meta_0["primary_role"] == "main_dish"
    assert "squid_octopus" in meta_0["allergen_tags"]
    assert "allergen_assessments" in meta_0

    # 2. Query canonical staple
    meta_rice = get_recipe_metadata("canonical_staple_com_trang")
    assert meta_rice is not None
    assert meta_rice["primary_role"] == "staple"
    assert meta_rice["eligible_combo_roles"] == ["staple"]
    assert meta_rice["nutrition_verified"] is True

    # 3. Query non-existent ID
    meta_none = get_recipe_metadata("non_existent_recipe_id_99999")
    assert meta_none is None
