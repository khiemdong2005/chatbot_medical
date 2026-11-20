"""
tests/test_clinical_safety_phase1.py
Regression suite cho PHASE 1 — CLINICAL SAFETY REMEDIATION:
1. Medication data safety: không tự điền 40mg, 1 viên, default_qty, lịch 07:00 hoặc sau ăn khi thiếu dữ liệu.
2. Lab result safety: không mặc định Normal khi thiếu reference range/unit/flag hoặc kết quả phi số ('Âm tính').
3. Chatbot triage safety: không để câu chào kèm triệu chứng đi vào greeting fast-path; không bịa medlineplus.gov hay liều Paracetamol 500mg; giữ emergency handling.
4. PII protection: mask_pii=True với bboxes rỗng không đánh lừa đã che và chặn gửi ảnh chưa che ra external AI.
"""
from unittest.mock import Mock
from PIL import Image, ImageDraw

import core.pipeline_orchestrator as pipe
from core.reconciliation_service import (
    _extract_medications_robust,
    parse_clinical_prescription_blocks,
    _clean_and_refine_medication_list,
    extract_schema_from_ocr,
)
from core.grounding_service import parse_frequency_to_schedule
from core.validation_service import calculate_lab_flag, validate_lab_rules
from core.intake_service import mask_pii_on_image, generate_pre_visit_summary
from core.chat_service import process_clinical_chat
from core.gemini_service import GeminiMedicalService
from core.triage import analyze_symptoms


def test_medication_extractors_never_fabricate_missing_dosage_or_schedule():
    rows = [{"text": "1. Febuxostat", "items": [{"text": "1. Febuxostat"}]}]
    meds = _extract_medications_robust(rows, "1. Febuxostat")
    assert len(meds) == 1
    assert meds[0]["strength"] == ""
    assert meds[0]["dose"] == ""
    assert meds[0]["frequency"] == ""
    assert meds[0]["usage"] == ""
    assert meds[0]["needs_review"] is True

    block_meds = parse_clinical_prescription_blocks(["1. Gastosic"])
    assert len(block_meds) == 1
    assert block_meds[0]["dose"] == ""
    assert block_meds[0]["quantity"] == ""
    assert block_meds[0]["usage"] == ""
    assert block_meds[0]["needs_review"] is True

    refined = _clean_and_refine_medication_list(
        [{"name": "Gastosic", "days": "20", "strength": "", "dose": "", "frequency": "", "usage": ""}],
        raw_text="1. Gastosic",
    )
    assert len(refined) == 1
    assert refined[0]["dose"] == ""
    assert refined[0]["frequency"] == ""
    assert refined[0]["usage"] == ""
    assert refined[0]["needs_review"] is True

    sched = parse_frequency_to_schedule("", "")
    assert not any(sched[slot]["active"] for slot in ("morning", "noon", "evening", "bedtime", "external"))
    assert sched.get("schedule_unverified") is True


def test_lab_rules_do_not_default_unknown_or_non_numeric_to_normal():
    assert calculate_lab_flag("Âm tính", "Âm tính") == "UNKNOWN"
    assert calculate_lab_flag("Negative", "Non-reactive") == "UNKNOWN"
    assert calculate_lab_flag("7.8", "") == "UNKNOWN"
    assert calculate_lab_flag("", "3.9 - 6.4") == "UNKNOWN"

    ocr_lab = extract_schema_from_ocr(
        {
            "raw_text": "Glucose | 7.8 | mmol/L | 3.9 - 6.4\nHBsAg | Âm tính | Định tính | Âm tính",
            "rows": [
                {"text": "Glucose | 7.8 | mmol/L | 3.9 - 6.4"},
                {"text": "HBsAg | Âm tính | Định tính | Âm tính"},
            ],
            "lines": [],
        },
        doc_type="lab_test",
    )
    assert len(ocr_lab["metrics"]) == 2
    assert ocr_lab["metrics"][0]["flag_on_paper"] == "UNKNOWN"
    assert ocr_lab["metrics"][1]["flag_on_paper"] == "UNKNOWN"

    validated = validate_lab_rules([
        {"test_name": "HBsAg", "result": "Âm tính", "unit": "", "reference_range": "", "flag_on_paper": ""},
        {"test_name": "Glucose", "result": "5.0", "unit": "mmol/L", "reference_range": "3.9 - 6.4", "flag_on_paper": "High"},
        {"test_name": "Cholesterol", "result": "4.2", "unit": "mmol/L", "reference_range": "3.4 - 5.2", "flag_on_paper": "Normal"},
    ])
    assert validated[0]["computed_flag"] == "UNKNOWN"
    assert validated[0]["needs_review"] is True
    assert validated[0]["verification_status"] == "unverified"

    assert validated[1]["computed_flag"] == "Normal"
    assert validated[1]["flag_mismatch"] is True
    assert validated[1]["needs_review"] is True
    assert validated[1]["verification_status"] == "mismatch"

    assert validated[2]["computed_flag"] == "Normal"
    assert validated[2]["flag_mismatch"] is False
    assert validated[2]["verification_status"] == "verified"


def test_greeting_with_symptoms_bypasses_fast_path_and_no_fake_sources(monkeypatch):
    monkeypatch.setattr("core.chat_service.medical_rag_service.retrieve_context", lambda *a, **kw: [])
    monkeypatch.setattr("core.chat_service.medical_rag_service.is_available", lambda: False)

    mock_gemini = GeminiMedicalService(api_key="test_key_123456")
    mock_gemini.generate_clinical_response = Mock(return_value={
        "answer": "Bạn nên theo dõi triệu chứng phát ban và đi khám chuyên khoa Da liễu nếu lan rộng.",
        "risk_level": "Thấp",
        "risk_score": 20,
        "symptoms": ["Phát ban"],
        "specialist": "Da liễu",
        "is_emergency": False,
    })
    res = process_clinical_chat(
        message="Xin chào tôi bị phát ban khắp tay",
        history=[],
        gemini_service=mock_gemini,
    )
    mock_gemini.generate_clinical_response.assert_called_once()
    assert res["sources"] == []
    assert res["rag_status"] == "not_ready"

    offline_fever = analyze_symptoms("Tôi bị sốt cao và ho rát họng", history=[])
    assert "paracetamol" not in offline_fever["answer"].lower()
    assert "500mg" not in offline_fever["answer"].lower()
    assert offline_fever["sources"] == []

    offline_emg = analyze_symptoms("Tôi đang đau ngực dữ dội và khó thở", history=[])
    assert offline_emg["is_emergency"] is True
    assert offline_emg["sources"] == []

    # Intake summary error path must never invent medlineplus.gov
    def failing_rag(*a, **kw):
        raise RuntimeError("RAG down")

    monkeypatch.setattr("core.intake_service.medical_rag_service.retrieve_context", failing_rag)
    summary = generate_pre_visit_summary({"facts": {"chief_complaint": "Đau họng", "present_symptoms": ["Đau họng"]}})
    assert summary["part_b_system_assessment"]["sources"] == []


def test_pii_masking_empty_bboxes_blocks_external_ai(tmp_path, monkeypatch):
    rx = tmp_path / "rx_with_pii.png"
    img = Image.new("RGB", (600, 400), "white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "Ho ten: NGUYEN VAN TEST", fill="black")
    img.save(rx)

    # mask_pii_on_image với bboxes rỗng không được tạo file _masked.jpg giả
    returned = mask_pii_on_image(str(rx), [])
    assert returned == str(rx)
    assert not (tmp_path / "rx_with_pii_masked.jpg").exists()

    monkeypatch.setattr(pipe, "check_image_quality", lambda *a, **kw: {"passed": True})
    monkeypatch.setattr(pipe, "preprocess_lightweight", lambda p, **kw: {"processed_path": p})
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda *a, **kw: {"success": False, "lines": [], "rows": [], "raw_text": ""})
    external_ai = Mock(side_effect=AssertionError("Must not call external vision AI when PII masking failed!"))
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", external_ai)

    res = pipe.process_medical_document_pipeline(str(rx), "rx_with_pii.png", mask_pii=True)
    external_ai.assert_not_called()
    assert res["status"] == "blocked"
    assert res["error_code"] == "PII_MASKING_UNAVAILABLE"
    assert res["needs_review"] is True
    assert res["pii_protection"]["blocked_external_ai"] is True
