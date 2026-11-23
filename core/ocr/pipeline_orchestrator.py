import os
import sys
import json
import time
import re
import logging
import unicodedata
import tempfile
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

from core.intake_service import check_image_quality, mask_pii_on_image
from core.preprocessing_service import preprocess_lightweight
from core.ocr_parallel_service import extract_ocr_parallel
from core.gemini_schema_service import extract_with_gemini_schema
from core.reconciliation_service import reconcile_parallel_results, extract_schema_from_ocr
from core.grounding_service import normalize_drug_entity, map_lab_test, parse_frequency_to_schedule, normalize_lab_unit_and_value
from core.validation_service import validate_prescription_rules, validate_lab_rules
from core.interpretation_service import generate_clinical_interpretation
from core.ocr.prescription_transcription import read_transcription
from core.ocr.vietocr_reader import reread_name_cells


_MEDICATION_TOTAL = re.compile(
    r"\b(?:cong\s*khoan|tong\s*so\s*khoan)[ \t]*[:.;]?[ \t]*(?:\|[ \t]*)?([1-9][0-9]{0,2})"
    r"(?![ \t]*(?:\|[ \t]*)?(?:vien|goi|ong|chai|lo|hop|tuyp|ml)\b)"
    r"(?=[ \t]*(?:khoan\b|[|\r\n]|$))",
    re.IGNORECASE,
)


def _ocr_medication_totals(text: str) -> set[int]:
    """Read explicit totals for prescription entries, excluding dispensed quantities."""
    folded = "".join(char for char in unicodedata.normalize("NFD", text)
                     if not unicodedata.combining(char))
    return {int(match) for match in _MEDICATION_TOTAL.findall(folded)}


def _read_prescription_pdf(file_path):
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    pages = []
    with tempfile.TemporaryDirectory(prefix="medimind-rx-") as folder:
        for page in reader.pages:
            rows = []
            for line in (page.extract_text(extraction_mode="layout") or "").splitlines():
                cells = [{"text": cell} for cell in re.split(r"\s{2,}", line.strip()) if cell]
                if cells:
                    rows.append({"text": " | ".join(cell["text"] for cell in cells), "items": cells})
            if rows:
                pages.append(rows)
                continue

            # Image-only scans can embed an image covering a complete page.
            images = [image for image in page.images if 0 < len(image.data) <= 10 * 1024 * 1024
                      and image.image is not None]
            if not images:
                pages.append([])
                continue
            image = max(images, key=lambda item: item.image.width * item.image.height)
            path = os.path.join(folder, "page.png")
            image.image.convert("RGB").save(path)
            result = extract_ocr_parallel(path, doc_type="transcription")
            if not result.get("success"):
                return result
            pages.append(result.get("rows") or [])
    return {"success": True, "pages": pages}


def process_prescription_transcription(
    file_path: str,
    original_filename: str = "",
    enable_fallback: bool = False,
) -> Dict[str, Any]:
    """Read the printed source locally, with optional VLM crop-level fallback for hard cases."""
    filename = original_filename or os.path.basename(file_path)
    is_pdf = str(file_path).lower().endswith(".pdf")
    prep = {}
    reread_name = None
    if is_pdf:
        try:
            result = _read_prescription_pdf(file_path)
        except Exception as exc:
            logger.warning("Prescription PDF transcription failed (%s).", type(exc).__name__)
            return {"status": "failed", "message": "Không thể đọc PDF. Hãy thử xuất trang đơn thuốc thành ảnh JPG hoặc PNG."}
    else:
        quality = check_image_quality(file_path)
        if not quality.get("passed", True):
            return {"status": "rejected", "message": quality.get("recommendation") or "Ảnh chưa đủ rõ để đọc chữ."}
        prep = preprocess_lightweight(file_path, need_clahe=quality.get("need_clahe", False), upscale_small=True)
        active_image_path = prep.get("processed_path", file_path)
        result = extract_ocr_parallel(active_image_path, doc_type="transcription")
        # Rotated OCR boxes are projected back onto this same image.
        if not result.get("orientation_deg"):
            reread_name = reread_name_cells(active_image_path)
    if not result.get("success", True):
        return {"status": "failed", "message": "Bộ đọc chữ cục bộ chưa sẵn sàng. Vui lòng thử lại sau."}

    transform = prep.get("to_original")
    shape = prep.get("orig_shape")

    def project_box(box):
        if len(box) != 4 or not transform or not shape:
            return []
        width, height = shape
        points = []
        for x, y in box:
            px, py, scale = [row[0] * x + row[1] * y + row[2] for row in transform]
            if abs(scale) < 1e-8:
                return []
            points.append([float(px / scale / width), float(py / scale / height)])
        return points

    pages = result.get("pages") if is_pdf else [result.get("rows") or []]
    header = {}
    medicines = []
    for rows in pages:
        page_header, page_medicines = read_transcription(rows, project_box, reread_name)
        for field, value in page_header.items():
            header.setdefault(field, value)
        medicines.extend(page_medicines)

    # 1. Đối chiếu siêu tốc với danh mục thuốc quốc gia
    try:
        from core.ocr.drug_lexicon_service import get_drug_lexicon
        from core.ocr.prescription_transcription import _printed_name
        lex = get_drug_lexicon()
        for med in medicines:
            v_name = med.get("vietocr_name") or _printed_name(med.get("vietocr_text", ""))
            raw_txt = med.get("name") or med.get("raw_ocr_name") or ""
            clean_raw = _printed_name(raw_txt) or raw_txt

            paren_name = ""
            if med.get("raw_ocr_name"):
                m_p = re.search(r"\(([^)]+)\)", med["raw_ocr_name"])
                if m_p:
                    paren_name = _printed_name(m_p.group(1))

            v_match = lex.search(v_name, min_score=0.80) if v_name else {}
            r_match = lex.search(clean_raw, min_score=0.75) if clean_raw else {}
            p_match = lex.search(paren_name, min_score=0.80) if paren_name else {}

            candidates = [m for m in (p_match, r_match, v_match) if m.get("is_matched")]
            best_match = max(candidates, key=lambda x: x.get("match_confidence", 0.0)) if candidates else {}

            if best_match.get("is_matched"):
                med["standard_name"] = best_match.get("standard_name")
                med["active_ingredient"] = best_match.get("active_ingredient")
                med["category"] = best_match.get("category")
                med["is_insurance_covered"] = best_match.get("is_insurance_covered", False)
                med["match_confidence"] = best_match.get("match_confidence", 0.0)

                # VietOCR đọc lại ô chữ và khớp chính xác Dược thư với độ tin cậy cao
                if v_name and v_match.get("is_matched") and v_match.get("match_confidence", 0) >= 0.80:
                    if not med.get("name") or v_match.get("match_confidence", 0) > r_match.get("match_confidence", 0):
                        med["name"] = best_match.get("standard_name") or v_name
                        med["needs_review"] = False
                        med["raw_ocr_name"] = ""
    except Exception as exc:
        logger.debug("Local drug lexicon lookup error: %s", exc)

    # 2. VLM Crop Fallback cho các dòng khó / mờ / confidence thấp (tối đa 3 dòng / đơn)
    if enable_fallback and not is_pdf and medicines:
        try:
            from core.ocr.crop_fallback_service import refine_medication_with_crop_fallback
            from core.llm_provider import llm_provider
            api_key = llm_provider.resolve_api_key(profile="ocr")
            if llm_provider.is_configured(profile="ocr", explicit_key=api_key):
                fallback_count = 0
                max_fallback = 3
                for i, med in enumerate(medicines):
                    is_hard_case = not med.get("name") or (med.get("needs_review") and med.get("match_confidence", 0.0) < 0.80)
                    if is_hard_case and fallback_count < max_fallback:
                        refined = refine_medication_with_crop_fallback(
                            image_path=active_image_path,
                            med=med,
                            context=header.get("diagnosis", ""),
                            api_key=api_key
                        )
                        medicines[i] = refined
                        fallback_count += 1
        except Exception as exc:
            logger.warning("Crop fallback step encountered error: %s", exc)
    totals = _ocr_medication_totals("\n".join(row["text"] for rows in pages for row in rows))
    count = len(medicines)

    # 3. PHAO CỨU SINH TOÀN TRANG (FULL-PAGE VLM VISION FALLBACK)
    # Kích hoạt khi Local OCR thất bại (0 dòng thuốc hoặc đọc thiếu so với tổng khoản)
    if enable_fallback and not is_pdf and (count == 0 or (totals and count < min(totals))):
        try:
            from core.ocr.gemini_schema_service import extract_with_gemini_schema
            from core.llm_provider import llm_provider
            api_key = llm_provider.resolve_api_key(profile="ocr")
            if llm_provider.is_configured(profile="ocr", explicit_key=api_key):
                logger.info("Local OCR missed rows (count=%d, totals=%s). Activating Full-Page Vision Fallback...", count, totals)
                vlm_res = extract_with_gemini_schema(
                    image_path=file_path,
                    doc_type="prescription",
                    api_key=api_key,
                    ocr_result=result
                )
                if vlm_res and isinstance(vlm_res.get("medications"), list) and len(vlm_res["medications"]) > count:
                    for h_field in ("patient_name", "age", "gender", "dob", "diagnosis", "facility", "doctor", "date"):
                        v_val = str(vlm_res.get(h_field) or "").strip()
                        curr_val = str(header.get(h_field) or "").strip()
                        if v_val and (not curr_val or len(curr_val) <= 3 or curr_val.lower().startswith("mi")):
                            header[h_field] = v_val

                    medicines = vlm_res["medications"]
                    count = len(medicines)
                    try:
                        from core.ocr.drug_lexicon_service import get_drug_lexicon
                        lex = get_drug_lexicon()
                        for med in medicines:
                            q_name = med.get("name") or med.get("brand_name") or med.get("active_ingredient") or ""
                            if q_name:
                                m_cat = lex.search(q_name, min_score=0.75)
                                if m_cat.get("is_matched"):
                                    med["standard_name"] = m_cat.get("standard_name")
                                    med["active_ingredient"] = med.get("active_ingredient") or m_cat.get("active_ingredient")
                                    med["category"] = m_cat.get("category")
                                    med["is_insurance_covered"] = m_cat.get("is_insurance_covered", False)
                                    med["match_confidence"] = m_cat.get("match_confidence", 0.0)
                    except Exception:
                        pass
        except Exception as vlm_exc:
            logger.warning("Full-Page Vision Fallback error: %s", vlm_exc)

    mismatch = bool(totals and totals != {count})
    warning = ""
    if mismatch and len(totals) == 1:
        warning = f"Đọc được {count}/{next(iter(totals))} dòng thuốc. Hãy đối chiếu số dòng với ảnh gốc."
    elif mismatch:
        warning = "Tổng số dòng trên các vị trí của đơn chưa khớp. Hãy đối chiếu với tệp gốc."
    elif not count:
        warning = "Chưa nhận diện được dòng thuốc. Hãy đối chiếu ảnh gốc và thêm dòng thủ công."
    boxes = [
        {"text": line["text"], "points": points}
        for line in result.get("lines", [])
        if (points := project_box(line.get("box") or []))
    ]
    draft = {**header, "source_only": True, "medications": medicines}
    return {
        **draft, "status": "review", "type": "prescription", "doc_type": "prescription",
        "data": draft, "boxes": boxes, "requires_user_confirmation": True,
        "medication_count_mismatch": mismatch, "extraction_warning": warning,
        "extraction_source": "local_ocr", "uploaded_filename": filename,
    }


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
            return False
    return True

def _structure_ocr_text_with_groq(ocr_result: Dict[str, Any], doc_type: str = "prescription") -> Optional[Dict[str, Any]]:
    """
    Khi Vision AI (OpenRouter/Gemini) tạm quá tải (429) nhưng EasyOCR đã đọc được text thô,
    dùng Groq text LLM (openai/gpt-oss-120b) để chuẩn hóa & dọn nhiễu chính tả đơn thuốc thành JSON.
    """
    if doc_type == "lab_test":
        return None
    raw_lines = [str(line.get("text", "")).strip() for line in (ocr_result.get("lines") or []) if str(line.get("text", "")).strip()]
    if len(raw_lines) < 3:
        return None
    try:
        from core.llm_provider import llm_provider
        if not llm_provider.is_groq_active():
            return None
        joined_text = "\n".join(raw_lines)[:4500]
        prompt = (
            "Dưới đây là văn bản thô trích xuất từ EasyOCR trên ảnh đơn thuốc tiếng Việt (có thể bị lỗi dấu/ký tự OCR).\n"
            "Hãy bóc tách CHỈ các thông tin có thật trong văn bản OCR (không bịa thuốc không có trong đơn), "
            "sửa lỗi ký tự OCR rõ ràng và trả về DUY NHẤT JSON hợp lệ:\n"
            "{\n"
            '  "doc_type": "prescription",\n'
            '  "facility": "",\n'
            '  "doctor": "",\n'
            '  "patient_name": "",\n'
            '  "dob": "",\n'
            '  "age": "",\n'
            '  "gender": "",\n'
            '  "diagnosis": "",\n'
            '  "date": "",\n'
            '  "medications": [\n'
            '    {"name": "", "brand_name": "", "active_ingredient": "", "strength": "", "quantity": "", "schedule": "", "usage": ""}\n'
            "  ]\n"
            "}\n\n"
            f"VĂN BẢN OCR:\n{joined_text}"
        )
        groq_key = llm_provider.resolve_api_key(profile="chat")
        groq_model = llm_provider.get_default_model("chat", api_key=groq_key)
        res = llm_provider.generate_json(
            contents=prompt,
            model=groq_model,
            api_key=groq_key,
            provider="groq",
            temperature=0.1,
            max_output_tokens=2048,
            operation="ocr_text_structuring",
            profile="chat",
        )
        if isinstance(res, dict) and isinstance(res.get("medications"), list) and res["medications"]:
            cleaned_meds = []
            for item in res["medications"]:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or item.get("brand_name") or "").strip()
                if not name:
                    continue
                cleaned_meds.append({
                    "name": name,
                    "brand_name": str(item.get("brand_name") or name).strip(),
                    "active_ingredient": str(item.get("active_ingredient") or "").strip(),
                    "strength": str(item.get("strength") or "").strip(),
                    "quantity": str(item.get("quantity") or "").strip(),
                    "days": str(item.get("quantity") or "").strip(),
                    "schedule": str(item.get("schedule") or "").strip(),
                    "frequency": str(item.get("schedule") or "").strip(),
                    "usage": str(item.get("usage") or "").strip(),
                    "instructions": str(item.get("usage") or "").strip(),
                })
            if cleaned_meds:
                res["medications"] = cleaned_meds
                return res
    except Exception as exc:
        logger.warning("Groq OCR text structuring fallback unavailable (%s).", type(exc).__name__)
    return None


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
      [2] OCR EasyOCR bbox/rows và Gemini schema
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
    # [2] TRÍCH XUẤT OCR VÀ GEMINI
    #     Nhánh A: OCR Cục bộ (EasyOCR)
    #     Nhánh B: Gemini Vision Multimodal theo Response Schema
    # ==============================================================
    # 2.A: OCR cục bộ
    ocr_result = extract_ocr_parallel(active_image_path, doc_type=doc_type_hint)
    ocr_candidates = [(active_image_path, ocr_result)]
    # Geometric correction and resizing can erase small text. Keep an
    # independent reading of the original image for comparison.
    original_image_path = embedded_img_path if is_pdf and embedded_img_path else file_path
    can_read_original = (
        not mask_pii and original_image_path != active_image_path
        and os.path.splitext(original_image_path)[1].lower() != ".pdf"
    )
    if can_read_original and _ocr_needs_second_pass(ocr_result, doc_type_hint):
        original_ocr = extract_ocr_parallel(original_image_path, doc_type=doc_type_hint)
        ocr_candidates.append((original_image_path, original_ocr))

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

    selected_ocr_path, ocr_result = ocr_candidates[0]
    if len(ocr_candidates) > 1:
        selected_ocr_path, ocr_result = max(
            ocr_candidates, key=lambda candidate: _ocr_variant_score(candidate[1], doc_type)
        )

    # 2.B: Gemini Schema extraction (Cơ chế ảnh toàn trang + ảnh cắt phóng to LANCZOS)
    crop_image_path = None
    if doc_type in ("prescription", "auto"):
        try:
            from core.prescription_crop_service import crop_and_upscale_medication_region
            # The selected rows use coordinates from the image they were read from.
            crop_image_path = crop_and_upscale_medication_region(selected_ocr_path, ocr_result)
        except Exception as e:
            logger.warning("Lỗi cắt phóng to vùng thuốc: %s", e)
            crop_image_path = None

    gemini_data = extract_with_gemini_schema(
        active_image_path,
        doc_type=doc_type,
        crop_image_path=crop_image_path,
    )
    if not isinstance(gemini_data, dict):
        gemini_data = None
    if not gemini_data and not mask_pii and selected_ocr_path != active_image_path:
        gemini_data = extract_with_gemini_schema(
            selected_ocr_path,
            doc_type=doc_type,
            crop_image_path=crop_image_path,
        )
        if not isinstance(gemini_data, dict):
            gemini_data = None
    gemini_succeeded = bool(gemini_data)
    model_doc_type = gemini_data.get("doc_type") if gemini_data else None
    if model_doc_type in ("prescription", "lab_test") and model_doc_type != doc_type:
        doc_type = model_doc_type
        if len(ocr_candidates) > 1:
            selected_ocr_path, ocr_result = max(
                ocr_candidates, key=lambda candidate: _ocr_variant_score(candidate[1], doc_type)
            )

    if not gemini_data:
        # Nếu Vision API bận/429 -> thử chuẩn hóa text EasyOCR qua Groq LLM trước khi fallback regex
        gemini_data = _structure_ocr_text_with_groq(ocr_result, doc_type=doc_type)
    model_data = gemini_data or {}
    if not gemini_data:
        gemini_data = extract_schema_from_ocr(ocr_result, doc_type=doc_type)
    elif gemini_succeeded:
        # Nếu Gemini chạy được nhưng có trường bị khuyết, bổ sung từ OCR
        gemini_data = dict(model_data)
        ocr_fallback = extract_schema_from_ocr(ocr_result, doc_type=doc_type)
        for hf in HEADER_FIELDS:
            if not gemini_data.get(hf) and ocr_fallback.get(hf):
                gemini_data[hf] = ocr_fallback[hf]
        key = "metrics" if doc_type == "lab_test" else "medications"
        if not gemini_data.get(key) and ocr_fallback.get(key):
            gemini_data[key] = ocr_fallback[key]

    # Đảm bảo đồng bộ doc_type
    # The validated type was already applied before OCR fallback extraction.

    # ==============================================================
    # [3] ĐỐI CHIẾU A VÀ B THEO TỪNG FIELD (RECONCILIATION)
    # ==============================================================
    reconciled = reconcile_parallel_results(ocr_result, gemini_data, doc_type=doc_type)

    key = "metrics" if doc_type == "lab_test" else "medications"
    totals = set()
    if key == "medications":
        totals = _ocr_medication_totals("\n".join(
            str(candidate.get("raw_text") or "") for _, candidate in ocr_candidates
        ) + ("\n" + pdf_text if is_pdf else ""))
        if len(totals) == 1:
            expected = next(iter(totals))
            count = len(reconciled.get(key, []))
            # Give Vision a chance to resolve noisy rows before repeating local OCR.
            if count < expected and can_read_original and len(ocr_candidates) == 1:
                original_ocr = extract_ocr_parallel(original_image_path, doc_type=doc_type_hint)
                ocr_candidates.append((original_image_path, original_ocr))
                totals.update(_ocr_medication_totals(str(original_ocr.get("raw_text") or "")))
            if count != expected and totals == {expected}:
                for path, candidate in ocr_candidates:
                    if path == selected_ocr_path or not candidate.get("success", True):
                        continue
                    alternative = reconcile_parallel_results(candidate, model_data, doc_type=doc_type)
                    alternative_count = len(alternative.get(key, []))
                    if alternative_count == expected or count < alternative_count < expected:
                        selected_ocr_path, ocr_result, reconciled = path, candidate, alternative
                        break
    fields = REVIEW_FIELDS[key]
    draft = {field: reconciled.get(field) or "" for field in HEADER_FIELDS}
    draft[key] = []
    anchor_boxes = []
    for row in reconciled.get(key, []):
        review_row = {field: str(row.get(field) or "") for field in fields}
        if key == "medications":
            review_row["needs_review"] = bool(row.get("needs_review", False))
            review_row["field_confidence"] = row.get("field_confidence")
            review_row["ocr_matched_text"] = str(row.get("ocr_matched_text") or "")
            review_row["raw_ocr_name"] = str(row.get("raw_ocr_name") or "")
            review_row["raw_ocr_strength"] = str(row.get("raw_ocr_strength") or "")
            review_row["anchor_evidence_text"] = str(row.get("anchor_evidence_text") or "")
            for extra in ("brand_name", "active_ingredient", "quantity", "unit", "schedule", "instructions", "purpose"):
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
    medication_count_mismatch = False
    if key == "medications":
        count = len(draft[key])
        if totals and totals != {count}:
            medication_count_mismatch = True
            if len(totals) == 1:
                expected = next(iter(totals))
                count_warning = f"Đọc được {count} dòng thuốc. Đơn ghi tổng cộng {expected} dòng."
            else:
                count_warning = "OCR đọc được các giá trị tổng số dòng thuốc khác nhau trên đơn."
            extraction_warning = (
                f"{count_warning} Hãy đối chiếu số dòng với đơn gốc trước khi lưu."
                + (f" {extraction_warning}" if extraction_warning else "")
            )
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
    if normalize_points:
        for line in ocr_result.get("lines", []):
            source_box = line.get("box") or []
            if len(source_box) == 4:
                points = normalize_points(source_box)
                if len(points) == 4:
                    boxes.append({"text": line["text"], "points": points})
        if key == "medications":
            for review_row, anchor_box in zip(draft[key], anchor_boxes):
                if isinstance(anchor_box, list) and len(anchor_box) == 4:
                    points = normalize_points(anchor_box)
                    if len(points) == 4:
                        review_row["anchor_points"] = points
    return {
        "status": "review",
        "doc_type": doc_type,
        "patient_name": draft.get("patient_name") or reconciled.get("patient_name", ""),
        "dob": draft.get("dob") or reconciled.get("dob", ""),
        "age": draft.get("age") or reconciled.get("age", ""),
        "gender": draft.get("gender") or reconciled.get("gender", ""),
        "doctor": draft.get("doctor") or reconciled.get("doctor", ""),
        "facility": draft.get("facility") or reconciled.get("facility", ""),
        "diagnosis": draft.get("diagnosis") or reconciled.get("diagnosis", ""),
        "date": draft.get("date") or reconciled.get("date", ""),
        "medications": draft.get("medications") or reconciled.get("medications", []),
        "metrics": draft.get("metrics") or reconciled.get("metrics", []),
        "data": draft,
        "boxes": boxes,
        "header_alternatives": reconciled.get("header_alternatives", {}),
        "extraction_warning": extraction_warning,
        "medication_count_mismatch": medication_count_mismatch,
        "review_schema_version": 3,
        "extraction_source": "ocr_gemini" if gemini_succeeded else "ocr_only",
        "requires_user_confirmation": True
    }


HEADER_FIELDS = ("patient_name", "dob", "age", "gender", "doctor", "facility", "date", "diagnosis")
REVIEW_FIELDS = {
    "medications": ("name", "strength", "dose", "frequency", "days", "usage"),
    "metrics": ("test_name", "result", "unit", "reference_range", "flag_on_paper")
}


def finalize_reviewed_document(reconciled, doc_type, filename_clean, user_allergies, *, source_only=False):
    if source_only:
        return {
            **reconciled,
            "status": "success", "type": doc_type, "doc_type": doc_type,
            "source_only": True, "uploaded_filename": filename_clean,
            "data": reconciled, "requires_user_confirmation": False,
        }

    start_all = time.time()
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

