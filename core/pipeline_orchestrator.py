import os
import sys
import json
import time
import re
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

from core.intake_service import check_image_quality, mask_pii_on_image
from core.preprocessing_service import preprocess_lightweight
from core.ocr_parallel_service import extract_ocr_parallel, retry_ocr_crop_band, _group_ocr_rows
from core.groq_schema_service import extract_with_groq_schema

# Backward-compatible alias for tests patching extract_with_gemini_schema
extract_with_gemini_schema = extract_with_groq_schema
from core.reconciliation_service import (
    reconcile_parallel_results, extract_schema_from_ocr,
    _ascii_fold, _prescription_body_bounds, detect_left_column_ordinals,
)
from core.grounding_service import normalize_drug_entity, map_lab_test, parse_frequency_to_schedule, normalize_lab_unit_and_value
from core.validation_service import validate_prescription_rules, validate_lab_rules
from core.interpretation_service import generate_clinical_interpretation

def _ocr_variant_score(result: Dict[str, Any], doc_type: str) -> float:
    """Prefer the image pass that exposes actual table rows, not just more noise."""
    if not result or not result.get("success", True):
        return -1.0
    parsed = extract_schema_from_ocr(result, doc_type=doc_type)
    key = "metrics" if doc_type == "lab_test" else "medications"
    items = parsed.get(key) or []
    text = str(result.get("raw_text") or "")
    readable = len(re.findall(r"[\wÀ-ỹ]", text))
    confidence = result.get("avg_confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.0
    return (len(items) * 100 +
            sum(bool(parsed.get(field)) for field in HEADER_FIELDS) * 12 +
            min(readable, 1200) / 30 + confidence * 10)


def _ocr_needs_second_pass(result: Dict[str, Any], doc_type_hint: str) -> bool:
    if not result or not result.get("success", True):
        return True
    text = str(result.get("raw_text") or "")
    if len(re.findall(r"[\wÀ-ỹ]", text)) < 50:
        return True
    confidence = result.get("avg_confidence")
    if confidence is not None:
        try:
            if float(confidence) < 0.72:
                return True
        except (TypeError, ValueError):
            pass
    kinds = ("prescription", "lab_test") if doc_type_hint == "auto" else (doc_type_hint,)
    for kind in kinds:
        if kind not in ("prescription", "lab_test"):
            continue
        parsed = extract_schema_from_ocr(result, doc_type=kind)
        key = "medications" if kind == "prescription" else "metrics"
        if parsed.get(key):
            if kind == "prescription":
                expected = re.search(r"(?:cộng|cong)\s*(?:khoản|khoan)\s*[:.]?\s*(\d+)", text, re.IGNORECASE)
                if expected and len(parsed[key]) < int(expected.group(1)):
                    continue
            return False
    return True


def _compose_prescription_crop_ocr(full_ocr, crop_ocr, crop_path, bounds):
    """Use cropped OCR for medicine blocks and full-page OCR only for header/total anchors."""
    from PIL import Image
    from core.ocr_parallel_service import _group_ocr_rows

    x1, y1, x2, y2 = bounds
    with Image.open(crop_path) as image:
        crop_w, crop_h = image.size
    scale_x = crop_w / max(1, x2 - x1)
    scale_y = crop_h / max(1, y2 - y1)

    crop_lines = []
    for original in crop_ocr.get("lines", []):
        line = dict(original)
        line["box"] = [[x1 + point[0] / scale_x, y1 + point[1] / scale_y]
                       for point in original.get("box", [])]
        for key, offset, scale in (("x_min", x1, scale_x), ("x_max", x1, scale_x),
                                   ("y_min", y1, scale_y), ("y_max", y1, scale_y),
                                   ("y_center", y1, scale_y)):
            if original.get(key) is not None:
                line[key] = offset + original[key] / scale
        text = _ascii_fold(line.get("text", ""))
        if re.search(r"\b(?:cong\s*khoan|chan\s*doan)\b", text):
            continue
        crop_lines.append(line)

    full_rows = full_ocr.get("rows", [])
    diagnosis_row = next((row for row in full_rows
                          if re.search(r"\bchan\s*doan\b", _ascii_fold(row.get("text", "")))), None)
    first_medicine_row = next((row for row in full_rows
                               if re.match(r"^\s*\d+\s*[.)]\s*\S+", row.get("text", ""))
                               or ((row.get("items") or []) and re.fullmatch(
                                   r"\d+\s*[.)]?", str(row["items"][0].get("text", "")).strip()
                               ) and len(row.get("items", [])) > 1)), None)
    if diagnosis_row:
        header_cutoff = float(diagnosis_row.get("y_max", float("inf")))
    elif first_medicine_row:
        header_cutoff = float(first_medicine_row.get("y_min", 0)) - 1
    else:
        header_cutoff = float("-inf")
    header_lines = [dict(line) for line in full_ocr.get("lines", [])
                    if float(line.get("y_center", 0)) <= header_cutoff]

    total_rows = [row for row in full_rows if re.search(
        r"\b(?:cong\s*khoan|tong\s*cong)\s*[:|.]?\s*\d+\b",
        _ascii_fold(row.get("text", "")),
    )]
    total_lines = []
    if total_rows:
        total_row = total_rows[0]
        total_lines = [dict(line) for line in full_ocr.get("lines", [])
                       if float(line.get("y_center", 0)) >= float(total_row.get("y_min", 0)) - 3
                       and float(line.get("y_center", 0)) <= float(total_row.get("y_max", 0)) + 3]
    scoped_lines = header_lines + crop_lines + total_lines
    scoped_lines.sort(key=lambda line: float(line.get("y_center", 0)))
    for line_index, line in enumerate(scoped_lines):
        line["line_index"] = line_index
    scoped_rows = _group_ocr_rows(scoped_lines)
    raw_text = "\n".join(row.get("text", "") for row in scoped_rows)
    return {
        **full_ocr,
        "lines": scoped_lines,
        "rows": scoped_rows,
        "raw_text": raw_text,
        "total_lines": len(scoped_lines),
        "total_rows": len(scoped_rows),
        "avg_confidence": round(sum(float(line.get("confidence", 0)) for line in scoped_lines)
                                 / max(1, len(scoped_lines)), 3),
    }


def build_ui_timeline(medications: list) -> Dict[str, list]:
    """Xây dựng lịch uống & cữ thuốc trong ngày (morning/noon/evening/bedtime/external) bằng RULE."""
    ui_timeline = {
        "morning": [],
        "noon": [],
        "evening": [],
        "bedtime": [],
        "external": [],
    }
    if not isinstance(medications, list):
        return ui_timeline

    for med in medications:
        if not isinstance(med, dict):
            continue
        m_name = str(med.get("name") or med.get("standard_name") or "").strip()
        if not m_name:
            continue
        freq_str = str(med.get("frequency") or med.get("schedule_as_printed") or "").strip()
        usage_str = str(med.get("usage") or med.get("instructions") or med.get("huong_dan") or "").strip()
        route_str = str(med.get("route") or "").strip()
        combined_usage = f"{usage_str} {route_str}".strip()

        sched = med.get("schedule")
        if not isinstance(sched, dict) or not any(
            isinstance(sched.get(k), dict) and sched[k].get("active")
            for k in ("morning", "noon", "evening", "bedtime", "external")
        ):
            sched = parse_frequency_to_schedule(freq_str, combined_usage)

        raw_dose = med.get("dose") or med.get("dosage")
        has_dose = bool(raw_dose and str(raw_dose).strip())
        m_dose = str(raw_dose).strip() if has_dose else (
            "Dùng ngoài" if "ngoài" in route_str.lower() else "Theo đơn"
        )
        needs_review_item = bool(med.get("needs_review", False)) or (not has_dose and "ngoài" not in route_str.lower())

        for slot_key in ("morning", "noon", "evening", "bedtime", "external"):
            s_info = sched.get(slot_key)
            if isinstance(s_info, dict) and s_info.get("active"):
                slot_note = s_info.get("note") or usage_str or "Theo chỉ dẫn của bác sĩ/dược sĩ"
                ui_timeline[slot_key].append({
                    "name": m_name,
                    "dose": m_dose,
                    "note": slot_note,
                    "needs_review": needs_review_item,
                })
    return ui_timeline


def _build_default_overlay_boxes(medications, detail_boxes, rows, width, height):
    """Aggregate OCR fragments into one rendered box per medicine and header row."""
    boxes = []
    boxes_by_id = {}
    for detail in detail_boxes:
        if detail.get("medicine_id"):
            boxes_by_id.setdefault(detail["medicine_id"], []).append(detail)
    for medicine in medications:
        linked = boxes_by_id.get(medicine.get("medicine_id"), [])
        medicine["ocr_box_ids"] = [box["line_index"] for box in linked]
        if not linked:
            continue
        points = [point for box in linked for point in box["points"]]
        xs, ys = [point[0] for point in points], [point[1] for point in points]
        bbox = [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]
        card_status = medicine.get("card_status") or medicine.get("match_status")
        status = (
            "unmatched" if card_status == "missing_row"
            else "needs_review" if (card_status == "uncertain" or medicine.get("needs_review"))
            else "not_in_db" if card_status == "not_in_db"
            else "recognized"
        )
        boxes.append({
            "id": medicine["medicine_id"], "medicine_id": medicine["medicine_id"],
            "text": medicine.get("ocr_matched_text") or medicine.get("name", ""),
            "confidence": float(medicine.get("ocr_confidence") or 0),
            "bbox": bbox, "points": bbox,
            "bbox_pixels": [[x * width, y * height] for x, y in bbox],
            "line_index": linked[0]["line_index"],
            "line_indices": medicine["ocr_box_ids"], "status": status,
            "kind": "medicine",
        })

    patterns = {
        "patient_name": r"\bho\s*ten\b",
        "diagnosis": r"\bchan\s*doan\b",
        "date": r"\bngay\s*kham\b|\bngay\s*\d{1,2}\s*thang\b",
    }
    added = set()
    detail_by_line = {box["line_index"]: box for box in detail_boxes}
    for row in rows:
        row_text = _ascii_fold(row.get("text", ""))
        for field_name, pattern in patterns.items():
            if field_name in added or not re.search(pattern, row_text):
                continue
            linked = [detail_by_line[int(item["line_index"])] for item in row.get("items", [])
                      if item.get("line_index") is not None and int(item["line_index"]) in detail_by_line]
            if not linked:
                continue
            points = [point for box in linked for point in box["points"]]
            xs, ys = [point[0] for point in points], [point[1] for point in points]
            bbox = [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]
            boxes.append({
                "id": f"HDR_{field_name}", "medicine_id": None, "field_id": field_name,
                "text": row.get("text", ""),
                "confidence": min(float(box.get("confidence") or 0) for box in linked),
                "bbox": bbox, "points": bbox,
                "bbox_pixels": [[x * width, y * height] for x, y in bbox],
                "line_index": linked[0]["line_index"],
                "line_indices": [box["line_index"] for box in linked],
                "status": "recognized", "kind": "header",
            })
            added.add(field_name)
            break
    return boxes

def process_medical_document_pipeline(
    file_path: str,
    original_filename: str = "",
    doc_type_hint: str = "auto",
    user_allergies: list = None,
    mask_pii: bool = False,
) -> Dict[str, Any]:
    """
    KIẾN TRÚC ĐỌC ĐƠN THUỐC & PHIẾU XÉT NGHIỆM 8 BƯỚC:
      [0] Intake & Phân loại + Kiểm tra chất lượng (mờ, tối, lóa)
      [1] Tiền xử lý nhẹ (giữ cả ảnh gốc, crop/deskew/perspective, chỉ CLAHE khi tối)
      [2] OCR EasyOCR bbox/rows và Groq schema
      [3] Đối chiếu A và B từng field (needs_review=True nếu lệch)
      [4] Chuẩn hóa & Grounding (Rule + CSDL, không dùng LLM)
      [5] Validate & Luật nghiệp vụ (Cờ cao/thấp, tương tác thuốc, dị ứng)
      [6] Diễn giải (Groq chỉ nhận JSON đã validate)
      [7] Output JSON + sẵn sàng cho màn hình xác nhận người dùng
    """
    start_all = time.time()
    filename_clean = original_filename or os.path.basename(file_path)

    # Tạo scan ID duy nhất cho mỗi lần xử lý — dễ tra cứu trong log
    import uuid
    scan_id = str(uuid.uuid4())[:8].upper()
    logger.info(f"[SCAN:{scan_id}] START file={filename_clean}")

    if not os.path.exists(file_path):
        return {
            "status": "failed",
            "needs_review": True,
            "error_code": "FILE_NOT_FOUND",
            "message": "Không tìm thấy tệp tài liệu y tế.",
            "uploaded_filename": filename_clean
        }

    # ==============================================================
    # [0] & [1] INTAKE QUALITY CHECK & TIỀN XỬ LÝ NHẸ
    # ==============================================================
    is_pdf = file_path.lower().endswith(".pdf")
    if is_pdf:
        prep_res = {}
        active_image_path = file_path
        pdf_text = ""
        embedded_img_path = None
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            bounded_pages = list(reader.pages[:20])
            pdf_text = "\n".join((page.extract_text() or "") for page in bounded_pages).strip()[:100_000]
            if not pdf_text:
                for page in bounded_pages[:2]:
                    for img_obj in getattr(page, "images", ()):
                        raw_img_data = getattr(img_obj, "data", b"") or b""
                        if not (0 < len(raw_img_data) <= 10 * 1024 * 1024):
                            continue
                        img_ext = os.path.splitext(getattr(img_obj, "name", "") or "")[1].lower()
                        if img_ext not in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
                            img_ext = ".png"
                        cand_path = f"{os.path.splitext(file_path)[0]}_pdf_img{img_ext}"
                        with open(cand_path, "wb") as img_f:
                            img_f.write(raw_img_data)
                        embedded_img_path = cand_path
                        break
                    if embedded_img_path:
                        break
        except Exception:
            pdf_text = ""

        if embedded_img_path and os.path.exists(embedded_img_path):
            q_pdf = check_image_quality(embedded_img_path)
            prep_res = preprocess_lightweight(embedded_img_path, need_clahe=q_pdf.get("need_clahe", False))
            active_image_path = prep_res.get("processed_path", embedded_img_path)
        else:
            prep_res = {"processed_path": file_path, "deskew_angle": 0.0, "perspective_corrected": False}
            active_image_path = file_path
    else:
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
        need_clahe = quality_check.get("need_clahe", False)
        prep_res = preprocess_lightweight(file_path, need_clahe=need_clahe)
        active_image_path = prep_res.get("processed_path", file_path)

    # (Tùy chọn) Che PII trước khi gửi đi nếu người dùng bật
    if mask_pii:
        active_image_path = mask_pii_on_image(active_image_path, [])

    # ==============================================================
    # [2] TRÍCH XUẤT OCR VÀ GROQ
    #     Nhánh A: OCR Cục bộ (EasyOCR)
    #     Nhánh B: Groq Vision Multimodal theo Response Schema
    # ==============================================================
    # 2.A: OCR cục bộ
    ocr_result = extract_ocr_parallel(active_image_path, doc_type=doc_type_hint)
    ocr_candidates = [(active_image_path, ocr_result)]
    original_image_path = embedded_img_path if is_pdf and embedded_img_path else file_path
    if not mask_pii and original_image_path != active_image_path and _ocr_needs_second_pass(ocr_result, doc_type_hint):
        second_ocr = extract_ocr_parallel(original_image_path, doc_type=doc_type_hint)
        if second_ocr:
            ocr_candidates.append((original_image_path, second_ocr))
            selected_idx = max(range(len(ocr_candidates)), key=lambda i: _ocr_variant_score(ocr_candidates[i][1], doc_type_hint))
            selected_path, ocr_result = ocr_candidates[selected_idx]
        else:
            selected_path = active_image_path
    else:
        selected_path = active_image_path
    # One EasyOCR pass per scan keeps a single coordinate/text source. The
    # rectified, upscaled image is the OCR source; the original remains for UI.

    # Phân loại tự động nếu chưa có doc_type_hint
    doc_type = doc_type_hint
    if doc_type == "auto":
        from core.grounding_service import _fold_ascii
        comb_ascii = _fold_ascii(" ".join(
            candidate.get("raw_text", "") for _, candidate in ocr_candidates
        ) + " " + (pdf_text if is_pdf else ""))
        lab_score = (
            sum(3 for k in ("xet nghiem", "laboratory", "ket qua", "chi so", "don vi", "tri so bth") if k in comb_ascii)
            + sum(1 for k in ("glucose", "cholesterol", "triglyceride", "creatinine", "hba1c", "wbc", "rbc", "hgb", "plt") if k in comb_ascii)
        )
        rx_score = (
            sum(3 for k in ("don thuoc", "toa thuoc", "prescription") if k in comb_ascii)
            + sum(2 for k in ("vien", "uong", "lieu dung", "cach dung", "sl:") if k in comb_ascii)
            + sum(1 for k in ("sang", "trua", "chieu", "toi", "goi", "ong", "tuyp", "chan doan") if k in comb_ascii)
        )
        doc_type = "lab_test" if (lab_score >= 3 and lab_score > rx_score) else "prescription"

    selected_ocr_path, ocr_result = max(
        ocr_candidates, key=lambda candidate: _ocr_variant_score(candidate[1], doc_type)
    )

    # Kiểm tra chất lượng vùng thuốc: nếu số dòng STT cột trái (K) > số thuốc parse được,
    # chạy lại OCR riêng cho từng vùng y bị thiếu (crop + upscale x2) rồi gộp vào ocr_result.
    if doc_type == "prescription" and ocr_result.get("rows") and os.path.exists(selected_ocr_path):
        try:
            b_start, b_end = _prescription_body_bounds(ocr_result["rows"])
            b_rows = ocr_result["rows"][b_start:b_end]
            detected_ords = detect_left_column_ordinals(b_rows)
            initial_schema = extract_schema_from_ocr(ocr_result, doc_type="prescription")
            initial_meds = initial_schema.get("medications", [])
            parsed_ords = {m.get("source_ordinal") for m in initial_meds if m.get("source_ordinal") is not None}
            missing_ords = [o for o in detected_ords if o["ordinal"] not in parsed_ords]
            # Tìm thêm các thuốc đã đọc được tên nhưng thiếu dòng hướng dẫn/liều hoặc thiếu số lượng
            lines_by_idx_init = {int(l["line_index"]): l for l in ocr_result.get("lines", []) if l.get("line_index") is not None}
            med_y_ranges = []
            for m in initial_meds:
                m_lines = [lines_by_idx_init[i] for i in m.get("source_line_indices", []) if i in lines_by_idx_init]
                if not m_lines:
                    continue
                med_y_ranges.append((
                    min(float(l["y_min"]) for l in m_lines),
                    max(float(l["y_max"]) for l in m_lines),
                    m,
                ))
            med_y_ranges.sort(key=lambda t: t[0])

            retry_bands = []
            for idx_o, ord_info in enumerate(detected_ords):
                if ord_info["ordinal"] in parsed_ords:
                    continue
                # Mở rộng lên trên 85px để bắt cả trường hợp STT căn giữa ô bảng nằm dưới dòng tên thuốc
                y1 = max(0.0, ord_info["y_min"] - 85.0)
                y2 = (detected_ords[idx_o + 1]["y_min"] + 8.0) if idx_o + 1 < len(detected_ords) else (ord_info["y_max"] + 120.0)
                retry_bands.append((y1, y2, f"missing_ord_{ord_info['ordinal']}"))

            for idx_m, (my1, my2, m_obj) in enumerate(med_y_ranges):
                is_external = (m_obj.get("route") or "") in ("Dùng ngoài", "Dùng ngoài da")
                missing_regimen = (
                    (not m_obj.get("frequency"))
                    or (not is_external and not m_obj.get("dose"))
                )
                missing_qty = not (m_obj.get("quantity") or m_obj.get("days"))
                if missing_regimen or missing_qty:
                    next_y = med_y_ranges[idx_m + 1][0] if idx_m + 1 < len(med_y_ranges) else (my2 + 120.0)
                    band_y1 = max(0.0, my1 - 12.0)
                    band_y2 = max(my2 + 24.0, next_y + 4.0)
                    retry_bands.append((band_y1, band_y2, f"med_{m_obj.get('source_ordinal')}"))

            if retry_bands:
                added_lines = []
                for y1, y2, _tag in retry_bands[:8]:
                    band_lines = retry_ocr_crop_band(selected_ocr_path, y1, y2, scale=1.8, min_conf=0.20)
                    added_lines.extend(band_lines)
                if added_lines:
                    existing_lines = list(ocr_result.get("lines", []))
                    newly_merged = 0
                    for cand in added_lines:
                        cx1, cy1, cx2, cy2 = cand["x_min"], cand["y_min"], cand["x_max"], cand["y_max"]
                        c_area = max(1.0, (cx2 - cx1) * (cy2 - cy1))
                        dup = False
                        for ex in existing_lines:
                            ex1, ey1, ex2, ey2 = ex["x_min"], ex["y_min"], ex["x_max"], ex["y_max"]
                            inter = max(0.0, min(cx2, ex2) - max(cx1, ex1)) * max(0.0, min(cy2, ey2) - max(cy1, ey1))
                            if inter <= 0:
                                continue
                            ex_area = max(1.0, (ex2 - ex1) * (ey2 - ey1))
                            iou = inter / (c_area + ex_area - inter)
                            overlap_min = inter / min(c_area, ex_area)
                            if iou > 0.25 or overlap_min > 0.45:
                                dup = True
                                break
                        if not dup:
                            existing_lines.append(cand)
                            newly_merged += 1
                    if newly_merged:
                        existing_lines.sort(key=lambda item: item["y_center"])
                        for li, ln in enumerate(existing_lines):
                            ln["line_index"] = li
                        merged_rows = _group_ocr_rows(existing_lines)
                        ocr_result = {
                            **ocr_result,
                            "lines": existing_lines,
                            "rows": merged_rows,
                            "raw_text": "\n".join(r["text"] for r in merged_rows),
                            "total_lines": len(existing_lines),
                            "total_rows": len(merged_rows),
                        }
                        logger.info(
                            "[SCAN:%s] Band-retry OCR recovered %d new boxes across %d band(s)",
                            scan_id, newly_merged, len(retry_bands),
                        )
        except Exception as retry_err:
            logger.warning("[SCAN:%s] Bỏ qua band-retry OCR: %s", scan_id, retry_err)

    # 2.B: Groq Schema extraction (Cơ chế ảnh toàn trang + ảnh cắt phóng to LANCZOS)
    crop_image_path = None
    if doc_type in ("prescription", "auto"):
        try:
            from PIL import Image
            from core.prescription_crop_service import (
                crop_and_upscale_medication_region, detect_medication_bounds,
            )
            crop_source_path = selected_ocr_path
            with Image.open(crop_source_path) as source_image:
                source_width, source_height = source_image.size
            crop_bounds = detect_medication_bounds(
                ocr_result.get("lines", []), ocr_result.get("rows", []),
                source_width, source_height,
            )
            crop_image_path = crop_and_upscale_medication_region(crop_source_path, ocr_result)
            # The enlarged ROI is passed to vision extraction only. EasyOCR
            # stays single-pass and its bboxes all use the rectified page.
        except Exception as e:
            logger.warning("Lỗi cắt phóng to vùng thuốc: %s", e)
            crop_image_path = None

    model_data = extract_with_gemini_schema(
        active_image_path,
        doc_type=doc_type,
        crop_image_path=crop_image_path,
        ocr_result=ocr_result if selected_ocr_path == active_image_path else None,
    )
    if not isinstance(model_data, dict):
        model_data = None
    if not model_data and not mask_pii and selected_ocr_path != active_image_path:
        model_data = extract_with_gemini_schema(
            selected_ocr_path,
            doc_type=doc_type,
            crop_image_path=None,
            ocr_result=ocr_result
        )
        if not isinstance(model_data, dict):
            model_data = None
    model_succeeded = bool(model_data)
    model_doc_type = model_data.get("doc_type") if model_data else None
    if model_doc_type in ("prescription", "lab_test") and model_doc_type != doc_type:
        doc_type = model_doc_type
        selected_ocr_path, ocr_result = max(
            ocr_candidates, key=lambda candidate: _ocr_variant_score(candidate[1], doc_type)
        )

    if not model_data:
        # Nếu Groq API bận hoặc không khả dụng -> Fallback xây schema từ OCR
        model_data = extract_schema_from_ocr(ocr_result, doc_type=doc_type)
    else:
        # Nếu Groq chạy được nhưng có trường bị khuyết, bổ sung từ OCR
        ocr_fallback = extract_schema_from_ocr(ocr_result, doc_type=doc_type)
        for hf in HEADER_FIELDS:
            if not model_data.get(hf) and ocr_fallback.get(hf):
                model_data[hf] = ocr_fallback[hf]
        key = "metrics" if doc_type == "lab_test" else "medications"
        if not model_data.get(key) and ocr_fallback.get(key):
            model_data[key] = ocr_fallback[key]

    # Đảm bảo đồng bộ doc_type
    # The validated type was already applied before OCR fallback extraction.

    # ==============================================================
    # [3] ĐỐI CHIẾU A VÀ B THEO TỪNG FIELD (RECONCILIATION)
    # ==============================================================
    reconciled = reconcile_parallel_results(ocr_result, model_data, doc_type=doc_type)

    key = "metrics" if doc_type == "lab_test" else "medications"
    fields = REVIEW_FIELDS[key]
    draft = {field: reconciled.get(field) or "" for field in HEADER_FIELDS}
    draft[key] = []
    anchor_boxes = []
    for med_index, row in enumerate(reconciled.get(key, []), start=1):
        review_row = {
            field: (row.get(field) if row.get(field) not in ("", None) else None)
            for field in fields
        }
        if key == "medications":
            ocr_active_ingredient = str(row.get("active_ingredient") or "").strip()
            drug_match = normalize_drug_entity(str(row.get("name") or ""))
            if drug_match.get("status") != "matched" and ocr_active_ingredient:
                drug_match = normalize_drug_entity(ocr_active_ingredient)
            matched = drug_match.get("status") == "matched"
            ocr_conf = float(row.get("ocr_confidence") or 0.0)
            med_name_clean = str(row.get("name") or "").strip()
            is_clear_ocr_name = (
                ocr_conf >= 0.70
                and len(med_name_clean.replace(" ", "")) >= 4
                and bool(re.search(r"[A-Za-zÀ-ỹ]{4,}", med_name_clean))
            )
            if matched:
                card_status = "matched"
                match_status = "matched"
            elif is_clear_ocr_name:
                card_status = "not_in_db"
                match_status = "not_in_db"
            else:
                card_status = "uncertain"
                match_status = "unmatched"

            review_row["status"] = match_status
            review_row["match_status"] = match_status
            review_row["card_status"] = card_status
            review_row["match_score"] = drug_match.get("match_confidence", 0)
            review_row["ocr_confidence"] = round(ocr_conf, 3)
            review_row["standard_name"] = drug_match.get("standard_name") if matched else med_name_clean
            review_row["suggested_name"] = (
                drug_match.get("standard_name") if matched and drug_match.get("match_confidence", 0) < 95 else ""
            )
            review_row["active_ingredient"] = ocr_active_ingredient or (drug_match.get("active_ingredient", "") if matched else "")
            review_row["purpose"] = drug_match.get("purpose", "") if matched else ""
            has_regimen = bool(row.get("dose") or row.get("frequency") or row.get("huong_dan") or row.get("instructions"))
            review_row["needs_review"] = (
                card_status == "uncertain"
                or (matched and drug_match.get("match_confidence", 0) < 95)
                or not has_regimen
                or not bool(row.get("quantity") or row.get("days"))
            )
            review_row["field_confidence"] = row.get("field_confidence")
            review_row["ocr_matched_text"] = str(row.get("ocr_matched_text") or "")
            review_row["raw_ocr_name"] = str(row.get("raw_ocr_name") or "")
            review_row["raw_ocr_strength"] = str(row.get("raw_ocr_strength") or "")
            review_row["anchor_evidence_text"] = str(row.get("anchor_evidence_text") or "")
            review_row["medicine_id"] = f"MED_{med_index:03d}"
            review_row["source_ordinal"] = row.get("source_ordinal")
            review_row["source_line_indices"] = row.get("source_line_indices") or []
            for extra in ("brand_name", "active_ingredient", "quantity", "unit", "schedule", "instructions", "huong_dan", "route"):
                if row.get(extra):
                    review_row[extra] = str(row.get(extra))
            anchor_boxes.append(row.get("anchor_box"))
        draft[key].append(review_row)
    extraction_warning = ""
    if not draft[key]:
        extraction_warning = (
            "Chưa đọc được dòng thuốc nào từ ảnh. Hãy kiểm tra ảnh gốc và thêm từng dòng trước khi lưu."
            if key == "medications" else
            "Chưa đọc được chỉ số xét nghiệm nào từ ảnh. Hãy kiểm tra ảnh gốc và thêm từng dòng trước khi lưu."
        )
    elif key == "medications" and not ocr_result.get("lines"):
        extraction_warning = (
            "Tên thuốc chưa được OCR xác nhận trên ảnh. Hãy đối chiếu từng dòng với phiếu gốc trước khi lưu."
        )
    if key == "medications" and reconciled.get("count_warning"):
        extraction_warning = reconciled["count_warning"]
    boxes = []
    normalize_points = None
    if (selected_ocr_path == active_image_path and prep_res.get("to_original")
            and prep_res.get("orig_shape")):
        import numpy as np
        width, height = prep_res["orig_shape"]
        inverse = np.asarray(prep_res["to_original"])
        def normalize_points(box):
            points = []
            for x, y in box:
                px, py, scale = inverse @ [x, y, 1]
                if abs(scale) < 1e-8:
                    return []
                points.append([float(px / scale / width), float(py / scale / height)])
            return points
    elif selected_ocr_path == original_image_path:
        try:
            from PIL import Image
            with Image.open(original_image_path) as original_image:
                width, height = original_image.size
            def normalize_points(box):
                return [[float(x / width), float(y / height)] for x, y in box]
        except (OSError, ValueError, ZeroDivisionError):
            pass
    unclassified_ocr_regions = []
    detail_ocr_boxes = []
    boxes = []
    ocr_lines = ocr_result.get("lines", [])
    line_to_med = {}
    med_match_by_id = {}
    if key == "medications":
        for med in draft[key]:
            med_match_by_id[med["medicine_id"]] = med.get("match_status")
            for line_index in med.get("source_line_indices", []):
                line_to_med[int(line_index)] = med["medicine_id"]
    body_line_indices = set()
    ignored_line_indices = set()
    if key == "medications":
        ignored_line_indices = set(
            extract_schema_from_ocr(ocr_result, doc_type="prescription").get("ignored_ocr_line_indices", [])
        )
        rows_for_body = ocr_result.get("rows", [])
        body_start, body_end = _prescription_body_bounds(rows_for_body)
        for row in rows_for_body[body_start:body_end]:
            for item in row.get("items", []):
                if item.get("line_index") is not None:
                    body_line_indices.add(int(item["line_index"]))
    if normalize_points:
        for fallback_index, line in enumerate(ocr_lines):
            source_box = line.get("box") or []
            if len(source_box) == 4:
                points = normalize_points(source_box)
                if len(points) == 4:
                    line_index = int(line.get("line_index", fallback_index))
                    medicine_id = line_to_med.get(line_index)
                    confidence = float(line.get("confidence", 0) or 0)
                    status = "ignored_margin" if line_index in ignored_line_indices else (
                        "unclassified" if line_index in body_line_indices and not medicine_id else (
                            "unmatched" if medicine_id and med_match_by_id.get(medicine_id) == "unmatched"
                            else "low_confidence" if confidence < 0.7 else "recognized"
                        )
                    )
                    box_entry = {
                        "text": str(line.get("text", "")), "line_index": line_index,
                        "confidence": confidence,
                        "bbox": points,
                        "bbox_pixels": [[float(x * width), float(y * height)] for x, y in points],
                        "points": points,
                        "medicine_id": medicine_id, "status": status,
                    }
                    detail_ocr_boxes.append(box_entry)
                    if status == "unclassified":
                        unclassified_ocr_regions.append(box_entry)
    if normalize_points and key == "medications":
        for review_row, anchor_box in zip(draft[key], anchor_boxes):
            if isinstance(anchor_box, list) and len(anchor_box) == 4:
                points = normalize_points(anchor_box)
                if len(points) == 4:
                    review_row["anchor_points"] = points
        boxes = _build_default_overlay_boxes(
            draft[key], detail_ocr_boxes, ocr_result.get("rows", []), width, height,
        ) or detail_ocr_boxes
        # Kiểm tra chỉ số chất lượng K (số dòng STT ở cột trái) và gắn khung đỏ cho dòng thiếu nếu có
        body_rows_q = ocr_result.get("rows", [])[body_start:body_end]
        detected_ords = detect_left_column_ordinals(body_rows_q)
        k_detected = len(detected_ords)
        parsed_ords = {m.get("source_ordinal") for m in draft[key] if m.get("source_ordinal") is not None}
        if k_detected > len(draft[key]):
            missing_msg = f"Đọc được {len(draft[key])}/{k_detected} dòng thuốc, vui lòng đối chiếu"
            if not extraction_warning:
                extraction_warning = missing_msg
            if not reconciled.get("count_warning"):
                reconciled["count_warning"] = missing_msg
            for ord_info in detected_ords:
                if ord_info["ordinal"] not in parsed_ords:
                    raw_missing_box = [
                        [ord_info["x_min"], max(0.0, ord_info["y_min"] - 4)],
                        [ord_info["x_max"], max(0.0, ord_info["y_min"] - 4)],
                        [ord_info["x_max"], ord_info["y_max"] + 16],
                        [ord_info["x_min"], ord_info["y_max"] + 16],
                    ]
                    norm_missing = normalize_points(raw_missing_box)
                    if len(norm_missing) == 4:
                        boxes.append({
                            "id": f"MISSING_ROW_{ord_info['ordinal']}",
                            "medicine_id": None,
                            "text": f"Dòng thuốc số {ord_info['ordinal']} chưa đọc được đầy đủ",
                            "confidence": 0.0,
                            "bbox": norm_missing,
                            "points": norm_missing,
                            "bbox_pixels": [[x * width, y * height] for x, y in norm_missing],
                            "status": "unmatched",
                            "kind": "missing_row",
                        })
        # Giới hạn mặc định tối đa 12 khung trên ảnh
        if len(boxes) > 12:
            med_and_missing = [b for b in boxes if b.get("kind") in ("medicine", "missing_row")]
            hdr_boxes = [b for b in boxes if b.get("kind") == "header"]
            boxes = (med_and_missing + hdr_boxes)[:12]
    return {
        "status": "review",
        "doc_type": doc_type,
        "patient_name": draft.get("patient_name") or reconciled.get("patient_name", ""),
        "dob": draft.get("dob") or reconciled.get("dob", ""),
        "age": draft.get("age") or reconciled.get("age", ""),
        "gender": draft.get("gender") or reconciled.get("gender", ""),
        "doctor": draft.get("doctor") or reconciled.get("doctor", ""),
        "facility": draft.get("facility") or reconciled.get("facility", ""),
        "clinic": draft.get("clinic") or reconciled.get("clinic", ""),
        "diagnosis": draft.get("diagnosis") or reconciled.get("diagnosis", ""),
        "date": draft.get("date") or reconciled.get("date", ""),
        "medications": draft.get("medications") or reconciled.get("medications", []),
        "metrics": draft.get("metrics") or reconciled.get("metrics", []),
        "timeline": build_ui_timeline(draft.get("medications") or reconciled.get("medications", [])) if doc_type == "prescription" else {},
        "data": draft,
        "boxes": boxes,
        "raw_ocr_text": ocr_result.get("raw_text", ""),
        "ocr_lines": detail_ocr_boxes,
        "unclassified_ocr_regions": unclassified_ocr_regions,
        "ignored_ocr_line_indices": sorted(ignored_line_indices),
        "raw_ocr_preview": [str(line.get("text", "")) for line in ocr_lines[:30]],
        "ocr_metrics": {
            "avg_confidence": ocr_result.get("avg_confidence", 0),
            "total_lines": len(ocr_lines),
            "low_confidence_lines": sum(1 for line in ocr_lines if float(line.get("confidence", 0) or 0) < 0.7),
            "filter_stats": ocr_result.get("filter_stats", {}),
        },
        "header_alternatives": reconciled.get("header_alternatives", {}),
        "extraction_warning": extraction_warning,
        "expected_medication_count": reconciled.get("expected_medication_count"),
        "count_warning": reconciled.get("count_warning", ""),
        "review_schema_version": 3,
        "extraction_source": "ocr_groq" if model_succeeded else "ocr_only",
        "requires_user_confirmation": True
    }


HEADER_FIELDS = ("patient_name", "dob", "age", "gender", "doctor", "facility", "clinic", "date", "diagnosis")
REVIEW_FIELDS = {
    "medications": ("name", "strength", "dose", "frequency", "days", "usage"),
    "metrics": ("test_name", "result", "unit", "reference_range", "flag_on_paper")
}


def finalize_reviewed_document(reconciled, doc_type, filename_clean, user_allergies):
    import uuid
    start_all = time.time()
    scan_id = str(reconciled.get("scan_id") or str(uuid.uuid4())[:8].upper())
    reconciled["doc_type"] = doc_type
    # ==============================================================
    # [4] CHUẨN HÓA & GROUNDING (RULE + CSDL - KHÔNG DÙNG LLM)
    # ==============================================================
    if doc_type == "prescription":
        standardized_meds = []
        full_schedule = {}

        for med in reconciled.get("medications", []):
            med_entry = dict(med)
            ground_info = normalize_drug_entity(med_entry.get("name", ""))
            ocr_active_ingredient = str(med_entry.get("active_ingredient") or "").strip()
            if ground_info.get("status") != "matched" and ocr_active_ingredient:
                ground_info = normalize_drug_entity(ocr_active_ingredient)
            med_entry["standard_name"] = ground_info["standard_name"]
            med_entry["active_ingredient"] = ocr_active_ingredient or ground_info["active_ingredient"]
            med_entry["suggested_name"] = (
                ground_info["standard_name"] if ground_info.get("status") == "matched"
                and ground_info.get("match_confidence", 0) < 95 else med_entry.get("suggested_name", "")
            )
            med_entry["category"] = ground_info["category"]
            matched = ground_info.get("status") == "matched"
            med_entry["purpose"] = ground_info.get("purpose", "") if matched else ""
            med_entry["match_status"] = "matched" if matched else "unmatched"
            med_entry["match_score"] = ground_info.get("match_confidence", 0)
            med_entry["grounding_status"] = ground_info["status"]
            med_entry["needs_review"] = bool(
                med_entry.get("needs_review") or not matched
                or ground_info.get("match_confidence", 0) < 95
                or not med_entry.get("dose") or not (med_entry.get("quantity") or med_entry.get("days"))
            )

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
    # [6] DIỄN GIẢI (GROQ CHỈ NHẬN JSON ĐÃ ĐƯỢC VALIDATE)
    # ==============================================================
    interp_res = generate_clinical_interpretation(reconciled)

    # ==============================================================
    # [7] KẾT XUẤT OUTPUT JSON + MÀN HÌNH XÁC NHẬN NGƯỜI DÙNG
    # ==============================================================
    total_time = round(time.time() - start_all, 2)
    logger.info(f"[SCAN:{scan_id}] DONE meds_count={len(reconciled.get('medications', []))} time={total_time:.2f}s")

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
        m_name = med.get("name") or med.get("standard_name")
        # Không tự ý điền mặc định "1 viên" nếu tài liệu không ghi rõ liều
        has_dose = bool(med.get("dose") and str(med.get("dose")).strip())
        m_dose = med.get("dose") if has_dose else "Chưa rõ liều (Cần đối chiếu đơn)"
        needs_review_item = med.get("needs_review", False) or not has_dose

        for slot_key in ["morning", "noon", "evening", "bedtime", "external"]:
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

    inferred_duration = reconciled.get("duration") or ""
    if not inferred_duration and medications_list:
        import re as _re_dur
        day_nums = []
        for med in medications_list:
            m_dur = _re_dur.search(r"(\d+)\s*(?:ng[aà]y|days?)", str(med.get("days") or ""), _re_dur.IGNORECASE)
            if m_dur:
                day_nums.append(int(m_dur.group(1)))
        if day_nums:
            inferred_duration = f"{max(day_nums)} ngày"
    if not inferred_duration:
        inferred_duration = "Theo đơn cấp"

    output = {
        "status": "success",
        "type": doc_type,
        "doc_type": doc_type,
        "doc_title": f"Đơn thuốc {reconciled.get('facility', 'Bệnh viện')}" if doc_type == "prescription" else f"Phiếu Xét Nghiệm {reconciled.get('facility', '')}",
        "facility": reconciled.get("facility", "Bệnh viện"),
        "clinic": reconciled.get("clinic", ""),
        "department": reconciled.get("department", "Khoa Khám bệnh"),
        "doctor": reconciled.get("doctor", "Bác sĩ chuyên khoa"),
        "patient_name": reconciled.get("patient_name", "Bệnh nhân"),
        "dob": reconciled.get("dob") or reconciled.get("birth_date") or "",
        "age": reconciled.get("age", ""),
        "gender": reconciled.get("gender", ""),
        "diagnosis": reconciled.get("diagnosis", "Theo dõi điều trị"),
        "date": reconciled.get("date", "Hôm nay"),
        "duration": inferred_duration,
        "medications": medications_list,
        "metrics": metrics_list,
        "timeline": ui_timeline,
        "warnings": clinical_warnings,
        "requires_user_confirmation": False,
        "pipeline_version": "2.0-parallel-reconciled",
        "processing_time_sec": total_time,
        "uploaded_filename": filename_clean,
        "reconciliation": reconciled.get("reconciliation_review", {}),
        "scan_id": scan_id,
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

