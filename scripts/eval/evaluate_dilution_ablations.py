"""
================================================================================
🩺 MEDIMIND RETRIEVAL DILUTION ABLATION BENCHMARK (PHASE 6.6 - DEV ONLY)
================================================================================
Evaluates 6 retrieval variants strictly on DEV dataset (56 queries):
  Variant A: Active V2 (408 chunks, standard df cutoff)
  Variant B: Expanded V3 (687 chunks, standard df cutoff)
  Variant C: Expanded V3 + NO_DF_CUTOFF (687 chunks, no df cutoff)
  Variant D: Expanded V4 (725 chunks, symmetric bilingual, standard df cutoff)
  Variant E: Expanded V4 + NO_DF_CUTOFF (725 chunks, symmetric bilingual, no df cutoff)
  Variant F: Expanded V4 + NO_DF_CUTOFF + Source Diversity

STRICT INTEGRITY: HOLDOUT IS NOT ACCESSED OR EVALUATED DURING TUNING.
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

ROOT = Path(__file__).resolve().parents[2]
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

DEV_DATASET_PATH = ROOT / "evaluation" / "rag_dev_dataset.json"
DEV_CACHE_PATH = ROOT / "evaluation" / "cache" / "cross_language_queries.json"
OUTPUT_JSON_PATH = ROOT / "evaluation" / "results" / "dilution_remediation_dev_ablations.json"

V2_COLLECTION = "medical_knowledge_shadow_v2_20261114_211653"
V3_COLLECTION = "medical_knowledge_expanded_v3_20261115_000308"

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


def evaluate_variant(
    cases: List[Dict[str, Any]],
    rag: MedicalRAGService,
    cache_dict: Dict[str, Any],
    with_expansion: bool = False,
    no_df_cutoff: bool = False,
    source_diversity: bool = False
) -> Dict[str, Any]:
    results = []
    latencies = []
    top5_unique_urls_counts = []
    crowded_queries_count = 0  # queries where one URL occupies >= 3 Top-5 chunks

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

        t0 = time.perf_counter()
        if with_expansion and expanded_term:
            hits = retrieve_with_translation(
                rag, query, expanded_term, top_k=20,
                no_df_cutoff=no_df_cutoff, source_diversity=source_diversity
            )
        else:
            hits = rag.retrieve_candidates(
                query, top_k=20, lang=lang,
                no_df_cutoff=no_df_cutoff, source_diversity=source_diversity
            )
        t_ms = (time.perf_counter() - t0) * 1000
        latencies.append(t_ms)

        # Candidate order & metrics
        order = ranking(hits)
        m = metrics([x["id"] for x in order], relevant)

        # Candidate recall @ 20
        cand_found = len(set(x["id"] for x in order[:20]) & set(relevant))
        m["candidate_recall@20"] = cand_found / len(relevant)

        rank_first = next((r for r, d in enumerate(order, 1) if d["id"] in relevant), None)

        # Top-5 diversity & crowding
        top5_urls = [x["id"] for x in order[:5]]
        unique_urls_in_top5 = len(set(top5_urls))
        top5_unique_urls_counts.append(unique_urls_in_top5)

        url_counts = Counter(top5_urls)
        is_crowded = any(cnt >= 3 for cnt in url_counts.values())
        if is_crowded:
            crowded_queries_count += 1

        record = {
            "id": case["id"],
            "query": query,
            "language": lang,
            "category": case.get("category", "unknown"),
            "relevant_documents": relevant,
            "metrics": m,
            "rank_first": rank_first,
            "top5": top5_urls,
            "unique_urls_in_top5": unique_urls_in_top5,
            "is_crowded": is_crowded,
            "latency_ms": t_ms
        }
        results.append(record)

    agg = compute_aggregate_metrics(results)

    # VI vs EN breakdown
    lang_breakdown = {}
    for lg in ["vi", "en"]:
        sub = [r for r in results if r["language"] == lg]
        if sub:
            m_sub = compute_aggregate_metrics(sub)
            lang_breakdown[lg] = {
                "count": len(sub),
                "recall@5": m_sub.get("recall@5", 0.0),
                "candidate_recall@20": m_sub.get("candidate_recall@20", 0.0),
                "mrr": m_sub.get("mrr", 0.0)
            }

    # Category breakdown (focusing on emergency and medication)
    cat_breakdown = {}
    for cat in ["emergency", "medication", "prevention", "disease", "symptom", "diagnosis", "treatment"]:
        sub = [r for r in results if r["category"] == cat]
        if sub:
            m_sub = compute_aggregate_metrics(sub)
            cat_breakdown[cat] = {
                "count": len(sub),
                "recall@5": m_sub.get("recall@5", 0.0),
                "candidate_recall@20": m_sub.get("candidate_recall@20", 0.0)
            }

    mean_div = round(statistics.mean(top5_unique_urls_counts), 2) if top5_unique_urls_counts else 0.0

    return {
        "metrics": agg,
        "latency": summarize_latency(latencies),
        "language_breakdown": lang_breakdown,
        "category_breakdown": cat_breakdown,
        "diversity": {
            "mean_unique_urls_top5": mean_div,
            "crowded_queries_count": crowded_queries_count
        },
        "per_query": results
    }


def run_ablations():
    print("=" * 80)
    print("🚀 BẮT ĐẦU CHẠY MA TRẬN ABLATION RETRIEVAL DILUTION (CHỈ TRÊN TẬP DEV)")
    print(f" • Active V2: {V2_COLLECTION}")
    print(f" • Expanded V3: {V3_COLLECTION}")
    print(f" • Expanded V4: {V4_COLLECTION}")
    print("=" * 80)

    dev_cases = json.loads(DEV_DATASET_PATH.read_text(encoding="utf-8"))
    raw_cache = json.loads(DEV_CACHE_PATH.read_text(encoding="utf-8")) if DEV_CACHE_PATH.exists() else []
    dev_cache = {x["query"]: x for x in raw_cache} if isinstance(raw_cache, list) else raw_cache

    rag_v2 = MedicalRAGService(collection_name=V2_COLLECTION)
    rag_v3 = MedicalRAGService(collection_name=V3_COLLECTION)
    rag_v4 = MedicalRAGService(collection_name=V4_COLLECTION)

    variants_config = [
        ("Variant A (V2 Active)", rag_v2, False, False),
        ("Variant B (V3 Current)", rag_v3, False, False),
        ("Variant C (V3 + No DF Cutoff)", rag_v3, True, False),
        ("Variant D (V4 Bilingual + DF Cutoff)", rag_v4, False, False),
        ("Variant E (V4 Bilingual + No DF Cutoff)", rag_v4, True, False),
        ("Variant F (V4 + No DF Cutoff + Diversity)", rag_v4, True, True),
    ]

    all_results = {}

    print("\n--- 1. CHẠY BASELINE (QUERY EXPANSION OFF) ---")
    for name, rag_inst, no_df, div in variants_config:
        print(f" Đang đánh giá {name} (Baseline)...")
        res = evaluate_variant(dev_cases, rag_inst, dev_cache, with_expansion=False, no_df_cutoff=no_df, source_diversity=div)
        all_results[f"{name}__Baseline"] = res

    print("\n--- 2. CHẠY EXPANSION ON (QUERY EXPANSION ON) ---")
    for name, rag_inst, no_df, div in variants_config:
        print(f" Đang đánh giá {name} (Expansion ON)...")
        res = evaluate_variant(dev_cases, rag_inst, dev_cache, with_expansion=True, no_df_cutoff=no_df, source_diversity=div)
        all_results[f"{name}__Expansion"] = res

    # Tổng hợp bảng so sánh
    table_rows = []
    v2_base = all_results["Variant A (V2 Active)__Baseline"]["metrics"]

    print("\n" + "=" * 90)
    print(f"{'Variant':<42} | {'Recall@5':<9} | {'Cand@20':<8} | {'VI R@5':<7} | {'EN R@5':<7} | {'Exp R@5':<7} | {'Lat P50':<7}")
    print("-" * 90)

    for name, _, _, _ in variants_config:
        base_res = all_results[f"{name}__Baseline"]
        exp_res = all_results[f"{name}__Expansion"]

        r5 = base_res["metrics"].get("recall@5", 0.0)
        c20 = base_res["metrics"].get("candidate_recall@20", 0.0)
        vi_r5 = base_res["language_breakdown"].get("vi", {}).get("recall@5", 0.0)
        en_r5 = base_res["language_breakdown"].get("en", {}).get("recall@5", 0.0)
        exp_r5 = exp_res["metrics"].get("recall@5", 0.0)
        p50 = base_res["latency"].get("p50_ms", 0.0)

        row_str = f"{name:<42} | {r5:<9.4f} | {c20:<8.4f} | {vi_r5:<7.4f} | {en_r5:<7.4f} | {exp_r5:<7.4f} | {p50:<7.2f}ms"
        print(row_str)
        table_rows.append({
            "variant": name,
            "recall@5": r5,
            "candidate@20": c20,
            "vi_recall@5": vi_r5,
            "en_recall@5": en_r5,
            "expansion_recall@5": exp_r5,
            "latency_p50_ms": p50,
            "mean_unique_urls_top5": base_res["diversity"]["mean_unique_urls_top5"],
            "crowded_queries": base_res["diversity"]["crowded_queries_count"]
        })

    print("=" * 90)

    # Phân tích ranking shift so với Variant A
    v2_queries = {r["id"]: r for r in all_results["Variant A (V2 Active)__Baseline"]["per_query"]}
    shifts = {}

    for name, _, _, _ in variants_config[1:]:
        v_queries = {r["id"]: r for r in all_results[f"{name}__Baseline"]["per_query"]}
        improvements = []
        regressions = []
        for q_id, q_v2 in v2_queries.items():
            hit_v2 = q_v2["metrics"]["hit@5"] > 0
            hit_v = v_queries[q_id]["metrics"]["hit@5"] > 0
            if not hit_v2 and hit_v:
                improvements.append({
                    "id": q_id,
                    "query": q_v2["query"],
                    "old_rank": q_v2["rank_first"],
                    "new_rank": v_queries[q_id]["rank_first"]
                })
            elif hit_v2 and not hit_v:
                regressions.append({
                    "id": q_id,
                    "query": q_v2["query"],
                    "old_rank": q_v2["rank_first"],
                    "new_rank": v_queries[q_id]["rank_first"]
                })
        shifts[name] = {
            "improvements_count": len(improvements),
            "regressions_count": len(regressions),
            "improvements": improvements,
            "regressions": regressions
        }

    out_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary_table": table_rows,
        "ranking_shifts": shifts,
        "results": {k: {
            "metrics": v["metrics"],
            "latency": v["latency"],
            "language_breakdown": v["language_breakdown"],
            "category_breakdown": v["category_breakdown"],
            "diversity": v["diversity"]
        } for k, v in all_results.items()}
    }

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Đã lưu toàn bộ kết quả ablation tại: {OUTPUT_JSON_PATH}")
    return out_data


if __name__ == "__main__":
    run_ablations()
