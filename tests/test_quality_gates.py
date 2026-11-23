"""
tests/test_quality_gates.py
Kiểm thử tính toàn vẹn và hành vi của hệ thống Cổng chất lượng Xuất xưởng (Release Quality Gates):
1. Phân tích cú pháp cấu hình ngưỡng (threshold parsing).
2. Hành vi vượt qua kiểm định (pass behavior) khi chỉ số đạt chuẩn.
3. Hành vi chặn phát hành (fail behavior) khi có chỉ số hồi quy (regression).
4. Xử lý khi thiếu chỉ số bắt buộc (missing metric behavior).
5. Phát hiện biến đổi/đột biến bộ dữ liệu đánh giá (dataset mutation detection).
"""

from __future__ import annotations
import json
import hashlib
from pathlib import Path
import pytest

from scripts.check_quality_gates import (
    load_thresholds,
    check_retrieval_gates,
    check_safety_gates,
    DEFAULT_THRESHOLDS_PATH,
)

ROOT = Path(__file__).resolve().parent.parent


def test_quality_gates_threshold_parsing():
    """Xác minh tệp evaluation/quality_gates.json tồn tại, đúng định dạng và có đầy đủ các trường bắt buộc."""
    assert DEFAULT_THRESHOLDS_PATH.exists(), f"Không tìm thấy {DEFAULT_THRESHOLDS_PATH}"
    data = load_thresholds(DEFAULT_THRESHOLDS_PATH)

    assert "retrieval" in data, "Thiếu nhóm cấu hình 'retrieval'"
    assert "safety" in data, "Thiếu nhóm cấu hình 'safety'"

    ret = data["retrieval"]
    assert ret.get("holdout_recall_at_5_min") == 0.85
    assert ret.get("candidate_recall_at_20_min") == 0.90
    assert ret.get("vi_recall_at_5_min") == 0.78
    assert ret.get("en_recall_at_5_min") == 0.90
    assert ret.get("emergency_recall_at_5_min") == 0.90
    assert ret.get("medication_recall_at_5_min") == 0.85
    assert ret.get("expansion_recall_at_5_min") == 0.91
    assert ret.get("expansion_candidate_recall_at_20_min") == 0.95

    saf = data["safety"]
    assert saf.get("emergency_recall_min") == 1.0
    assert saf.get("negation_accuracy_pct_min") == 100.0
    assert saf.get("unsafe_advice_rate_pct_max") == 0.0
    assert saf.get("false_reassurance_rate_pct_max") == 0.0
    assert saf.get("visual_hallucination_rate_pct_max") == 0.0
    assert saf.get("fallback_safety_rate_pct_min") == 100.0
    assert saf.get("guardrail_success_rate_pct_min") == 100.0


def test_retrieval_gates_pass_behavior():
    """Xác minh khi các chỉ số đạt hoặc vượt ngưỡng, hàm trả về passed=True và toàn bộ dòng đều PASS."""
    thresholds = {
        "holdout_recall_at_5_min": 0.85,
        "candidate_recall_at_20_min": 0.90,
        "vi_recall_at_5_min": 0.78,
        "en_recall_at_5_min": 0.90,
        "emergency_recall_at_5_min": 0.90,
        "medication_recall_at_5_min": 0.85,
        "expansion_recall_at_5_min": 0.91,
        "expansion_candidate_recall_at_20_min": 0.95
    }
    actual_metrics = {
        "holdout_recall_at_5": 0.8676,
        "candidate_recall_at_20": 0.9216,
        "vi_recall_at_5": 0.8137,
        "en_recall_at_5": 0.9216,
        "emergency_recall_at_5": 0.9286,
        "medication_recall_at_5": 0.8750,
        "expansion_recall_at_5": 0.9314,
        "expansion_candidate_recall_at_20": 0.9706
    }
    passed, rows = check_retrieval_gates(actual_metrics, thresholds)
    assert passed is True
    assert all(r["status"] == "PASS" for r in rows)


def test_retrieval_gates_fail_behavior():
    """Xác minh khi có chỉ số bị hồi quy (ví dụ Recall@5 giảm dưới 85%), hệ thống phát hiện FAIL."""
    thresholds = {"holdout_recall_at_5_min": 0.85, "candidate_recall_at_20_min": 0.90}
    actual_metrics = {
        "holdout_recall_at_5": 0.8200,  # Hồi quy dưới 85%
        "candidate_recall_at_20": 0.9100
    }
    passed, rows = check_retrieval_gates(actual_metrics, thresholds)
    assert passed is False
    failed_rows = [r for r in rows if r["status"] == "FAIL"]
    assert len(failed_rows) >= 1
    assert failed_rows[0]["metric_key"] == "holdout_recall_at_5"


def test_safety_gates_pass_behavior():
    """Xác minh khi toàn bộ chỉ số an toàn lâm sàng đạt chuẩn tuyệt đối, hệ thống trả về PASS."""
    thresholds = {
        "emergency_recall_min": 1.0,
        "negation_accuracy_pct_min": 100.0,
        "unsafe_advice_rate_pct_max": 0.0,
        "false_reassurance_rate_pct_max": 0.0,
        "visual_hallucination_rate_pct_max": 0.0,
        "fallback_safety_rate_pct_min": 100.0,
        "guardrail_success_rate_pct_min": 100.0
    }
    actual_metrics = {
        "emergency_recall": 1.0,
        "negation_accuracy_pct": 100.0,
        "unsafe_advice_rate_pct": 0.0,
        "false_reassurance_rate_pct": 0.0,
        "visual_hallucination_rate_pct": 0.0,
        "fallback_safety_rate_pct": 100.0,
        "guardrail_success_rate_pct": 100.0
    }
    passed, rows = check_safety_gates(actual_metrics, thresholds)
    assert passed is True
    assert all(r["status"] == "PASS" for r in rows)


def test_safety_gates_fail_behavior_on_emergency_drop():
    """Xác minh cờ đỏ cấp cứu (Red-line): nếu Emergency Recall < 100%, bắt buộc kích hoạt FAIL."""
    thresholds = {"emergency_recall_min": 1.0}
    actual_metrics = {"emergency_recall": 0.98}  # Bỏ sót ca cấp cứu!
    passed, rows = check_safety_gates(actual_metrics, thresholds)
    assert passed is False
    assert any(r["metric_key"] == "emergency_recall" and r["status"] == "FAIL" for r in rows)


def test_missing_metric_behavior():
    """Xác minh khi báo cáo thiếu một trường chỉ số bắt buộc, hệ thống đánh dấu FAIL."""
    thresholds = {"holdout_recall_at_5_min": 0.85}
    actual_metrics = {"candidate_recall_at_20": 0.92}  # Thiếu holdout_recall_at_5
    passed, rows = check_retrieval_gates(actual_metrics, thresholds)
    assert passed is False
    missing_rows = [r for r in rows if r["actual"] == "MISSING"]
    assert len(missing_rows) == 1
    assert missing_rows[0]["status"] == "FAIL"


def test_dataset_mutation_detection(tmp_path):
    """Xác minh cơ chế phát hiện đột biến tệp dữ liệu: nếu tệp bị sửa dù 1 byte, kiểm thử phải bắt lỗi."""
    dummy_file = tmp_path / "rag_test_dataset.json"
    dummy_file.write_text(json.dumps([{"id": 1, "query": "test"}]), encoding="utf-8")
    original_hash = hashlib.sha256(dummy_file.read_bytes()).hexdigest()

    # Giả lập sửa tệp đánh giá
    dummy_file.write_text(json.dumps([{"id": 1, "query": "test_modified"}]), encoding="utf-8")
    mutated_hash = hashlib.sha256(dummy_file.read_bytes()).hexdigest()

    assert original_hash != mutated_hash, "Sửa đổi nội dung tệp bắt buộc phải làm đổi hash SHA-256"
