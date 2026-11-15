import io
import os
import pytest
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

import core.pipeline_orchestrator as pipe
from core.intake_service import check_image_quality
from core.reconciliation_service import extract_schema_from_ocr
from core.grounding_service import parse_frequency_to_schedule


def test_white_background_prescription_passes_quality_and_blank_white_fails(tmp_path):
    """Đơn thuốc nền giấy trắng chữ đen rõ nét phải vượt qua kiểm định chất lượng, còn ảnh trắng xóa thì bị từ chối."""
    rx_img = Image.new("RGB", (900, 600), "white")
    draw = ImageDraw.Draw(rx_img)
    draw.text((40, 40), "BENH VIEN DA KHOA MEDIMIND", fill="black")
    draw.text((40, 90), "Ho ten: NGUYEN VAN AN    Tuoi: 40", fill="black")
    draw.text((40, 140), "1. Paracetamol 500mg     SL: 10 Vien", fill="black")
    rx_path = tmp_path / "clean_white_rx.png"
    rx_img.save(rx_path)

    q_ok = check_image_quality(str(rx_path))
    assert q_ok["passed"] is True

    blank = np.full((400, 600, 3), 255, dtype=np.uint8)
    blank_path = tmp_path / "blank_overexposed.png"
    cv2.imwrite(str(blank_path), blank)
    q_blank = check_image_quality(str(blank_path))
    assert q_blank["passed"] is False


def test_two_line_prescription_merges_dosage_into_drug():
    """Dòng hướng dẫn uống ('Sáng 1 viên, Tối 1 viên...') phải gộp vào thuốc liền trước thay vì tách nhầm thành thuốc mới."""
    ocr_mock = {
        "success": True,
        "raw_text": (
            "BỆNH VIỆN ĐA KHOA TÂM ĐỨC\n"
            "Họ và tên: TRẦN MINH KHOA | Ngày sinh: 12/05/1988\n"
            "Chẩn đoán: Viêm dạ dày trào ngược\n"
            "1. Esomeprazole 40mg | SL: 30 Viên\n"
            "Uống: Sáng 1 viên, Tối 1 viên trước ăn 30 phút\n"
            "2. Sucralfate 1g | SL: 30 Gói\n"
            "Ngày uống 3 lần, mỗi lần 1 gói sau ăn"
        ),
        "rows": [
            {"text": "BỆNH VIỆN ĐA KHOA TÂM ĐỨC", "items": [{"text": "BỆNH VIỆN ĐA KHOA TÂM ĐỨC"}]},
            {"text": "Họ và tên: TRẦN MINH KHOA | Ngày sinh: 12/05/1988", "items": [{"text": "Họ và tên: TRẦN MINH KHOA"}, {"text": "Ngày sinh: 12/05/1988"}]},
            {"text": "Chẩn đoán: Viêm dạ dày trào ngược", "items": [{"text": "Chẩn đoán: Viêm dạ dày trào ngược"}]},
            {"text": "1. Esomeprazole 40mg | SL: 30 Viên", "items": [{"text": "1. Esomeprazole 40mg"}, {"text": "SL: 30 Viên"}]},
            {"text": "Uống: Sáng 1 viên, Tối 1 viên trước ăn 30 phút", "items": [{"text": "Uống: Sáng 1 viên, Tối 1 viên trước ăn 30 phút"}]},
            {"text": "2. Sucralfate 1g | SL: 30 Gói", "items": [{"text": "2. Sucralfate 1g"}, {"text": "SL: 30 Gói"}]},
            {"text": "Ngày uống 3 lần, mỗi lần 1 gói sau ăn", "items": [{"text": "Ngày uống 3 lần, mỗi lần 1 gói sau ăn"}]},
        ],
    }
    parsed = extract_schema_from_ocr(ocr_mock, doc_type="prescription")
    assert parsed["patient_name"] == "TRẦN MINH KHOA"
    assert parsed["dob"] == "12/05/1988"
    assert "Viêm dạ dày" in parsed["diagnosis"]
    assert len(parsed["medications"]) == 2
    assert parsed["medications"][0]["name"] == "Esomeprazole"
    assert parsed["medications"][0]["strength"] == "40mg"
    assert parsed["medications"][0]["dose"] == "1 viên"
    assert "Sáng" in parsed["medications"][0]["frequency"] and "Tối" in parsed["medications"][0]["frequency"]
    assert parsed["medications"][0]["days"] == "30 Viên"
    assert "trước ăn" in parsed["medications"][0]["usage"].lower()
    assert parsed["medications"][1]["name"] == "Sucralfate"
    assert parsed["medications"][1]["days"] == "30 Gói"


def test_schedule_activates_both_morning_and_evening():
    """Khi tần suất ghi cả Sáng và Tối, lịch uống phải bật đồng thời cả 2 khung giờ."""
    sched = parse_frequency_to_schedule("2 lần / ngày (Sáng 1 - Tối 1)", "Uống sau ăn")
    assert sched["morning"]["active"] is True
    assert sched["evening"]["active"] is True
    assert sched["noon"]["active"] is False


def test_lab_report_ocr_auto_classification_and_metrics(tmp_path, monkeypatch):
    """Phiếu xét nghiệm không cần Gemini vẫn tự phân loại lab_test và trích xuất đầy đủ chỉ số."""
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: None)
    monkeypatch.setattr(pipe, "check_image_quality", lambda *a, **kw: {"passed": True})
    monkeypatch.setattr(pipe, "preprocess_lightweight", lambda p, **kw: {"processed_path": p})
    monkeypatch.setattr(
        pipe,
        "extract_ocr_parallel",
        lambda *a, **kw: {
            "success": True,
            "lines": [{"text": "Glucose"}, {"text": "7.8"}],
            "rows": [
                {"text": "BENH VIEN DA KHOA QUOC TE", "items": [{"text": "BENH VIEN DA KHOA QUOC TE"}]},
                {"text": "PHIEU XET NGHIEM SINH HOA MAU", "items": [{"text": "PHIEU XET NGHIEM SINH HOA MAU"}]},
                {"text": "Ho ten: LE THI MAI | Tuoi: 51", "items": [{"text": "Ho ten: LE THI MAI"}, {"text": "Tuoi: 51"}]},
                {"text": "Glucose | 7.8 | mmol/L | 3.9 - 6.4 | High", "items": []},
                {"text": "Cholesterol | 6.1 | mmol/L | 3.4 - 5.2 | High", "items": []},
            ],
            "raw_text": "BENH VIEN DA KHOA QUOC TE\nPHIEU XET NGHIEM SINH HOA MAU\nHo ten: LE THI MAI\nGlucose | 7.8 | mmol/L | 3.9 - 6.4 | High\nCholesterol | 6.1 | mmol/L | 3.4 - 5.2 | High",
        },
    )
    img_p = tmp_path / "lab.png"
    img_p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 128)

    res = pipe.process_medical_document_pipeline(str(img_p), "lab.png")
    assert res["status"] == "review"
    assert res["doc_type"] == "lab_test"
    assert res["data"]["patient_name"] == "LE THI MAI"
    assert len(res["data"]["metrics"]) == 2
    assert res["data"]["metrics"][0]["test_name"] == "Glucose"
    assert res["data"]["metrics"][0]["result"] == "7.8"


@pytest.mark.skipif(os.name != "nt", reason="Windows Native WinRT OCR end-to-end check")
def test_windows_native_ocr_extracts_real_prescription_image_without_gemini(tmp_path, monkeypatch):
    """Kiểm thử thực tế trên Windows: ảnh đơn thuốc nền trắng được WinRT OCR đọc ra thuốc mà không cần EasyOCR hay Gemini."""
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: None)
    img = Image.new("RGB", (1000, 650), "white")
    draw = ImageDraw.Draw(img)
    font_path = "C:/Windows/Fonts/arial.ttf"
    font = ImageFont.truetype(font_path, 26) if os.path.exists(font_path) else ImageFont.load_default()
    draw.text((50, 40), "BENH VIEN DA KHOA MEDIMIND", fill="black", font=font)
    draw.text((50, 95), "Ho ten: PHAM QUOC BAO       Tuoi: 36", fill="black", font=font)
    draw.text((50, 150), "Chan doan: Viem hong cap", fill="black", font=font)
    draw.text((50, 220), "1. Amoxicillin 500mg        SL: 20 Vien", fill="black", font=font)
    draw.text((80, 260), "Sang 1 vien, Toi 1 vien sau an", fill="black", font=font)
    draw.text((50, 325), "2. Paracetamol 500mg        SL: 10 Vien", fill="black", font=font)
    draw.text((80, 365), "Uong 1 vien x 3 lan/ngay sau an", fill="black", font=font)

    rx_file = tmp_path / "real_winrt_rx.png"
    img.save(rx_file)

    res = pipe.process_medical_document_pipeline(str(rx_file), "real_winrt_rx.png")
    assert res["status"] == "review"
    assert "PHAM QUOC BAO" in res["data"]["patient_name"].upper()
    med_names = [m["name"].lower() for m in res["data"]["medications"]]
    assert any("amoxicillin" in n for n in med_names)
    assert any("paracetamol" in n for n in med_names)


def test_diabetes_cholesterol_prescription_not_misclassified_as_lab_test(tmp_path, monkeypatch):
    """Đơn thuốc có chữ 'cholesterol'/'glucose' trong chẩn đoán vẫn phải phân loại là prescription và giữ giới tính."""
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: None)
    monkeypatch.setattr(pipe, "check_image_quality", lambda *a, **kw: {"passed": True})
    monkeypatch.setattr(pipe, "preprocess_lightweight", lambda p, **kw: {"processed_path": p})
    raw = (
        "BENH VIEN TIM MACH\nDON THUOC\n"
        "Ho ten: DO VAN HUNG | Ngay sinh: 10/04/1975 | Gioi tinh: Nam\n"
        "Chan doan: Tang cholesterol mau / Tang glucose mau (E78)\n"
        "1. Atorvastatin 10mg | SL: 30 Vien\n"
        "Toi uong 1 vien sau an\n"
        "2. Metformin 500mg | SL: 60 Vien\n"
        "Sang 1 vien, Toi 1 vien sau an"
    )
    monkeypatch.setattr(
        pipe,
        "extract_ocr_parallel",
        lambda *a, **kw: {
            "success": True,
            "lines": [{"text": ln} for ln in raw.splitlines()],
            "rows": [],
            "raw_text": raw,
        },
    )
    img_p = tmp_path / "rx_cholesterol.png"
    img_p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 128)

    res = pipe.process_medical_document_pipeline(str(img_p), "rx_cholesterol.png")
    assert res["doc_type"] == "prescription"
    assert res["data"]["gender"] == "Nam"
    assert len(res["data"]["medications"]) == 2


def test_upright_prescription_table_not_cropped_or_tilted_by_preprocessing(tmp_path):
    """Tờ đơn thuốc nền trắng dựng thẳng có khung bảng thuốc không bị cắt mất tiêu đề hoặc xoay nghiêng sai."""
    from core.preprocessing_service import preprocess_lightweight

    img = Image.new("RGB", (900, 1200), "white")
    draw = ImageDraw.Draw(img)
    draw.text((60, 50), "BENH VIEN DA KHOA MEDIMIND - DON THUOC", fill="black")
    draw.text((60, 100), "Ho va ten: NGUYEN VAN BINH   Gioi tinh: Nam", fill="black")
    draw.rectangle([50, 200, 850, 950], outline="black", width=3)
    draw.text((80, 240), "1. Paracetamol 500mg   SL: 15 Vien   Sang 1 vien, Toi 1 vien", fill="black")
    p = tmp_path / "upright_table.png"
    img.save(p)

    prep = preprocess_lightweight(str(p))
    assert prep["perspective_corrected"] is False
    assert prep["deskew_angle"] == 0.0


def test_scanned_image_pdf_extracts_embedded_image_ocr(tmp_path, monkeypatch):
    """PDF scan chỉ chứa ảnh nhúng (không có lớp text) vẫn phải trích xuất ảnh nhúng qua pypdf để chạy OCR."""
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: None)
    monkeypatch.setattr(pipe, "check_image_quality", lambda *a, **kw: {"passed": True})
    monkeypatch.setattr(pipe, "preprocess_lightweight", lambda p, **kw: {"processed_path": p})
    monkeypatch.setattr(
        pipe,
        "extract_ocr_parallel",
        lambda p, **kw: {
            "success": True,
            "lines": [{"text": "1. Cefuroxime 500mg | SL: 10 Vien"}],
            "rows": [],
            "raw_text": "DON THUOC\nHo ten: TRAN VAN TAM\n1. Cefuroxime 500mg | SL: 10 Vien\nSang 1 vien, Toi 1 vien",
        },
    )
    img = Image.new("RGB", (400, 300), "white")
    pdf_path = tmp_path / "scanned_rx.pdf"
    img.save(pdf_path, "PDF")

    res = pipe.process_medical_document_pipeline(str(pdf_path), "scanned_rx.pdf")
    assert res["status"] == "review"
    assert res["doc_type"] == "prescription"
    assert res["data"]["patient_name"] == "TRAN VAN TAM"
    assert len(res["data"]["medications"]) == 1


def test_confirm_doc_type_override_blank_rows_and_topical_external_slot(client, test_users, monkeypatch):
    """Endpoint /confirm cho phép đổi doc_type, lọc dòng rỗng dư thừa, ẩn ocr_draft khỏi /api/scan-files và gom thuốc ngoài da vào external."""
    uid = test_users["user_a_id"]
    with client.session_transaction() as sess:
        sess["user_id"] = uid

    monkeypatch.setattr(pipe, "check_image_quality", lambda *a, **kw: {"passed": True})
    monkeypatch.setattr(pipe, "preprocess_lightweight", lambda *a, **kw: {})
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda *a, **kw: {"lines": [], "raw_text": ""})
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: {"doc_type": "lab_test", "metrics": []})
    monkeypatch.setattr(pipe, "generate_clinical_interpretation", lambda validated, **kw: {"interpretation_md": "OK", "disclaimer": "OK"})

    png_buf = io.BytesIO()
    Image.new("RGB", (120, 120), "white").save(png_buf, format="PNG")
    png_buf.seek(0)
    scan_res = client.post("/api/prescription/scan", data={"file": (png_buf, "switch_test.png")})
    assert scan_res.status_code == 200
    doc_id = scan_res.get_json()["document_id"]

    # Bản nháp ocr_draft chưa xác nhận không được rò rỉ sang /api/scan-files
    scan_files_before = client.get("/api/scan-files").get_json()["files"]
    assert all(f["id"] != doc_id for f in scan_files_before)

    # Người dùng chuyển từ lab_test sang prescription, kèm 1 dòng trống dư từ nút "+ Thêm dòng" và 1 thuốc ngoài da
    confirm_res = client.post(
        f"/api/prescription/{doc_id}/confirm",
        json={
            "confirmed": True,
            "doc_type": "prescription",
            "patient_name": "Lê Quốc Tuấn",
            "gender": "Nam",
            "diagnosis": "Đau lưng cấp (M54.5)",
            "medications": [
                {"name": "Cồn xoa bóp Viện", "dose": "Thoa mỏng", "frequency": "Khi đau", "days": "7 ngày", "usage": "Xoa ngoài da vùng lưng"},
                {"name": "", "strength": "", "dose": "", "frequency": "", "days": "", "usage": ""},
            ],
        },
    )
    assert confirm_res.status_code == 200
    confirmed = confirm_res.get_json()
    assert confirmed["doc_type"] == "prescription"
    assert confirmed["gender"] == "Nam"
    assert confirmed["duration"] == "7 ngày"
    assert len(confirmed["medications"]) == 1
    assert len(confirmed["timeline"]["external"]) == 1
    assert confirmed["timeline"]["morning"] == []
