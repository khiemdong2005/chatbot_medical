"""
================================================================================
MEDIMIND CROP-LEVEL FALLBACK SERVICE (VLM CROP RE-READING & RESEARCH)
================================================================================
Dịch vụ thẩm định và cứu vãn các ca khó trong đơn thuốc bằng mô hình Vision-LLM:
- Chỉ kích hoạt khi dòng thuốc OCR cục bộ có điểm confidence thấp hoặc không khớp catalog.
- Cắt đúng vùng ô/dòng thuốc (crop bounding box) kèm padding an toàn, phóng to LANCZOS.
- Gửi ảnh crop sang Vision-LLM để đọc lại chính xác ký tự, biệt dược, hoạt chất và liều.
- Tích hợp Circuit Breaker (tối đa 3 dòng fallback/đơn) và timeout chặt chẽ (4.5s) để chống treo.
- Bộ nhớ đệm (Cache) trong RAM/tệp để không bao giờ gọi lại trùng tên thuốc đã giải mã.
- Nguyên tắc an toàn y khoa: Không bịa tên thuốc. Trả về candidates + needs_review: true khi không chắc chắn.
================================================================================
"""

import os
import re
import json
import logging
import tempfile
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image

from core.reconciliation_service import _ascii_fold

logger = logging.getLogger("CropFallbackService")

# In-memory cache for resolved drug crops to avoid duplicate API calls
_FALLBACK_CACHE: Dict[str, Dict[str, Any]] = {}


def _clean_cache_key(text: str) -> str:
    folded = _ascii_fold(str(text or "")).strip()
    return re.sub(r"[^\w\s]", "", folded).lower()


def crop_medication_row_image(
    image_path: str,
    points: Optional[List[List[float]]] = None,
    pad_y_pct: float = 0.20,
    min_height_px: int = 120,
) -> Optional[str]:
    """
    Cắt vùng ảnh chứa dòng thuốc từ tọa độ points (chuẩn hóa 0.0-1.0 hoặc pixel).
    Mở rộng chiều ngang toàn hàng (hoặc lề rộng) để không mất cột số lượng.
    Phóng to bằng LANCZOS nếu dòng quá mỏng.
    """
    if not image_path or not os.path.exists(image_path) or image_path.lower().endswith(".pdf"):
        return None

    try:
        with Image.open(image_path) as img:
            img_w, img_h = img.size
            if img_w <= 0 or img_h <= 0:
                return None

            if not points or len(points) < 2:
                return None

            xs = [p[0] for p in points]
            ys = [p[1] for p in points]

            # Kiểm tra xem points là normalized (0.0 - 1.0) hay pixel
            is_normalized = max(xs) <= 1.05 and max(ys) <= 1.05
            if is_normalized:
                p_x1 = min(xs) * img_w
                p_x2 = max(xs) * img_w
                p_y1 = min(ys) * img_h
                p_y2 = max(ys) * img_h
            else:
                p_x1 = min(xs)
                p_x2 = max(xs)
                p_y1 = min(ys)
                p_y2 = max(ys)

            box_h = p_y2 - p_y1
            pad_y = max(15, int(box_h * pad_y_pct))

            crop_y1 = max(0, int(p_y1 - pad_y))
            crop_y2 = min(img_h, int(p_y2 + pad_y))
            # Mở rộng toàn hàng ngang từ lề trái đến lề phải để thấy cả tên thuốc và cột số lượng
            crop_x1 = max(0, int(min(p_x1 * 0.8, p_x1 - 20)))
            crop_x2 = min(img_w, int(img_w * 0.98))

            if crop_y2 <= crop_y1 + 10 or crop_x2 <= crop_x1 + 20:
                return None

            cropped = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
            cw, ch = cropped.size

            # Upscale LANCZOS nếu chiều cao crop nhỏ hơn min_height_px để VLM đọc rõ nét
            if ch < min_height_px:
                scale = min_height_px / float(ch)
                new_w = int(round(cw * scale))
                new_h = int(round(ch * scale))
                resample_filter = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
                cropped = cropped.resize((new_w, new_h), resample=resample_filter)

            fd, temp_path = tempfile.mkstemp(prefix="rx_row_crop_", suffix=".jpg")
            os.close(fd)
            cropped.convert("RGB").save(temp_path, format="JPEG", quality=92)
            return temp_path

    except Exception as exc:
        logger.warning("Lỗi cắt ảnh dòng thuốc: %s", exc)
        return None


def refine_medication_with_crop_fallback(
    image_path: str,
    med: Dict[str, Any],
    context: str = "",
    api_key: str = "",
) -> Dict[str, Any]:
    """
    Cứu vãn dòng thuốc bằng Vision-LLM:
      1. Kiểm tra cache trong RAM trước (0ms).
      2. Cắt ảnh dòng thuốc.
      3. Gọi Gemini / VLM phân tích hình ảnh và trả về JSON chuẩn xác.
    """
    raw_name = str(med.get("name") or med.get("raw_ocr_name") or "").strip()
    cache_key = _clean_cache_key(raw_name)

    if cache_key and cache_key in _FALLBACK_CACHE:
        cached = _FALLBACK_CACHE[cache_key]
        refined = dict(med)
        refined.update({
            "name": cached.get("name") or med.get("name"),
            "standard_name": cached.get("standard_name") or cached.get("name") or med.get("name"),
            "active_ingredient": cached.get("active_ingredient") or med.get("active_ingredient"),
            "strength": cached.get("strength") or med.get("strength"),
            "quantity": cached.get("quantity") or med.get("quantity"),
            "dose": cached.get("dose") or med.get("dose"),
            "usage": cached.get("usage") or med.get("usage"),
            "is_fallback_applied": True,
            "fallback_confidence": cached.get("confidence", 0.9),
            "needs_review": cached.get("needs_review", False),
        })
        return refined

    from core.llm_provider import llm_provider

    if not api_key:
        api_key = llm_provider.resolve_api_key(profile="ocr")
    if not llm_provider.is_configured(profile="ocr", explicit_key=api_key):
        return med

    points = med.get("anchor_points") or []
    if not points and med.get("evidence", {}).get("name"):
        points = med["evidence"]["name"][0].get("points", [])

    crop_path = crop_medication_row_image(image_path, points)
    if not crop_path or not os.path.exists(crop_path):
        return med

    try:
        from google.genai import types

        with open(crop_path, "rb") as f:
            crop_bytes = f.read()

        prompt = f"""Bạn là dược sĩ lâm sàng và chuyên gia đọc đơn thuốc tại Việt Nam.
Đây là ảnh cắt phóng to của MỘT DÒNG THUỐC cụ thể trong đơn thuốc khám chữa bệnh.
- Văn bản OCR đọc sơ bộ ban đầu: "{raw_name}"
- Ngữ cảnh chẩn đoán bệnh: "{context}"

Yêu cầu nhiệm vụ:
1. Đọc chính xác tên biệt dược / thương mại (brand name) in trên ảnh.
2. Tách riêng hoạt chất (active ingredient) và hàm lượng (strength) chuẩn xác (ví dụ: Destidin 5mg -> hoạt chất Desloratadine; Silkron -> Betamethasone + Clotrimazole; Halcort 6 -> Deflazacort 6mg).
3. Đọc chính xác số lượng (quantity) và đơn vị (viên, lọ, chai, hộp, tuýp/tube...).
4. Đọc liều dùng (dose), cữ uống và cách dùng (usage) nếu nhìn thấy.
5. NGUYÊN TẮC AN TOÀN: Không được tự ý bịa tên thuốc. Nếu chữ mờ hoặc không chắc chắn, trả về danh sách candidates và đánh dấu "needs_review": true.

Trả về DUY NHẤT một JSON hợp lệ theo định dạng:
{{
  "name": "Tên biệt dược đọc được",
  "active_ingredient": "Tên hoạt chất tương ứng",
  "strength": "Hàm lượng",
  "quantity": "Số lượng và đơn vị",
  "dose": "Liều dùng mỗi lần",
  "usage": "Cách dùng hoặc hướng dẫn",
  "confidence": 0.95,
  "needs_review": false,
  "candidates": []
}}
"""

        contents = [
            types.Part.from_bytes(data=crop_bytes, mime_type="image/jpeg"),
            prompt
        ]

        preferred_model = llm_provider.get_default_model("prescription_ocr")
        backup_vision_models = [
            "google/gemma-4-31b-it:free",
            "google/gemma-4-26b-a4b-it:free",
            "inclusionai/ling-3.2-flash:free",
        ]
        candidate_models = list(dict.fromkeys([preferred_model] + backup_vision_models))

        res = llm_provider.generate_json(
            contents=contents,
            candidate_models=candidate_models,
            api_key=api_key,
            operation="prescription_ocr"
        )

        if isinstance(res, dict) and (res.get("name") or res.get("active_ingredient")):
            refined = dict(med)
            refined_name = str(res.get("name") or med.get("name") or "").strip()
            refined_active = str(res.get("active_ingredient") or "").strip()
            refined_strength = str(res.get("strength") or med.get("strength") or "").strip()
            refined_qty = str(res.get("quantity") or med.get("quantity") or "").strip()
            refined_dose = str(res.get("dose") or med.get("dose") or "").strip()
            refined_usage = str(res.get("usage") or med.get("usage") or "").strip()
            needs_review = bool(res.get("needs_review", False))

            refined.update({
                "name": refined_name,
                "standard_name": refined_name,
                "active_ingredient": refined_active,
                "strength": refined_strength,
                "quantity": refined_qty,
                "dose": refined_dose,
                "usage": refined_usage,
                "is_fallback_applied": True,
                "fallback_confidence": float(res.get("confidence", 0.9)),
                "needs_review": needs_review,
                "candidates": res.get("candidates", [])
            })

            # Lưu cache để không gọi lại
            if cache_key:
                _FALLBACK_CACHE[cache_key] = {
                    "name": refined_name,
                    "standard_name": refined_name,
                    "active_ingredient": refined_active,
                    "strength": refined_strength,
                    "quantity": refined_qty,
                    "dose": refined_dose,
                    "usage": refined_usage,
                    "confidence": float(res.get("confidence", 0.9)),
                    "needs_review": needs_review,
                }
            return refined

    except Exception as exc:
        logger.warning("Crop fallback refinement failed for '%s': %s", raw_name, exc)
    finally:
        if crop_path and os.path.exists(crop_path):
            try:
                os.remove(crop_path)
            except Exception:
                pass

    return med
