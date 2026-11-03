import os
import re
import cv2
import numpy as np
from typing import Dict, Any, Tuple, Optional

def check_image_quality(image_path: str) -> Dict[str, Any]:
    """
    [0] Intake: Kiểm tra chất lượng ảnh (mờ, tối, lóa sáng).
    - Độ sắc nét (Blur): Variance of Laplacian.
    - Độ sáng trung bình (Brightness): Mean pixel intensity.
    - Tỉ lệ lóa sáng (Glare): Tỉ lệ pixel > 250.
    """
    if not os.path.exists(image_path):
        return {"passed": False, "reason": "Tệp ảnh không tồn tại."}

    # Đọc ảnh an toàn với đường dẫn tiếng Việt / Unicode
    try:
        with open(image_path, "rb") as f:
            chunk = f.read()
        img_arr = np.frombuffer(chunk, dtype=np.uint8)
        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
    except Exception:
        img = cv2.imread(image_path)

    if img is None:
        return {"passed": False, "reason": "Không thể giải mã dữ liệu ảnh."}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. Đo độ sắc nét (Laplacian Variance)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    is_blur = laplacian_var < 45.0  # Ngưỡng mờ

    # 2. Đo độ sáng trung bình (0-255)
    mean_brightness = float(np.mean(gray))
    is_too_dark = mean_brightness < 40.0
    is_dark = mean_brightness < 90.0  # Cần CLAHE

    # 3. Đo tỉ lệ lóa sáng (Glare)
    glare_ratio = float(np.sum(gray > 250)) / float(gray.size)
    is_glare = glare_ratio > 0.15

    passed = True
    issues = []
    recommendation = "Ảnh đạt chuẩn phân tích."

    if is_blur:
        passed = False
        issues.append("Ảnh bị rung lắc hoặc mờ nét chữ.")
        recommendation = "Vui lòng giữ chắc tay, lấy nét lại và chụp lại ảnh rõ hơn."
    elif is_too_dark:
        passed = False
        issues.append("Ảnh quá tối, thiếu sáng nghiêm trọng.")
        recommendation = "Vui lòng bật đèn hoặc chụp ở nơi có ánh sáng tốt hơn."
    elif is_glare:
        passed = False
        issues.append("Ảnh bị lóa đèn flash hoặc phản quang trắng.")
        recommendation = "Vui lòng tắt đèn flash hoặc nghiêng góc chụp để tránh chói sáng."

    return {
        "passed": passed,
        "sharpness_score": round(float(laplacian_var), 1),
        "brightness": round(mean_brightness, 1),
        "glare_ratio": round(glare_ratio, 3),
        "need_clahe": is_dark,
        "issues": issues,
        "recommendation": recommendation
    }

def mask_pii_on_image(image_path: str, bboxes_to_mask: list) -> str:
    """
    (Tùy chọn) Che thông tin định danh (PII: tên, ngày sinh, địa chỉ)
    trước khi gửi ảnh ra API bên ngoài.
    """
    try:
        with open(image_path, "rb") as f:
            chunk = f.read()
        img_arr = np.frombuffer(chunk, dtype=np.uint8)
        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        if img is None:
            return image_path
            
        for box in bboxes_to_mask:
            if len(box) == 4 and isinstance(box[0], (int, float)):
                # box dạng [x1, y1, x2, y2]
                x1, y1, x2, y2 = map(int, box)
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 0), -1)
            elif len(box) >= 4 and isinstance(box[0], (list, tuple)):
                # polygon box [[x1, y1], [x2, y2], ...]
                pts = np.array(box, dtype=np.int32)
                cv2.fillPoly(img, [pts], (0, 0, 0))

        out_path = os.path.splitext(image_path)[0] + "_masked.jpg"
        is_success, buffer = cv2.imencode(".jpg", img)
        if is_success:
            with open(out_path, "wb") as f:
                f.write(buffer)
            return out_path
    except Exception as e:
        print(f"[PII MASK ERROR] {e}")
    return image_path

