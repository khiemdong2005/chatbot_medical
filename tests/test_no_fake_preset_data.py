import io
import pytest
from unittest.mock import patch
from core.prescription_service import analyze_uploaded_document, get_preset_data
from core.models import db, User, ClinicalConsultation


def test_ocr_llm_failure_does_not_return_preset(tmp_path):
    """Kiểm thử 4a: Khi OCR và LLM thất bại, trả status failed thay vì bịa dữ liệu mẫu."""
    # Tạo 1 file ảnh trống/nhiễu
    test_img = tmp_path / "noisy_unreadable.jpg"
    test_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 200)

    # Mock OCR và Gemini trả về không thành công
    with patch("core.prescription_service.extract_prescription_text") as mock_ocr, \
         patch("core.prescription_service.scan_prescription_with_gemini_vision") as mock_vision:
        
        mock_ocr.return_value = {"success": False, "total_lines": 0, "avg_confidence": 0.0}
        mock_vision.return_value = None

        result = analyze_uploaded_document(str(test_img), "noisy_unreadable.jpg")

        assert result["status"] == "failed"
        assert result["needs_review"] is True
        assert result["error_code"] == "OCR_OR_AI_ANALYSIS_FAILED"
        # Tuyệt đối không bịa thông tin Trần Trung hay thuốc dạ dày Yesom
        assert "TRẦN TRUNG" not in str(result)
        assert "YESOM" not in str(result)
        assert "sucrate" not in str(result).lower()


def test_preset_clearly_marked_as_demo():
    """Kiểm thử 4b: Dữ liệu mẫu (Preset) chỉ hoạt động khi yêu cầu rõ ràng và luôn có is_demo: True."""
    preset = get_preset_data("binh_dan")
    assert preset["status"] == "demo"
    assert preset["is_demo"] is True
    assert "Dữ liệu Demo" in preset["doc_title"] or "[DỮ LIỆU MẪU DEMO]" in str(preset["warnings"])

    lab_preset = get_preset_data("lab_blood")
    assert lab_preset["status"] == "demo"
    assert lab_preset["is_demo"] is True

    # Kịch bản không tồn tại
    invalid_preset = get_preset_data("non_existent_preset")
    assert invalid_preset["status"] == "error"
    assert invalid_preset["is_demo"] is True


def test_prescription_scan_rejects_missing_input(client):
    """Kiểm thử 4c: Endpoint scan không tự ý fallback về dữ liệu mẫu nếu không có file hay preset."""
    res = client.post("/api/prescription/scan", json={})
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"
    assert "đính kèm tệp" in data["message"] or "preset" in data["message"]


def test_clinical_summary_handles_no_data(client, test_users):
    """Kiểm thử 4d: /api/clinical-summary trả về no_data khi người dùng chưa có lượt tư vấn nào."""
    user_a_id = test_users["user_a_id"]

    # Đăng nhập với User A (chưa từng chat lần nào)
    with client.session_transaction() as sess:
        sess["user_id"] = user_a_id

    res = client.get("/api/clinical-summary")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "no_data"
    assert "Chưa có dữ liệu tư vấn" in data["message"]
    # Tuyệt đối không trả về bệnh án hardcode 'Đau rát họng kèm sốt nhẹ về chiều (Nghiêm trọng: 6/10)'
    assert "Đau rát họng kèm sốt nhẹ về chiều" not in str(data)


def test_clinical_summary_uses_real_consultation(client, test_users):
    """Kiểm thử 4e: /api/clinical-summary xuất dữ liệu thật từ lượt tư vấn gần nhất của chính người dùng."""
    user_a_id = test_users["user_a_id"]

    # Thêm 1 ca tư vấn thực tế của User A vào CSDL
    with client.application.app_context():
        consultation = ClinicalConsultation(
            user_id=user_a_id,
            message="Tôi bị đau lưng dữ dội khi cúi xuống bê vác đồ",
            answer="Bạn có thể bị căng cơ thắt lưng cấp. Hãy nghỉ ngơi...",
            risk_level="Trung bình (Cần thăm khám)",
            risk_score=50,
            symptoms='["Đau lưng", "Co cứng cơ"]',
            specialist="Cơ Xương Khớp",
            is_emergency=False
        )
        db.session.add(consultation)
        db.session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user_a_id

    res = client.get("/api/clinical-summary")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["patient_name"] == "Nguyễn Văn A"
    assert "đau lưng" in data["chief_complaint"].lower()
    assert "Cơ Xương Khớp" in data["provisional_diagnosis"]

