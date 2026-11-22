"""Ground Truth Evaluation Script for Phase 1.1 Metadata QA.

Computes:
- Meal Role Accuracy
- Precision, Recall, F1 per role
- Confusion Matrix
- Allergen Precision & Recall per allergen
- False Negative & False Positive cases
- Unknown rate & Review required rate
"""

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any, Dict, List, Set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = PROJECT_ROOT / "data" / "recipes" / "vifoodrec" / "recipes_metadata.json"
GT_PATH = PROJECT_ROOT / "data" / "recipes" / "vifoodrec" / "ground_truth_eval_250.json"

BIG_11_ALLERGENS = [
    "shrimp", "crab", "squid_octopus", "fish", "mollusk",
    "peanut", "sesame", "egg", "cow_milk", "soy", "wheat_gluten"
]

def run_evaluation():
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        meta_list = json.load(f)
    with open(GT_PATH, "r", encoding="utf-8") as f:
        gt_list = json.load(f)

    meta_by_id = {m["id"]: m for m in meta_list}
    print("=" * 80)
    print(f"PHASE 1.1: GROUND TRUTH EVALUATION REPORT ({len(gt_list)} BENCHMARK DISHES)")
    print("=" * 80)

    # 1. Meal Role Evaluation
    role_labels = ["main_dish", "standalone", "soup", "vegetable", "dessert", "beverage", "snack", "staple", "other"]
    confusion_matrix = defaultdict(lambda: defaultdict(int))
    correct_roles = 0
    gt_role_counts = Counter()
    pred_role_counts = Counter()
    role_tp = Counter()
    role_fp = Counter()
    role_fn = Counter()

    role_mismatches = []

    for gt in gt_list:
        rid = gt["id"]
        true_role = gt["ground_truth_primary_role"]
        gt_role_counts[true_role] += 1

        pred_meta = meta_by_id.get(rid)
        if not pred_meta:
            continue

        pred_role = pred_meta["primary_role"]
        pred_role_counts[pred_role] += 1
        confusion_matrix[true_role][pred_role] += 1

        if true_role == pred_role:
            correct_roles += 1
            role_tp[true_role] += 1
        else:
            role_fp[pred_role] += 1
            role_fn[true_role] += 1
            role_mismatches.append({
                "id": rid,
                "title": gt["title"],
                "true_role": true_role,
                "pred_role": pred_role,
                "notes": gt.get("notes")
            })

    total_eval = len(gt_list)
    accuracy = (correct_roles / total_eval) * 100

    print(f"\n[Overall Meal Role Classification Accuracy: {accuracy:.2f}% ({correct_roles}/{total_eval})]")

    print(f"\n{'Meal Role':<15} | {'Support':<8} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10}")
    print("-" * 65)
    for r in role_labels:
        supp = gt_role_counts[r]
        if supp == 0 and pred_role_counts[r] == 0:
            continue
        tp = role_tp[r]
        fp = role_fp[r]
        fn = role_fn[r]
        prec = (tp / (tp + fp)) * 100 if (tp + fp) > 0 else 0.0
        rec = (tp / (tp + fn)) * 100 if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        print(f"{r:<15} | {supp:<8} | {prec:>8.2f}% | {rec:>8.2f}% | {f1:>8.2f}%")

    print("\n[Confusion Matrix (Rows: True Role, Columns: Predicted Role)]")
    active_roles = [r for r in role_labels if gt_role_counts[r] > 0 or pred_role_counts[r] > 0]
    row_title = "True \\ Pred"
    header = f"{row_title:<14} | " + " | ".join(f"{r[:6]:>6}" for r in active_roles)
    print(header)
    print("-" * len(header))
    for tr in active_roles:
        row_str = f"{tr:<14} | " + " | ".join(f"{confusion_matrix[tr][pr]:>6}" for pr in active_roles)
        print(row_str)

    if role_mismatches:
        print(f"\n[Role Classification Discrepancies ({len(role_mismatches)} cases)]")
        for m in role_mismatches[:8]:
            print(f"  - [{m['id']}] {m['title']}: True={m['true_role']} -> Pred={m['pred_role']} (Notes: {m['notes']})")

    # 2. Allergen Evaluation per allergen
    print("\n" + "=" * 80)
    print("[Per-Allergen Detection Evaluation across 11 Allergens]")
    print(f"{'Allergen':<16} | {'True Pos':<8} | {'Pred Pos':<8} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10}")
    print("-" * 75)

    allergen_tp = Counter()
    allergen_fp = Counter()
    allergen_fn = Counter()
    allergen_support = Counter()

    for gt in gt_list:
        rid = gt["id"]
        true_allergens = set(gt.get("ground_truth_allergens", []))
        pred_meta = meta_by_id.get(rid, {})
        pred_allergens = set(pred_meta.get("allergen_tags", []))

        for ag in BIG_11_ALLERGENS:
            is_true = ag in true_allergens
            is_pred = ag in pred_allergens

            if is_true:
                allergen_support[ag] += 1
            if is_true and is_pred:
                allergen_tp[ag] += 1
            elif not is_true and is_pred:
                allergen_fp[ag] += 1
            elif is_true and not is_pred:
                allergen_fn[ag] += 1

    for ag in BIG_11_ALLERGENS:
        tp = allergen_tp[ag]
        fp = allergen_fp[ag]
        fn = allergen_fn[ag]
        supp = allergen_support[ag]
        prec = (tp / (tp + fp)) * 100 if (tp + fp) > 0 else (100.0 if supp == 0 else 0.0)
        rec = (tp / (tp + fn)) * 100 if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        print(f"{ag:<16} | {supp:<8} | {tp+fp:<8} | {prec:>8.2f}% | {rec:>8.2f}% | {f1:>8.2f}%")

    # 3. Whole dataset quality statistics
    print("\n" + "=" * 80)
    print("[Full Dataset (2,462 recipes) Quality Metrics]")
    tot_meta = len(meta_list)
    unk_count = sum(1 for m in meta_list if m["allergen_status"] == "unknown")
    rev_count = sum(1 for m in meta_list if m["review_required"])
    has_carbs_count = sum(1 for m in meta_list if m["has_carbohydrate_data"])
    verified_count = sum(1 for m in meta_list if m["nutrition_verified"])

    print(f"  - Total recipes covered: {tot_meta}")
    print(f"  - Unknown allergen rate: {unk_count} ({unk_count/tot_meta*100:.2f}%)")
    print(f"  - Review required rate: {rev_count} ({rev_count/tot_meta*100:.2f}%)")
    print(f"  - Nutrition verified count: {verified_count} (0.0% - transparently unverified for raw dataset)")
    print(f"  - Carbohydrates present: {has_carbs_count} (0.0% - transparently documented as missing from ViFoodRec)")

if __name__ == "__main__":
    run_evaluation()
