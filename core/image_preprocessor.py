import os
import sys
import cv2
import numpy as np
from typing import Dict, Any, Tuple

# Ensure UTF-8 output on console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def preprocess_prescription_image(image_path: str, save_debug: bool = True) -> Dict[str, Any]:
    """
    Tiền xử lý ảnh tài liệu y khoa (Đơn thuốc / Phiếu xét nghiệm) bằng OpenCV:
      1. Chuyển đổi ảnh Grayscale
      2. Tăng cường độ tương phản cục bộ bằng CLAHE (Contrast Limited Adaptive Histogram Equalization)
      3. Khử nhiễu bảo toàn biên cạnh bằng Bilateral Filter (tốc độ siêu nhanh ~5ms)
      4. Căn chỉnh góc nghiêng tự động (Deskewing) dựa trên góc xoay văn bản
      5. Lưu bản xem trước tiền xử lý phục vụ nghiên cứu & báo cáo đồ án
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Không tìm thấy tệp ảnh tại: {image_path}")

    # Đọc ảnh tiếng Việt / Unicode an toàn bằng numpy
    try:
        with open(image_path, "rb") as f:
            chunk = f.read()
        image_array = np.frombuffer(chunk, dtype=np.uint8)
        img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    except Exception:
        img = cv2.imread(image_path)

    if img is None:
        raise ValueError(f"Không thể đọc định dạng ảnh từ: {image_path}")

    orig_h, orig_w = img.shape[:2]

    # 1. Giới hạn độ phân giải hợp lý (max 1400px) để OCR chạy siêu nhanh và chính xác
    max_dim = 1400
    scale = 1.0
    if max(orig_h, orig_w) > max_dim:
        scale = max_dim / float(max(orig_h, orig_w))
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # 2. Chuyển sang ảnh xám (Grayscale)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 3. Tăng tương phản bằng CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 4. Khử nhiễu nhanh bảo toàn viền chữ bằng Bilateral Filter
    denoised = cv2.bilateralFilter(enhanced, d=5, sigmaColor=40, sigmaSpace=40)

    # 5. Phát hiện góc nghiêng (Deskew)
    deskew_angle = 0.0
    try:
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) > 50:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            elif angle > 45:
                angle = 90 - angle
            else:
                angle = -angle

            # Chỉ xoay nếu góc nghiêng vừa phải (từ 0.8 đến 15 độ)
            if 0.8 < abs(angle) < 15.0:
                deskew_angle = round(float(angle), 2)
                h, w = denoised.shape
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, deskew_angle, 1.0)
                denoised = cv2.warpAffine(denoised, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    except Exception as deskew_err:
        pass

    # 6. Lưu ảnh tiền xử lý
    output_dir = os.path.dirname(image_path)
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    processed_filename = f"preprocessed_{base_name}.jpg"
    processed_path = os.path.join(output_dir, processed_filename)

    if save_debug:
        try:
            is_success, buffer = cv2.imencode(".jpg", denoised)
            if is_success:
                with open(processed_path, "wb") as f:
                    f.write(buffer)
        except Exception:
            processed_path = image_path

    return {
        "status": "success",
        "original_dimensions": {"width": orig_w, "height": orig_h},
        "processed_dimensions": {"width": denoised.shape[1], "height": denoised.shape[0]},
        "scale_applied": round(scale, 3),
        "skew_angle": deskew_angle,
        "clahe_applied": True,
        "denoised": True,
        "processed_image_path": processed_path if os.path.exists(processed_path) else image_path
    }
