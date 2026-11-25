import os
import json
import re
import logging
import unicodedata
from typing import Dict, Any, Optional

from core.ai.prompts import (
    PRESCRIPTION_OCR_FEW_SHOT_RULES,
    PRESCRIPTION_OCR_HANDWRITTEN_RULE,
    PRESCRIPTION_OCR_REDACTED_RULE,
    PRESCRIPTION_OCR_SYSTEM_PROMPT,
)

logger = logging.getLogger("GeminiSchemaService")


_VIETNAMESE_UNIT_MAP = {
    "vien": "Viên",
    "viên": "Viên",
    "goi": "Gói",
    "gói": "Gói",
    "ong": "Ống",
    "ống": "Ống",
    "chai": "Chai",
    "tuyp": "Tuýp",
    "tuýp": "Tuýp",
    "lo": "Lọ",
    "lọ": "Lọ",
    "hop": "Hộp",
    "hộp": "Hộp",
}


def _normalize_vietnamese_units(text: str) -> str:
    """Chuẩn hóa đơn vị tính tiếng Việt có dấu sau số lượng hoặc phân số liều dùng."""
    if not text:
        return ""

    def _replace(match: re.Match) -> str:
        qty = re.sub(r"\s*/\s*", "/", match.group(1).strip())
        unit_raw = match.group(2)
        unit_key = unit_raw.casefold()
        needs_normalization = (
            unit_key in {"vien", "goi", "ong", "tuyp", "lo", "hop"}
            or unit_raw.isupper()
        )
        normalized_unit = _VIETNAMESE_UNIT_MAP.get(unit_key, unit_raw) if needs_normalization else unit_raw
        return f"{qty} {normalized_unit}"

    return re.sub(
        r"(?i)\b(\d+(?:\s*/\s*\d+|[.,]\d+)?)\s*(viên|vien|gói|goi|ống|ong|chai|tuýp|tuyp|lọ|lo|hộp|hop)\b",
        _replace,
        str(text).strip(),
    )


_REDACTED_ADMIN_PLACEHOLDERS = {
    "benh nhan",
    "nguoi benh",
    "ho ten",
    "ho va ten",
    "ten benh nhan",
    "khong ro",
    "khong xac dinh",
    "chua xac dinh",
    "chua ro",
    "null",
    "none",
    "n a",
    "na",
    "unknown",
    "redacted",
}


def _fold_admin_text(text: str) -> str:
    """Fold Vietnamese diacritics and punctuation to compare redacted placeholders uniformly."""
    decomposed = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


def _sanitize_redacted_admin_field(value: Any, *, is_gender: bool = False) -> str:
    """Convert missing, null, or placeholder administrative values into an empty string."""
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    folded = _fold_admin_text(raw)
    if not folded or folded in _REDACTED_ADMIN_PLACEHOLDERS:
        return ""
    if is_gender:
        if re.fullmatch(r"(?:nu|female|woman|girl|f)", folded):
            return "Nữ"
        if re.fullmatch(r"(?:nam|male|man|boy|m)", folded):
            return "Nam"
        return ""
    return raw


def _get_image_mime_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".png":
        return "image/png"
    elif ext == ".pdf":
        return "application/pdf"
    elif ext == ".webp":
        return "image/webp"
    return "image/jpeg"


def extract_with_gemini_schema(
    image_path: str,
    doc_type: str = "prescription",
    api_key: str = "",
    crop_image_path: Optional[str] = None,
    ocr_result: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Optional[Dict[str, Any]]:
    """
    [2.B] Đọc ảnh đơn thuốc -> JSON theo response schema chuẩn y khoa lâm sàng qua Unified LLM Provider:
      - Hỗ trợ cơ chế kép (Dual-image): Ảnh 1 toàn trang (bố cục/hành chính) + Ảnh 2 cắt phóng to LANCZOS (đọc chi tiết thuốc).
      - Đảm bảo thực thi trong DUY NHẤT 1 lần gọi Vision API qua Groq/Gemini.
      - Nếu không có ảnh cắt, tự động fallback gửi ảnh toàn trang.
      - Chép trung thực từng hàng thuốc, tách riêng biệt dược, hoạt chất, số lượng, lịch dùng, cách dùng.
    """
    from core.ai.llm_provider import llm_provider

    if not api_key:
        api_key = llm_provider.resolve_api_key(profile="ocr")
    if not llm_provider.is_configured(profile="ocr", explicit_key=api_key):
        return None

    auto_crop = False
    try:
        from google.genai import types

        with open(image_path, "rb") as f:
            file_bytes = f.read()

        mime_type = _get_image_mime_type(image_path)

        # Tự động phát hiện và cắt nếu crop_image_path chưa được truyền nhưng có ocr_result
        if not crop_image_path and ocr_result and doc_type in ("prescription", "auto"):
            try:
                from core.ocr.prescription_crop_service import crop_and_upscale_medication_region
                crop_image_path = crop_and_upscale_medication_region(image_path, ocr_result)
                if crop_image_path and os.path.exists(crop_image_path):
                    auto_crop = True
            except Exception as ce:
                logger.debug("Automatic crop attempt failed: %s", ce)

        # 1. Chuẩn bị ảnh toàn trang (Image 1)
        contents = [
            types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
        ]

        # 2. Chuẩn bị ảnh cắt phóng to danh sách thuốc (Image 2) nếu có
        has_crop = False
        if crop_image_path and os.path.exists(crop_image_path) and crop_image_path != image_path:
            try:
                with open(crop_image_path, "rb") as cf:
                    crop_bytes = cf.read()
                crop_mime = _get_image_mime_type(crop_image_path)
                contents.append(types.Part.from_bytes(data=crop_bytes, mime_type=crop_mime))
                has_crop = True
            except Exception as ce:
                logger.warning("Could not load cropped medication image: %s", ce)

        if has_crop:
            doc_intro = """BẠN ĐANG NHẬN ĐƯỢC 2 ẢNH CỦA CÙNG MỘT ĐƠN THUỐC (CÙNG MỘT TÀI LIỆU):
- Ảnh 1: Toàn bộ trang đơn thuốc để xác định bố cục và thông tin hành chính.
- Ảnh 2: Ảnh cắt phóng to chi tiết vùng bảng thuốc để đọc chữ rõ nét."""
        else:
            doc_intro = """BẠN ĐANG NHẬN ĐƯỢC 1 ẢNH TOÀN BỘ TRANG ĐƠN THUỐC để xác định bố cục và đọc chữ."""

        prompt = f"""
{doc_intro}

Hãy chép từng hàng thuốc theo đúng thứ tự trên ảnh.

Quy tắc:
- Chỉ ghi chữ nhìn thấy trên ảnh; không đoán dựa vào kiến thức y khoa.
- Tách tên biệt dược in đậm và hoạt chất trong ngoặc.
- Không thay tên biệt dược bằng tên hoạt chất; trường "name" phải giữ ĐẦY ĐỦ tên thương mại, hàm lượng và tên hoạt chất trong ngoặc.
- Không tự thêm số lượng, buổi uống hoặc cách dùng.
- {PRESCRIPTION_OCR_HANDWRITTEN_RULE} Khi có nét viết tay sửa đổi, ưu tiên ghi giá trị theo chữ viết tay vào các trường dose, quantity_as_printed, schedule_as_printed và usage_as_printed.
- {PRESCRIPTION_OCR_FEW_SHOT_RULES}
- {PRESCRIPTION_OCR_REDACTED_RULE}
- Nếu chữ không rõ, để trống trường đó và ghi tên trường vào uncertain_fields.
- Chỉ trả về JSON, không thêm Markdown.

Dạng JSON:
{{
  "doc_type": "prescription",
  "facility": "",
  "doctor": "",
  "patient_name": "",
  "dob": "",
  "age": "",
  "gender": "",
  "diagnosis": "",
  "date": "",
  "medications": [
    {{
      "stt": 1,
      "name": "",
      "brand_name_as_printed": "",
      "ingredients_as_printed": "",
      "dose": "",
      "quantity_as_printed": "",
      "schedule_as_printed": "",
      "usage_as_printed": "",
      "purpose": "",
      "uncertain_fields": []
    }}
  ]
}}
"""
        contents.append(prompt)

        preferred_model = llm_provider.get_default_model("prescription_ocr")
        candidate_models = list(dict.fromkeys([preferred_model, "gemini-flash-latest"]))

        res = llm_provider.generate_json(
            contents=contents,
            candidate_models=candidate_models,
            system_instruction=PRESCRIPTION_OCR_SYSTEM_PROMPT,
            api_key=api_key,
            operation="prescription_ocr"
        )

        if not isinstance(res, dict):
            return None

        # Chuẩn hóa cấu trúc kết quả trả về để tương thích tuyệt đối với pipeline
        if "medications" in res and isinstance(res["medications"], list):
            normalized_meds = []
            for item in res["medications"]:
                if not isinstance(item, dict):
                    continue
                brand_name = str(item.get("brand_name_as_printed") or item.get("brand_name") or "").strip()
                active_ingredient = str(item.get("ingredients_as_printed") or item.get("active_ingredient") or "").strip()
                explicit_name = str(item.get("name") or "").strip()
                clean_ing = active_ingredient.strip("() ").strip()
                if explicit_name:
                    name = explicit_name
                elif brand_name and clean_ing and clean_ing.lower() not in brand_name.lower():
                    name = f"{brand_name} ({clean_ing})"
                else:
                    name = brand_name or active_ingredient
                if not name:
                    continue

                quantity = _normalize_vietnamese_units(
                    item.get("quantity_as_printed") or item.get("quantity") or item.get("days") or ""
                )
                schedule = _normalize_vietnamese_units(
                    item.get("schedule_as_printed") or item.get("schedule") or item.get("frequency") or ""
                )
                usage = _normalize_vietnamese_units(
                    item.get("usage_as_printed") or item.get("usage") or item.get("instructions") or ""
                )
                uncertain = item.get("uncertain_fields") or []
                needs_review = bool(item.get("needs_review") or uncertain)

                # Bóc tách strength từ brand_name hoặc ingredients nếu có
                strength = str(item.get("strength") or "").strip()
                if not strength:
                    m_str = re.search(
                        r"(\d+(?:\.\d+)?\s*(?:mg|mcg|ml|g|iu)(?:\s*\+\s*\d+(?:\.\d+)?\s*(?:mg|mcg|ml|g|iu))*|\(\d+.*?\)/\d+ml)",
                        brand_name, re.IGNORECASE
                    )
                    if m_str:
                        strength = m_str.group(1).strip()

                dose = _normalize_vietnamese_units(item.get("dose") or "")
                if not dose:
                    m_dose = re.search(
                        r"(\d+(?:\s*/\s*\d+|[.,]\d+)?\s*(?:viên|vien|gói|goi|ống|ong|lọ|lo|chai|tuýp|tuyp|hộp|hop|ml|giọt|giot))",
                        f"{usage} {schedule}",
                        re.IGNORECASE,
                    )
                    dose = _normalize_vietnamese_units(m_dose.group(1).strip()) if m_dose else "1"

                normalized_meds.append({
                    "stt": item.get("stt"),
                    "name": name,
                    "brand_name": brand_name,
                    "active_ingredient": active_ingredient,
                    "strength": strength,
                    "dose": dose,
                    "frequency": schedule,
                    "schedule": schedule,
                    "days": quantity,
                    "quantity": quantity,
                    "unit": "",
                    "usage": usage,
                    "instructions": usage,
                    "purpose": str(item.get("purpose") or "").strip(),
                    "needs_review": needs_review,
                    "uncertain_fields": uncertain
                })
            res["medications"] = normalized_meds

        for admin_key in ("patient_name", "dob", "age"):
            if admin_key in res:
                res[admin_key] = _sanitize_redacted_admin_field(res.get(admin_key))
        if "gender" in res:
            res["gender"] = _sanitize_redacted_admin_field(res.get("gender"), is_gender=True)

        return res

    except Exception as e:
        logger.warning("Gemini schema extraction failed (%s).", type(e).__name__)
        return None
    finally:
        if auto_crop and crop_image_path and os.path.exists(crop_image_path):
            try:
                os.remove(crop_image_path)
            except Exception:
                pass
