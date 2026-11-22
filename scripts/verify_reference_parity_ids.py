"""Verify 9/9 Reference Parity based on Candidate IDs (Not just counts)."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.nutrition.constraint_resolver import ConstraintResolver
from core.nutrition.constraint_filter import ConstraintFilter
from core.nutrition.reference_filter import ReferenceFilter
from core.nutrition.metadata_index import get_metadata_index

idx = get_metadata_index()

BENCHMARK_SCENARIOS = [
    ("1. Healthy Eating", {}, "ăn lành mạnh"),
    ("2. Gút cấp (Gout)", {"conditions": ["gout"]}, "bệnh gút"),
    ("3. Dị ứng tôm (Shrimp)", {"allergies": ["shrimp"]}, "dị ứng tôm"),
    ("4. Nhiều dị ứng (Tôm+Trứng+Sữa)", {"allergies": ["shrimp", "egg", "cow_milk"]}, "dị ứng tôm và trứng"),
    ("5. Gút + Tiểu đường", {"conditions": ["gout", "diabetes"]}, "gút và tiểu đường"),
    ("6. Tiểu đường + Tôm + Không chiên", {"conditions": ["diabetes"], "allergies": ["shrimp"]}, "tiểu đường, dị ứng tôm, không ăn đồ chiên"),
    ("7. Dị ứng chưa hỗ trợ (Tree Nuts)", {"allergies": ["tree_nuts"]}, "dị ứng hạt điều và óc chó"),
    ("8. Lọc fail-closed (Gluten)", {"allergies": ["wheat_gluten"]}, "kiêng gluten"),
    ("9. Tập rỗng (Impossible)", {"disliked_ingredients": ["tat ca cac mon"]}, "không ăn bất kỳ món nào"),
]

print("=" * 105)
print("VERIFYING 9/9 REFERENCE FILTER PARITY AT CANDIDATE ID LEVEL")
print("=" * 105)

header = f"{'Scenario':<36} | {'Index Count':<11} | {'Ref Count':<9} | {'Jaccard':<7} | {'False Inc (+)':<13} | {'False Exc (-)':<13} | {'Parity'}"
print(header)
print("-" * len(header))

all_parity_passed = True

for name, prof, q in BENCHMARK_SCENARIOS:
    res = ConstraintResolver.resolve_constraints(profile=prof, condition_query=q)
    pools = ConstraintFilter.filter_candidates(res, index=idx)
    ref_list = ReferenceFilter.filter_candidates(
        res,
        recipe_by_id=idx.recipe_by_id,
        metadata_by_id=idx.metadata_by_id,
        manual_review_ids=idx.manual_review_ids
    )

    index_ids = pools.unique_candidate_ids
    ref_ids = set(ref_list)

    false_inc = index_ids - ref_ids
    false_exc = ref_ids - index_ids
    sym_diff = index_ids ^ ref_ids

    intersection = index_ids & ref_ids
    union = index_ids | ref_ids
    jaccard = (len(intersection) / len(union)) if union else 1.0

    is_parity = (sym_diff == set())

    if not is_parity:
        all_parity_passed = False

    print(
        f"{name:<36} | {len(index_ids):>11} | {len(ref_ids):>9} | {jaccard:>7.4f} | {len(false_inc):>13} | {len(false_exc):>13} | {'EXACT PASS' if is_parity else 'FAIL'}"
    )

print("-" * len(header))
if all_parity_passed:
    print(">>> FINAL VERDICT: 9/9 SCENARIOS REACHED 100% CANDIDATE ID LEVEL PARITY (0 DIFFERENCES) <<<")
else:
    print(">>> PARITY CHECK FAILED <<<")
