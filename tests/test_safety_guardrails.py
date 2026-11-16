import pytest
from core.triage import assess_emergency_risk, apply_safety_guardrails, analyze_symptoms
from core.chat_service import process_clinical_chat


def test_negation_handling_in_emergency_assessment():
    """Kiểm thử 6a: Xử lý bẫy phủ định - Không báo nhầm cờ đỏ cấp cứu khi có từ phủ định."""
    # Các câu có chứa từ khóa cờ đỏ nhưng bị phủ định
    negated_cases = [
        "Tôi bị sốt nhưng không khó thở",
        "Tôi bị ho rát họng, không bị tức ngực",
        "Người mệt mỏi nhưng chẳng hề đau ngực dữ dội",
        "Cảm cúm nhẹ, không nôn ra máu",
        "dau hong nhung khong tuc nguc"  # Không dấu
    ]

    for msg in negated_cases:
        res = assess_emergency_risk(msg, lang="vi")
        assert res["is_emergency"] is False, f"Báo nhầm cờ đỏ cho câu phủ định: '{msg}'"


def test_true_emergency_signs_triggered():
    """Kiểm thử 6b: Dấu hiệu cấp cứu thật sự phải kích hoạt cờ đỏ cảnh báo ngay tức khắc."""
    emergency_cases = [
        "Tôi bị đau ngực dữ dội và vã mồ hôi lạnh",
        "Bác tôi bị méo miệng và nói đớ đột ngột",
        "Khó thở dữ dội, không thể hít thở được",
        "Bệnh nhân nôn ra máu tươi",
        "tuc nguc du doi kem kho tho"  # Không dấu
    ]

    for msg in emergency_cases:
        res = assess_emergency_risk(msg, lang="vi")
        assert res["is_emergency"] is True, f"Không phát hiện dấu hiệu cấp cứu: '{msg}'"
        assert len(res["symptoms"]) > 0


def test_antibiotic_guardrails_intervene_and_redact():
    """Kiểm thử 6c: Can thiệp và thay thế nội dung vi phạm kê đơn kháng sinh."""
    prohibited_prescriptions = [
        "Bạn hãy uống Amoxicillin 500mg ngày 2 viên sau ăn trong 5 ngày để trị viêm họng.",
        "Nên dùng thêm Ciprofloxacin 500mg hoặc Augmentin để kháng viêm.",
        "Đơn thuốc cho bạn: Azithromycin 250mg ngày 1 viên."
    ]

    for bad_text in prohibited_prescriptions:
        cleaned = apply_safety_guardrails(bad_text, lang="vi")
        assert "không được tự ý" in cleaned.lower()
        assert "500mg" not in cleaned and "250mg" not in cleaned


@pytest.mark.parametrize("answer", [
    "Bạn không nên tự dùng amoxicillin vì đã tự khai dị ứng penicillin. Hãy hỏi bác sĩ.",
    "Amoxicillin là một kháng sinh. Thông tin này không phải đơn thuốc.",
    "Tránh dùng amoxicillin khi chưa được bác sĩ kiểm tra thông tin dị ứng.",
    "Đừng dùng amoxicillin khi chưa hỏi bác sĩ.",
    "Do not take amoxicillin without speaking to your doctor about the reported penicillin allergy.",
])
def test_antibiotic_explanation_and_safe_refusal_are_preserved(answer):
    assert apply_safety_guardrails(answer) == answer


@pytest.mark.parametrize("answer", [
    "Tôi không kê đơn. Bạn hãy uống amoxicillin 500mg ngày 2 lần.",
    "Bạn không dị ứng thuốc, hãy uống amoxicillin 500mg ngày 2 lần.",
    "Không tự dùng penicillin. Bạn nên dùng azithromycin mỗi ngày.",
    "Amoxicillin 500mg ngày 2 lần trong 5 ngày.",
    "You should take amoxicillin 500mg twice daily.",
])
def test_antibiotic_dosing_is_not_allowed_after_an_unrelated_negation(answer):
    result = apply_safety_guardrails(answer)
    assert result != answer
    assert "500mg" not in result


def test_antibiotic_block_preserves_emergency_action():
    result = apply_safety_guardrails("Hãy gọi 115 ngay. Bạn hãy uống amoxicillin 500mg ngày 2 lần.")
    assert "115" in result
    assert "500mg" not in result


def test_no_invented_visual_findings_without_image():
    """Kiểm thử 6d: Không suy diễn phát hiện hình ảnh khi không có xử lý ảnh thành công."""
    # Chỉ chat văn bản, không gửi ảnh
    res = analyze_symptoms(message="Da tôi bị mẩn ngứa và nổi mụn nước", history=[], has_image=False)
    assert res["visual_findings"] == [], "Tự tiện bịa visual_findings khi không có ảnh chụp!"

    # Khi có ảnh thật
    res_with_img = analyze_symptoms(message="Da tôi bị mẩn ngứa", history=[], has_image=True)
    assert len(res_with_img["visual_findings"]) > 0


# ------------------------------------------------------------------------------
# REGRESSION TESTS (PHASE 2.3 SAFETY HARDENING)
# ------------------------------------------------------------------------------

def test_ophthalmic_emergency_detection():
    """Verify that acute ophthalmic emergencies trigger immediate emergency alerts."""
    emergency_cases = [
        "Sudden vision loss in left eye with painless gray shadow covering vision.",
        "Curtain over vision suddenly appeared while driving.",
        "Suddenly cannot see from one eye this morning.",
        "Acute vision loss in right eye.",
        "Sudden blindness in left eye."
    ]
    for msg in emergency_cases:
        res = assess_emergency_risk(msg, lang="en")
        assert res["is_emergency"] is True, f"Failed to detect ophthalmic emergency: '{msg}'"
        assert len(res["symptoms"]) > 0


def test_safe_ophthalmic_cases_not_triggered():
    """Verify that routine/gradual eye symptoms are never falsely classified as emergencies."""
    safe_cases = [
        "My eyes feel tired after using a computer.",
        "My vision has gradually become blurry over several months.",
        "I need stronger glasses.",
        "My eyes are dry.",
        "Mild eye irritation after swimming."
    ]
    for msg in safe_cases:
        res = assess_emergency_risk(msg, lang="en")
        assert res["is_emergency"] is False, f"Falsely triggered emergency for safe ophthalmic query: '{msg}'"


def test_english_negation_and_contractions():
    """Verify that English negation markers and contractions prevent false emergency alarms."""
    negated_cases = [
        "I feel tired and have a mild headache, without any slurred speech or facial drooping.",
        "I felt faint for a second upon standing up quickly, but I never passed out or became unconscious.",
        "Localized muscle soreness across upper chest from bench press, with no severe chest pain or cardiac issues.",
        "Mild rash on forearm after gardening, without any anaphylaxis or breathing problems.",
        "I don't have chest pain.",
        "I didn't pass out.",
        "I haven't had trouble breathing.",
        "I can't say I have severe chest pain."
    ]
    for msg in negated_cases:
        res = assess_emergency_risk(msg, lang="en")
        assert res["is_emergency"] is False, f"Falsely triggered emergency for negated English query: '{msg}'"


def test_negation_clause_boundary_preserves_emergency():
    """Verify that negation in one clause does not leak across contrastive clause boundaries."""
    boundary_cases = [
        ("I don't smoke, but I have severe chest pain.", "en"),
        ("I don't have fever, but I have severe chest pain.", "en"),
        ("I have no headache and severe chest pain.", "en"),
        ("I have severe chest pain and no fever.", "en"),
        ("Tôi không sốt nhưng bị đau ngực dữ dội.", "vi"),
    ]
    for msg, lang in boundary_cases:
        res = assess_emergency_risk(msg, lang=lang)
        assert res["is_emergency"] is True, f"Failed to detect emergency across clause boundary: '{msg}'"


def test_fallback_emergency_escalation_on_llm_failure(monkeypatch):
    """Verify that when LLM service fails AND pre-check missed, fallback engine deterministically escalates emergency."""
    class FailingMockGemini:
        def generate_clinical_response(self, *args, **kwargs):
            raise RuntimeError("Simulated Gemini 503 ServerError")

    # Simulate scenario: Pre-check in Tier 1 missed (call_count == 1 returns False),
    # but Tier 3 Fallback re-assessment catches the emergency signal (call_count == 2 returns True).
    import core.chat_service as cs
    real_assess = cs.assess_emergency_risk

    call_count = 0
    def mock_assess(msg, lang="vi", previous_question=""):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call (Tier 1 Pre-check) misses
            return {"is_emergency": False, "symptoms": []}
        # Second call (Tier 3 Fallback) catches it
        return real_assess(msg, lang=lang, previous_question=previous_question)

    monkeypatch.setattr(cs, "assess_emergency_risk", mock_assess)

    res_en = cs.process_clinical_chat(
        message="I have severe chest pain and cannot breathe.",
        lang="en",
        gemini_service=FailingMockGemini()
    )
    assert res_en["is_emergency"] is True
    assert res_en["risk_score"] == 90
    assert "CLINICAL EMERGENCY ALERT" in res_en["answer"]
    assert "DO NOT WAIT FOR AI SERVICE RECOVERY" in res_en["answer"]
    assert res_en["degraded"] is True

    # Reset call count for Vietnamese test
    call_count = 0
    res_vi = cs.process_clinical_chat(
        message="Tôi bị đau ngực dữ dội như đá đè và khó thở.",
        lang="vi",
        gemini_service=FailingMockGemini()
    )
    assert res_vi["is_emergency"] is True
    assert res_vi["risk_score"] == 90
    assert "CẢNH BÁO LÂM SÀNG KHẨN CẤP" in res_vi["answer"]
    assert "TUYỆT ĐỐI KHÔNG CHỜ ĐỢI AI PHỤC HỒI" in res_vi["answer"]
    assert res_vi["degraded"] is True


