"""Scenario Audit and Detailed Trace Generator for Phase 3.1.

Generates the 15 required audit debug points for each scenario:
1. Input (profile + query)
2. Recognized conditions
3. Recognized allergies
4. Activated clinical rule IDs
5. Resolved hard constraints (allergens, ingredients, groups, methods, roles)
6. Resolved soft constraints (preferred, avoided, nutrient limits)
7. Index keys used
8. Match counts per index key
9. Per-constraint exclusion counts (individual impact)
10. Multi-constraint overlap exclusion counts (intersection)
11. Final surviving candidate counts (total and unique)
12. Sample excluded recipes (with titles and reason codes)
13. Sample surviving recipes (with titles and roles)
14. Unresolved constraints and warnings
15. Final assessment and safety status
"""

import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.nutrition.clinical_constraints import (
    CandidatePools,
    ReasonCode,
    ResolvedConstraints,
    SafetyStatus,
)
from core.nutrition.constraint_resolver import ConstraintResolver
from core.nutrition.constraint_filter import ConstraintFilter, ORGAN_MEAT_REGEX, ORGAN_EXCLUSION_CLEANER
from core.nutrition.reference_filter import ReferenceFilter
from core.nutrition.metadata_index import get_metadata_index

idx = get_metadata_index()

AUDIT_SCENARIOS = [
    {
        "id": "healthy_eating",
        "name": "1. Ăn lành mạnh (Healthy Eating)",
        "profile": {},
        "query": "ăn lành mạnh",
    },
    {
        "id": "gout",
        "name": "2. Bệnh gút cấp (Acute Gout)",
        "profile": {"conditions": ["gout"]},
        "query": "bệnh gút",
    },
    {
        "id": "hyperuricemia",
        "name": "3. Tăng acid uric (Asymptomatic Hyperuricemia)",
        "profile": {},
        "query": "tăng acid uric, kiêng hải sản",
    },
    {
        "id": "diabetes",
        "name": "4. Đái tháo đường Type 2 (Diabetes)",
        "profile": {"conditions": ["diabetes"]},
        "query": "đái tháo đường type 2",
    },
    {
        "id": "fatty_liver",
        "name": "5. Gan nhiễm mỡ (Fatty Liver)",
        "profile": {"conditions": ["fatty_liver"]},
        "query": "gan nhiễm mỡ, không ăn đồ chiên",
    },
    {
        "id": "shrimp_allergy",
        "name": "6. Dị ứng tôm (Shrimp Allergy)",
        "profile": {"allergies": ["shrimp"]},
        "query": "dị ứng tôm",
    },
    {
        "id": "cow_milk_allergy",
        "name": "7. Dị ứng sữa bò (Cow Milk Allergy)",
        "profile": {"allergies": ["cow_milk"]},
        "query": "dị ứng sữa bò",
    },
    {
        "id": "multi_allergy",
        "name": "8. Nhiều dị ứng (Tôm + Trứng + Sữa bò)",
        "profile": {"allergies": ["shrimp", "egg", "cow_milk"]},
        "query": "dị ứng tôm và trứng",
    },
    {
        "id": "gout_diabetes",
        "name": "9. Nhiều bệnh lý (Gút + Tiểu đường)",
        "profile": {"conditions": ["gout", "diabetes"]},
        "query": "gút và tiểu đường",
    },
    {
        "id": "diabetes_shrimp_nofrying",
        "name": "10. Đa ràng buộc (Tiểu đường + Dị ứng tôm + Không chiên)",
        "profile": {"conditions": ["diabetes"], "allergies": ["shrimp"]},
        "query": "tiểu đường, dị ứng tôm, không ăn đồ chiên",
    },
    {
        "id": "unsupported_allergen",
        "name": "11. Dị ứng chưa hỗ trợ (Hạt cây - Tree Nuts)",
        "profile": {"allergies": ["tree_nuts"]},
        "query": "dị ứng hạt điều và óc chó",
    },
    {
        "id": "ckd_safeguard",
        "name": "12. Rào chắn suy thận mạn (CKD Safeguard)",
        "profile": {"conditions": ["ckd"]},
        "query": "bệnh nhân suy thận mạn",
    },
    {
        "id": "unmapped_disease",
        "name": "13. Rào chắn bệnh lý phức tạp (Ung thư dạ dày)",
        "profile": {},
        "query": "ung thư dạ dày",
    },
    {
        "id": "empty_candidate_pool",
        "name": "14. Tập ứng viên rỗng (Loại trừ toàn bộ vai trò món ăn)",
        "profile": {"disliked_ingredients": ["tat ca cac mon"]},
        "query": "không ăn bất kỳ món nào",
    },
    {
        "id": "combo_incomplete_standalone_viable",
        "name": "15. Thiếu thành phần combo nhưng standalone hợp lệ (Không ăn tinh bột / staple)",
        "profile": {"disliked_ingredients": ["staple"]},
        "query": "không ăn cơm",
    },
]


def audit_scenario(scenario: Dict[str, Any]) -> Dict[str, Any]:
    name = scenario["name"]
    prof = scenario["profile"]
    query = scenario["query"]

    # 1. Input
    resolved = ConstraintResolver.resolve_constraints(profile=prof, condition_query=query)

    # 2. Filter execution
    pools = ConstraintFilter.filter_candidates(resolved, index=idx)

    # 3. Reference filter verification
    ref_ids = ReferenceFilter.filter_candidates(
        resolved,
        recipe_by_id=idx.recipe_by_id,
        metadata_by_id=idx.metadata_by_id,
        manual_review_ids=idx.manual_review_ids
    )

    clean_base = set(idx.all_recipe_ids - idx.manual_review_ids)

    # Trace index keys and individual impact
    index_keys_used = []
    key_match_counts = {}
    individual_exclusions = {}

    # Allergen keys
    for a in resolved.hard_excluded_allergens:
        key = f"allergen:{a}"
        index_keys_used.append(key)
        blocked = (idx.allergen_present_index.get(a, set()) | idx.allergen_unknown_index.get(a, set()))
        key_match_counts[key] = len(blocked)
        individual_exclusions[key] = len(clean_base & blocked)

    # Ingredient keys
    for ing in resolved.hard_excluded_ingredients:
        key = f"ingredient:{ing}"
        index_keys_used.append(key)
        blocked = idx.ingredient_index.get(ing, set())
        key_match_counts[key] = len(blocked)
        individual_exclusions[key] = len(clean_base & blocked)

    # Group keys
    for grp in resolved.hard_excluded_ingredient_groups:
        key = f"ingredient_group:{grp}"
        index_keys_used.append(key)
        blocked = idx.ingredient_group_index.get(grp, set())
        key_match_counts[key] = len(blocked)
        individual_exclusions[key] = len(clean_base & blocked)

    # Method keys
    for m in resolved.hard_excluded_cooking_methods:
        key = f"cooking_method:{m}"
        index_keys_used.append(key)
        blocked = idx.cooking_method_index.get(m, set())
        key_match_counts[key] = len(blocked)
        individual_exclusions[key] = len(clean_base & blocked)

    # Role keys
    for r in resolved.hard_excluded_roles:
        key = f"role:{r}"
        index_keys_used.append(key)
        blocked = idx.primary_role_index.get(r, set())
        key_match_counts[key] = len(blocked)
        individual_exclusions[key] = len(clean_base & blocked)

    # Residual organ meat impact
    if "organ_meat" in resolved.hard_excluded_ingredient_groups or "organ_meat" in resolved.hard_excluded_ingredients:
        organ_blocked = set()
        for rid in clean_base:
            rec = idx.get_recipe_by_id(rid)
            if not rec: continue
            txt = ORGAN_EXCLUSION_CLEANER.sub("", f"{rec.get('title', '')} {' '.join(rec.get('raw_ingredients', []))}")
            if ORGAN_MEAT_REGEX.search(txt):
                organ_blocked.add(rid)
        key = "residual:organ_meat"
        index_keys_used.append(key)
        key_match_counts[key] = len(organ_blocked)
        individual_exclusions[key] = len(clean_base & organ_blocked)

    # Overlap calculation
    all_individual_sum = sum(individual_exclusions.values())
    surviving_set = pools.unique_candidate_ids
    total_removed = len(clean_base - surviving_set) if resolved.is_safe_to_proceed else len(clean_base)
    overlap_count = max(0, all_individual_sum - total_removed)

    # Excluded sample recipes
    excluded_sample = []
    if resolved.is_safe_to_proceed:
        removed_ids = list(clean_base - surviving_set)[:5]
        for rid in removed_ids:
            r = idx.get_recipe_by_id(rid) or {}
            excluded_sample.append(f"{rid}: {r.get('title', '')}")
    else:
        excluded_sample.append(f"ALL_RECIPES_HALTED ({resolved.safety_halt_reason})")

    # Surviving sample recipes
    surviving_sample = []
    for rid in list(surviving_set)[:5]:
        r = idx.get_recipe_by_id(rid) or {}
        m = idx.get_metadata_by_id(rid) or {}
        surviving_sample.append(f"{rid} [{m.get('primary_role')}]: {r.get('title', '')}")

    parity_status = (sorted(list(surviving_set)) == ref_ids)

    return {
        "id": scenario["id"],
        "name": name,
        "input": {"profile": prof, "query": query},
        "recognized_conditions": [r.condition_id for r in resolved.applied_rules if r.condition_id not in ("healthy",)],
        "recognized_allergies": list(resolved.hard_excluded_allergens),
        "activated_rules": [r.rule_id for r in resolved.applied_rules],
        "hard_constraints": {
            "allergens": list(resolved.hard_excluded_allergens),
            "ingredients": list(resolved.hard_excluded_ingredients),
            "ingredient_groups": list(resolved.hard_excluded_ingredient_groups),
            "cooking_methods": list(resolved.hard_excluded_cooking_methods),
            "roles": list(resolved.hard_excluded_roles),
        },
        "soft_constraints": pools.soft_constraints,
        "index_keys_used": index_keys_used,
        "key_match_counts": key_match_counts,
        "individual_exclusions": individual_exclusions,
        "overlap_exclusion_count": overlap_count,
        "before_filter_count": len(idx.all_recipe_ids),
        "clean_catalog_base": len(clean_base),
        "surviving_unique_count": len(surviving_set),
        "total_role_memberships": pools.total_role_memberships,
        "pool_breakdown": {
            "staple": len(pools.combo_candidates["staple"]),
            "main_dish": len(pools.combo_candidates["main_dish"]),
            "soup": len(pools.combo_candidates["soup"]),
            "vegetable": len(pools.combo_candidates["vegetable"]),
            "standalone": len(pools.standalone_candidates),
            "beverage": len(pools.beverage_candidates),
            "dessert": len(pools.dessert_candidates),
            "snack": len(pools.snack_candidates),
        },
        "is_combo_viable": pools.execution_metrics.get("is_combo_viable", False),
        "is_standalone_viable": pools.execution_metrics.get("is_standalone_viable", False),
        "sample_excluded": excluded_sample,
        "sample_surviving": surviving_sample,
        "unresolved_constraints": pools.unresolved_constraints,
        "safety_status": pools.safety_status,
        "reference_parity": parity_status,
    }


def main():
    print("=" * 80)
    print("PHASE 3.1: DETAILED AUDIT SCENARIO TRACES")
    print("=" * 80)

    results = []
    for sc in AUDIT_SCENARIOS:
        trace = audit_scenario(sc)
        results.append(trace)

        print(f"\n--- {trace['name']} ---")
        print(f"  Input: Query='{trace['input']['query']}' | Profile={trace['input']['profile']}")
        print(f"  Recognized Conditions : {trace['recognized_conditions']}")
        print(f"  Recognized Allergies  : {trace['recognized_allergies']}")
        print(f"  Activated Rules       : {trace['activated_rules']}")
        print(f"  Hard Constraints      : Allergens={trace['hard_constraints']['allergens']} | Groups={trace['hard_constraints']['ingredient_groups']} | Methods={trace['hard_constraints']['cooking_methods']} | Roles={trace['hard_constraints']['roles']}")
        print(f"  Index Keys Used       : {trace['index_keys_used']}")
        print(f"  Individual Exclusions : {trace['individual_exclusions']}")
        print(f"  Overlap Count         : {trace['overlap_exclusion_count']}")
        print(f"  Surviving Unique IDs  : {trace['surviving_unique_count']} / {trace['clean_catalog_base']} (Clean Base)")
        print(f"  Total Role Memberships: {trace['total_role_memberships']}")
        print(f"  Pool Breakdown        : Staple={trace['pool_breakdown']['staple']} | Main={trace['pool_breakdown']['main_dish']} | Soup={trace['pool_breakdown']['soup']} | Veg={trace['pool_breakdown']['vegetable']} | Standalone={trace['pool_breakdown']['standalone']}")
        print(f"  Viability             : Combo Viable={trace['is_combo_viable']} | Standalone Viable={trace['is_standalone_viable']}")
        print(f"  Safety Status         : {trace['safety_status']}")
        print(f"  Reference Parity      : {'100% PASS' if trace['reference_parity'] else 'FAIL'}")
        print(f"  Sample Excluded       : {trace['sample_excluded'][:3]}")
        print(f"  Sample Surviving      : {trace['sample_surviving'][:3]}")

    out_path = PROJECT_ROOT / "scripts" / "audit_scenario_traces.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved full trace output to: {out_path}")


if __name__ == "__main__":
    main()
