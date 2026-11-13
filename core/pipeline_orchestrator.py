import os
import sys
import json
import time
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

from core.intake_service import check_image_quality, mask_pii_on_image
from core.preprocessing_service import preprocess_lightweight
from core.ocr_parallel_service import extract_ocr_parallel
from core.gemini_schema_service import extract_with_gemini_schema
from core.reconciliation_service import reconcile_parallel_results, extract_schema_from_ocr
from core.grounding_service import normalize_drug_entity, map_lab_test, parse_frequency_to_schedule, normalize_lab_unit_and_value
from core.validation_service import validate_prescription_rules, validate_lab_rules
from core.interpretation_service import generate_clinical_interpretation

def process_medical_document_pipeline(
    file_path: str,
    original_filename: str = "",
    doc_type_hint: str = "auto",
    user_allergies: list = None,
    mask_pii: bool = False
) -> Dict[str, Any]:
    """
    KIẾN TRÚC ĐỌC ĐƠN THUỐC & PHIẾU XÉT NGHIỆM 8 BƯỚC:
      [0] Intake & Phân loại + Kiểm tra chất lượng (mờ, tối, lóa)
      [1] Tiền xử lý nhẹ (giữ cả ảnh gốc, crop/deskew/perspective, chỉ CLAHE khi tối)
      [2] Trích xuất song song (A: OCR EasyOCR bbox/rows + B: Gemini schema)
      [3] Đối chiếu A và B từng field (needs_review=True nếu lệch)
      [4] Chuẩn hóa & Grounding (Rule + CSDL, không dùng LLM)
      [5] Validate & Luật nghiệp vụ (Cờ cao/thấp, tương tác thuốc, dị ứng)
      [6] Diễn giải (Gemini chỉ nhận JSON đã validate)
      [7] Output JSON + sẵn sàng cho màn hình xác nhận người dùng
    """
    start_all = time.time()
    filename_clean = original_filename or os.path.basename(file_path)

    if not os.path.exists(file_path):
        return {
            "status": "failed",
            "needs_review": True,
            "error_code": "FILE_NOT_FOUND",
            "message": "Không tìm thấy tệp tài liệu y tế.",
            "uploaded_filename": filename_clean
        }

    # ==============================================================
    # [0] INTAKE & PHÂN LOẠI & KIỂM TRA CHẤT LƯỢNG
    # ==============================================================
    quality_check = check_image_quality(file_path)
    if not quality_check.get("passed", True):
        return {
            "status": "rejected",
            "needs_review": True,
            "stage": "[0] Intake Quality Check",
            "error_code": "POOR_IMAGE_QUALITY",
            "message": quality_check.get("recommendation", "Ảnh chụp không đạt yêu cầu rõ nét."),
            "quality_details": quality_check,
            "uploaded_filename": filename_clean
        }

    # ==============================================================
    # [1] TIỀN XỬ LÝ NHẸ (GIỮ NGUYÊN ẢNH GỐC)
    # ==============================================================
    need_clahe = quality_check.get("need_clahe", False)
    prep_res = preprocess_lightweight(file_path, need_clahe=need_clahe)
    active_image_path = prep_res.get("processed_path", file_path)

    # (Tùy chọn) Che PII trước khi gửi đi nếu người dùng bật
    if mask_pii:
        active_image_path = mask_pii_on_image(active_image_path, [])

    # ==============================================================
    # [2] TRÍCH XUẤT SONG SONG (PARALLEL EXTRACTION)
    #     Nhánh A: OCR Cục bộ (EasyOCR)
    #     Nhánh B: Gemini Vision Multimodal theo Response Schema
    # ==============================================================
    # 2.A: OCR cục bộ
    ocr_result = extract_ocr_parallel(active_image_path, doc_type=doc_type_hint)

    # Phân loại tự động nếu chưa có doc_type_hint
    doc_type = doc_type_hint
    if doc_type == "auto":
        comb_text = (ocr_result.get("raw_text") or "").lower()
        if any(k in comb_text for k in ["xét nghiệm", "huyết học", "sinh hóa", "glucose", "cholesterol", "kết quả", "trị số bình thường", "chỉ số"]):
            doc_type = "lab_test"
        else:
            doc_type = "prescription"

    # 2.B: Gemini Schema extraction
    gemini_data = extract_with_gemini_schema(active_image_path, doc_type=doc_type)

    if not gemini_data:
        # Nếu Gemini API bận hoặc không khả dụng -> Fallback xây schema từ OCR
        gemini_data = extract_schema_from_ocr(ocr_result, doc_type=doc_type)
    else:
        # Nếu Gemini chạy được nhưng có trường bị khuyết, bổ sung từ OCR
        ocr_fallback = extract_schema_from_ocr(ocr_result, doc_type=doc_type)
        for hf in HEADER_FIELDS:
            if not gemini_data.get(hf) and ocr_fallback.get(hf):
                gemini_data[hf] = ocr_fallback[hf]
        key = "metrics" if doc_type == "lab_test" else "medications"
        if not gemini_data.get(key) and ocr_fallback.get(key):
            gemini_data[key] = ocr_fallback[key]

    # Đảm bảo đồng bộ doc_type
    doc_type = gemini_data.get("doc_type", doc_type)

    # ==============================================================
    # [3] ĐỐI CHIẾU A VÀ B THEO TỪNG FIELD (RECONCILIATION)
    # ==============================================================
    reconciled = reconcile_parallel_results(ocr_result, gemini_data, doc_type=doc_type)

    key = "metrics" if doc_type == "lab_test" else "medications"
    fields = REVIEW_FIELDS[key]
    draft = {field: reconciled.get(field) or "" for field in HEADER_FIELDS}
    draft[key] = [{field: str(row.get(field) or "") for field in fields}
                  for row in reconciled.get(key, [])]
    boxes = []
    if prep_res.get("to_original") and prep_res.get("orig_shape"):
        import numpy as np
        width, height = prep_res["orig_shape"]
        inverse = np.asarray(prep_res["to_original"])
        for line in ocr_result.get("lines", []):
            points = []
            for x, y in line["box"]:
                px, py, scale = inverse @ [x, y, 1]
                if abs(scale) < 1e-8:
                    break
                points.append([float(px / scale / width), float(py / scale / height)])
            if len(points) == 4:
                boxes.append({"text": line["text"], "points": points})
    return {"status": "review", "doc_type": doc_type, "data": draft, "boxes": boxes,
            "requires_user_confirmation": True}


HEADER_FIELDS = ("patient_name", "dob", "doctor", "facility", "date", "diagnosis")
REVIEW_FIELDS = {
    "medications": ("name", "strength", "dose", "frequency", "days", "usage"),
    "metrics": ("test_name", "result", "unit", "reference_range", "flag_on_paper")
}


def finalize_reviewed_document(reconciled, doc_type, filename_clean, user_allergies):
    start_all = time.time()
    # ==============================================================
    # [4] CHUẨN HÓA & GROUNDING (RULE + CSDL - KHÔNG DÙNG LLM)
    # ==============================================================
    if doc_type == "prescription":
        standardized_meds = []
        full_schedule = {}

        for med in reconciled.get("medications", []):
            med_entry = dict(med)
            ground_info = normalize_drug_entity(med_entry.get("name", ""))
            med_entry["standard_name"] = ground_info["standard_name"]
            med_entry["active_ingredient"] = ground_info["active_ingredient"]
            med_entry["category"] = ground_info["category"]
            med_entry["purpose"] = med_entry.get("purpose") or ground_info.get("purpose", ground_info["category"])
            med_entry["grounding_status"] = ground_info["status"]

            # Lập lịch uống bằng RULE
            med_sched = parse_frequency_to_schedule(med_entry.get("frequency", ""), med_entry.get("usage", ""))
            med_entry["schedule"] = med_sched

            standardized_meds.append(med_entry)

        reconciled["medications"] = standardized_meds

    elif doc_type == "lab_test":
        standardized_metrics = []
        for item in reconciled.get("metrics", []):
            m_entry = dict(item)
            map_res = map_lab_test(m_entry.get("test_name", ""))
            m_entry["standard_name"] = map_res["standard_name"]
            m_entry["loinc_code"] = map_res["loinc_code"]
            standardized_metrics.append(m_entry)

        reconciled["metrics"] = standardized_metrics

    # ==============================================================
    # [5] VALIDATE & LUẬT NGHIỆP VỤ
    # ==============================================================
    clinical_alerts = []
    if doc_type == "prescription":
        val_res = validate_prescription_rules(reconciled.get("medications", []), user_allergies=user_allergies)
        clinical_alerts.extend(val_res.get("alerts", []))
    elif doc_type == "lab_test":
        reconciled["metrics"] = validate_lab_rules(reconciled.get("metrics", []))

    reconciled["clinical_alerts"] = clinical_alerts

    # ==============================================================
    # [6] DIỄN GIẢI (GEMINI CHỈ NHẬN JSON ĐÃ ĐƯỢC VALIDATE)
    # ==============================================================
    interp_res = generate_clinical_interpretation(reconciled)

    # ==============================================================
    # [7] KẾT XUẤT OUTPUT JSON + MÀN HÌNH XÁC NHẬN NGƯỜI DÙNG
    # ==============================================================
    total_time = round(time.time() - start_all, 2)

    # Map sang định dạng tương thích với giao diện dashboard người dùng
    medications_list = reconciled.get("medications", [])
    metrics_list = reconciled.get("metrics", [])
    clinical_warnings = reconciled.get("clinical_alerts", [])
    if reconciled.get("reconciliation_review", {}).get("needs_review"):
        clinical_warnings.extend(reconciled["reconciliation_review"].get("review_reasons", []))

    ui_timeline = {
        "morning": [],
        "noon": [],
        "evening": [],
        "bedtime": [],
        "external": []
    }
    for med in medications_list:
        sched = med.get("schedule", {})
        m_name = med.get("standard_name") or med.get("name")
        # Không tự ý điền mặc định "1 viên" nếu tài liệu không ghi rõ liều
        has_dose = bool(med.get("dose") and str(med.get("dose")).strip())
        m_dose = med.get("dose") if has_dose else "Chưa rõ liều (Cần đối chiếu đơn)"
        needs_review_item = med.get("needs_review", False) or not has_dose

        for slot_key in ["morning", "noon", "evening", "bedtime"]:
            s_info = sched.get(slot_key)
            if s_info and s_info.get("active"):
                # Không gán bừa "Uống sau ăn" nếu đơn thuốc không chỉ định
                slot_note = s_info.get("note") or "Theo chỉ dẫn của bác sĩ/dược sĩ"
                ui_timeline[slot_key].append({
                    "name": m_name,
                    "dose": m_dose,
                    "note": slot_note,
                    "needs_review": needs_review_item
                })

    output = {
        "status": "success",
        "type": doc_type,
        "doc_type": doc_type,
        "doc_title": f"Đơn thuốc {reconciled.get('facility', 'Bệnh viện')}" if doc_type == "prescription" else f"Phiếu Xét Nghiệm {reconciled.get('facility', '')}",
        "facility": reconciled.get("facility", "Bệnh viện"),
        "department": reconciled.get("department", "Khoa Khám bệnh"),
        "doctor": reconciled.get("doctor", "Bác sĩ chuyên khoa"),
        "patient_name": reconciled.get("patient_name", "Bệnh nhân"),
        "dob": reconciled.get("dob") or reconciled.get("birth_date") or "",
        "age": reconciled.get("age", ""),
        "gender": reconciled.get("gender", ""),
        "diagnosis": reconciled.get("diagnosis", "Theo dõi điều trị"),
        "date": reconciled.get("date", "Hôm nay"),
        "duration": reconciled.get("duration", "Theo đơn cấp"),
        "medications": medications_list,
        "metrics": metrics_list,
        "timeline": ui_timeline,
        "warnings": clinical_warnings,
        "requires_user_confirmation": False,
        "pipeline_version": "2.0-parallel-reconciled",
        "processing_time_sec": total_time,
        "uploaded_filename": filename_clean,
        "reconciliation": reconciled.get("reconciliation_review", {}),
        "data": reconciled,
        "interpretation": interp_res.get("interpretation_md", ""),
        "disclaimer": interp_res.get("disclaimer", "")
    }

    return output


def _build_unified_timeline(medications: list) -> list:
    """Tạo timeline tổng hợp các cữ thuốc trong ngày sau khi phân bổ bằng rule."""
    slots = [
        {"slot_id": "morning", "time": "07:00", "label": "Buổi Sáng (06:30 - 08:00)", "drugs": []},
        {"slot_id": "noon", "time": "12:00", "label": "Buổi Trưa (11:30 - 12:30)", "drugs": []},
        {"slot_id": "evening", "time": "18:30", "label": "Buổi Tối (18:00 - 19:30)", "drugs": []},
        {"slot_id": "bedtime", "time": "21:30", "label": "Trước khi ngủ (21:00 - 22:00)", "drugs": []}
    ]

    for med in medications:
        sched = med.get("schedule", {})
        for s in slots:
            slot_info = sched.get(s["slot_id"])
            if slot_info and slot_info.get("active"):
                s["drugs"].append({
                    "name": med.get("standard_name") or med.get("name"),
                    "dose": med.get("dose", "1 viên"),
                    "note": slot_info.get("note", "Uống sau ăn"),
                    "needs_review": med.get("needs_review", False)
                })

    return [s for s in slots if len(s["drugs"]) > 0]

