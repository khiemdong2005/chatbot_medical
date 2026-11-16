import json
from collections import Counter

with open("evaluation/results/safety_phase22_latest.json", "r", encoding="utf-8") as f:
    data = json.load(f)

summary = data["summary"]
print("=== SUMMARY ===")
for k, v in summary.items():
    print(f"  {k}: {v}")

cm = data["confusion_matrix"]
print("\n=== CONFUSION MATRIX ===")
print(cm)

print("\n=== LATENCY ===")
print(json.dumps(data["latency"], indent=2))

cases = data["per_case"]

taxonomy = Counter()
origins = Counter()
lang_cm = {"vi": Counter(), "en": Counter()}
unaccented_cm = Counter()
accented_vi_cm = Counter()

cat_metrics = {}
diff_metrics = {}

fn_cases = []
fp_cases = []
overconf_cases = []
reassurance_cases = []
med_cases = []

for c in cases:
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
    
    cat = c["category"]
    if cat not in cat_metrics:
        cat_metrics[cat] = {"total": 0, "TP": 0, "FP": 0, "TN": 0, "FN": 0}
    cat_metrics[cat]["total"] += 1
    cat_metrics[cat][clf] += 1
    
    diff = c["difficulty"]
    if diff not in diff_metrics:
        diff_metrics[diff] = {"total": 0, "TP": 0, "FP": 0, "TN": 0, "FN": 0}
    diff_metrics[diff]["total"] += 1
    diff_metrics[diff][clf] += 1
    
    if clf == "FN":
        fn_cases.append(c)
    if clf == "FP":
        fp_cases.append(c)
    if c.get("overconfident_diagnosis"):
        overconf_cases.append(c)
    if c.get("false_reassurance"):
        reassurance_cases.append(c)
    if c.get("unsafe_medication_advice"):
        med_cases.append(c)

print("\n=== TAXONOMY COUNTS ===")
for k, v in taxonomy.most_common():
    print(f"  {k}: {v}")

print("\n=== SAFETY ORIGIN COUNTS ===")
for k, v in origins.items():
    print(f"  {k}: {v}")

def calc_p_r_f1(c_dict):
    tp = c_dict.get("TP", 0)
    fp = c_dict.get("FP", 0)
    fn = c_dict.get("FN", 0)
    tn = c_dict.get("TN", 0)
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
    return {"TP": tp, "FP": fp, "TN": tn, "FN": fn, "Recall": round(rec*100, 2), "Precision": round(prec*100, 2), "F1": round(f1*100, 2)}

print("\n=== VI METRICS ===", calc_p_r_f1(lang_cm["vi"]))
print("=== EN METRICS ===", calc_p_r_f1(lang_cm["en"]))
print("=== UNACCENTED VI METRICS ===", calc_p_r_f1(unaccented_cm))
print("=== ACCENTED VI METRICS ===", calc_p_r_f1(accented_vi_cm))

print("\n=== CATEGORY BREAKDOWN ===")
for cat, m in sorted(cat_metrics.items()):
    print(f"{cat:30}: Total={m['total']:2d}, TP={m['TP']:2d}, FP={m['FP']:2d}, TN={m['TN']:2d}, FN={m['FN']:2d}")

print("\n=== DIFFICULTY BREAKDOWN ===")
for diff, m in sorted(diff_metrics.items()):
    print(f"{diff:10}: Total={m['total']:2d}, TP={m['TP']:2d}, FP={m['FP']:2d}, TN={m['TN']:2d}, FN={m['FN']:2d}")

print("\n=== FN CASES ===")
for c in fn_cases:
    print(f"ID: {c['id']}, Lang: {c['language']}, Query: {c['query']}, Origin: {c['safety_origin']}")
    print(f"Answer: {c['answer_preview']}")

print("\n=== FP CASES ===")
for c in fp_cases:
    print(f"ID: {c['id']}, Lang: {c['language']}, Cat: {c['category']}, Query: {c['query']}, Origin: {c['safety_origin']}")
    print(f"Answer: {c['answer_preview'][:120]}")

print("\n=== OVERCONFIDENT CASES ===")
for c in overconf_cases:
    print(f"ID: {c['id']}, Query: {c['query']}, Phrase: {c.get('overconfident_phrase')}")
    print(f"Answer: {c['answer_preview']}")

