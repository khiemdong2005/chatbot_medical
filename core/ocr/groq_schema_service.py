import os
import json
import re
import logging
import base64
from typing import Dict, Any, Optional

logger = logging.getLogger("GroqSchemaService")


def _get_image_mime_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".png":
        return "image/png"
    elif ext == ".pdf":
        return "application/pdf"
    elif ext == ".webp":
        return "image/webp"
    return "image/jpeg"


def _encode_image_for_vision(file_path: str, max_dim: int = 1600) -> tuple:
    """Resize oversized preprocessed/cropped images before sending to Vision API."""
    mime_type = _get_image_mime_type(file_path)
    if mime_type == "application/pdf":
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii"), mime_type
    try:
        import io
        from PIL import Image

        with Image.open(file_path) as img:
            w, h = img.size
            if max(w, h) > max_dim or img.mode not in ("RGB", "L"):
                if img.mode != "RGB":
                    img = img.convert("RGB")
                if max(w, h) > max_dim:
                    scale = max_dim / float(max(w, h))
                    new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=88, optimize=True)
                return base64.b64encode(buf.getvalue()).decode("ascii"), "image/jpeg"
    except Exception as exc:
        logger.debug("Vision resize skipped for %s: %s", file_path, exc)

    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii"), mime_type


def extract_with_groq_schema(
    image_path: str,
    doc_type: str = "prescription",
    api_key: str = "",
    crop_image_path: Optional[str] = None,
    ocr_result: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Optional[Dict[str, Any]]:
    """
    Đọc ảnh đơn thuốc hoặc phiếu xét nghiệm -> JSON theo schema qua Unified LLM Provider:
      - Hỗ trợ cơ chế kép (Dual-image): Ảnh 1 toàn trang (bố cục/hành chính) + Ảnh 2 cắt phóng to LANCZOS (đọc chi tiết thuốc).
      - Gửi ảnh tới Groq Vision qua API tương thích OpenAI.
      - Hỗ trợ cả đơn thuốc (prescription) và phiếu kết quả xét nghiệm (lab_test).
      - Chép trung thực từng hàng thuốc / chỉ số xét nghiệm, tuyệt đối không bịa thêm dữ liệu.
    """
    from core.ai.llm_provider import llm_provider

    if not api_key:
        api_key = llm_provider.resolve_api_key(profile="ocr")
    if not llm_provider.is_configured(profile="ocr", explicit_key=api_key):
        return None

    auto_crop = False
    try:
        b64_main, mime_type = _encode_image_for_vision(image_path, max_dim=1600)

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
        contents = [{
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{b64_main}"},
        }]

        # 2. Chuẩn bị ảnh cắt phóng to danh sách thuốc (Image 2) nếu có
        has_crop = False
        if doc_type != "lab_test" and crop_image_path and os.path.exists(crop_image_path) and crop_image_path != image_path:
            try:
                b64_crop, crop_mime = _encode_image_for_vision(crop_image_path, max_dim=1600)
                contents.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{crop_mime};base64,{b64_crop}"},
                })
                has_crop = True
            except Exception as ce:
                logger.warning("Could not load cropped medication image: %s", ce)

        if doc_type == "lab_test":
            prompt = """
BẠN ĐANG NHẬN ĐƯỢC ẢNH PHIẾU KẾT QUẢ XÉT NGHIỆM Y TẾ.
Hãy chép trung thực thông tin hành chính và từng dòng chỉ số trong bảng kết quả xét nghiệm theo đúng thứ tự trên ảnh.

Quy tắc:
- Chỉ ghi đúng chữ và số nhìn thấy trên ảnh; tuyệt đối không đoán hay tự bịa chỉ số.
- Không đưa thông tin hành chính (họ tên, địa chỉ, thời gian nhận mẫu, người duyệt, tiêu đề cột) vào mảng metrics.
- Giữ nguyên ký hiệu so sánh (<, >, <=, >=) trong result và reference_range nếu có.
- Nếu giá trị in đậm hoặc có ký hiệu H/L/Cao/Thấp cho thấy ngoài khoảng tham chiếu, ghi vào flag_on_paper; ngược lại để trống.
- Nếu chữ bị che mờ hoặc cắt mất, để trống trường đó.
- Chỉ trả về JSON hợp lệ, không thêm Markdown.

Dạng JSON:
{
  "doc_type": "lab_test",
  "facility": "",
  "doctor": "",
  "patient_name": "",
  "dob": "",
  "age": "",
  "gender": "",
  "diagnosis": "",
  "date": "",
  "metrics": [
    {
      "test_name": "",
      "result": "",
      "unit": "",
      "reference_range": "",
      "flag_on_paper": ""
    }
  ]
}
"""
        else:
            if has_crop:
                doc_intro = """BẠN ĐANG NHẬN ĐƯỢC 2 ẢNH CỦA CÙNG MỘT ĐƠN THUỐC (CÙNG MỘT TÀI LIỆU):
- Ảnh 1: Toàn bộ trang đơn thuốc để xác định bố cục và thông tin hành chính.
- Ảnh 2: Ảnh cắt phóng to chi tiết vùng bảng thuốc để đọc chữ rõ nét."""
            else:
                doc_intro = """BẠN ĐANG NHẬN ĐƯỢC 1 ẢNH TOÀN BỘ TRANG ĐƠN THUỐC để xác định bố cục và đọc chữ."""

            prompt = f"""
{doc_intro}

Hãy chép ĐẦY ĐỦ từng hàng thuốc theo đúng thứ tự trên ảnh (bao gồm thuốc uống, thuốc bôi/dùng ngoài, thuốc y học cổ truyền, vật tư y tế được đánh số trong bảng thuốc).

Quy tắc:
- Chỉ ghi chữ nhìn thấy trên ảnh; tuyệt đối không đoán dựa vào kiến thức y khoa.
- Không đưa dòng "Chẩn đoán" hay "Bệnh kèm theo" vào mảng medications.
- Đọc cả dòng hướng dẫn ngay dưới tên từng thuốc; không bỏ qua dòng bắt đầu bằng "Ngày uống", "Uống", "Sáng/Trưa/Chiều/Tối", "Bôi", "Xoa", "Rửa", "Lau", "Chấm", "Tắm".
- Ghi nguyên văn liều mỗi lần (ví dụ "1 viên", "1/2 viên", "1/3 chai", "2 gói", "3 viên") vào dose_as_printed; nếu không ghi liều mỗi lần (ví dụ thuốc bôi hoặc phiếu phát thuốc không có cách dùng) thì để trống "".
- Ghi nguyên văn tần suất và thời điểm dùng (ví dụ "Sáng 1 viên, Chiều 1 viên", "Ngày uống 3 lần", "Bôi sáng và trưa") vào schedule_as_printed.
- Ghi cách dùng ("trước ăn", "sau ăn", "bôi mỏng", "dùng ngoài da", v.v.) vào usage_as_printed; ghi đường dùng ("Đường uống", "Dùng ngoài da", "Tiêm", v.v.) vào route_as_printed nếu rõ.
- Ghi đúng tổng số lượng cấp ở cột Số lượng/ĐVT (ví dụ "30 Viên", "20 Viên", "1 Tuýp", "3 Lọ", "60 Cái", "1 Hộp") vào quantity_as_printed; KHÔNG nhầm số lượng tổng với liều mỗi lần.
- Tách tên biệt dược / tên chính và hoạt chất trong ngoặc nếu có; không thay tên biệt dược bằng hoạt chất.
- Nếu phần thông tin bệnh nhân bị che mờ (pixelated/blurred), để trống "".
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
      "strength_as_printed": "",
      "quantity_as_printed": "",
      "dose_as_printed": "",
      "schedule_as_printed": "",
      "usage_as_printed": "",
      "route_as_printed": "",
      "uncertain_fields": []
    }}
  ]
}}
"""
        contents.append(prompt)

        preferred_model = llm_provider.get_default_model("prescription_ocr")
        candidate_models = [preferred_model]

        res = llm_provider.generate_json(
            contents=contents,
            candidate_models=candidate_models,
            api_key=None if llm_provider.is_groq_active() else api_key,
            operation="prescription_ocr"
        )

        if not isinstance(res, dict):
            return None

        # Chuẩn hóa cấu trúc kết quả xét nghiệm
        if "metrics" in res and isinstance(res["metrics"], list):
            normalized_metrics = []
            for item in res["metrics"]:
                if not isinstance(item, dict):
                    continue
                t_name = str(item.get("test_name") or item.get("name") or "").strip()
                t_res = str(item.get("result") or item.get("value") or "").strip()
                if not t_name or not t_res:
                    continue
                normalized_metrics.append({
                    "test_name": t_name,
                    "result": t_res,
                    "unit": str(item.get("unit") or "").strip(),
                    "reference_range": str(item.get("reference_range") or "").strip(),
                    "flag_on_paper": str(item.get("flag_on_paper") or "").strip(),
                })
            res["metrics"] = normalized_metrics

        # Chuẩn hóa cấu trúc kết quả thuốc để tương thích tuyệt đối với pipeline
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
                route = str(item.get("route_as_printed") or item.get("route") or "").strip()
                uncertain = item.get("uncertain_fields") or []
                needs_review = bool(item.get("needs_review") or uncertain)

                # Bóc tách strength từ strength_as_printed, brand_name hoặc ingredients nếu có
                strength = str(item.get("strength_as_printed") or item.get("strength") or "").strip()
                if not strength:
                    for src_s in (brand_name, active_ingredient):
                        m_str = re.search(
                            r"(\d+(?:[.,]\d+)?\s*(?:mg|mcg|ml|g|iu|ui|%)(?:\s*(?:\+|\/|x)\s*\d+(?:[.,]\d+)?\s*(?:mg|mcg|ml|g|iu|ui|%))*|\(\d+.*?\)/\d+ml)",
                            src_s, re.IGNORECASE
                        )
                        if m_str:
                            strength = m_str.group(1).strip()
                            break

                dose = str(item.get("dose_as_printed") or item.get("dose") or "").strip()
                if not dose:
                    m_dose = re.search(
                        r"(\d+(?:[\/.,]\d+)?\s*(?:viên|vien|v\b|gói|goi|ống|ong|lọ|lo|chai|hộp|hop|ml|giọt|giot|nhát|nhat))",
                        f"{schedule} {usage}", re.IGNORECASE
                    )
                    dose = m_dose.group(1).strip() if m_dose else ""

                unit = str(item.get("unit") or "").strip()
                if not unit and quantity:
                    m_u = re.search(r"(viên|vien|gói|goi|ống|ong|lọ|lo|chai|hộp|hop|tuýp|tuyp|tube|cái|cai|vỉ|vi)\b", quantity, re.IGNORECASE)
                    if m_u:
                        unit = m_u.group(1).strip()

                if not route:
                    comb_usage = f"{usage} {schedule}".lower()
                    comb_all = f"{comb_usage} {name}".lower()
                    if any(k in comb_usage for k in ("uống", "ngậm")):
                        route = "Đường uống"
                    elif any(k in comb_all for k in ("bôi", "xoa", "thoa", "rửa mặt", "lau", "tắm", "gội", "chấm", "ngoài da", "cream", "tuýp", "tube", "gel")):
                        route = "Dùng ngoài da"

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
                    "unit": unit,
                    "usage": usage,
                    "instructions": usage,
                    "route": route,
                    "purpose": str(item.get("purpose") or "").strip(),
                    "needs_review": needs_review,
                    "uncertain_fields": uncertain
                })
            res["medications"] = normalized_meds

        return res

    except Exception as e:
        logger.warning("Groq schema extraction failed (%s).", type(e).__name__)
        return None
    finally:
        if auto_crop and crop_image_path and os.path.exists(crop_image_path):
            try:
                os.remove(crop_image_path)
            except Exception:
                pass
