import re
import time
from typing import Dict, Any, List
from core.ocr_extractor import get_ocr_reader

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

    duration = round(time.time() - start_t, 2)
    if not results:
        return {"success": True, "lines": [], "rows": [], "raw_text": "", "duration": duration}

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

