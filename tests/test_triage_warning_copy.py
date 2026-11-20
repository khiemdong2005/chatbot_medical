from core.triage import analyze_symptoms, assess_emergency_risk


def test_urgent_sign_uses_risk_warning_without_hotline_instruction():
    assessment = assess_emergency_risk("Tôi bị tức ngực", lang="vi")
    assert assessment["is_emergency"] is True
    assert "CẢNH BÁO NGUY CƠ CAO" in assessment["message"]
    assert "đánh giá trực tiếp khẩn" in assessment["message"]
    assert "115" not in assessment["message"]

    fallback = analyze_symptoms("Tôi bị tức ngực", lang="vi")
    assert fallback["risk_level"].startswith("Nguy cơ cao")
    assert fallback["specialist"] == "Khoa Cấp cứu"
    assert "115" not in fallback["answer"]


def test_english_urgent_warning_is_consistent():
    assessment = assess_emergency_risk("I have chest pain", lang="en")
    assert assessment["is_emergency"] is True
    assert "HIGH RISK WARNING" in assessment["message"]
    assert "urgent in-person medical assessment" in assessment["message"]
    assert "911" not in assessment["message"]
