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


def _parse_course(quantity: str):
    """'x 10 ngày = 20 Viên' -> (10, 20.0, 'Viên'); '63 Viên' -> (None, 63.0, 'Viên')."""
    text = str(quantity or "")
    days = None
    m_days = re.search(r"(\d+)\s*ngày", text, re.IGNORECASE)
    if m_days:
        days = int(m_days.group(1))
    m_total = re.search(r"(?:=|^|\s)(\d+(?:[.,]\d+)?)\s*([A-Za-zÀ-ỹ]+)\s*$", text.strip())
    if not m_total:
        return days, None, ""
    unit = m_total.group(2)
    if unit.lower() in ("ngày", "ngay"):
        return days, None, ""
    return days, float(m_total.group(1).replace(",", ".")), unit


_SLOT_RE = re.compile(r"(sáng|sang|trưa|trua|chiều|chieu|tối|toi)\s*[:\-]?\s*(\d+(?:[.,/]\d+)?)", re.IGNORECASE)


def _to_number(token: str) -> Optional[float]:
    token = str(token or "").replace(",", ".")
    try:
        if "/" in token:
            num, den = token.split("/", 1)
            return float(num) / float(den)
        return float(token)
    except (ValueError, ZeroDivisionError):
        return None


def _daily_amount(schedule: str, dose: str) -> Optional[float]:
    """Số đơn vị dùng mỗi ngày đọc được từ cữ/lịch uống (None nếu không xác định được)."""
    slots = _SLOT_RE.findall(schedule or "")
    if slots:
        values = [_to_number(v) for _, v in slots]
        return sum(v for v in values if v) if all(v is not None for v in values) else None
    m_times = re.search(r"(\d+)\s*lần", schedule or "", re.IGNORECASE)
    m_each = re.search(r"mỗi\s*lần\s*(\d+(?:[.,/]\d+)?)", f"{schedule} {dose}", re.IGNORECASE)
    if m_times:
        each = _to_number(m_each.group(1)) if m_each else _to_number((re.match(r"\s*(\d+(?:[.,/]\d+)?)", dose or "") or [None, None])[1])
        if each:
            return int(m_times.group(1)) * each
    return None


def _check_schedule_against_quantity(med: Dict[str, Any]) -> None:
    """Đánh dấu cần xem lại khi lịch uống đọc được không khớp số lượng cấp (không tự sửa/đoán)."""
    days, total, unit = _parse_course(med.get("quantity"))
    schedule = str(med.get("schedule") or "")
    dose = str(med.get("dose") or "")
    # Model sometimes copies the slot string ("Sáng: 1") into dose: keep only the per-intake amount
    if _SLOT_RE.search(dose):
        first = _SLOT_RE.search(dose).group(2)
        med["dose"] = f"{first} {unit}".strip()
        dose = med["dose"]
    if days:
        med["course_days"] = days
    if not days or not total:
        return
    daily = _daily_amount(schedule, dose)
    if not daily:
        return
    expected = daily * days
    if abs(expected - total) > 0.01:
        med["schedule_mismatch"] = True
        med["needs_review"] = True
        uncertain = list(med.get("uncertain_fields") or [])
        if "schedule_as_printed" not in uncertain:
            uncertain.append("schedule_as_printed")
        med["uncertain_fields"] = uncertain
        fmt = lambda v: (str(int(v)) if float(v).is_integer() else str(round(v, 2)))  # noqa: E731
        med["schedule_check"] = (
            f"Lịch đọc được {fmt(daily)} {unit}/ngày × {days} ngày = {fmt(expected)} {unit}, "
            f"nhưng đơn cấp {fmt(total)} {unit}. Hãy đối chiếu lại cữ uống trên ảnh gốc."
        )


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
- Nếu đơn ghi cữ dạng "Sáng: 1 Trưa: 0 Chiều: 1 Tối: 0" hoặc có các cột Sáng/Trưa/Chiều/Tối, phải ghi ĐỦ MỌI cữ có số lớn hơn 0 (ví dụ "Sáng: 1, Chiều: 1"), không dừng ở cữ đầu tiên.
- Tự kiểm tra từng hàng: tổng số lượng cấp phải bằng (tổng liều 1 ngày) × (số ngày). Ví dụ "x 10 ngày = 20 Viên" nghĩa là 2 viên/ngày, nên phải có 2 cữ 1 viên hoặc 1 cữ 2 viên. Nếu chưa khớp, hãy đọc lại hàng đó trên ảnh; nếu vẫn không chắc thì giữ đúng chữ nhìn thấy và thêm "schedule_as_printed" vào uncertain_fields.
- dose_as_printed chỉ ghi liều MỖI LẦN (ví dụ "1 Viên"), không chép cả chuỗi cữ "Sáng: 1" vào dose_as_printed.
- Ghi số ngày dùng nếu có (ví dụ "x 10 ngày" -> "10 ngày") vào days_as_printed.
- Ghi riêng số lượng mỗi cữ vào morning (Sáng), noon (Trưa), afternoon (Chiều), evening (Tối); để "" nếu cữ đó trống hoặc ghi 0. Nhìn kỹ cả 4 cữ trên cùng dòng, vì các cữ sau thường nằm xa bên phải.
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
      "days_as_printed": "",
      "dose_as_printed": "",
      "schedule_as_printed": "",
      "morning": "",
      "noon": "",
      "afternoon": "",
      "evening": "",
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
                days_printed = str(item.get("days_as_printed") or "").strip()
                if days_printed and "ngày" not in quantity.lower() and re.search(r"\d", days_printed):
                    days_txt = days_printed if "ngày" in days_printed.lower() else f"{days_printed} ngày"
                    quantity = f"x {days_txt} = {quantity}" if quantity else days_txt
                schedule = str(item.get("schedule_as_printed") or item.get("schedule") or item.get("frequency") or "").strip()
                slot_labels = (("morning", "Sáng"), ("noon", "Trưa"), ("afternoon", "Chiều"), ("evening", "Tối"))
                slot_parts = []
                for key, label in slot_labels:
                    raw_slot = str(item.get(key) or "").strip()
                    if re.fullmatch(r"\d+(?:[.,/]\d+)?(?:\s*[A-Za-zÀ-ỹ]+)?", raw_slot) and _to_number(re.match(r"[\d.,/]+", raw_slot).group(0)):
                        slot_parts.append(f"{label}: {raw_slot}")
                if slot_parts and len(slot_parts) > len(_SLOT_RE.findall(schedule)):
                    schedule = ", ".join(slot_parts)
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
                _check_schedule_against_quantity(normalized_meds[-1])
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
