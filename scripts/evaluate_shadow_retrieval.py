"""
================================================================================
🩺 MEDIMIND SHADOW RETRIEVAL BENCHMARK RUNNER (PHASE 6.2)
================================================================================
Chạy benchmark độc lập so sánh chất lượng truy xuất giữa:
  A. Collection CŨ (medical_knowledge - Baseline v1 chunking)
  B. Collection MỚI (medical_knowledge_shadow_v2_* - Phase 6.1 boundary-aware chunking)

Thực hiện trên 2 bộ dữ liệu chuẩn đã đóng băng (frozen datasets):
  1. DEV dataset (evaluation/rag_dev_dataset.json - 56 queries)
  2. HOLDOUT dataset (evaluation/rag_test_dataset.json - 102 queries)

Chế độ kiểm thử:
  - Baseline mode: Query Expansion OFF, Vector OFF, Reranker OFF.
  - Secondary mode: Query Expansion ON (với cross-language translation cache).

Lưu kết quả dạng machine-readable JSON tại evaluation/results/shadow_v2_retrieval_benchmark.json
để phục vụ tái hiện và phân tích hồi quy.
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

# Thiết lập đường dẫn root
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

DEV_DATASET_PATH = ROOT / "evaluation" / "rag_dev_dataset.json"
HOLDOUT_DATASET_PATH = ROOT / "evaluation" / "rag_test_dataset.json"
DEV_CACHE_PATH = ROOT / "evaluation" / "cache" / "cross_language_queries.json"
HOLDOUT_CACHE_PATH = ROOT / "evaluation" / "cache" / "cross_language_test_queries.json"
OUTPUT_JSON_PATH = ROOT / "evaluation" / "results" / "shadow_v2_retrieval_benchmark.json"


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


def run_benchmark_on_dataset(
    cases: List[Dict[str, Any]],
    rag_old: MedicalRAGService,
    rag_shadow: MedicalRAGService,
    cache_dict: Dict[str, Any],
    with_expansion: bool = False
) -> Dict[str, Any]:
    old_results = []
    shadow_results = []
    old_latencies = []
    shadow_latencies = []

    for case in cases:
        query = case["query"]
        relevant = case["relevant_documents"]
        lang = case.get("language", "vi")

        # Xác định câu truy vấn mở rộng nếu có
        expanded_term = ""
        if with_expansion and lang == "vi":
            cached = cache_dict.get(query)
            if cached and isinstance(cached, dict):
                raw_exp = cached.get("expanded_query", "")
                try:
                    expanded_term = keywords(raw_exp)
                except Exception:
                    expanded_term = raw_exp

        # 1. Truy xuất với RAG OLD
        t0 = time.perf_counter()
        if with_expansion and expanded_term:
            hits_old = retrieve_with_translation(rag_old, query, expanded_term, 20)
        else:
            hits_old = rag_old.retrieve_candidates(query, 20)
        t_old_ms = (time.perf_counter() - t0) * 1000
        old_latencies.append(t_old_ms)

        # 2. Truy xuất với RAG SHADOW
        t0 = time.perf_counter()
        if with_expansion and expanded_term:
            hits_shadow = retrieve_with_translation(rag_shadow, query, expanded_term, 20)
        else:
            hits_shadow = rag_shadow.retrieve_candidates(query, 20)
        t_shadow_ms = (time.perf_counter() - t0) * 1000
        shadow_latencies.append(t_shadow_ms)

        # Xếp hạng tài liệu theo source_url
        order_old = ranking(hits_old)
        order_shadow = ranking(hits_shadow)

        m_old = metrics([x["id"] for x in order_old], relevant)
        m_shadow = metrics([x["id"] for x in order_shadow], relevant)

        # Candidate recall at 20
        cand_found_old = len(set(x["id"] for x in order_old[:20]) & set(relevant))
        cand_found_shadow = len(set(x["id"] for x in order_shadow[:20]) & set(relevant))
        m_old["candidate_recall@20"] = cand_found_old / len(relevant)
        m_shadow["candidate_recall@20"] = cand_found_shadow / len(relevant)

        # Phân loại Outcome tại Top-5
        old_hit = m_old["hit@5"] > 0
        shadow_hit = m_shadow["hit@5"] > 0
        if old_hit and shadow_hit:
            outcome = "both_hit"
        elif not old_hit and not shadow_hit:
            outcome = "both_miss"
        elif not old_hit and shadow_hit:
            outcome = "improvement"
        else:
            outcome = "regression"

        old_rank_first = next((r for r, d in enumerate(order_old, 1) if d["id"] in relevant), None)
        shadow_rank_first = next((r for r, d in enumerate(order_shadow, 1) if d["id"] in relevant), None)

        record_base = {
            "id": case["id"],
            "query": query,
            "language": lang,
            "category": case.get("category", "unknown"),
            "difficulty": case.get("difficulty", "medium"),
            "relevant_documents": relevant,
            "outcome_at_5": outcome,
            "old_rank_first": old_rank_first,
            "shadow_rank_first": shadow_rank_first,
        }

        old_results.append({**record_base, "metrics": m_old, "latency_ms": t_old_ms})
        shadow_results.append({**record_base, "metrics": m_shadow, "latency_ms": t_shadow_ms})

    # Phân tích tổng thể
    old_agg = compute_aggregate_metrics(old_results)
    shadow_agg = compute_aggregate_metrics(shadow_results)

    # Phân tách theo Ngôn ngữ (VI vs EN)
    languages = sorted(list(set(c.get("language", "vi") for c in cases)))
    lang_breakdown = {}
    for lg in languages:
        old_sub = [r for r in old_results if r["language"] == lg]
        shadow_sub = [r for r in shadow_results if r["language"] == lg]
        lang_breakdown[lg] = {
            "count": len(old_sub),
            "old": compute_aggregate_metrics(old_sub),
            "shadow": compute_aggregate_metrics(shadow_sub)
        }

    # Phân tách theo Chuyên mục (Category breakdown - Recall@5)
    categories = sorted(list(set(c.get("category", "unknown") for c in cases)))
    cat_breakdown = {}
    for cat in categories:
        old_sub = [r for r in old_results if r["category"] == cat]
        shadow_sub = [r for r in shadow_results if r["category"] == cat]
        old_m = compute_aggregate_metrics(old_sub)
        shadow_m = compute_aggregate_metrics(shadow_sub)
        cat_breakdown[cat] = {
            "count": len(old_sub),
            "old_recall@5": old_m.get("recall@5", 0.0),
            "shadow_recall@5": shadow_m.get("recall@5", 0.0),
            "delta": round(shadow_m.get("recall@5", 0.0) - old_m.get("recall@5", 0.0), 4)
        }

    # Phân tách theo Độ khó (Difficulty breakdown - Recall@5)
    difficulties = sorted(list(set(c.get("difficulty", "medium") for c in cases if c.get("difficulty"))))
    diff_breakdown = {}
    for diff in difficulties:
        old_sub = [r for r in old_results if r["difficulty"] == diff]
        shadow_sub = [r for r in shadow_results if r["difficulty"] == diff]
        old_m = compute_aggregate_metrics(old_sub)
        shadow_m = compute_aggregate_metrics(shadow_sub)
        diff_breakdown[diff] = {
            "count": len(old_sub),
            "old_recall@5": old_m.get("recall@5", 0.0),
            "shadow_recall@5": shadow_m.get("recall@5", 0.0),
            "delta": round(shadow_m.get("recall@5", 0.0) - old_m.get("recall@5", 0.0), 4)
        }

    # Phân loại Hồi quy & Cải thiện
    outcomes = Counter(r["outcome_at_5"] for r in shadow_results)
    regressions = [r for r in shadow_results if r["outcome_at_5"] == "regression"]
    improvements = [r for r in shadow_results if r["outcome_at_5"] == "improvement"]

    return {
        "total_cases": len(cases),
        "old_metrics": old_agg,
        "shadow_metrics": shadow_agg,
        "delta": {k: round(shadow_agg[k] - old_agg[k], 4) for k in shadow_agg},
        "latency_old": summarize_latency(old_latencies),
        "latency_shadow": summarize_latency(shadow_latencies),
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
        "difficulty_breakdown": diff_breakdown,
        "per_query_shadow": shadow_results
    }


def main():
    shadow_col_name = "medical_knowledge_shadow_v2_20261114_211653"
    print(f"🚀 Khởi tạo RAG Service cho Old (medical_knowledge) và Shadow ({shadow_col_name})...")

    rag_old = MedicalRAGService(collection_name="medical_knowledge", vector_search_enabled=False)
    rag_shadow = MedicalRAGService(collection_name=shadow_col_name, vector_search_enabled=False)

    assert rag_old.collection.count() == 414, f"Old collection count != 414 ({rag_old.collection.count()})"
    assert rag_shadow.collection.count() == 408, f"Shadow collection count != 408 ({rag_shadow.collection.count()})"

    # Tải frozen datasets
    dev_cases = json.loads(DEV_DATASET_PATH.read_text(encoding="utf-8"))
    holdout_cases = json.loads(HOLDOUT_DATASET_PATH.read_text(encoding="utf-8"))

    dev_cache = {}
    if DEV_CACHE_PATH.exists():
        raw_c = json.loads(DEV_CACHE_PATH.read_text(encoding="utf-8"))
        dev_cache = {x["query"]: x for x in raw_c}

    holdout_cache = {}
    if HOLDOUT_CACHE_PATH.exists():
        raw_c = json.loads(HOLDOUT_CACHE_PATH.read_text(encoding="utf-8"))
        holdout_cache = {x["query"]: x for x in raw_c}

    print("\n" + "=" * 70)
    print("📊 1. BENCHMARK DEV DATASET (Baseline Mode: Expansion OFF, Vector OFF)")
    print("=" * 70)
    dev_baseline = run_benchmark_on_dataset(dev_cases, rag_old, rag_shadow, dev_cache, with_expansion=False)

    print("\n" + "=" * 70)
    print("📊 2. BENCHMARK HOLDOUT DATASET (Baseline Mode: Expansion OFF, Vector OFF)")
    print("=" * 70)
    holdout_baseline = run_benchmark_on_dataset(holdout_cases, rag_old, rag_shadow, holdout_cache, with_expansion=False)

    print("\n" + "=" * 70)
    print("📊 3. BENCHMARK DEV DATASET (Secondary Mode: Query Expansion ON)")
    print("=" * 70)
    dev_expansion = run_benchmark_on_dataset(dev_cases, rag_old, rag_shadow, dev_cache, with_expansion=True)

    print("\n" + "=" * 70)
    print("📊 4. BENCHMARK HOLDOUT DATASET (Secondary Mode: Query Expansion ON)")
    print("=" * 70)
    holdout_expansion = run_benchmark_on_dataset(holdout_cases, rag_old, rag_shadow, holdout_cache, with_expansion=True)

    # Tổng hợp toàn bộ kết quả benchmark
    benchmark_report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "old_collection": "medical_knowledge",
        "shadow_collection": shadow_col_name,
        "dev_baseline": dev_baseline,
        "holdout_baseline": holdout_baseline,
        "dev_expansion": dev_expansion,
        "holdout_expansion": holdout_expansion,
    }

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(json.dumps(benchmark_report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✅ Đã lưu kết quả machine-readable benchmark JSON tại: {OUTPUT_JSON_PATH}")


if __name__ == "__main__":
    from collections import Counter
    main()
