import os
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image, ImageDraw

from core.prescription_crop_service import detect_medication_bounds, crop_and_upscale_medication_region
from core.gemini_schema_service import extract_with_gemini_schema
import core.pipeline_orchestrator as pipe


@pytest.fixture
def dummy_rx_image(tmp_path):
    """Tạo ảnh đơn thuốc mẫu 1000x1500 (dọc) với bảng thuốc ở giữa."""
    img_path = str(tmp_path / "rx_sample.jpg")
    img = Image.new("RGB", (1000, 1500), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Header
    draw.text((50, 50), "BỆNH VIỆN ĐA KHOA TRUNG ƯƠNG", fill=(0, 0, 0))
    draw.text((50, 100), "Họ tên: NGUYỄN VĂN A - 45 tuổi", fill=(0, 0, 0))
    draw.text((50, 150), "Chẩn đoán: Viêm dạ dày trào ngược (K21)", fill=(0, 0, 0))
    # Table header
    draw.text((50, 250), "STT | Tên thuốc | Hàm lượng | Đơn vị | Số lượng | Cách dùng", fill=(0, 0, 0))
    # Rows
    draw.text((50, 320), "1. Nexium (Esomeprazole) | 40mg | Viên | 30 | Uống sáng 1 viên", fill=(0, 0, 0))
    draw.text((50, 390), "2. Sucralfate | 1g | Gói | 30 | Uống trước ăn 30 phút", fill=(0, 0, 0))
    draw.text((50, 460), "3. Domperidone | 10mg | Viên | 20 | Ngày 2 lần, mỗi lần 1 viên", fill=(0, 0, 0))
    # Footer
    draw.text((50, 580), "Cộng khoản: 3 khoản", fill=(0, 0, 0))
    draw.text((50, 650), "Lời dặn: Uống thuốc đúng giờ, kiêng đồ chua cay", fill=(0, 0, 0))
    draw.text((600, 800), "Bác sĩ điều trị: BS. Nguyễn Văn B", fill=(0, 0, 0))
    img.save(img_path, format="JPEG")
    return img_path


# ==============================================================================
# 1. TEST XÁC ĐỊNH VÙNG CẮT VỚI NHIỀU BỐ CỤC VÀ ĐỘ PHÂN GIẢI KHÁC NHAU
# ==============================================================================

def test_detect_medication_bounds_portrait():
    """Ảnh dọc, bảng thuốc ở giữa (y từ 250 đến 580)."""
    lines = [
        {"text": "BỆNH VIỆN ĐA KHOA", "y_min": 50, "y_max": 80, "x_min": 50, "x_max": 400},
        {"text": "Chẩn đoán: Viêm loét dạ dày", "y_min": 150, "y_max": 180, "x_min": 50, "x_max": 450},
        {"text": "STT | Tên thuốc | Hàm lượng", "y_min": 250, "y_max": 280, "x_min": 50, "x_max": 500},
        {"text": "1. Nexium 40mg - SL: 30 viên", "y_min": 320, "y_max": 350, "x_min": 50, "x_max": 600},
        {"text": "2. Sucralfate 1g - SL: 30 gói", "y_min": 400, "y_max": 430, "x_min": 50, "x_max": 600},
        {"text": "Cộng khoản: 2 khoản", "y_min": 550, "y_max": 580, "x_min": 50, "x_max": 300},
        {"text": "Bác sĩ kê đơn: BS. Minh", "y_min": 700, "y_max": 730, "x_min": 600, "x_max": 900},
    ]
    bounds = detect_medication_bounds(lines, rows=[], img_w=1000, img_h=1500)
    assert bounds is not None
    x1, y1, x2, y2 = bounds
    assert x1 == 0 and x2 == 1000
    assert y1 < 250  # Có padding trên
    assert y2 >= 550  # Bao trùm đến trước/tại footer


def test_detect_medication_bounds_landscape():
    """Ảnh ngang (1600x900) với bảng thuốc ở giữa."""
    lines = [
        {"text": "PHÒNG KHÁM QUỐC TẾ", "y_min": 40, "y_max": 70, "x_min": 50, "x_max": 400},
        {"text": "Thuốc điều trị:", "y_min": 200, "y_max": 230, "x_min": 50, "x_max": 300},
        {"text": "1. Paracetamol 500mg - 20 viên", "y_min": 250, "y_max": 280, "x_min": 50, "x_max": 600},
        {"text": "Uống khi sốt trên 38.5 độ", "y_min": 290, "y_max": 310, "x_min": 50, "x_max": 500},
        {"text": "Lời dặn của bác sĩ: Nghỉ ngơi", "y_min": 450, "y_max": 480, "x_min": 50, "x_max": 500},
    ]
    bounds = detect_medication_bounds(lines, rows=[], img_w=1600, img_h=900)
    assert bounds is not None
    x1, y1, x2, y2 = bounds
    assert x1 == 0 and x2 == 1600
    assert y1 <= 200
    assert y2 >= 450


def test_detect_medication_bounds_fallback_when_no_med_section():
    """Không có phần thuốc (hoặc chỉ có tiêu đề viện), trả về None để fallback dùng ảnh toàn trang."""
    lines = [
        {"text": "BỆNH VIỆN BẠCH MAI", "y_min": 50, "y_max": 80, "x_min": 50, "x_max": 400},
        {"text": "Hà Nội, Việt Nam", "y_min": 90, "y_max": 110, "x_min": 50, "x_max": 300},
    ]
    bounds = detect_medication_bounds(lines, rows=[], img_w=1000, img_h=1500)
    assert bounds is None


# ==============================================================================
# 2. TEST CẮT VÙNG VÀ PHÓNG TO BẰNG PIL LANCZOS
# ==============================================================================

def test_crop_and_upscale_medication_region_success(dummy_rx_image):
    """Cắt vùng thành công và phóng to bằng PIL LANCZOS."""
    ocr_result = {
        "lines": [
            {"text": "Chẩn đoán: Viêm dạ dày", "y_min": 150, "y_max": 180, "x_min": 50, "x_max": 500},
            {"text": "Tên thuốc, hàm lượng", "y_min": 250, "y_max": 280, "x_min": 50, "x_max": 600},
            {"text": "1. Nexium 40mg", "y_min": 320, "y_max": 350, "x_min": 50, "x_max": 400},
            {"text": "Cộng khoản: 1 khoản", "y_min": 550, "y_max": 580, "x_min": 50, "x_max": 300},
        ],
        "rows": []
    }
    crop_path = crop_and_upscale_medication_region(dummy_rx_image, ocr_result)
    assert crop_path is not None
    assert os.path.exists(crop_path)
    assert crop_path.endswith("_med_crop.jpg")

    # Kiểm tra ảnh phóng to
    with Image.open(crop_path) as cimg:
        # Scale phóng to của chiều rộng 1000px
        assert cimg.width in (2000, 3000)
        assert cimg.height > 400


def test_crop_and_upscale_medication_region_fallback_none(tmp_path):
    """Khi không có OCR hoặc tệp không tồn tại, trả về None."""
    assert crop_and_upscale_medication_region("non_existent_file.jpg", {}) is None

    empty_img = str(tmp_path / "empty.png")
    Image.new("RGB", (500, 500), "white").save(empty_img)
    assert crop_and_upscale_medication_region(empty_img, {"lines": [], "rows": []}) is None


# ==============================================================================
# 3. TEST TRÍCH XUẤT QUA VISION MODEL (ĐÚNG 1 LẦN GỌI VỚI 2 ẢNH)
# ==============================================================================

def test_extract_with_gemini_schema_dual_images_single_call(dummy_rx_image, tmp_path):
    """
    Xác nhận trong MỘT lần gọi model thị giác qua OpenRouter:
      1. Gửi ảnh toàn trang trước (Image 1)
      2. Gửi ảnh cắt sau (Image 2)
      3. Prompt giải thích hai ảnh là cùng một tài liệu
      4. Bóc tách từng hàng thuốc, phân tách biệt dược, hoạt chất, số lượng, lịch dùng, cách dùng.
    """
    crop_path = str(tmp_path / "crop_sample.jpg")
    Image.new("RGB", (600, 300), "white").save(crop_path)

    mock_model_response = {
        "doc_type": "prescription",
        "patient_name": "NGUYỄN VĂN A",
        "dob": "1980",
        "age": "45",
        "gender": "Nam",
        "diagnosis": "Viêm dạ dày trào ngược",
        "facility": "Bệnh viện Đa khoa",
        "doctor": "BS. Nguyễn Văn B",
        "date": "18/11/2026",
        "medications": [
            {
                "name": "Nexium 40mg",
                "brand_name": "Nexium",
                "active_ingredient": "Esomeprazole",
                "strength": "40mg",
                "dose": "1 viên",
                "frequency": "1 lần/ngày",
                "schedule": "Sáng 1 viên",
                "quantity": "30",
                "unit": "Viên",
                "days": "30 Viên",
                "usage": "Uống trước ăn 30 phút",
                "instructions": "Uống với nước ấm",
                "needs_review": False
            }
        ]
    }

    with patch("core.llm_provider.llm_provider.is_configured", return_value=True), \
         patch("core.llm_provider.llm_provider.generate_json", return_value=mock_model_response) as mock_gen_json:

        res = extract_with_gemini_schema(
            image_path=dummy_rx_image,
            doc_type="prescription",
            crop_image_path=crop_path
        )

        # 1. Khẳng định DUY NHẤT 1 lần gọi API
        assert mock_gen_json.call_count == 1

        # 2. Kiểm tra contents gửi đi: Phải chứa 2 Part ảnh và 1 prompt
        call_kwargs = mock_gen_json.call_args[1]
        contents = call_kwargs.get("contents")
        assert len(contents) == 3  # [Image 1, Image 2, Prompt]

        prompt_text = contents[2]
        assert "BẠN ĐANG NHẬN ĐƯỢC 2 ẢNH CỦA CÙNG MỘT ĐƠN THUỐC" in prompt_text
        assert "Ảnh 1: Toàn bộ trang đơn thuốc" in prompt_text
        assert "Ảnh 2: Ảnh cắt phóng to chi tiết" in prompt_text
        assert "CÙNG MỘT TÀI LIỆU" in prompt_text

        # 3. Kết quả trả về được chuẩn hóa đúng cấu trúc
        assert res is not None
        assert res["patient_name"] == "NGUYỄN VĂN A"
        assert len(res["medications"]) == 1
        med = res["medications"][0]
        assert med["name"] == "Nexium 40mg"
        assert med["brand_name"] == "Nexium"
        assert med["active_ingredient"] == "Esomeprazole"
        assert med["quantity"] == "30"
        assert med["schedule"] == "Sáng 1 viên"


def test_extract_with_gemini_schema_single_image_fallback(dummy_rx_image):
    """Khi không cắt được ảnh (crop_image_path=None), gửi ảnh toàn trang trong 1 lần gọi."""
    mock_model_response = {
        "doc_type": "prescription",
        "patient_name": "NGUYỄN VĂN A",
        "medications": []
    }

    with patch("core.llm_provider.llm_provider.is_configured", return_value=True), \
         patch("core.llm_provider.llm_provider.generate_json", return_value=mock_model_response) as mock_gen_json:

        res = extract_with_gemini_schema(
            image_path=dummy_rx_image,
            doc_type="prescription",
            crop_image_path=None
        )

        assert mock_gen_json.call_count == 1
        contents = mock_gen_json.call_args[1].get("contents")
        assert len(contents) == 2  # [Image 1, Prompt]
        assert "BẠN ĐANG NHẬN ĐƯỢC 1 ẢNH TOÀN BỘ TRANG ĐƠN THUỐC" in contents[1]


# ==============================================================================
# 4. TEST TÍCH HỢP TOÀN BỘ PIPELINE ORCHESTRATOR
# ==============================================================================

def test_pipeline_orchestrator_integration_status_review_and_fields(dummy_rx_image, monkeypatch):
    """
    Test tích hợp pipeline:
      - Quét OCR -> Cắt phóng to LANCZOS -> Gửi dual-image -> Đối soát -> Trả draft status='review'.
      - Giữ nguyên cấu trúc JSON cho frontend: status, data, medications, boxes, extraction_warning.
    """
    # Mock OCR
    monkeypatch.setattr(pipe, "check_image_quality", lambda *a, **kw: {"passed": True})
    monkeypatch.setattr(pipe, "preprocess_lightweight", lambda p, **kw: {"processed_path": p})
    monkeypatch.setattr(
        pipe,
        "extract_ocr_parallel",
        lambda *a, **kw: {
            "success": True,
            "lines": [
                {"text": "Chẩn đoán: Viêm dạ dày", "box": [[50, 150], [500, 150], [500, 180], [50, 180]], "y_min": 150, "y_max": 180, "x_min": 50, "x_max": 500, "confidence": 0.95},
                {"text": "Tên thuốc", "box": [[50, 250], [200, 250], [200, 280], [50, 280]], "y_min": 250, "y_max": 280, "x_min": 50, "x_max": 200, "confidence": 0.92},
                {"text": "1. Nexium 40mg", "box": [[50, 320], [300, 320], [300, 350], [50, 350]], "y_min": 320, "y_max": 350, "x_min": 50, "x_max": 300, "confidence": 0.90},
                {"text": "Cộng khoản: 1 khoản", "box": [[50, 550], [300, 550], [300, 580], [50, 580]], "y_min": 550, "y_max": 580, "x_min": 50, "x_max": 300, "confidence": 0.88},
            ],
            "rows": [
                {"text": "Chẩn đoán: Viêm dạ dày", "y_min": 150, "y_max": 180, "x_min": 50, "x_max": 500, "items": []},
                {"text": "Tên thuốc", "y_min": 250, "y_max": 280, "x_min": 50, "x_max": 200, "items": []},
                {"text": "1. Nexium 40mg", "y_min": 320, "y_max": 350, "x_min": 50, "x_max": 300, "items": []},
                {"text": "Cộng khoản: 1 khoản", "y_min": 550, "y_max": 580, "x_min": 50, "x_max": 300, "items": []},
            ],
            "raw_text": "Chẩn đoán: Viêm dạ dày\nTên thuốc\n1. Nexium 40mg\nCộng khoản: 1 khoản"
        }
    )

    mock_gemini_return = {
        "doc_type": "prescription",
        "patient_name": "NGUYỄN VĂN A",
        "dob": "1980",
        "age": "45",
        "gender": "Nam",
        "diagnosis": "Viêm dạ dày",
        "facility": "Bệnh viện Đa khoa",
        "doctor": "BS. Nguyễn Văn B",
        "date": "18/11/2026",
        "medications": [
            {
                "name": "Nexium 40mg",
                "brand_name": "Nexium",
                "active_ingredient": "Esomeprazole",
                "strength": "40mg",
                "dose": "1 viên",
                "frequency": "1 lần / ngày",
                "schedule": "Sáng 1 viên",
                "days": "30 Viên",
                "quantity": "30",
                "unit": "Viên",
                "usage": "Uống trước ăn",
                "instructions": "Uống với nước ấm",
                "needs_review": False
            }
        ]
    }

    mock_extract = MagicMock(return_value=mock_gemini_return)
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", mock_extract)

    result = pipe.process_medical_document_pipeline(
        file_path=dummy_rx_image,
        original_filename="DonThuoc.jpg",
        mask_pii=False,
        user_allergies=[]
    )

    assert mock_extract.call_count == 1
    # Kiểm tra crop_image_path đã được tạo và truyền vào extract_with_gemini_schema
    call_kwargs = mock_extract.call_args[1]
    assert call_kwargs.get("crop_image_path") is not None
    assert os.path.exists(call_kwargs.get("crop_image_path"))

    # Kiểm tra hợp đồng JSON cho giao diện người dùng
    assert result["status"] == "review"
    assert result["requires_user_confirmation"] is True
    assert result["patient_name"] == "NGUYỄN VĂN A"
    assert len(result["medications"]) == 1

    med0 = result["medications"][0]
    assert "Nexium" in med0["name"]
    assert med0["strength"] == "40mg"
    assert med0["dose"] == "1 viên"
    assert med0["brand_name"] == "Nexium"
    assert med0["active_ingredient"] == "Esomeprazole"
    assert med0["quantity"] == "30"

    # Kiểm tra cấu trúc data bản nháp
    assert "data" in result
    assert "Nexium" in result["data"]["medications"][0]["name"]


def test_pipeline_orchestrator_graceful_fallback_when_vision_model_fails(dummy_rx_image, monkeypatch):
    """Khi OpenRouter/Gemini thất bại hoặc trả JSON lỗi, pipeline tự động fallback về OCR draft an toàn."""
    monkeypatch.setattr(pipe, "check_image_quality", lambda *a, **kw: {"passed": True})
    monkeypatch.setattr(pipe, "preprocess_lightweight", lambda p, **kw: {"processed_path": p})
    monkeypatch.setattr(
        pipe,
        "extract_ocr_parallel",
        lambda *a, **kw: {
            "success": True,
            "lines": [
                {"text": "BỆNH VIỆN BẠCH MAI", "box": [[10, 10], [200, 10], [200, 40], [10, 40]], "y_min": 10, "y_max": 40, "x_min": 10, "x_max": 200, "confidence": 0.9},
                {"text": "1. Amoxicillin 500mg - SL: 20 viên", "box": [[10, 100], [400, 100], [400, 130], [10, 130]], "y_min": 100, "y_max": 130, "x_min": 10, "x_max": 400, "confidence": 0.85},
            ],
            "rows": [
                {"text": "BỆNH VIỆN BẠCH MAI", "y_min": 10, "y_max": 40, "x_min": 10, "x_max": 200, "items": []},
                {"text": "1. Amoxicillin 500mg - SL: 20 viên", "y_min": 100, "y_max": 130, "x_min": 10, "x_max": 400, "items": []},
            ],
            "raw_text": "BỆNH VIỆN BẠCH MAI\n1. Amoxicillin 500mg - SL: 20 viên"
        }
    )

    # Giả lập Gemini Schema trả về None (OpenRouter sập/lỗi JSON)
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: None)
    result = pipe.process_medical_document_pipeline(
        file_path=dummy_rx_image,
        original_filename="DonThuoc.jpg",
        mask_pii=False,
        user_allergies=[]
    )

    assert result["status"] == "review"
    assert result["extraction_source"] == "ocr_only"
    assert result["requires_user_confirmation"] is True
    assert len(result["medications"]) >= 1
    assert "Amoxicillin" in result["medications"][0]["name"]
