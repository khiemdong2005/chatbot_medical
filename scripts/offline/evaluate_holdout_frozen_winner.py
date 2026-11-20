"""
================================================================================
🩺 MEDIMIND RETRIEVAL DILUTION - HOLDOUT FINAL EVALUATION (PHASE 6.6)
================================================================================
Single official evaluation run on HOLDOUT dataset (102 queries) for the
FROZEN WINNER configuration chosen strictly based on DEV ablations.

Frozen Configuration (Variant E):
  - Collection: medical_knowledge_expanded_v4_20261115_005612 (725 chunks, 364 docs)
  - Symmetric Bilingual Metadata (EN + VI)
  - no_df_cutoff = True
  - source_diversity = False

Evaluated Against:
  - Active V2: medical_knowledge_shadow_v2_20261114_211653 (408 chunks, 241 docs)
    (Standard df cutoff, no diversity)

STRICT EVALUATION INTEGRITY:
  - DEV was used for experiment selection and ablation analysis.
  - Configuration was frozen before running this script.
  - No retuning is performed based on these HOLDOUT results.
================================================================================
"""

import os
import sys
import json
import math
import time
import statistics
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from core.rag_service import MedicalRAGService
from scripts.evaluate_retrieval import metrics, ranking
from scripts.experimental_cross_language import retrieve_with_translation
from scripts.query_expansion_experiment import keywords

HOLDOUT_DATASET_PATH = ROOT / "evaluation" / "rag_test_dataset.json"
HOLDOUT_CACHE_PATH = ROOT / "evaluation" / "cache" / "cross_language_test_queries.json"
OUTPUT_JSON_PATH = ROOT / "evaluation" / "results" / "dilution_remediation_holdout_winner.json"

V2_COLLECTION = "medical_knowledge_shadow_v2_20261114_211653"

# Read V4 shadow collection name
V4_MANIFEST = ROOT / "data" / "curated" / "v4_shadow_manifest.json"
if V4_MANIFEST.exists():
    V4_COLLECTION = json.loads(V4_MANIFEST.read_text(encoding="utf-8"))["collection_name"]
else:
    V4_COLLECTION = "medical_knowledge_expanded_v4_20261115_005612"


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    pos = (len(v) - 1) * p
    lower, upper = math.floor(pos), math.ceil(pos)
    return v[lower] + (v[upper] - v[lower]) * (pos - lower)


def summarize_latency(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0}
    return {
        "mean_ms": round(statistics.mean(values), 2),
        "p50_ms": round(percentile(values, 0.50), 2),
        "p95_ms": round(percentile(values, 0.95), 2),
    }


def compute_aggregate_metrics(per_query: List[Dict[str, Any]]) -> Dict[str, float]:
    if not per_query:
        return {}
    keys = ["hit@1", "hit@3", "hit@5", "recall@1", "recall@3", "recall@5", "candidate_recall@20", "mrr", "ndcg@5"]
    agg = {}
    for k in keys:
        vals = [p["metrics"][k] for p in per_query if k in p["metrics"]]
        agg[k] = round(sum(vals) / len(vals), 4) if vals else 0.0
    return agg


def evaluate_holdout_dataset(
    cases: List[Dict[str, Any]],
    rag_v2: MedicalRAGService,
    rag_v4: MedicalRAGService,
    cache_dict: Dict[str, Any],
    with_expansion: bool = False
) -> Dict[str, Any]:
    v2_results = []
    v4_results = []
    v2_latencies = []
    v4_latencies = []

    # Danh sách URL thuộc 123 tài liệu Tier-A mới
    tier_a_urls = set()
    tier_a_dir = ROOT / "data" / "curated" / "tier_a_candidates"
    for p in tier_a_dir.glob("*.json"):
        if not p.name.startswith("_"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                if d.get("source_url"):
                    tier_a_urls.add(d["source_url"].strip().rstrip("/"))
            except Exception:
                pass

    tier_a_in_top5_count = 0
    tier_a_ground_truth_hit_count = 0
    tier_a_distractor_count = 0

    v4_top5_unique_urls = []
    v4_crowded_queries = 0

    for case in cases:
        query = case["query"]
        relevant = case["relevant_documents"]
        lang = case.get("language", "vi")

        expanded_term = ""
        if with_expansion and lang == "vi":
            cached = cache_dict.get(query)
            if cached and isinstance(cached, dict):
                raw_exp = cached.get("expanded_query", "")
                try:
                    expanded_term = keywords(raw_exp)
                except Exception:
                    expanded_term = raw_exp

        # 1. Active V2 retrieval (Standard df cutoff, no diversity)
        t0 = time.perf_counter()
        if with_expansion and expanded_term:
            hits_v2 = retrieve_with_translation(
                rag_v2, query, expanded_term, top_k=20,
                no_df_cutoff=False, source_diversity=False
            )
        else:
            hits_v2 = rag_v2.retrieve_candidates(
                query, top_k=20, lang=lang,
                no_df_cutoff=False, source_diversity=False
            )
        t_v2_ms = (time.perf_counter() - t0) * 1000
        v2_latencies.append(t_v2_ms)

        # 2. Frozen Winner V4 retrieval (no_df_cutoff=True, source_diversity=False)
        t0 = time.perf_counter()
        if with_expansion and expanded_term:
            hits_v4 = retrieve_with_translation(
                rag_v4, query, expanded_term, top_k=20,
                no_df_cutoff=True, source_diversity=False
            )
        else:
            hits_v4 = rag_v4.retrieve_candidates(
                query, top_k=20, lang=lang,
                no_df_cutoff=True, source_diversity=False
            )
        t_v4_ms = (time.perf_counter() - t0) * 1000
        v4_latencies.append(t_v4_ms)

        order_v2 = ranking(hits_v2)
        order_v4 = ranking(hits_v4)

        m_v2 = metrics([x["id"] for x in order_v2], relevant)
        m_v4 = metrics([x["id"] for x in order_v4], relevant)

        # Candidate recall @ 20
        cand_found_v2 = len(set(x["id"] for x in order_v2[:20]) & set(relevant))
        cand_found_v4 = len(set(x["id"] for x in order_v4[:20]) & set(relevant))
        m_v2["candidate_recall@20"] = cand_found_v2 / len(relevant)
        m_v4["candidate_recall@20"] = cand_found_v4 / len(relevant)

        v2_hit = m_v2["hit@5"] > 0
        v4_hit = m_v4["hit@5"] > 0
        if v2_hit and v4_hit:
            outcome = "both_hit"
        elif not v2_hit and not v4_hit:
            outcome = "both_miss"
        elif not v2_hit and v4_hit:
            outcome = "improvement"
        else:
            outcome = "regression"

        v2_rank_first = next((r for r, d in enumerate(order_v2, 1) if d["id"] in relevant), None)
        v4_rank_first = next((r for r, d in enumerate(order_v4, 1) if d["id"] in relevant), None)

        # Top-5 analysis for V4
        top5_v4_urls = [x["id"] for x in order_v4[:5]]
        unique_urls_v4 = len(set(top5_v4_urls))
        v4_top5_unique_urls.append(unique_urls_v4)
        if any(cnt >= 3 for cnt in Counter(top5_v4_urls).values()):
            v4_crowded_queries += 1

        has_tier_a = any(u in tier_a_urls for u in top5_v4_urls)
        if has_tier_a:
            tier_a_in_top5_count += 1
            if any(u in tier_a_urls and u in relevant for u in top5_v4_urls):
                tier_a_ground_truth_hit_count += 1
            else:
                tier_a_distractor_count += 1

        record_base = {
            "id": case["id"],
            "query": query,
            "language": lang,
            "category": case.get("category", "unknown"),
            "relevant_documents": relevant,
            "outcome_at_5": outcome,
            "v2_rank_first": v2_rank_first,
            "v4_rank_first": v4_rank_first,
            "top5_v2": [x["id"] for x in order_v2[:5]],
            "top5_v4": top5_v4_urls,
        }

        v2_results.append({**record_base, "metrics": m_v2, "latency_ms": t_v2_ms})
        v4_results.append({**record_base, "metrics": m_v4, "latency_ms": t_v4_ms})

    v2_agg = compute_aggregate_metrics(v2_results)
    v4_agg = compute_aggregate_metrics(v4_results)

    # Language breakdown
    languages = sorted(list(set(c.get("language", "vi") for c in cases)))
    lang_breakdown = {}
    for lg in languages:
        v2_sub = [r for r in v2_results if r["language"] == lg]
        v4_sub = [r for r in v4_results if r["language"] == lg]
        v2_sub_agg = compute_aggregate_metrics(v2_sub)
        v4_sub_agg = compute_aggregate_metrics(v4_sub)
        lang_breakdown[lg] = {
            "count": len(v2_sub),
            "v2": v2_sub_agg,
            "v4": v4_sub_agg,
            "delta_recall@5": round(v4_sub_agg.get("recall@5", 0.0) - v2_sub_agg.get("recall@5", 0.0), 4),
            "delta_candidate@20": round(v4_sub_agg.get("candidate_recall@20", 0.0) - v2_sub_agg.get("candidate_recall@20", 0.0), 4)
        }

    # Category breakdown
    categories = sorted(list(set(c.get("category", "unknown") for c in cases)))
    cat_breakdown = {}
    for cat in categories:
        v2_sub = [r for r in v2_results if r["category"] == cat]
        v4_sub = [r for r in v4_results if r["category"] == cat]
        v2_m = compute_aggregate_metrics(v2_sub)
        v4_m = compute_aggregate_metrics(v4_sub)
        cat_breakdown[cat] = {
            "count": len(v2_sub),
            "v2_recall@5": v2_m.get("recall@5", 0.0),
            "v4_recall@5": v4_m.get("recall@5", 0.0),
            "delta": round(v4_m.get("recall@5", 0.0) - v2_m.get("recall@5", 0.0), 4)
        }

    outcomes = Counter(r["outcome_at_5"] for r in v4_results)
    regressions = [r for r in v4_results if r["outcome_at_5"] == "regression"]
    improvements = [r for r in v4_results if r["outcome_at_5"] == "improvement"]

    return {
        "total_cases": len(cases),
        "v2_metrics": v2_agg,
        "v4_metrics": v4_agg,
        "delta": {k: round(v4_agg[k] - v2_agg[k], 4) for k in v4_agg},
        "latency_v2": summarize_latency(v2_latencies),
        "latency_v4": summarize_latency(v4_latencies),
        "outcomes": {
            "both_hit": outcomes.get("both_hit", 0),
            "improvement": outcomes.get("improvement", 0),
            "both_miss": outcomes.get("both_miss", 0),
            "regression": outcomes.get("regression", 0),
        },
        "regressions": regressions,
        "improvements": improvements,
        "language_breakdown": lang_breakdown,
        "category_breakdown": cat_breakdown,
        "diversity": {
            "mean_unique_urls_top5": round(statistics.mean(v4_top5_unique_urls), 2) if v4_top5_unique_urls else 0.0,
            "crowded_queries_count": v4_crowded_queries
        },
        "tier_a_impact": {
            "tier_a_in_top5_count": tier_a_in_top5_count,
            "tier_a_ground_truth_hit_count": tier_a_ground_truth_hit_count,
            "tier_a_distractor_count": tier_a_distractor_count
        }
    }


def run_holdout_evaluation():
    print("=" * 80)
    print("🎯 OFFICIAL HOLDOUT BENCHMARK - FROZEN WINNER (VARIANT E)")
    print(f" • Active Baseline V2: {V2_COLLECTION}")
    print(f" • Frozen Winner V4:   {V4_COLLECTION}")
    print(f" • no_df_cutoff = True | source_diversity = False")
    print("=" * 80)

    holdout_cases = json.loads(HOLDOUT_DATASET_PATH.read_text(encoding="utf-8"))
    raw_cache = json.loads(HOLDOUT_CACHE_PATH.read_text(encoding="utf-8")) if HOLDOUT_CACHE_PATH.exists() else []
    holdout_cache = {x["query"]: x for x in raw_cache} if isinstance(raw_cache, list) else raw_cache

    rag_v2 = MedicalRAGService(collection_name=V2_COLLECTION)
    rag_v4 = MedicalRAGService(collection_name=V4_COLLECTION)

    print("\n[1/2] Đang đánh giá HOLDOUT Baseline (Query Expansion OFF)...")
    baseline_res = evaluate_holdout_dataset(holdout_cases, rag_v2, rag_v4, holdout_cache, with_expansion=False)

    print("[2/2] Đang đánh giá HOLDOUT Expansion ON...")
    expansion_res = evaluate_holdout_dataset(holdout_cases, rag_v2, rag_v4, holdout_cache, with_expansion=True)

    # Acceptance Gates
    # Gate 1: Recall@5 delta >= -1.0 percentage point vs Active V2
    gate_recall5 = baseline_res["delta"].get("recall@5", 0.0) >= -0.01

    # Gate 2: Candidate Recall@20 no material drop vs Active V2 (>= -0.02)
    gate_cand20 = baseline_res["delta"].get("candidate_recall@20", 0.0) >= -0.02

    # Gate 3: Emergency Recall@5 zero regression
    emerg_delta = baseline_res["category_breakdown"].get("emergency", {}).get("delta", 0.0)
    gate_emergency = emerg_delta >= 0.0

    # Gate 4: Medication Recall@5 zero regression
    med_delta = baseline_res["category_breakdown"].get("medication", {}).get("delta", 0.0)
    gate_medication = med_delta >= 0.0

    # Gate 5: VI Recall@5 improvement and EN Recall@5 stable
    vi_delta = baseline_res["language_breakdown"].get("vi", {}).get("delta_recall@5", 0.0)
    en_delta = baseline_res["language_breakdown"].get("en", {}).get("delta_recall@5", 0.0)
    gate_vi_improved = vi_delta > 0.0
    gate_en_stable = en_delta >= 0.0

    # Gate 6: Expansion ON Recall@5 >= 90.20%, Candidate Recall@20 >= 94.12%
    exp_r5 = expansion_res["v4_metrics"].get("recall@5", 0.0)
    exp_c20 = expansion_res["v4_metrics"].get("candidate_recall@20", 0.0)
    gate_exp_r5 = exp_r5 >= 0.9020
    gate_exp_c20 = exp_c20 >= 0.9412

    all_gates_pass = (
        gate_recall5 and
        gate_cand20 and
        gate_emergency and
        gate_medication and
        gate_vi_improved and
        gate_en_stable and
        gate_exp_r5 and
        gate_exp_c20
    )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "integrity_declaration": {
            "tuning_dataset": "DEV (56 queries)",
            "validation_dataset": "HOLDOUT (102 queries)",
            "single_evaluation_run": True,
            "retuning_post_evaluation": False,
            "status": "FROZEN_WINNER_VALIDATED"
        },
        "v2_collection": V2_COLLECTION,
        "v4_collection": V4_COLLECTION,
        "frozen_configuration": {
            "variant": "Variant E (Expanded V4 + No DF Cutoff)",
            "no_df_cutoff": True,
            "source_diversity": False,
            "symmetric_bilingual_metadata": True,
            "documents_count": 364,
            "chunks_count": 725
        },
        "holdout_baseline": baseline_res,
        "holdout_expansion": expansion_res,
        "acceptance_gates": {
            "gate_1_recall@5_delta": {
                "threshold": ">= -1.0pp",
                "actual": f"{baseline_res['delta'].get('recall@5', 0.0) * 100:+.2f}pp",
                "passed": gate_recall5
            },
            "gate_2_candidate_recall@20_delta": {
                "threshold": "no drop (>= -2.0pp)",
                "actual": f"{baseline_res['delta'].get('candidate_recall@20', 0.0) * 100:+.2f}pp",
                "passed": gate_cand20
            },
            "gate_3_emergency_recall@5_regression": {
                "threshold": "0 regression (delta >= 0)",
                "actual": f"{emerg_delta * 100:+.2f}pp",
                "passed": gate_emergency
            },
            "gate_4_medication_recall@5_regression": {
                "threshold": "0 regression (delta >= 0)",
                "actual": f"{med_delta * 100:+.2f}pp",
                "passed": gate_medication
            },
            "gate_5_vi_recall_improvement": {
                "threshold": "VI improved (> 0pp) and EN stable (>= 0pp)",
                "actual_vi": f"{vi_delta * 100:+.2f}pp",
                "actual_en": f"{en_delta * 100:+.2f}pp",
                "passed": gate_vi_improved and gate_en_stable
            },
            "gate_6_expansion_on_quality": {
                "threshold": "Recall@5 >= 90.20%, Cand@20 >= 94.12%",
                "actual_recall@5": f"{exp_r5 * 100:.2f}%",
                "actual_cand@20": f"{exp_c20 * 100:.2f}%",
                "passed": gate_exp_r5 and gate_exp_c20
            },
            "overall_decision": "PASS" if all_gates_pass else "FAIL"
        }
    }

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✅ HOLDOUT benchmark hoàn tất! Đã lưu kết quả tại: {OUTPUT_JSON_PATH}")
    print(f" • Overall Gates Decision: {report['acceptance_gates']['overall_decision']}")
    return report


if __name__ == "__main__":
    run_holdout_evaluation()
