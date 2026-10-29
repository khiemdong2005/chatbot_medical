import os
import sys
import time
from typing import Dict, Any, List, Optional

# Ensure UTF-8 console encoding on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from core.image_preprocessor import preprocess_prescription_image

# Global singleton EasyOCR Reader để tránh nạp lại mô hình nhiều lần gây chậm
_OCR_READER = None


def get_ocr_reader():
    """
    Khởi tạo hoặc trả về bộ đọc EasyOCR tiếng Việt + tiếng Anh.
    Singleton pattern: Tải trọng số 1 lần duy nhất trong suốt vòng đời ứng dụng.
    """
    global _OCR_READER
    if _OCR_READER is None:
        try:
            import easyocr
            print("[OCR ENGINE] Đang khởi tạo mô hình EasyOCR (Ngôn ngữ: Tiếng Việt + Tiếng Anh)...")
            start_t = time.time()
            _OCR_READER = easyocr.Reader(['vi', 'en'], gpu=False, verbose=False)
            print(f"[OCR ENGINE] Mô hình OCR sẵn sàng ({time.time() - start_t:.2f}s)!")
        except Exception as e:
            print(f"[OCR ENGINE ERROR] Không thể khởi tạo EasyOCR: {e}")
            _OCR_READER = None
    return _OCR_READER


def extract_prescription_text(image_path: str) -> Dict[str, Any]:
    """
    Bóc tách toàn bộ thông tin từ ảnh tài liệu y tế bằng mô hình cục bộ:
      1. Tiền xử lý ảnh (Khử nhiễu, tăng tương phản CLAHE, căn thẳng góc nghiêng)
      2. Nhận diện ký tự quang học (OCR) với EasyOCR tiếng Việt
      3. Gom cụm dòng và phân tích bố cục (Layout & Block Segmentation)
      4. Đánh giá độ tin cậy và xuất văn bản có cấu trúc
    """
    if not os.path.exists(image_path):
        return {
            "success": False,
            "error": f"Không tìm thấy tệp: {image_path}",
            "lines": [],
            "raw_text": ""
        }

    # Bước 1: Tiền xử lý ảnh bằng OpenCV
    try:
        prep_info = preprocess_prescription_image(image_path, save_debug=True)
        target_image_path = prep_info.get("processed_image_path", image_path)
    except Exception as e:
        print(f"[PREPROCESS WARNING] Bỏ qua tiền xử lý OpenCV do lỗi: {e}")
        prep_info = {"status": "skipped", "error": str(e)}
        target_image_path = image_path

    # Bước 2: Chạy EasyOCR
    reader = get_ocr_reader()
    if reader is None:
        return {
            "success": False,
            "error": "Bộ máy EasyOCR chưa được nạp.",
            "prep_info": prep_info,
            "lines": [],
            "raw_text": ""
        }

    start_ocr = time.time()
    try:
        results = reader.readtext(target_image_path)
    except Exception as ocr_err:
        print(f"[OCR ERROR] Lỗi trong quá trình quét văn bản: {ocr_err}")
        return {
            "success": False,
            "error": str(ocr_err),
            "prep_info": prep_info,
            "lines": [],
            "raw_text": ""
        }

    ocr_duration = round(time.time() - start_ocr, 2)

    if not results:
        return {
            "success": True,
            "prep_info": prep_info,
            "ocr_duration_sec": ocr_duration,
            "total_lines": 0,
            "avg_confidence": 0.0,
            "lines": [],
            "raw_text": "",
            "structured_blocks": {}
        }

    # Bước 3: Sắp xếp các đoạn nhận diện theo tọa độ hình học (từ trên xuống dưới, trái sang phải)
    # bbox format: [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    def get_sort_key(item):
        bbox, text, prob = item
        y_top = min(point[1] for point in bbox)
        x_left = min(point[0] for point in bbox)
        return (y_top // 15, x_left)

    sorted_results = sorted(results, key=get_sort_key)

    extracted_lines = []
    total_conf = 0.0

    for idx, (bbox, text, prob) in enumerate(sorted_results):
        cleaned_text = text.strip()
        if not cleaned_text:
            continue
        total_conf += prob
        extracted_lines.append({
            "line_no": idx + 1,
            "text": cleaned_text,
            "confidence": round(float(prob), 3),
            "box": [[int(p[0]), int(p[1])] for p in bbox]
        })

    avg_confidence = round(total_conf / max(len(extracted_lines), 1), 3)
    full_raw_text = "\n".join([line["text"] for line in extracted_lines])

    # Bước 4: Phân cụm khối sơ bộ (Rule-based heuristics)
    admin_lines = []
    med_lines = []
    warning_lines = []

    med_keywords = [
        "viên", "vien", "gói", "goi", "ống", "ong", "chai", "hộp", "lọ",
        "uống", "uong", "mg", "ml", "g", "lần", "lan", "sau ăn", "trước ăn",
        "ngày", "ngay", "tối", "sáng", "trưa", "chiều", "1/2", "1/3"
    ]

    for line in extracted_lines:
        txt_lower = line["text"].lower()
        if any(k in txt_lower for k in ["bác sĩ", "bs", "tái khám", "dặn dò", "chú ý", "lời dặn", "khám lại"]):
            warning_lines.append(line["text"])
        elif any(k in txt_lower for k in med_keywords) or any(char.isdigit() for char in line["text"]):
            med_lines.append(line["text"])
        else:
            admin_lines.append(line["text"])

    return {
        "success": True,
        "prep_info": prep_info,
        "ocr_duration_sec": ocr_duration,
        "total_lines": len(extracted_lines),
        "avg_confidence": avg_confidence,
        "lines": extracted_lines,
        "raw_text": full_raw_text,
        "structured_blocks": {
            "administrative": admin_lines,
            "medications_raw": med_lines,
            "instructions": warning_lines
        }
    }
