"""
================================================================================
🩺 MEDIMIND RELEASE AI QUALITY & CLINICAL SAFETY GATES RUNNER
================================================================================
Responsibilities:
  - Run or validate frozen HOLDOUT retrieval quality metrics.
  - Run or validate frozen clinical safety evaluation metrics.
  - Enforce release thresholds defined in evaluation/quality_gates.json.
  - Output concise, human-readable terminal summary tables.
  - Exit 0 if all quality gates pass, exit 1 if any gate fails.
================================================================================
"""

from __future__ import annotations
import os
import sys

# CRITICAL ZERO-SECRET OFFLINE ENFORCEMENT
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_API_KEY"] = ""
os.environ["GEMINI_NUTRITION_API_KEY"] = ""
os.environ["TWILIO_ACCOUNT_SID"] = ""
os.environ["SPEEDSMS_API_KEY"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["RAG_QUERY_EXPANSION_ENABLED"] = "false"
os.environ["RAG_VECTOR_SEARCH_ENABLED"] = "false"
os.environ["RAG_RERANK_ENABLED"] = "false"

import json
import time
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_THRESHOLDS_PATH = ROOT / "evaluation" / "quality_gates.json"
HOLDOUT_DATASET_PATH = ROOT / "evaluation" / "rag_test_dataset.json"
SAFETY_DATASET_PATH = ROOT / "evaluation" / "safety_eval_dataset.json"
TRANSLATION_CACHE_PATH = ROOT / "evaluation" / "cache" / "cross_language_test_queries.json"


def load_thresholds(path: Path = DEFAULT_THRESHOLDS_PATH) -> Dict[str, Any]:
    """Load release quality thresholds configuration."""
    if not path.exists():
        raise FileNotFoundError(f"Quality gates threshold file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_temporary_eval_index(temp_db_dir: Path, collection_name: str = "release_eval_temp") -> Tuple[bool, Any]:
    """Build a deterministic evaluation Chroma collection from data/curated/ready_documents."""
    from scripts.ingest import run_ingestion
    curated_dir = ROOT / "data" / "curated" / "ready_documents"
    if not curated_dir.exists():
        raise FileNotFoundError(f"Curated ready_documents directory not found: {curated_dir}")

    success, stats = run_ingestion(
        custom_db_dir=temp_db_dir,
        shadow_mode=True,
        collection_name_override=collection_name,
        curated_dirs=[curated_dir]
    )
    if not success:
        raise RuntimeError("Temporary index build failed during ingestion.")

    # Invariant checks per Phase 7.4 specifications
    assert stats.get("total_source_files") == 364, f"Expected 364 source files, got {stats.get('total_source_files')}"
    assert stats.get("total_chunks_planned") == 725, f"Expected 725 chunks, got {stats.get('total_chunks_planned')}"
    assert stats.get("tiny_chunks_count") == 0, f"Expected 0 tiny chunks, got {stats.get('tiny_chunks_count')}"
    assert stats.get("broken_starts_count") == 0, f"Expected 0 broken starts, got {stats.get('broken_starts_count')}"
    assert "100.0%" in stats.get("prefix_coverage_ratio", ""), f"Expected 100% prefix coverage, got {stats.get('prefix_coverage_ratio')}"

    return success, stats


def run_retrieval_benchmark(
    custom_db_dir: Optional[Path] = None,
    collection_name: Optional[str] = None
) -> Dict[str, Any]:
    """Execute the full frozen HOLDOUT retrieval benchmark (Baseline & Expansion)."""
    import tempfile
    from core.rag_service import MedicalRAGService
    from scripts.evaluate_retrieval import metrics, ranking
    from scripts.experimental_cross_language import retrieve_with_translation
    from scripts.query_expansion_experiment import keywords

    if not HOLDOUT_DATASET_PATH.exists():
        raise FileNotFoundError(f"HOLDOUT dataset not found: {HOLDOUT_DATASET_PATH}")

    cases = json.loads(HOLDOUT_DATASET_PATH.read_text(encoding="utf-8"))

    # Determine collection and DB directory
    rag: Optional[MedicalRAGService] = None
    if custom_db_dir and collection_name:
        try:
            candidate = MedicalRAGService(
                db_dir=custom_db_dir,
                collection_name=collection_name,
                no_df_cutoff=True
            )
            if candidate.is_available():
                rag = candidate
        except Exception:
            rag = None

    if rag is None or not rag.is_available():
        # Check active collection in medical_vectordb
        active_config = ROOT / "medical_vectordb" / "active_collection.json"
        if active_config.exists():
            cfg = json.loads(active_config.read_text(encoding="utf-8"))
            coll = collection_name or cfg.get("active_collection")
            try:
                candidate = MedicalRAGService(collection_name=coll, no_df_cutoff=True)
                if candidate.is_available():
                    rag = candidate
            except Exception:
                rag = None

    if rag is None or not rag.is_available():
        temp_eval_dir = Path(tempfile.mkdtemp(prefix="medimind_release_eval_"))
        temp_coll = collection_name or "release_eval_temp"
        print(f"[Quality Gates] Active index unavailable. Building temporary evaluation index at {temp_eval_dir}...")
        build_temporary_eval_index(temp_eval_dir, collection_name=temp_coll)
        rag = MedicalRAGService(db_dir=temp_eval_dir, collection_name=temp_coll, no_df_cutoff=True)

    if not rag.is_available():
        raise RuntimeError("RAG service collection is unavailable for benchmark.")

    # Load cached expansions for deterministic expansion evaluation
    cache_dict = {}
    if TRANSLATION_CACHE_PATH.exists():
        raw_cache = json.loads(TRANSLATION_CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw_cache, list):
            cache_dict = {x["query"]: x for x in raw_cache}
        elif isinstance(raw_cache, dict):
            cache_dict = raw_cache

    t_start = time.perf_counter()

    # 1. Evaluate Baseline (Query Expansion OFF, Vector OFF, Reranker OFF)
    baseline_query_results = []
    for case in cases:
        query = case["query"]
        lang = case.get("language", "vi")
        rel = case["relevant_documents"]

        hits = rag.retrieve_candidates(query, top_k=20, lang=lang, no_df_cutoff=True, source_diversity=False)
        order = ranking(hits)
        m = metrics([x["id"] for x in order], rel)
        cand_found = len(set(x["id"] for x in order[:20]) & set(rel))
        m["candidate_recall@20"] = cand_found / len(rel)
        baseline_query_results.append({"case": case, "metrics": m})

    # 2. Evaluate Expansion ON (deterministic with cached expansions)
    expansion_query_results = []
    for case in cases:
        query = case["query"]
        lang = case.get("language", "vi")
        rel = case["relevant_documents"]

        expanded_term = ""
        if lang == "vi" and query in cache_dict:
            raw_exp = cache_dict[query].get("expanded_query", "")
            try:
                expanded_term = keywords(raw_exp)
            except Exception:
                expanded_term = raw_exp

        if expanded_term:
            hits = retrieve_with_translation(rag, query, expanded_term, top_k=20, no_df_cutoff=True, source_diversity=False)
        else:
            hits = rag.retrieve_candidates(query, top_k=20, lang=lang, no_df_cutoff=True, source_diversity=False)

        order = ranking(hits)
        m = metrics([x["id"] for x in order], rel)
        cand_found = len(set(x["id"] for x in order[:20]) & set(rel))
        m["candidate_recall@20"] = cand_found / len(rel)
        expansion_query_results.append({"case": case, "metrics": m})

    elapsed_s = time.perf_counter() - t_start

    # Compute aggregate metrics
    tot = len(cases)
    overall_rec5 = sum(p["metrics"]["recall@5"] for p in baseline_query_results) / tot
    overall_cand20 = sum(p["metrics"]["candidate_recall@20"] for p in baseline_query_results) / tot
    overall_mrr = sum(p["metrics"]["mrr"] for p in baseline_query_results) / tot
    overall_ndcg5 = sum(p["metrics"]["ndcg@5"] for p in baseline_query_results) / tot

    vi_cases = [p for p in baseline_query_results if p["case"].get("language") == "vi"]
    en_cases = [p for p in baseline_query_results if p["case"].get("language") == "en"]
    emg_cases = [p for p in baseline_query_results if p["case"].get("category") == "emergency"]
    med_cases = [p for p in baseline_query_results if p["case"].get("category") == "medication"]

    vi_rec5 = sum(p["metrics"]["recall@5"] for p in vi_cases) / len(vi_cases) if vi_cases else 0.0
    en_rec5 = sum(p["metrics"]["recall@5"] for p in en_cases) / len(en_cases) if en_cases else 0.0
    emg_rec5 = sum(p["metrics"]["recall@5"] for p in emg_cases) / len(emg_cases) if emg_cases else 0.0
    med_rec5 = sum(p["metrics"]["recall@5"] for p in med_cases) / len(med_cases) if med_cases else 0.0

    exp_rec5 = sum(p["metrics"]["recall@5"] for p in expansion_query_results) / tot
    exp_cand20 = sum(p["metrics"]["candidate_recall@20"] for p in expansion_query_results) / tot

    return {
        "summary": {
            "query_count": tot,
            "benchmark_time_seconds": round(elapsed_s, 2),
            "holdout_recall_at_5": round(overall_rec5, 4),
            "candidate_recall_at_20": round(overall_cand20, 4),
            "vi_recall_at_5": round(vi_rec5, 4),
            "en_recall_at_5": round(en_rec5, 4),
            "emergency_recall_at_5": round(emg_rec5, 4),
            "medication_recall_at_5": round(med_rec5, 4),
            "mrr": round(overall_mrr, 4),
            "ndcg_at_5": round(overall_ndcg5, 4),
            "expansion_recall_at_5": round(exp_rec5, 4),
            "expansion_candidate_recall_at_20": round(exp_cand20, 4)
        }
    }


def run_clinical_safety_benchmark() -> Dict[str, Any]:
    """Execute the full frozen clinical safety evaluation (100 scenarios, offline/zero secrets)."""
    from scripts.evaluate_clinical_safety import run_safety_evaluation

    if not SAFETY_DATASET_PATH.exists():
        raise FileNotFoundError(f"Safety dataset not found: {SAFETY_DATASET_PATH}")

    cases = json.loads(SAFETY_DATASET_PATH.read_text(encoding="utf-8"))
    report = run_safety_evaluation(cases, gemini_service=None, pacing_seconds=0, mock_mode=False)
    return report


def check_retrieval_gates(
    metrics: Dict[str, float],
    thresholds: Dict[str, float]
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Compare retrieval metrics against configured thresholds."""
    mapping = [
        ("holdout_recall_at_5", "holdout_recall_at_5_min", ">=", "HOLDOUT Recall@5 (Baseline)"),
        ("candidate_recall_at_20", "candidate_recall_at_20_min", ">=", "Candidate Recall@20 (Baseline)"),
        ("vi_recall_at_5", "vi_recall_at_5_min", ">=", "Vietnamese Queries Recall@5"),
        ("en_recall_at_5", "en_recall_at_5_min", ">=", "English Queries Recall@5"),
        ("emergency_recall_at_5", "emergency_recall_at_5_min", ">=", "Emergency Category Recall@5"),
        ("medication_recall_at_5", "medication_recall_at_5_min", ">=", "Medication Category Recall@5"),
        ("expansion_recall_at_5", "expansion_recall_at_5_min", ">=", "Query Expansion ON Recall@5"),
        ("expansion_candidate_recall_at_20", "expansion_candidate_recall_at_20_min", ">=", "Query Expansion ON Candidate Recall@20"),
    ]

    all_passed = True
    rows = []

    for metric_key, thresh_key, op, label in mapping:
        thresh = thresholds.get(thresh_key)
        if thresh is None:
            continue

        if metric_key not in metrics:
            all_passed = False
            rows.append({
                "label": label,
                "metric_key": metric_key,
                "threshold": f"{thresh * 100:.2f}%",
                "actual": "MISSING",
                "status": "FAIL",
                "delta": "N/A"
            })
            continue

        actual = metrics[metric_key]
        passed = actual >= thresh if op == ">=" else actual <= thresh
        if not passed:
            all_passed = False

        delta = round(actual - thresh, 4)
        rows.append({
            "label": label,
            "metric_key": metric_key,
            "threshold": f"{thresh * 100:.2f}%",
            "actual": f"{actual * 100:.2f}%",
            "status": "PASS" if passed else "FAIL",
            "delta": f"{'+' if delta >= 0 else ''}{delta * 100:.2f}%"
        })

    return all_passed, rows


def check_safety_gates(
    metrics: Dict[str, float],
    thresholds: Dict[str, float]
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Compare clinical safety metrics against configured thresholds."""
    mapping = [
        ("emergency_recall", "emergency_recall_min", ">=", "Emergency Recall (Triage Red-line)"),
        ("negation_accuracy_pct", "negation_accuracy_pct_min", ">=", "Negation Accuracy"),
        ("unsafe_advice_rate_pct", "unsafe_advice_rate_pct_max", "<=", "Unsafe Medication Advice Rate"),
        ("false_reassurance_rate_pct", "false_reassurance_rate_pct_max", "<=", "False Reassurance Rate"),
        ("visual_hallucination_rate_pct", "visual_hallucination_rate_pct_max", "<=", "Visual Hallucination Rate"),
        ("fallback_safety_rate_pct", "fallback_safety_rate_pct_min", ">=", "Fallback Safety Rate"),
        ("guardrail_success_rate_pct", "guardrail_success_rate_pct_min", ">=", "Guardrail Success Rate"),
    ]

    all_passed = True
    rows = []

    for metric_key, thresh_key, op, label in mapping:
        thresh = thresholds.get(thresh_key)
        if thresh is None:
            continue

        is_pct = metric_key.endswith("_pct") or metric_key in ("negation_accuracy_pct", "unsafe_advice_rate_pct", "false_reassurance_rate_pct", "visual_hallucination_rate_pct", "fallback_safety_rate_pct", "guardrail_success_rate_pct")
        unit = "%" if is_pct else ""
        thresh_str = f"{thresh:.2f}{unit}" if is_pct else f"{thresh * 100:.2f}%"

        if metric_key not in metrics:
            all_passed = False
            rows.append({
                "label": label,
                "metric_key": metric_key,
                "threshold": thresh_str,
                "actual": "MISSING",
                "status": "FAIL",
                "delta": "N/A"
            })
            continue

        actual = metrics[metric_key]
        passed = actual >= thresh if op == ">=" else actual <= thresh
        if not passed:
            all_passed = False

        delta = round(actual - thresh, 4)
        actual_str = f"{actual:.2f}{unit}" if is_pct else f"{actual * 100:.2f}%"
        delta_str = f"{'+' if delta >= 0 else ''}{delta:.2f}{unit}" if is_pct else f"{'+' if delta >= 0 else ''}{delta * 100:.2f}%"

        rows.append({
            "label": label,
            "metric_key": metric_key,
            "threshold": thresh_str,
            "actual": actual_str,
            "status": "PASS" if passed else "FAIL",
            "delta": delta_str
        })

    return all_passed, rows


def print_table(title: str, rows: List[Dict[str, Any]]):
    """Print an aligned terminal table for quality gate results."""
    print("\n" + "=" * 90)
    print(f" {title}")
    print("=" * 90)
    print(f"{'Metric':<42} | {'Threshold':<12} | {'Actual':<12} | {'Delta':<10} | {'Status':<6}")
    print("-" * 90)
    for r in rows:
        print(f"{r['label']:<42} | {r['threshold']:<12} | {r['actual']:<12} | {r['delta']:<10} | {r['status']:<6}")
    print("=" * 90)


def main():
    parser = argparse.ArgumentParser(description="Check AI Quality & Safety Gates against Release Thresholds")
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS_PATH, help="Path to quality_gates.json")
    parser.add_argument("--retrieval", type=Path, default=None, help="Path to existing retrieval quality JSON")
    parser.add_argument("--safety", type=Path, default=None, help="Path to existing safety quality JSON")
    parser.add_argument("--run-retrieval", action="store_true", help="Run retrieval benchmark live")
    parser.add_argument("--run-safety", action="store_true", help="Run clinical safety benchmark live")
    parser.add_argument("--output-retrieval", type=Path, default=None, help="Where to save retrieval benchmark JSON")
    parser.add_argument("--output-safety", type=Path, default=None, help="Where to save safety benchmark JSON")
    parser.add_argument("--db-dir", type=Path, default=None, help="Optional Chroma DB directory for retrieval benchmark")
    parser.add_argument("--collection-name", type=str, default=None, help="Optional Chroma collection name override")

    args = parser.parse_args()

    thresholds_data = load_thresholds(args.thresholds)
    retrieval_thresholds = thresholds_data.get("retrieval", {})
    safety_thresholds = thresholds_data.get("safety", {})

    overall_passed = True

    # 1. Retrieval Benchmark / Check
    if args.run_retrieval:
        print("\n[Quality Gates] Đang thực thi benchmark truy xuất RAG trên tập HOLDOUT (102 câu hỏi)...")
        ret_result = run_retrieval_benchmark(
            custom_db_dir=args.db_dir,
            collection_name=args.collection_name
        )
        if args.output_retrieval:
            args.output_retrieval.parent.mkdir(parents=True, exist_ok=True)
            args.output_retrieval.write_text(json.dumps(ret_result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"[Quality Gates] Đã lưu kết quả truy xuất vào {args.output_retrieval}")
        ret_metrics = ret_result.get("summary", {})
        passed, rows = check_retrieval_gates(ret_metrics, retrieval_thresholds)
        print_table("RAG RETRIEVAL QUALITY GATES (HOLDOUT 102 QUERIES)", rows)
        if not passed:
            overall_passed = False
    elif args.retrieval:
        ret_data = json.loads(args.retrieval.read_text(encoding="utf-8"))
        ret_metrics = ret_data.get("summary", {}) if "summary" in ret_data else ret_data
        passed, rows = check_retrieval_gates(ret_metrics, retrieval_thresholds)
        print_table("RAG RETRIEVAL QUALITY GATES (FROM ARTIFACT)", rows)
        if not passed:
            overall_passed = False

    # 2. Safety Benchmark / Check
    if args.run_safety:
        print("\n[Quality Gates] Đang thực thi kiểm định An toàn Lâm sàng (100 kịch bản)...")
        safety_result = run_clinical_safety_benchmark()
        if args.output_safety:
            args.output_safety.parent.mkdir(parents=True, exist_ok=True)
            args.output_safety.write_text(json.dumps(safety_result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"[Quality Gates] Đã lưu kết quả an toàn lâm sàng vào {args.output_safety}")
        safety_metrics = safety_result.get("summary", {})
        passed, rows = check_safety_gates(safety_metrics, safety_thresholds)
        print_table("CLINICAL SAFETY QUALITY GATES (100 SCENARIOS)", rows)
        if not passed:
            overall_passed = False
    elif args.safety:
        safety_data = json.loads(args.safety.read_text(encoding="utf-8"))
        safety_metrics = safety_data.get("summary", {}) if "summary" in safety_data else safety_data
        passed, rows = check_safety_gates(safety_metrics, safety_thresholds)
        print_table("CLINICAL SAFETY QUALITY GATES (FROM ARTIFACT)", rows)
        if not passed:
            overall_passed = False

    print("\n" + "=" * 90)
    if overall_passed:
        print("  🎉 TOÀN BỘ CỔNG CHẤT LƯỢNG AI & AN TOÀN LÂM SÀNG ĐẠT CHUẨN XUẤT XƯỞNG (RELEASE PASSED)")
        print("=" * 90 + "\n")
        sys.exit(0)
    else:
        print("  ❌ CÓ CHỈ SỐ KHÔNG ĐẠT NGƯỠNG AN TOÀN HOẶC CHẤT LƯỢNG — BLOCK RELEASE!")
        print("=" * 90 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
