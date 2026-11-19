"""
core/prescription_crop_service.py
Dịch vụ phát hiện vùng bảng thuốc và phóng to bằng PIL LANCZOS (Dual-Image Extraction).
Hỗ trợ đa dạng bố cục và kích thước ảnh đơn thuốc (dọc, ngang, nhiều cột, bảng ở đầu/giữa/cuối trang).
Khi không xác định được vùng thuốc tin cậy, trả về None để pipeline tự động fallback về ảnh toàn trang.
"""

import os
import re
import logging
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image

from core.reconciliation_service import _prescription_body_bounds, _ascii_fold

logger = logging.getLogger("PrescriptionCropService")


def detect_medication_bounds(
    lines: List[Dict[str, Any]],
    rows: List[Dict[str, Any]],
    img_w: int,
    img_h: int
) -> Optional[Tuple[int, int, int, int]]:
    """
    Xác định tọa độ vùng danh sách thuốc (x1, y1, x2, y2) trên ảnh dựa vào OCR bounding boxes.
    Không dùng tọa độ cố định, thích ứng với mọi kích thước và hướng ảnh.
    
    Quy tắc an toàn:
      1. Ưu tiên phân tích cấu trúc theo hàng (rows) qua _prescription_body_bounds.
      2. Nếu rows không tìm thấy, quét theo dòng (lines) qua từ khóa tiêu đề, chỉ định, số thứ tự và lời dặn/chữ ký.
      3. Thêm lề an toàn (padding 2% chiều cao ảnh) để không cắt mất nét chữ hoặc dấu tiếng Việt.
      4. Kiểm tra tính hợp lệ: vùng cắt phải chiếm từ 8% đến 95% chiều cao ảnh.
      5. Chiều ngang mở rộng toàn trang (0 -> img_w) để không bao giờ cắt mất cột số lượng bên phải hoặc STT bên trái.
    """
    if img_w <= 0 or img_h <= 0:
        return None

    y_min: Optional[int] = None
    y_max: Optional[int] = None

    # Chiến lược 1: Dùng rows và _prescription_body_bounds
    if rows:
        try:
            start_idx, end_idx = _prescription_body_bounds(rows)
            if start_idx is not None and start_idx < end_idx and start_idx < len(rows):
                body = rows[start_idx:end_idx]
                if body:
                    y_min = min(int(r.get("y_min", 0)) for r in body)
                    y_max = max(int(r.get("y_max", 0)) for r in body)
        except Exception as e:
            logger.debug("Row-based bounds detection failed: %s", e)

    # Chiến lược 2: Quét lines theo từ khóa mở đầu và kết thúc
    if (y_min is None or y_max is None or y_max <= y_min + 30) and lines:
        header_patterns = re.compile(
            r"\b(?:tên\s*thuốc|ten\s*thuoc|hoạt\s*chất|hoat\s*chat|hàm\s*lượng|ham\s*luong|"
            r"biệt\s*dược|biet\s*duoc|thuốc\s*điều\s*trị|thuoc\s*dieu\s*tri|chỉ\s*định\s*dùng\s*thuốc|"
            r"chỉ\s*định\s*thuốc|danh\s*mục\s*thuốc|don\s*thuoc|toa\s*thuoc|rx|r\/x|stt)\b",
            re.IGNORECASE
        )
        med_row_patterns = re.compile(
            r"^\s*[1-9]\d*[\.\)\/\-]\s*\S|"
            r"\b(?:\d+\s*(?:mg|mcg|ml|g|iu)\b|uống|sáng\b|chiều\b|viên\b|gói\b|ống\b|lọ\b|chai\b)",
            re.IGNORECASE
        )
        footer_patterns = re.compile(
            r"\b(?:cộng\s*khoản|cong\s*khoan|tổng\s*số\s*khoản|tong\s*so\s*khoan|"
            r"lời\s*dặn|loi\s*dan|dặn\s*dò|dan\s*do|hẹn\s*khám|hen\s*kham|tái\s*khám|tai\s*kham|"
            r"khám\s*lại|kham\s*lai|bác\s*sĩ|bac\s*si|bác\s*sỹ|bac\s*sy|chữ\s*ký|chu\s*ky|"
            r"người\s*kê\s*đơn|nguoi\s*ke\s*don|người\s*khám|nguoi\s*kham)\b",
            re.IGNORECASE
        )

        detected_starts = []
        detected_ends = []
        med_lines_y = []

        for line in lines:
            txt = str(line.get("text", "")).strip()
            ly_min = int(line.get("y_min", 0))
            ly_max = int(line.get("y_max", 0))

            if header_patterns.search(txt) and ly_min >= 0.08 * img_h:
                detected_starts.append(ly_min)
            elif med_row_patterns.search(txt) and ly_min >= 0.10 * img_h:
                med_lines_y.append((ly_min, ly_max))

            if footer_patterns.search(txt) and ly_min >= 0.25 * img_h:
                detected_ends.append(ly_min)

        if detected_starts:
            y_min = min(detected_starts)
        elif med_lines_y:
            y_min = min(item[0] for item in med_lines_y)

        if y_min is not None:
            # Chọn footer xuất hiện sau y_min
            valid_ends = [ey for ey in detected_ends if ey > y_min + 30]
            if valid_ends:
                y_max = min(valid_ends)
            elif med_lines_y:
                valid_meds_max = [item[1] for item in med_lines_y if item[1] > y_min]
                if valid_meds_max:
                    y_max = max(valid_meds_max)

    # Kiểm tra tính hợp lệ
    if y_min is None or y_max is None or y_max <= y_min + 40:
        return None

    # Thêm padding dọc an toàn (2% chiều cao ảnh)
    pad_y = int(0.02 * img_h)
    crop_y1 = max(0, y_min - pad_y)
    crop_y2 = min(img_h, y_max + pad_y)

    crop_h = crop_y2 - crop_y1
    # Vùng cắt phải chiếm tối thiểu 8% và không vượt quá 95% chiều cao ảnh
    if crop_h < int(0.08 * img_h) or crop_h > int(0.95 * img_h):
        return None

    crop_x1 = 0
    crop_x2 = img_w

    return crop_x1, crop_y1, crop_x2, crop_y2


def crop_and_upscale_medication_region(
    image_path: str,
    ocr_result: Dict[str, Any]
) -> Optional[str]:
    """
    Tạo ảnh cắt vùng danh sách thuốc và phóng to bằng PIL LANCZOS.
    Nếu không xác định được vùng thuốc tin cậy, trả về None để dùng ảnh toàn trang.
    """
    if not image_path or not os.path.exists(image_path):
        return None

    if image_path.lower().endswith(".pdf"):
        return None

    try:
        with Image.open(image_path) as img:
            img_w, img_h = img.size
            if img_w <= 0 or img_h <= 0:
                return None

            lines = ocr_result.get("lines", []) if isinstance(ocr_result, dict) else []
            rows = ocr_result.get("rows", []) if isinstance(ocr_result, dict) else []

            bounds = detect_medication_bounds(lines, rows, img_w, img_h)
            if not bounds:
                return None

            x1, y1, x2, y2 = bounds
            cropped = img.crop((x1, y1, x2, y2))
            crop_w, crop_h = cropped.size
            if crop_w <= 0 or crop_h <= 0:
                return None

            # Phóng to bằng LANCZOS (scale 3.0x như Colab, tối đa 3200px để chữ nhỏ sắc nét)
            scale = 3.0
            max_target_dim = 3200
            if max(crop_w * scale, crop_h * scale) > max_target_dim:
                scale = max(1.0, max_target_dim / float(max(crop_w, crop_h)))

            resample_filter = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
            if scale > 1.05:
                new_w = int(round(crop_w * scale))
                new_h = int(round(crop_h * scale))
                upscaled = cropped.resize((new_w, new_h), resample=resample_filter)
            else:
                upscaled = cropped

            base_dir = os.path.dirname(image_path) or "."
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            crop_path = os.path.join(base_dir, f"{base_name}_med_crop.jpg")
            upscaled.convert("RGB").save(crop_path, format="JPEG", quality=92)
            return crop_path

    except Exception as e:
        logger.warning("crop_and_upscale_medication_region encountered an error: %s", e)
        return None
