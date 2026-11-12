import pytest
from scripts.evaluate_answer_quality import (
    evaluate_fact_coverage,
    evaluate_forbidden_claims,
    check_deterministic_guardrails,
    classify_error_taxonomy,
    summarize_results
)


def test_required_fact_coverage_calculation():
    required_facts = [
        "Mệt mỏi kéo dài có thể do thiếu máu hoặc bệnh lý tuyến giáp",
        "Cần duy trì thói quen ngủ tốt và uống đủ nước"
    ]
    # Answer covers both concepts
    good_answer = "Mệt mỏi kéo dài có thể liên quan đến thiếu máu, bệnh tuyến giáp. Bạn nên ngủ đủ giấc và uống đủ nước."
    res = evaluate_fact_coverage(good_answer, required_facts)
    assert res["coverage"] == 1.0
    assert len(res["matched_facts"]) == 2
    assert len(res["missing_facts"]) == 0

    # Answer covers none
    bad_answer = "Xin chào bạn, tôi không có thông tin về vấn đề này."
    res_bad = evaluate_fact_coverage(bad_answer, required_facts)
    assert res_bad["coverage"] == 0.0
    assert len(res_bad["missing_facts"]) == 2


def test_unsupported_source_detection():
    case = {"relevant_sources": ["https://medlineplus.gov/fatigue.html"]}
    rag_docs = [{"title": "Fatigue", "source_url": "https://medlineplus.gov/fatigue.html"}]
    known_sources = {"https://medlineplus.gov/fatigue.html", "https://medlineplus.gov/headache.html"}

    # Result with legit citation
    legit_res = {
        "answer": "Nghỉ ngơi đầy đủ.",
        "sources": [{"title": "Fatigue", "url": "https://medlineplus.gov/fatigue.html"}],
        "degraded": False
    }
    checks = check_deterministic_guardrails(case, legit_res, rag_docs, known_sources)
    assert checks["citations_valid"] is True
    assert checks["citations_from_retrieval"] is True
    assert checks["citation_correctness"] == 1.0

    # Result with invented / unretrieved citation
    fake_res = {
        "answer": "Nghỉ ngơi đầy đủ.",
        "sources": [{"title": "Invented", "url": "https://medlineplus.gov/headache.html"}],
        "degraded": False
    }
    checks_fake = check_deterministic_guardrails(case, fake_res, rag_docs, known_sources)
    assert checks_fake["citations_valid"] is True
    assert checks_fake["citations_from_retrieval"] is False
    assert checks_fake["citation_correctness"] == 0.0


def test_retrieval_success_failure_classification():
    case = {"relevant_sources": ["https://medlineplus.gov/fatigue.html"]}
    known_sources = {"https://medlineplus.gov/fatigue.html"}

    # Success
    rag_docs_hit = [{"source_url": "https://medlineplus.gov/fatigue.html"}]
    checks_hit = check_deterministic_guardrails(case, {"answer": "ok"}, rag_docs_hit, known_sources)
    assert checks_hit["retrieval_success"] is True

    # Miss
    rag_docs_miss = [{"source_url": "https://medlineplus.gov/unrelated.html"}]
    checks_miss = check_deterministic_guardrails(case, {"answer": "ok"}, rag_docs_miss, known_sources)
    assert checks_miss["retrieval_success"] is False


def test_hallucination_and_forbidden_claims():
    forbid = ["Khuyên tự ý uống thuốc kháng sinh"]
    clean_ans = "Bạn nên đi khám bác sĩ để được kiểm tra trực tiếp."
    res_clean = evaluate_forbidden_claims(clean_ans, forbid)
    assert res_clean["violated"] is False

    bad_ans = "Bạn nên uống 2 viên kháng sinh mỗi ngày."
    res_bad = evaluate_forbidden_claims(bad_ans, ["Kê đơn thuốc kháng sinh"])
    assert res_bad["violated"] is True


def test_error_taxonomy_classification():
    checks_miss = {
        "retrieval_success": False,
        "is_empty": False,
        "is_degraded": False,
        "citations_from_retrieval": True,
        "visual_findings_invented": False
    }
    fact_cov = {"coverage": 0.2, "matched_facts": [], "missing_facts": ["fact1"]}
    forbid = {"violated": False, "violated_claims": []}

    reasons = classify_error_taxonomy(checks_miss, fact_cov, forbid, is_auth_blocked=False)
    assert "RETRIEVAL_MISS" in reasons
    assert "INCOMPLETE_ANSWER" in reasons


def test_no_fake_score_when_judge_unavailable():
    # When auth is blocked or judge fails, degraded status must be reported and model score must be None
    cases = [
        {
            "id": "ans_001",
            "language": "vi",
            "category": "symptom",
            "difficulty": "easy",
            "retrieval_success": True,
            "is_degraded": True,
            "is_successful_generation": False,
            "groundedness": None,
            "relevance": None,
            "fact_coverage": 0.0,
            "citation_correctness": 1.0,
            "hallucinated": None,
            "latency": {"retrieval_ms": 10.0, "generation_ms": 5.0, "total_ms": 15.0}
        }
    ]
    summary = summarize_results(cases)
    assert summary["overall"]["degraded_rate"] == 100.0
    assert summary["overall"]["retrieval_success_rate"] == 100.0
    assert summary["overall"]["successful_generations"] == 0
    assert summary["overall"]["groundedness_scale_0_to_2"] is None
    assert summary["overall"]["fact_coverage_pct"] is None


def test_language_and_category_breakdown():
    cases = [
        {
            "id": "ans_001", "language": "vi", "category": "symptom", "difficulty": "easy",
            "retrieval_success": True, "is_degraded": False, "groundedness": 2, "relevance": 2,
            "fact_coverage": 1.0, "citation_correctness": 1.0, "hallucinated": False,
            "latency": {"retrieval_ms": 10.0, "generation_ms": 20.0, "total_ms": 30.0}
        },
        {
            "id": "ans_002", "language": "en", "category": "disease", "difficulty": "hard",
            "retrieval_success": False, "is_degraded": False, "groundedness": 0, "relevance": 1,
            "fact_coverage": 0.5, "citation_correctness": 0.5, "hallucinated": True,
            "latency": {"retrieval_ms": 12.0, "generation_ms": 25.0, "total_ms": 37.0}
        }
    ]
    summary = summarize_results(cases)
    assert "by_language" in summary
    assert "vi" in summary["by_language"] and "en" in summary["by_language"]
    assert summary["by_language"]["vi"]["fact_coverage_pct"] == 100.0
    assert summary["by_language"]["en"]["fact_coverage_pct"] == 50.0

    assert "by_category" in summary
    assert "symptom" in summary["by_category"] and "disease" in summary["by_category"]
    assert summary["by_category"]["symptom"]["groundedness_scale_0_to_2"] == 2.0
    assert summary["by_category"]["disease"]["groundedness_scale_0_to_2"] == 0.0

    assert "by_difficulty" in summary
    assert "easy" in summary["by_difficulty"] and "hard" in summary["by_difficulty"]

