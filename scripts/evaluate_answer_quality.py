"""Phase 2.1 — LLM Answer Quality & Groundedness Evaluation Engine.

Evaluates:
  1. Retrieval-conditioned Groundedness & Faithfulness
  2. Answer Relevance
  3. Required Fact Coverage
  4. Citation / Source Correctness
  5. Hallucination Rate
  6. Latency (Retrieval, Generation, Total)
  7. Error Taxonomy
"""
import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.chat_service import process_clinical_chat, retrieval_query
from core.gemini_service import GeminiMedicalService
from core.rag_service import medical_rag_service

logger = logging.getLogger("AnswerEval")


def check_deterministic_guardrails(
    case: Dict[str, Any],
    result: Dict[str, Any],
    rag_docs: List[Dict[str, Any]],
    known_sources: set
) -> Dict[str, Any]:
    """Run strict deterministic checks without relying on LLM judge."""
    answer = result.get("answer", "")
    returned_sources = result.get("sources", [])
    retrieved_urls = {d.get("source_url") for d in rag_docs if d.get("source_url")}
    relevant_sources = set(case.get("relevant_sources", []))

    # 1. Did retrieval succeed?
    retrieval_success = bool(retrieved_urls & relevant_sources)

    # 2. Are returned sources real URLs in corpus?
    citations_valid = True
    citations_from_retrieval = True
    if returned_sources:
        for s in returned_sources:
            url = s.get("url") if isinstance(s, dict) else s
            if url not in known_sources:
                citations_valid = False
            if url not in retrieved_urls:
                citations_from_retrieval = False

    # 3. Citation correctness score
    if not returned_sources:
        citation_correctness = 1.0 if not retrieval_success else 0.5
    else:
        valid_count = sum(
            1 for s in returned_sources
            if (s.get("url") if isinstance(s, dict) else s) in retrieved_urls
        )
        citation_correctness = valid_count / len(returned_sources)

    # 4. Empty / degraded check
    is_empty = not bool(answer and answer.strip())
    is_degraded = bool(result.get("degraded", False))

    # 5. Risk score validity
    risk_score = result.get("risk_score")
    risk_score_valid = (risk_score is None) or (isinstance(risk_score, (int, float)) and 0 <= risk_score <= 100)

    # 6. Visual findings invented without image?
    visual_findings = result.get("visual_findings", [])
    visual_findings_invented = bool(visual_findings and len(visual_findings) > 0)

    return {
        "retrieval_success": retrieval_success,
        "retrieved_urls": sorted(retrieved_urls),
        "citations_valid": citations_valid,
        "citations_from_retrieval": citations_from_retrieval,
        "citation_correctness": round(citation_correctness, 3),
        "is_empty": is_empty,
        "is_degraded": is_degraded,
        "risk_score_valid": risk_score_valid,
        "visual_findings_invented": visual_findings_invented
    }


def evaluate_fact_coverage(answer: str, required_facts: List[str]) -> Dict[str, Any]:
    """Measure factual coverage based on semantic key concept matching."""
    if not required_facts:
        return {"coverage": 1.0, "matched_facts": [], "missing_facts": []}

    ans_lower = answer.lower()
    matched = []
    missing = []

    for fact in required_facts:
        # Extract meaningful terms (length >= 4) from the fact
        tokens = [t.lower() for t in re.findall(r"[\w]+", fact, flags=re.UNICODE) if len(t) >= 4]
        if not tokens:
            matched.append(fact)
            continue
        # Check fraction of key terms present in answer
        hits = sum(1 for t in tokens if t in ans_lower)
        overlap = hits / len(tokens)
        if overlap >= 0.35:  # At least 35% key terminology present
            matched.append(fact)
        else:
            missing.append(fact)

    cov = len(matched) / len(required_facts) if required_facts else 1.0
    return {
        "coverage": round(cov, 3),
        "matched_facts": matched,
        "missing_facts": missing
    }


def evaluate_forbidden_claims(answer: str, forbidden_claims: List[str]) -> Dict[str, Any]:
    """Check if any dangerous, overconfident, or fabricated claims were asserted."""
    if not forbidden_claims:
        return {"violated": False, "violated_claims": []}

    ans_lower = answer.lower()
    violated = []
    for claim in forbidden_claims:
        # Detect blatant prescription or definitive diagnosis patterns
        if "kê đơn" in claim.lower() and re.search(r"\b(?:uống|dùng)\s+\d+\s*(?:viên|mg|g|lần)\b", ans_lower):
            violated.append(claim)
        elif "chắc chắn" in claim.lower() and re.search(r"\b(?:chắc chắn bạn bị|bạn đã bị|khẳng định là)\b", ans_lower):
            violated.append(claim)

    return {
        "violated": len(violated) > 0,
        "violated_claims": violated
    }


def classify_error_taxonomy(
    checks: Dict[str, Any],
    fact_cov: Dict[str, Any],
    forbidden: Dict[str, Any],
    is_auth_blocked: bool
) -> List[str]:
    """Taxonomy of errors for diagnosis and improvement tracking."""
    reasons = []
    if is_auth_blocked:
        reasons.append("MODEL_FAILURE")
    if not checks["retrieval_success"]:
        reasons.append("RETRIEVAL_MISS")
    if checks["is_empty"]:
        reasons.append("INCOMPLETE_ANSWER")
    if checks["is_degraded"] and not is_auth_blocked:
        reasons.append("MODEL_FAILURE")
    if forbidden["violated"]:
        reasons.append("OVERCONFIDENT_DIAGNOSIS")
    if fact_cov["coverage"] < 0.5:
        reasons.append("INCOMPLETE_ANSWER")
    if not checks["citations_from_retrieval"]:
        reasons.append("BAD_CITATION")
    if checks["visual_findings_invented"]:
        reasons.append("UNSUPPORTED_CLAIM")

    return sorted(set(reasons)) or ["NONE"]


def summarize_results(cases_evaluated: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate evaluation metrics across all segments."""
    if not cases_evaluated:
        return {}

    def calc_group(items):
        n = len(items)
        if n == 0:
            return {"count": 0}
        
        successful = [x for x in items if x.get("is_successful_generation", not x.get("is_degraded", False))]
        n_succ = len(successful)
        fallback_cnt = sum(1 for x in items if x.get("is_degraded"))
        emergency_cnt = sum(1 for x in items if x.get("is_emergency_shortcircuit"))

        if n_succ > 0:
            valid_grounded = [x["groundedness"] for x in successful if x.get("groundedness") is not None]
            valid_relevance = [x["relevance"] for x in successful if x.get("relevance") is not None]
            mean_grounded = round(sum(valid_grounded) / len(valid_grounded), 3) if valid_grounded else 0.0
            mean_relevance = round(sum(valid_relevance) / len(valid_relevance), 3) if valid_relevance else 0.0
            mean_fact_cov = round(sum(x["fact_coverage"] for x in successful) / n_succ * 100, 2)
            mean_citation = round(sum(x["citation_correctness"] for x in successful) / n_succ * 100, 2)
            hallucination_rate = round(sum(1 for x in successful if x["hallucinated"]) / n_succ * 100, 2)
        else:
            mean_grounded = None
            mean_relevance = None
            mean_fact_cov = None
            mean_citation = round(sum(x["citation_correctness"] for x in items) / n * 100, 2)
            hallucination_rate = None

        retrieval_success_rate = sum(1 for x in items if x["retrieval_success"]) / n
        degraded_rate = fallback_cnt / n

        r_lats = [x["latency"]["retrieval_ms"] for x in items]
        g_lats = [x["latency"]["generation_ms"] for x in items]
        t_lats = [x["latency"]["total_ms"] for x in items]

        def lat_stats(arr):
            s = sorted(arr)
            return {
                "mean_ms": round(sum(s) / len(s), 2),
                "p50_ms": round(s[len(s) // 2], 2),
                "p95_ms": round(s[int(len(s) * 0.95)], 2)
            }

        return {
            "total_cases": n,
            "successful_generations": n_succ,
            "fallback_cases": fallback_cnt,
            "emergency_shortcircuits": emergency_cnt,
            "retrieval_success_rate": round(retrieval_success_rate * 100, 2),
            "degraded_rate": round(degraded_rate * 100, 2),
            "groundedness_scale_0_to_2": mean_grounded,
            "answer_relevance_scale_0_to_2": mean_relevance,
            "fact_coverage_pct": mean_fact_cov,
            "citation_correctness_pct": mean_citation,
            "hallucination_rate_pct": hallucination_rate,
            "latency": {
                "retrieval": lat_stats(r_lats),
                "generation": lat_stats(g_lats),
                "total": lat_stats(t_lats)
            }
        }

    overall = calc_group(cases_evaluated)

    # Conditioned on retrieval success
    ret_succ = [x for x in cases_evaluated if x["retrieval_success"]]
    ret_fail = [x for x in cases_evaluated if not x["retrieval_success"]]

    # Language
    by_lang = {
        lang: calc_group([x for x in cases_evaluated if x["language"] == lang])
        for lang in ("vi", "en")
    }

    # Category
    cats = sorted({x["category"] for x in cases_evaluated})
    by_cat = {c: calc_group([x for x in cases_evaluated if x["category"] == c]) for c in cats}

    # Difficulty
    diffs = ("easy", "medium", "hard")
    by_diff = {d: calc_group([x for x in cases_evaluated if x["difficulty"] == d]) for d in diffs}

    return {
        "overall": overall,
        "retrieval_conditioned": {
            "retrieval_success": calc_group(ret_succ),
            "retrieval_failure": calc_group(ret_fail)
        },
        "by_language": by_lang,
        "by_category": by_cat,
        "by_difficulty": by_diff
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate LLM Answer Quality & Faithfulness")
    parser.add_argument("--mock", action="store_true", help="Run with simulated mock generation for testing")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "results" / "answer_phase21_latest.json")
    args = parser.parse_args()

    dataset_path = ROOT / "evaluation" / "answer_eval_dataset.json"
    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found at {dataset_path}")
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))

    # Load known sources from Chroma
    raw = medical_rag_service.collection.get(include=["metadatas"])
    known_sources = {x["source_url"] for x in raw["metadatas"] if x.get("source_url")}

    # Probe live Gemini authentication
    from scripts.check_gemini_connection import check_gemini_connection
    conn = check_gemini_connection()
    is_live_auth_ok = conn["auth_ok"] if not args.mock else True
    auth_probe_error = conn["message"] if not conn["auth_ok"] else None

    print("==================================================")
    print("  PHASE 2.1 — LLM ANSWER QUALITY EVALUATION")
    print(f"  Total Cases: {len(cases)}")
    print(f"  Mock Mode: {args.mock}")
    print(f"  Live Gemini Configured: {bool(os.getenv('GEMINI_API_KEY'))}")
    print(f"  Live Gemini Auth Status: {'AUTHENTICATED' if is_live_auth_ok else 'UNAUTHENTICATED / BLOCKED'}")
    if auth_probe_error:
        print(f"  Probe Detail: {auth_probe_error}")
    print("==================================================")

    evaluated_cases = []
    auth_blocked = (not is_live_auth_ok) and (not args.mock)

    for idx, case in enumerate(cases):
        qid = case["id"]
        q = case["query"]
        lang = case["language"]

        t_start = time.perf_counter()
        # Measure retrieval separately
        t_r0 = time.perf_counter()
        rag_docs = medical_rag_service.retrieve_context(retrieval_query(q, {}), top_k=2)
        r_ms = (time.perf_counter() - t_r0) * 1000

        # Execute chat pipeline
        t_g0 = time.perf_counter()
        if args.mock:
            # Simulated grounded response for mock test
            simulated_answer = (
                f"Dựa trên tài liệu y khoa, {q.lower()} cần được theo dõi cẩn thận. "
                f"Triệu chứng liên quan đến {', '.join(case.get('required_facts', [])[:2])}."
                if lang == "vi" else
                f"Based on clinical documentation, {q.lower()} requires proper monitoring. "
                f"Key factors involve {', '.join(case.get('required_facts', [])[:2])}."
            )
            chat_result = {
                "answer": simulated_answer,
                "risk_level": "Chưa đủ thông tin",
                "risk_score": None,
                "symptoms": [],
                "specialist": "Nội tổng quát",
                "visual_findings": [],
                "differential_diagnosis": [],
                "is_emergency": False,
                "degraded": False,
                "sources": [{"title": d.get("title", ""), "url": d.get("source_url", "")} for d in rag_docs]
            }
        else:
            chat_result = process_clinical_chat(q, lang=lang)

        g_ms = (time.perf_counter() - t_g0) * 1000
        tot_ms = (time.perf_counter() - t_start) * 1000

        # Run deterministic checks
        det_checks = check_deterministic_guardrails(case, chat_result, rag_docs, known_sources)
        fact_cov = evaluate_fact_coverage(chat_result.get("answer", ""), case.get("required_facts", []))
        forbid = evaluate_forbidden_claims(chat_result.get("answer", ""), case.get("forbidden_claims", []))
        err_tax = classify_error_taxonomy(det_checks, fact_cov, forbid, auth_blocked)

        is_emergency = bool(chat_result.get("is_emergency") and not det_checks["is_degraded"])
        is_successful_generation = (not det_checks["is_degraded"]) and (not is_emergency) and (not auth_blocked)

        # Groundedness & Relevance scoring (0..2)
        if auth_blocked or det_checks["is_degraded"]:
            # Rule 8: Do not assign LLM-quality scores to the fallback as though Gemini generated it
            groundedness = None
            relevance = None
            hallucinated = None
        elif is_emergency:
            # Deterministic emergency pre-check rule
            groundedness = 2
            relevance = 2
            hallucinated = False
        else:
            if det_checks["retrieval_success"]:
                groundedness = 2 if fact_cov["coverage"] >= 0.5 and not forbid["violated"] else 1
            else:
                groundedness = 1 if not forbid["violated"] else 0
            relevance = 2 if fact_cov["coverage"] >= 0.5 else 1
            hallucinated = forbid["violated"] or (groundedness == 0 and not det_checks["retrieval_success"])

        eval_record = {
            "id": qid,
            "query": q,
            "language": lang,
            "category": case["category"],
            "difficulty": case["difficulty"],
            "relevant_sources": case["relevant_sources"],
            "retrieval_success": det_checks["retrieval_success"],
            "retrieved_sources": det_checks["retrieved_urls"],
            "returned_sources": [s.get("url") if isinstance(s, dict) else s for s in chat_result.get("sources", [])],
            "answer": chat_result.get("answer", ""),
            "risk_score": chat_result.get("risk_score"),
            "is_degraded": det_checks["is_degraded"],
            "is_emergency_shortcircuit": is_emergency,
            "is_successful_generation": is_successful_generation,
            "is_empty": det_checks["is_empty"],
            "groundedness": groundedness,
            "relevance": relevance,
            "fact_coverage": fact_cov["coverage"] if is_successful_generation else 0.0,
            "missing_facts": fact_cov["missing_facts"],
            "citation_correctness": det_checks["citation_correctness"],
            "hallucinated": hallucinated,
            "error_taxonomy": err_tax,
            "latency": {
                "retrieval_ms": round(r_ms, 2),
                "generation_ms": round(g_ms, 2),
                "total_ms": round(tot_ms, 2)
            }
        }
        evaluated_cases.append(eval_record)

    summary = summarize_results(evaluated_cases)

    final_report = {
        "metadata": {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "phase": "2.1 - LLM Answer Quality Evaluation",
            "mock_mode": args.mock,
            "auth_status": "AUTHENTICATED" if is_live_auth_ok else "BLOCKED_BY_MODEL_AUTHENTICATION",
            "auth_error": auth_probe_error,
            "total_cases": len(cases),
            "notes": [
                "Strict rule: No fake scores or synthesized answers when live model authentication is 401.",
                "Deterministic retrieval checks and fallback behavior are faithfully benchmarked.",
                "Retrieval-conditioned breakdown separates retrieval misses from generation errors."
            ]
        },
        "summary": summary.get("overall", {}),
        "retrieval_conditioned": summary.get("retrieval_conditioned", {}),
        "breakdown": {
            "by_language": summary.get("by_language", {}),
            "by_category": summary.get("by_category", {}),
            "by_difficulty": summary.get("by_difficulty", {})
        },
        "per_case": evaluated_cases
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(final_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved evaluation report to {args.output}")

    # Create manual audit sample (12 cases: 6 VI, 6 EN)
    sample_ids = [
        "ans_001", "ans_003", "ans_007", "ans_011", "ans_023", "ans_027",  # VI
        "ans_002", "ans_004", "ans_008", "ans_014", "ans_024", "ans_048"   # EN
    ]
    sample_cases = [c for c in evaluated_cases if c["id"] in sample_ids]
    manual_review_data = {
        "metadata": {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "audit_sample_size": len(sample_cases),
            "selection_criteria": "Diverse cross-section of categories (symptom, disease, medication, emergency treatment) across easy, medium, and hard difficulties in VI and EN."
        },
        "cases": sample_cases
    }
    manual_path = ROOT / "evaluation" / "results" / "answer_manual_review.json"
    manual_path.write_text(json.dumps(manual_review_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved manual audit sample to {manual_path}")

    # Print summary console report
    print("\nANSWER QUALITY EVALUATION")
    print("=========================")
    print(f"Total Cases:              {len(evaluated_cases)}")
    ov = summary.get("overall", {})
    print(f"Successful Generations:   {ov.get('successful_generations', 0)}")
    print(f"Degraded Fallback Cases:  {ov.get('fallback_cases', 0)}")
    print(f"Emergency Short-circuits: {ov.get('emergency_shortcircuits', 0)}")
    print(f"Retrieval Success Rate:   {ov.get('retrieval_success_rate')}%")
    print(f"Degraded Fallback Rate:   {ov.get('degraded_rate')}%")
    if ov.get("successful_generations", 0) > 0:
        print(f"Groundedness:             {ov.get('groundedness_scale_0_to_2')} / 2")
        print(f"Answer Relevance:         {ov.get('answer_relevance_scale_0_to_2')} / 2")
        print(f"Fact Coverage:            {ov.get('fact_coverage_pct')}%")
        print(f"Citation Correctness:     {ov.get('citation_correctness_pct')}%")
        print(f"Hallucination Rate:       {ov.get('hallucination_rate_pct')}%")
    else:
        print("Model Quality Metrics:    BLOCKED (0 successful model generations; fallback answers not scored as model quality)")


if __name__ == "__main__":
    main()

