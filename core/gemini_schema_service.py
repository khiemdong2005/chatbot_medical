import os
import json
import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("GeminiSchemaService")


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
      - Đảm bảo thực thi trong DUY NHẤT 1 lần gọi Vision API qua OpenRouter/Gemini.
      - Nếu không có ảnh cắt, tự động fallback gửi ảnh toàn trang.
      - Chép trung thực từng hàng thuốc, tách riêng biệt dược, hoạt chất, số lượng, lịch dùng, cách dùng.
    """
    from core.llm_provider import llm_provider

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
                from core.prescription_crop_service import crop_and_upscale_medication_region
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
- Không thay tên biệt dược bằng tên hoạt chất.
- Không tự thêm số lượng, buổi uống hoặc cách dùng.
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
      "brand_name_as_printed": "",
      "ingredients_as_printed": "",
      "quantity_as_printed": "",
      "schedule_as_printed": "",
      "usage_as_printed": "",
      "uncertain_fields": []
    }}
  ]
}}
"""
        contents.append(prompt)

        preferred_model = llm_provider.get_default_model("prescription_ocr")
        candidate_models = list(dict.fromkeys([preferred_model, "inclusionai/ling-3.2-flash:free"]))

        res = llm_provider.generate_json(
            contents=contents,
            candidate_models=candidate_models,
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
                name = str(item.get("name") or brand_name or active_ingredient).strip()
                if not name:
                    continue

                quantity = str(item.get("quantity_as_printed") or item.get("quantity") or item.get("days") or "").strip()
                schedule = str(item.get("schedule_as_printed") or item.get("schedule") or item.get("frequency") or "").strip()
                usage = str(item.get("usage_as_printed") or item.get("usage") or item.get("instructions") or "").strip()
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

                dose = str(item.get("dose") or "").strip()
                if not dose:
                    m_dose = re.search(r"(\d+\s*(?:viên|vien|gói|goi|ống|ong|lọ|lo|chai|hộp|hop))", f"{usage} {schedule}", re.IGNORECASE)
                    dose = m_dose.group(1).strip() if m_dose else ""

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


def extract_with_gemini_text(raw_text: str, doc_type: str = "prescription", api_key: str = "") -> Optional[Dict[str, Any]]:
    """
    [2.B-TEXT] Bóc tách văn bản PDF thuần đã rút trích thành JSON chuẩn y khoa qua OpenRouter.
    Tránh gửi nhị phân application/pdf vào trường image_url không được hỗ trợ.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None
    from core.llm_provider import llm_provider

    if not api_key:
        api_key = llm_provider.resolve_api_key(profile="ocr")
    if not llm_provider.is_configured(profile="ocr", explicit_key=api_key):
        return None

    try:
        schema_hint = (
            '{"doc_type":"lab_test","patient_name":"","dob":"","age":"","gender":"","diagnosis":"","facility":"","doctor":"","date":"","metrics":[{"test_name":"","result":"","unit":"","reference_range":"","flag_on_paper":""}]}'
            if doc_type == "lab_test"
            else '{"doc_type":"prescription","patient_name":"","dob":"","age":"","gender":"","diagnosis":"","facility":"","doctor":"","date":"","medications":[{"name":"","strength":"","purpose":"","dose":"","frequency":"","days":"","usage":""}]}'
        )
        prompt = (
            "Bạn là Hệ thống AI Bóc tách Tài liệu Y tế Lâm sàng từ văn bản PDF đã trích xuất.\n"
            "Chỉ trích xuất thông tin thực sự có trong văn bản bên dưới; KHÔNG bịa đặt tên thuốc, hàm lượng, liều dùng hoặc chỉ số.\n"
            "Nếu trường nào không rõ hãy để chuỗi rỗng.\n\n"
            f"MẪU SCHEMA JSON BẮT BUỘC:\n{schema_hint}\n\n"
            f"VĂN BẢN TÀI LIỆU:\n{raw_text[:20000]}\n\n"
            "CHỈ TRẢ VỀ 1 ĐỐI TƯỢNG JSON HỢP LỆ."
        )
        preferred_model = llm_provider.get_default_model("chat")
        candidate_models = list(dict.fromkeys([preferred_model, "openrouter/free"]))
        return llm_provider.generate_json(
            contents=prompt,
            candidate_models=candidate_models,
            api_key=api_key,
            operation="prescription_ocr",
        )
    except Exception as e:
        logger.warning("Text schema extraction failed (%s).", type(e).__name__)
        return None
