"""
Benchmark runner comparing RAG performance: Runtime Expansion OFF vs ON.
Evaluates the independent holdout dataset (evaluation/rag_test_dataset.json).
"""
import sys
import json
import time
import math
from pathlib import Path
from collections import Counter
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.rag_service import medical_rag_service
from core.query_expansion_service import query_expansion_service
from scripts.evaluate_retrieval import metrics, ranking, average


def run_holdout_benchmark(warm_cache: bool = True) -> Dict[str, Any]:
    dataset_path = ROOT / "evaluation" / "rag_test_dataset.json"
    cache_path = ROOT / "evaluation" / "cache" / "cross_language_test_queries.json"

    if not dataset_path.exists():
        raise FileNotFoundError(f"Holdout dataset not found at {dataset_path}")

    cases = json.loads(dataset_path.read_text(encoding="utf-8"))

    # Optional cache pre-warming for holdout reproducibility
    if warm_cache and cache_path.exists():
        cached_queries = json.loads(cache_path.read_text(encoding="utf-8"))
        for item in cached_queries:
            q = item.get("query", "")
            exp = item.get("expanded_query", "")
            if q and exp:
                key_hash = query_expansion_service._hash_key(q)
                query_expansion_service._put_to_cache(key_hash, exp)

    results = {}

    for mode_name, enabled in [("expansion_off", False), ("expansion_on", True)]:
        query_expansion_service.enabled = enabled
        rows = []

        for case in cases:
            query = case["query"]
            lang = case["language"]
            relevant = case["relevant_documents"]

            start_t = time.perf_counter()
            candidates = medical_rag_service.retrieve_candidates(query, top_k=20, lang=lang)
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0

            ordered = ranking(candidates)
            ranks = [r["id"] for r in ordered]
            m = metrics(ranks, relevant)
            cand_recall_20 = len(set(ranks[:20]) & set(relevant)) / len(relevant)

            rows.append({
                "id": case["id"],
                "query": query,
                "language": lang,
                "category": case["category"],
                "relevant_documents": relevant,
                "ranking": ordered,
                "metrics": m,
                "candidate_recall_at_20": cand_recall_20,
                "latency_ms": elapsed_ms
            })

        # Calculate aggregations
        def summarize_group(sub_rows):
            n = len(sub_rows)
            if n == 0:
                return {}
            avg_m = average([r["metrics"] for r in sub_rows])
            cand_r20 = sum(r["candidate_recall_at_20"] for r in sub_rows) / n
            latencies = sorted(r["latency_ms"] for r in sub_rows)
            p50 = latencies[int(n * 0.50)]
            p95 = latencies[min(n - 1, int(n * 0.95))]
            mean_lat = sum(latencies) / n
            return {
                "count": n,
                "recall_at_1": avg_m.get("recall@1", 0.0),
                "recall_at_3": avg_m.get("recall@3", 0.0),
                "recall_at_5": avg_m.get("recall@5", 0.0),
                "candidate_recall_at_20": cand_r20,
                "mrr": avg_m.get("mrr", 0.0),
                "ndcg_at_5": avg_m.get("ndcg@5", 0.0),
                "latency_ms": {
                    "mean": round(mean_lat, 2),
                    "p50": round(p50, 2),
                    "p95": round(p95, 2)
                }
            }

        vi_rows = [r for r in rows if r["language"] == "vi"]
        en_rows = [r for r in rows if r["language"] == "en"]

        results[mode_name] = {
            "overall": summarize_group(rows),
            "vi": summarize_group(vi_rows),
            "en": summarize_group(en_rows),
            "per_case": rows
        }

    # Reset expansion to default disabled state
    query_expansion_service.enabled = False

    output_path = ROOT / "evaluation" / "results" / "rag_runtime_expansion_benchmark.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results


if __name__ == "__main__":
    print("Running RAG Runtime Expansion Benchmark...")
    res = run_holdout_benchmark(warm_cache=True)
    off_ov = res["expansion_off"]["overall"]
    on_ov = res["expansion_on"]["overall"]
    off_vi = res["expansion_off"]["vi"]
    on_vi = res["expansion_on"]["vi"]
    off_en = res["expansion_off"]["en"]
    on_en = res["expansion_on"]["en"]

    print("\n================== BENCHMARK RESULTS ==================")
    print(f"Overall Recall@5:        OFF={off_ov['recall_at_5']*100:.2f}% -> ON={on_ov['recall_at_5']*100:.2f}%")
    print(f"VI Recall@5:             OFF={off_vi['recall_at_5']*100:.2f}% -> ON={on_vi['recall_at_5']*100:.2f}%")
    print(f"EN Recall@5:             OFF={off_en['recall_at_5']*100:.2f}% -> ON={on_en['recall_at_5']*100:.2f}%")
    print(f"Overall Cand Recall@20:  OFF={off_ov['candidate_recall_at_20']*100:.2f}% -> ON={on_ov['candidate_recall_at_20']*100:.2f}%")
    print(f"VI Cand Recall@20:       OFF={off_vi['candidate_recall_at_20']*100:.2f}% -> ON={on_vi['candidate_recall_at_20']*100:.2f}%")
    print(f"MRR:                     OFF={off_ov['mrr']:.4f} -> ON={on_ov['mrr']:.4f}")
    print(f"NDCG@5:                  OFF={off_ov['ndcg_at_5']:.4f} -> ON={on_ov['ndcg_at_5']:.4f}")
    print("=======================================================")

