import os
import cv2
import numpy as np
from typing import Dict, Any

def preprocess_lightweight(image_path: str, need_clahe: bool = False) -> Dict[str, Any]:
    """
    [1] Tiền xử lý nhẹ (giữ cả ảnh gốc):
      - Giữ nguyên ảnh màu gốc RGB (không áp Bilateral / Grayscale mặc định).
      - Resize an toàn (max 1800px) đảm bảo tỷ lệ khung hình.
      - Tự động phát hiện viền tài liệu & căn chỉnh phối cảnh (Perspective Transform) nếu phát hiện contour 4 góc rõ ràng.
      - Tự động xoay thẳng (Deskewing).
      - Chỉ áp dụng CLAHE trên kênh Luminance (LAB/YUV) nếu ảnh bị tối (need_clahe=True).
    """
    if not os.path.exists(image_path):
        return {"processed_path": image_path, "deskew_angle": 0.0, "perspective_corrected": False}

    try:
        with open(image_path, "rb") as f:
            chunk = f.read()
        img_arr = np.frombuffer(chunk, dtype=np.uint8)
        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
    except Exception:
        img = cv2.imread(image_path)

    if img is None:
        return {"processed_path": image_path, "deskew_angle": 0.0, "perspective_corrected": False}

    h, w = img.shape[:2]
    orig_shape = (w, h)

    # 1. Resize nhẹ nếu ảnh quá lớn (> 1800px)
    max_dim = 1800
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        new_w, new_h = int(w * scale), int(h * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]

    transform = np.diag([w / orig_shape[0], h / orig_shape[1], 1.0])
    perspective_corrected = False

    # 2. Phát hiện khung viền 4 điểm và căn phối cảnh (Perspective Transform)
    try:
        gray_for_contour = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray_for_contour, (5, 5), 0)
        edged = cv2.Canny(blurred, 50, 150)
        
        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
        
        doc_contour = None
        for c in contours:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4 and cv2.contourArea(c) > (w * h * 0.35): # Chiếm ít nhất 35% diện tích ảnh
                doc_contour = approx
                break

        if doc_contour is not None:
            pts = doc_contour.reshape(4, 2)
            rect = np.zeros((4, 2), dtype="float32")
            s = pts.sum(axis=1)
            rect[0] = pts[np.argmin(s)] # top-left
            rect[2] = pts[np.argmax(s)] # bottom-right
            diff = np.diff(pts, axis=1)
            rect[1] = pts[np.argmin(diff)] # top-right
            rect[3] = pts[np.argmax(diff)] # bottom-left

            (tl, tr, br, bl) = rect
            widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
            widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
            maxWidth = max(int(widthA), int(widthB))

            heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
            heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
            maxHeight = max(int(heightA), int(heightB))

            dst = np.array([
                [0, 0],
                [maxWidth - 1, 0],
                [maxWidth - 1, maxHeight - 1],
                [0, maxHeight - 1]], dtype="float32")

            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(img, M, (maxWidth, maxHeight))
            transform = M @ transform
            img = warped
            h, w = img.shape[:2]
            perspective_corrected = True
    except Exception as e:
        print(f"[PERSPECTIVE LOG] Bỏ qua căn chỉnh viền tự động: {e}")

    # 3. Tính góc xoay nghiêng (Deskewing)
    deskew_angle = 0.0
    try:
        gray_for_deskew = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        thresh = cv2.threshold(gray_for_deskew, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) > 200:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            elif angle > 45:
                angle = 90 - angle
            else:
                angle = -angle

            if 0.5 < abs(angle) < 25.0:
                deskew_angle = round(float(angle), 2)
                (cX, cY) = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D((cX, cY), deskew_angle, 1.0)
                img = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
                transform = np.vstack([M, [0, 0, 1]]) @ transform
    except Exception as e:
        print(f"[DESKEW LOG] Bỏ qua deskew: {e}")

    # 4. Chỉ áp dụng CLAHE khi ảnh tối (need_clahe=True) trên kênh Luminance của hệ màu LAB
    clahe_applied = False
    if need_clahe:
        try:
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            limg = cv2.merge((cl, a, b))
            img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
            clahe_applied = True
        except Exception:
            pass

    # Lưu ảnh đã tiền xử lý nhẹ
    out_dir = os.path.dirname(image_path)
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    out_path = os.path.join(out_dir, f"{base_name}_prepped.jpg")
    
    is_success, buffer = cv2.imencode(".jpg", img)
    if is_success:
        with open(out_path, "wb") as f:
            f.write(buffer)
        processed_path = out_path
    else:
        processed_path = image_path

    return {
        "processed_path": processed_path,
        "to_original": (np.linalg.pinv(transform) if is_success else np.eye(3)).tolist(),
        "original_path": image_path,
        "orig_shape": orig_shape,
        "current_shape": (w, h),
        "perspective_corrected": perspective_corrected,
        "deskew_angle": deskew_angle,
        "clahe_applied": clahe_applied
    }

