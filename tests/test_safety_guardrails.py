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
        # Phải can thiệp thay thế đoạn kê đơn bằng cảnh báo an toàn của Bộ Y Tế
        assert "CAN THIỆP AN TOÀN Y TẾ" in cleaned or "KHÁNG SINH KÊ ĐƠN" in cleaned
        # Không được giữ nguyên lời khuyên uống thuốc bình thường mà không can thiệp
        assert "tuyệt đối không kê đơn" in cleaned.lower() or "không được tự ý" in cleaned.lower()


def test_no_invented_visual_findings_without_image():
    """Kiểm thử 6d: Không suy diễn phát hiện hình ảnh khi không có xử lý ảnh thành công."""
    # Chỉ chat văn bản, không gửi ảnh
    res = analyze_symptoms(message="Da tôi bị mẩn ngứa và nổi mụn nước", history=[], has_image=False)
    assert res["visual_findings"] == [], "Tự tiện bịa visual_findings khi không có ảnh chụp!"

    # Khi có ảnh thật
    res_with_img = analyze_symptoms(message="Da tôi bị mẩn ngứa", history=[], has_image=True)
    assert len(res_with_img["visual_findings"]) > 0

