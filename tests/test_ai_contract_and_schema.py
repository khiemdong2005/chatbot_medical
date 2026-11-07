import pytest
from core.gemini_service import GeminiMedicalService
from core.chat_service import process_clinical_chat


def test_gemini_malformed_json_triggers_fallback():
    """Kiểm thử 5a: Gemini trả về JSON sai cú pháp -> Không bịa kết quả mà trả None để kích hoạt Fallback."""
    service = GeminiMedicalService(api_key="mock_key_for_testing_1234567890")
    
    # JSON hỏng hoàn toàn
    assert service._validate_and_parse_json("{invalid json content...") is None
    # Chuỗi rỗng
    assert service._validate_and_parse_json("") is None
    # JSON hợp lệ nhưng không phải dict
    assert service._validate_and_parse_json('["just", "a", "list"]') is None


def test_gemini_missing_required_fields_rejected():
    """Kiểm thử 5b: JSON thiếu trường bắt buộc 'answer' không được coi là kết quả hợp lệ."""
    service = GeminiMedicalService(api_key="mock_key_for_testing_1234567890")

    # Thiếu trường answer
    incomplete_json = '{"risk_level": "Low", "risk_score": 20, "symptoms": ["ho"]}'
    assert service._validate_and_parse_json(incomplete_json) is None

    # Trường answer rỗng
    empty_answer_json = '{"answer": "   ", "risk_level": "Low", "risk_score": 20}'
    assert service._validate_and_parse_json(empty_answer_json) is None


def test_gemini_risk_score_clamped_to_range():
    """Kiểm thử 5c: risk_score luôn được clamp trong khoảng 0..100."""
    service = GeminiMedicalService(api_key="mock_key_for_testing_1234567890")

    # Điểm quá 100
    res_high = service._validate_and_parse_json('{"answer": "Nội dung tư vấn", "risk_score": 999}')
    assert res_high is not None
    assert res_high["risk_score"] == 100

    # Điểm âm
    res_neg = service._validate_and_parse_json('{"answer": "Nội dung tư vấn", "risk_score": -45}')
    assert res_neg is not None
    assert res_neg["risk_score"] == 0

    # Không phải số
    res_invalid_num = service._validate_and_parse_json('{"answer": "Nội dung tư vấn", "risk_score": "not_a_number"}')
    assert res_invalid_num is not None
    assert 0 <= res_invalid_num["risk_score"] <= 100


def test_chat_service_fallback_marks_degraded():
    """Kiểm thử 5d: Khi Gemini không khả dụng, Fallback Engine được kích hoạt và đánh dấu degraded=True."""
    mock_gemini = GeminiMedicalService(api_key="mock_key_1234567890")
    # Giả lập Gemini không có mạng hoặc trả None
    mock_gemini.generate_clinical_response = lambda *args, **kwargs: None

    result = process_clinical_chat(
        message="Tôi bị sốt nhẹ và ho có đờm",
        history=[],
        gemini_service=mock_gemini
    )

    assert result["degraded"] is True
    assert result["answer"] != ""
    assert 0 <= result["risk_score"] <= 100
    assert isinstance(result["sources"], list)
    assert len(result["sources"]) > 0


def test_chat_service_does_not_invent_fake_medlineplus_when_no_sources():
    """Kiểm thử: Khi không có tài liệu trích dẫn thực tế, không tự bịa nguồn MedlinePlus hay gán nguy cơ Thấp."""
    from unittest.mock import MagicMock
    mock_gemini = GeminiMedicalService(api_key="mock_key_1234567890")
    # Giả lập Gemini trả về kết quả không có sources và không có risk_level
    mock_gemini.generate_clinical_response = MagicMock(return_value={
        "answer": "Đây là tư vấn chung về dinh dưỡng.",
        "sources": []
    })
    result = process_clinical_chat(
        message="Tôi muốn hỏi về dinh dưỡng khi chơi thể thao",
        history=[],
        gemini_service=mock_gemini
    )
    assert result["sources"] == []
    assert "Chưa xác định" in result["risk_level"]

