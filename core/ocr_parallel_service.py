import re
import time
from typing import Dict, Any, List
from core.ocr_extractor import get_ocr_reader


def _recover_small_prescription_details(reader, image_path: str, results: list) -> list:
    """Re-read tiny age text and the quantity column on small prescriptions."""
    try:
        import cv2
        import numpy as np

        with open(image_path, "rb") as image_file:
            image = cv2.imdecode(np.frombuffer(image_file.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return results
        height, width = image.shape[:2]
        if width > 900 or height > 1200:
            return results
        scale = 2

        additions = []
        header_text = " ".join(
            str(text) for box, text, _ in results
            if sum(point[1] for point in box) / len(box) < height * 0.32
        )
        age_pattern = r"(?:tuổi|tuoi|tuói|tubi)\s*[:. ]*\s*(\d{1,3})\b"
        if (re.search(r"tuổi|tuoi|tuói|tubi", header_text, re.IGNORECASE)
                and not re.search(age_pattern, header_text, re.IGNORECASE)):
            header = cv2.resize(image[:int(height * 0.30)], None,
                                fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            for box, text, confidence in reader.readtext(header):
                match = re.search(age_pattern, str(text), re.IGNORECASE)
                if match and float(confidence) >= 0.5:
                    mapped = [[point[0] / scale, point[1] / scale] for point in box]
                    additions.append((mapped, f"Tuổi: {match.group(1)}", confidence))
                    break

        unit_boxes = []
        for box, text, _confidence in results:
            if not re.fullmatch(r"(?:viên|vien|ven|gói|gôi|goi|chai|chal|ống|ông|ong|lọ|lo|hộp|hop|vỉ|vi)",
                                str(text).strip(), re.IGNORECASE):
                continue
            if min(point[0] for point in box) > width * 0.65:
                unit_boxes.append(box)
        if not unit_boxes:
            return results + additions

        centers = [sum(point[1] for point in box) / len(box) for box in unit_boxes]
        top = max(0, int(min(centers) - 20))
        bottom = min(height, int(max(centers) + 20))
        left = int(width * 0.65)
        crop = image[top:bottom, left:width]
        if crop.size == 0:
            return results + additions
        enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        for box, text, confidence in reader.readtext(enlarged):
            value = str(text).strip()
            if not re.fullmatch(r"\d{1,3}", value) or float(confidence) < 0.65:
                continue
            mapped = [[left + point[0] / scale, top + point[1] / scale] for point in box]
            center_y = sum(point[1] for point in mapped) / len(mapped)
            duplicate = any(
                str(old_text).strip() == value
                and abs(sum(point[1] for point in old_box) / len(old_box) - center_y) < 8
                for old_box, old_text, _ in results
            )
            if not duplicate:
                additions.append((mapped, value, confidence))
        return results + additions
    except Exception:
        return results

def extract_ocr_parallel(image_path: str, doc_type: str = "auto") -> Dict[str, Any]:
    """
    [2.A] OCR Engine: Trích xuất text + bbox + confidence.
    Đối với phiếu xét nghiệm: thêm thuật toán gom dòng/cột theo hàng ngang (table row grouping).
    """
    reader = get_ocr_reader()
    if reader is None:
        return {"success": False, "error": "EasyOCR engine chưa sẵn sàng", "lines": [], "rows": [], "raw_text": ""}

    start_t = time.time()
    try:
        results = reader.readtext(image_path)
    except Exception as e:
        return {"success": False, "error": str(e), "lines": [], "rows": [], "raw_text": ""}

    if not results:
        duration = round(time.time() - start_t, 2)
        return {"success": True, "lines": [], "rows": [], "raw_text": "", "duration": duration}

    rough_text = " ".join(str(item[1]) for item in results)
    is_prescription = doc_type == "prescription" or (
        doc_type == "auto"
        and bool(re.search(r"(?:đơn|don)[\s|]{0,8}(?:thuốc|thuoc)", rough_text, re.IGNORECASE))
    )
    if is_prescription:
        results = _recover_small_prescription_details(reader, image_path, results)
    duration = round(time.time() - start_t, 2)

    # Bóc tách và định dạng tọa độ
    lines = []
    for item in results:
        bbox, text, prob = item
        text = text.strip()
        if not text:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        lines.append({
            "text": text,
            "confidence": round(float(prob), 3),
            "box": [[int(p[0]), int(p[1])] for p in bbox],
            "x_min": min(xs),
            "x_max": max(xs),
            "y_min": min(ys),
            "y_max": max(ys),
            "y_center": sum(ys) / len(ys)
        })

    # Sắp xếp các đoạn nhận diện theo tọa độ hình học từ trên xuống dưới
    lines.sort(key=lambda item: item["y_center"])

    # Thuật toán gom theo hàng ngang (Row Clustering) - Đặc biệt quan trọng cho phiếu xét nghiệm
    rows = []
    if lines:
        current_row = [lines[0]]
        current_y = lines[0]["y_center"]
        y_tolerance = 16.0  # Dung sai lệch hàng pixel

        for item in lines[1:]:
            if abs(item["y_center"] - current_y) <= y_tolerance:
                current_row.append(item)
                # Cập nhật trung bình cộng y
                current_y = sum(x["y_center"] for x in current_row) / len(current_row)
            else:
                # Sắp xếp các phần tử trong hàng từ trái sang phải
                current_row.sort(key=lambda x: x["x_min"])
                rows.append({
                    "y_center": round(current_y, 1),
                    "text": " | ".join(x["text"] for x in current_row),
                    "items": current_row
                })
                current_row = [item]
                current_y = item["y_center"]

        if current_row:
            current_row.sort(key=lambda x: x["x_min"])
            rows.append({
                "y_center": round(current_y, 1),
                "text": " | ".join(x["text"] for x in current_row),
                "items": current_row
            })

    raw_text = "\n".join(r["text"] for r in rows) if rows else "\n".join(l["text"] for l in lines)
    avg_conf = round(sum(l["confidence"] for l in lines) / max(len(lines), 1), 3)

    return {
        "success": True,
        "duration_sec": duration,
        "total_lines": len(lines),
        "total_rows": len(rows),
        "avg_confidence": avg_conf,
        "lines": lines,
        "rows": rows,
        "raw_text": raw_text
    }

