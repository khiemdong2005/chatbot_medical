"""Allergen Invariant Verification Script for Phase 3.1.

Verifies at the candidate ID level:
- Zero recipes with 'known_present' for excluded allergens.
- Zero recipes with 'unknown' for excluded allergens (Fail-closed).
- 100% of surviving recipes have 'assessed_not_detected' for declared allergens.
- Residual scans on title and raw_ingredients confirm zero leakage.
"""

from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.nutrition.constraint_resolver import ConstraintResolver
from core.nutrition.constraint_filter import (
    ConstraintFilter,
    DAIRY_RESIDUAL_REGEX,
    ORGAN_MEAT_REGEX,
    ORGAN_EXCLUSION_CLEANER,
)
from core.nutrition.metadata_index import get_metadata_index

idx = get_metadata_index()

ALLERGENS_TO_TEST = ["cow_milk", "shrimp", "egg"]

print("=" * 80)
print("ALLERGEN INVARIANT AUDIT AT CANDIDATE ID LEVEL")
print("=" * 80)

results = {}

for allergen in ALLERGENS_TO_TEST:
    res = ConstraintResolver.resolve_constraints(profile={"allergies": [allergen]})
    pools = ConstraintFilter.filter_candidates(res, index=idx)
    surviving_ids = pools.unique_candidate_ids

    total_surviving = len(surviving_ids)
    known_present_count = 0
    unknown_count = 0
    assessed_not_detected_count = 0
    missing_assessment_count = 0
    residual_matches = []

    for rid in surviving_ids:
        meta = idx.get_metadata_by_id(rid)
        recipe = idx.get_recipe_by_id(rid)
        if not meta:
            continue

        assessments = meta.get("allergen_assessments") or {}
        al_info = assessments.get(allergen)

        if not al_info:
            missing_assessment_count += 1
            continue

        status = al_info.get("status")
        if status == "known_present":
            known_present_count += 1
        elif status == "unknown":
            unknown_count += 1
        elif status == "assessed_not_detected":
            assessed_not_detected_count += 1

        # Check residual text
        title = recipe.get("title", "")
        raw_ings = " ".join(recipe.get("raw_ingredients", []))
        full_text = f"{title} {raw_ings}"

        if allergen == "cow_milk":
            if DAIRY_RESIDUAL_REGEX.search(full_text):
                residual_matches.append((rid, title))
        elif allergen == "shrimp":
            if re.search(r"\b(?:tôm|tep|prawn|shrimp)\b", full_text, re.I):
                residual_matches.append((rid, title))
        elif allergen == "egg":
            if re.search(r"\b(?:trứng|mayonnaise|trứng\s+gà|trứng\s+vịt)\b", full_text, re.I):
                residual_matches.append((rid, title))

    results[allergen] = {
        "surviving_count": total_surviving,
        "known_present": known_present_count,
        "unknown": unknown_count,
        "assessed_not_detected": assessed_not_detected_count,
        "missing_assessment": missing_assessment_count,
        "residual_leakages": len(residual_matches),
    }

    print(f"\n--- Allergen: '{allergen}' ---")
    print(f"  Surviving candidates: {total_surviving} / 2,446")
    print(f"  Status distribution:")
    print(f"    - known_present:         {known_present_count} (Must be 0)")
    print(f"    - unknown:               {unknown_count} (Must be 0 - Fail-closed invariant)")
    print(f"    - missing_assessment:    {missing_assessment_count} (Must be 0)")
    print(f"    - assessed_not_detected: {assessed_not_detected_count} (100% of surviving candidates)")
    print(f"  Residual text leakages:    {len(residual_matches)} (Must be 0)")

    assert known_present_count == 0, f"Leaked known_present in {allergen}"
    assert unknown_count == 0, f"Leaked unknown in {allergen}"
    assert missing_assessment_count == 0, f"Missing assessment in {allergen}"
    assert assessed_not_detected_count == total_surviving, f"Not all candidates assessed_not_detected in {allergen}"
    assert len(residual_matches) == 0, f"Residual text matched in {allergen}: {residual_matches[:3]}"

print("\n>>> ALL ALLERGEN INVARIANTS VERIFIED WITH 100% COMPLIANCE AT CANDIDATE ID LEVEL <<<")
