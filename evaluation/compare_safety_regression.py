import json
from collections import Counter

with open("evaluation/results/safety_phase22_before.json", "r", encoding="utf-8") as f:
    before = json.load(f)

with open("evaluation/results/safety_phase23_regression.json", "r", encoding="utf-8") as f:
    after = json.load(f)

print("=== SUMMARY COMPARISON ===")
metrics = [
    ("emergency_recall", "Recall", lambda v: f"{v*100:.2f}%"),
    ("emergency_precision", "Precision", lambda v: f"{v*100:.2f}%"),
    ("emergency_f1", "F1", lambda v: f"{v*100:.2f}%"),
    ("negation_accuracy_pct", "Negation Accuracy", lambda v: f"{v:.2f}%"),
    ("unsafe_advice_rate_pct", "Unsafe Advice Rate", lambda v: f"{v:.2f}%"),
    ("false_reassurance_rate_pct", "False Reassurance", lambda v: f"{v:.2f}%"),
    ("overconfident_diagnosis_rate_pct", "Overconfident Diagnosis", lambda v: f"{v:.2f}%"),
    ("visual_hallucination_rate_pct", "Visual Hallucination", lambda v: f"{v:.2f}%"),
    ("guardrail_success_rate_pct", "Guardrail Success", lambda v: f"{v:.2f}%"),
    ("fallback_safety_rate_pct", "Fallback Safety", lambda v: f"{v:.2f}%"),
]

for k, name, fmt in metrics:
    b_val = before["summary"][k]
    a_val = after["summary"][k]
    print(f"{name:25}: Before={fmt(b_val):8s} -> After={fmt(a_val):8s}")

print("\n=== CONFUSION MATRIX ===")
print("Before:", before["confusion_matrix"])
print("After :", after["confusion_matrix"])

print("\n=== LATENCY COMPARISON ===")
print("Before Short-circuit:", before["latency"]["emergency_short_circuit"])
print("After  Short-circuit:", after["latency"]["emergency_short_circuit"])
print("Before Total        :", before["latency"]["total"])
print("After  Total        :", after["latency"]["total"])

# Language breakdown for After
lang_cm = {"vi": Counter(), "en": Counter()}
unaccented_cm = Counter()
accented_vi_cm = Counter()
taxonomy = Counter()
origins = Counter()
fp_cases = []
fn_cases = []

for c in after["per_case"]:
    l = c["language"]
    clf = c["confusion_classification"]
    lang_cm[l][clf] += 1
    if c["is_unaccented"]:
        unaccented_cm[clf] += 1
    elif l == "vi":
        accented_vi_cm[clf] += 1
    for tax in c["error_taxonomy"]:
        taxonomy[tax] += 1
    origins[c["safety_origin"]] += 1
    if clf == "FP":
        fp_cases.append(c)
    if clf == "FN":
        fn_cases.append(c)

def calc_p_r_f1(c_dict):
    tp = c_dict.get("TP", 0)
    fp = c_dict.get("FP", 0)
    fn = c_dict.get("FN", 0)
    tn = c_dict.get("TN", 0)
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
    return {"TP": tp, "FP": fp, "TN": tn, "FN": fn, "Recall": f"{rec*100:.2f}%", "Precision": f"{prec*100:.2f}%", "F1": f"{f1*100:.2f}%"}

print("\n=== VI METRICS (AFTER) ===", calc_p_r_f1(lang_cm["vi"]))
print("=== EN METRICS (AFTER) ===", calc_p_r_f1(lang_cm["en"]))
print("=== UNACCENTED VI (AFTER) ===", calc_p_r_f1(unaccented_cm))
print("=== ACCENTED VI (AFTER) ===", calc_p_r_f1(accented_vi_cm))

print("\n=== TAXONOMY COUNTS (AFTER) ===")
for k, v in taxonomy.most_common():
    print(f"  {k}: {v}")

print("\n=== SAFETY ORIGIN COUNTS (AFTER) ===")
for k, v in origins.items():
    print(f"  {k}: {v}")

print("\n=== REMAINING FP CASES (AFTER) ===")
for c in fp_cases:
    print(f"ID: {c['id']}, Lang: {c['language']}, Cat: {c['category']}, Query: {c['query']}, Origin: {c['safety_origin']}")
    print(f"  Answer: {c['answer_preview'][:120]}")

print("\n=== REMAINING FN CASES (AFTER) ===")
for c in fn_cases:
    print(f"ID: {c['id']}, Lang: {c['language']}, Query: {c['query']}")

