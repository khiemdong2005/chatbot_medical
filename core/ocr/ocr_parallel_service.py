import re
import time
import logging
from statistics import median
from typing import Dict, Any, List
from core.ocr.ocr_extractor import get_ocr_reader

logger = logging.getLogger(__name__)


def _group_ocr_rows(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group OCR boxes by their text height instead of a fixed pixel distance.

    A fixed threshold merges adjacent lines in small photos and splits columns
    that belong to one row in high-resolution scans.
    """
    if not lines:
        return []

    rows = []
    current = []

    def append_row(items):
        ordered = sorted(items, key=lambda item: item["x_min"])
        row = {
            "y_center": round(sum(item["y_center"] for item in ordered) / len(ordered), 1),
            "text": " | ".join(item["text"] for item in ordered),
            "items": ordered,
            "x_min": min(item["x_min"] for item in ordered),
            "x_max": max(item.get("x_max", item["x_min"]) for item in ordered),
            "y_min": min(item["y_min"] for item in ordered),
            "y_max": max(item["y_max"] for item in ordered),
        }
        points = [point for item in ordered for point in item.get("box", [])]
        if points:
            left, right = min(p[0] for p in points), max(p[0] for p in points)
            top, bottom = min(p[1] for p in points), max(p[1] for p in points)
            row["union_bbox"] = [[left, top], [right, top], [right, bottom], [left, bottom]]
        rows.append(row)

    for item in sorted(lines, key=lambda part: part["y_center"]):
        if current:
            row_center = sum(part["y_center"] for part in current) / len(current)
            row_height = median(max(1, part["y_max"] - part["y_min"]) for part in current)
            item_height = max(1, item["y_max"] - item["y_min"])
            offset = abs(item["y_center"] - row_center)
            tolerance = max(5.0, min(32.0, 0.6 * max(row_height, item_height) + 2.0))
            row_top = min(part["y_min"] for part in current)
            row_bottom = max(part["y_max"] for part in current)
            overlap = max(0.0, min(row_bottom, item["y_max"]) - max(row_top, item["y_min"]))
            overlap_fraction = overlap / min(row_height, item_height)
            same_line_by_overlap = (overlap_fraction >= 0.55
                                    and offset <= 0.6 * max(row_height, item_height) + 2.0)
            # A box below another box in the same column is usually the next
            # printed line even when a taller OCR box overlaps both vertically.
            same_line = offset <= tolerance or same_line_by_overlap
            if same_line and offset > 0.35 * min(row_height, item_height):
                for part in current:
                    left = max(part["x_min"], item["x_min"])
                    right = min(part.get("x_max", part["x_min"]),
                                item.get("x_max", item["x_min"]))
                    narrow_width = min(part.get("x_max", part["x_min"]) - part["x_min"],
                                       item.get("x_max", item["x_min"]) - item["x_min"])
                    if narrow_width > 0 and right - left > 0.3 * narrow_width:
                        same_line = False
                        break
            if not same_line:
                append_row(current)
                current = []
        current.append(item)

    if current:
        append_row(current)
    return rows


def _ocr_orientation_score(results: list) -> float:
    """Compare orientations using recognized text, confidence and form labels."""
    score = 0.0
    text_parts = []
    for _box, value, confidence in results:
        value = str(value).strip()
        letters = sum(char.isalnum() for char in value)
        if letters < 2:
            continue
        score += min(letters, 60) * max(0.0, min(1.0, float(confidence)))
        text_parts.append(value.lower())
    text = " ".join(text_parts)
    score += 25 * sum(label in text for label in (
        "đơn thuốc", "don thuoc", "toa thuốc", "toa thuoc",
        "bệnh nhân", "benh nhan", "tên thuốc", "ten thuoc",
        "xét nghiệm", "xet nghiem",
    ))
    return score


def _retry_page_orientation(reader, image_path: str, results: list) -> tuple:
    """Re-read sideways pages only when the first pass lacks convincing text."""
    initial_score = _ocr_orientation_score(results)
    if initial_score >= 120:
        return results, 0, results

    try:
        import cv2
        import numpy as np

        with open(image_path, "rb") as image_file:
            image = cv2.imdecode(np.frombuffer(image_file.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return results, 0, results
        height, width = image.shape[:2]
        best_results, best_score, best_angle = results, initial_score, 0
        rotations = (
            (90, cv2.ROTATE_90_CLOCKWISE),
            (180, cv2.ROTATE_180),
            (270, cv2.ROTATE_90_COUNTERCLOCKWISE),
        )
        for angle, rotation in rotations:
            try:
                candidate = reader.readtext(cv2.rotate(image, rotation))
            except Exception:
                continue
            score = _ocr_orientation_score(candidate)
            if score > best_score * 1.35 and score - best_score > 12:
                best_results, best_score, best_angle = candidate, score, angle

        if best_angle == 0:
            return results, 0, results

        def original_point(point):
            x, y = point
            if best_angle == 90:
                return [y, height - 1 - x]
            if best_angle == 180:
                return [width - 1 - x, height - 1 - y]
            return [width - 1 - y, x]

        mapped = [([original_point(point) for point in box], value, confidence)
                  for box, value, confidence in best_results]
        return mapped, best_angle, best_results
    except Exception:
        return results, 0, results


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


def _read_prescription_variants(reader, image_path: str, results: list) -> list:
    """Add text found by contrast/threshold/upscale passes without dropping weak detections."""
    try:
        import cv2
        import numpy as np

        with open(image_path, "rb") as image_file:
            image = cv2.imdecode(np.frombuffer(image_file.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return results
        height, width = image.shape[:2]
        if max(height, width) > 2400:
            return results

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        adaptive = cv2.adaptiveThreshold(
            clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11,
        )
        scale = min(2.0, 1800 / max(height, width))
        if scale > 1.05:
            clahe = cv2.resize(clahe, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            adaptive = cv2.resize(adaptive, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        combined = list(results)
        for variant in (clahe, adaptive):
            try:
                candidates = reader.readtext(variant)
            except Exception:
                continue
            for box, text, confidence in candidates:
                mapped = [[float(point[0]) / scale, float(point[1]) / scale] for point in box]
                candidate_text = re.sub(r"\s+", " ", str(text)).strip().casefold()
                if not candidate_text:
                    continue
                center = (sum(p[0] for p in mapped) / len(mapped), sum(p[1] for p in mapped) / len(mapped))
                duplicate = False
                for old_box, old_text, _old_conf in combined:
                    old_norm = re.sub(r"\s+", " ", str(old_text)).strip().casefold()
                    if old_norm != candidate_text or not old_box:
                        continue
                    old_center = (sum(p[0] for p in old_box) / len(old_box), sum(p[1] for p in old_box) / len(old_box))
                    if abs(center[0] - old_center[0]) <= max(12, width * 0.02) and abs(center[1] - old_center[1]) <= max(10, height * 0.015):
                        duplicate = True
                        break
                if not duplicate:
                    combined.append((mapped, text, confidence))
        return combined
    except Exception:
        return results


def _dedupe_ocr_results(results: list, iou_threshold: float = 0.30) -> list:
    """NMS duplicate, near-identical OCR boxes while retaining distinct low-confidence text."""
    import difflib

    def bounds(item):
        box = item[0] or []
        if not box:
            return (0.0, 0.0, 0.0, 0.0)
        return (min(point[0] for point in box), min(point[1] for point in box),
                max(point[0] for point in box), max(point[1] for point in box))

    def normalized(text):
        return re.sub(r"[^a-z0-9]+", "", str(text).casefold())

    kept = []
    for candidate in sorted(results, key=lambda item: float(item[2] or 0), reverse=True):
        left, top, right, bottom = bounds(candidate)
        candidate_text = normalized(candidate[1])
        duplicate = False
        for current in kept:
            x1, y1, x2, y2 = bounds(current)
            intersection = max(0, min(right, x2) - max(left, x1)) * max(0, min(bottom, y2) - max(top, y1))
            if intersection <= 0:
                continue
            area_c = max(0, right - left) * max(0, bottom - top)
            area_k = max(0, x2 - x1) * max(0, y2 - y1)
            union = area_c + area_k - intersection
            iou = (intersection / union) if union else 0.0
            if iou <= iou_threshold:
                continue
            other = normalized(current[1])
            if iou > 0.55:
                duplicate = True
                break
            if not candidate_text or not other:
                continue
            text_similarity = difflib.SequenceMatcher(None, candidate_text, other).ratio()
            if text_similarity >= 0.75:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept


def _readtext_relaxed(
    reader,
    img_or_path,
    min_size: int = 5,
    text_threshold: float = 0.5,
    low_text: float = 0.3,
    contrast_ths: float = 0.1,
    adjust_contrast: float = 0.5,
) -> list:
    """Gọi EasyOCR với ngưỡng mềm hơn để không sót chữ số đơn hoặc dòng liều in nghiêng/mờ; fallback cho mock reader."""
    try:
        return reader.readtext(
            img_or_path,
            min_size=min_size,
            text_threshold=text_threshold,
            low_text=low_text,
            contrast_ths=contrast_ths,
            adjust_contrast=adjust_contrast,
        )
    except TypeError:
        return reader.readtext(img_or_path)


def _run_tiled_prescription_ocr(reader, image_path: str, min_conf: float = 0.30) -> tuple:
    """Chạy OCR theo 2 tile chồng lấn 15% theo chiều dọc để đọc rõ cả nửa dưới đơn thuốc,
    ghi log đầy đủ số box bị loại ở từng bước lọc."""
    stats = {
        "tiles": 1,
        "raw_detected": 0,
        "dropped_empty": 0,
        "dropped_low_conf": 0,
        "dropped_dedupe": 0,
        "low_conf_flagged": 0,
        "kept_after_ocr": 0,
    }
    try:
        import cv2
        import numpy as np

        with open(image_path, "rb") as image_file:
            image = cv2.imdecode(np.frombuffer(image_file.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        image = None

    if image is None:
        raw_results = _readtext_relaxed(reader, image_path)
    else:
        height, width = image.shape[:2]
        if height >= 1200:
            stats["tiles"] = 2
            overlap_half = int(height * 0.075)
            mid = height // 2
            tiles = [
                (0, min(height, mid + overlap_half)),
                (max(0, mid - overlap_half), height),
            ]
            raw_results = []
            for y_start, y_end in tiles:
                crop = image[y_start:y_end, :]
                tile_res = _readtext_relaxed(reader, crop)
                for box, text, prob in tile_res:
                    mapped_box = [[float(p[0]), float(p[1]) + y_start] for p in box]
                    raw_results.append((mapped_box, text, prob))
        else:
            raw_results = _readtext_relaxed(reader, image)

    stats["raw_detected"] = len(raw_results)

    filtered = []
    for box, text, prob in raw_results:
        clean_t = str(text or "").strip()
        if not clean_t:
            stats["dropped_empty"] += 1
            continue
        conf = float(prob or 0.0)
        if conf < min_conf:
            stats["dropped_low_conf"] += 1
            continue
        if conf < 0.70:
            stats["low_conf_flagged"] += 1
        filtered.append((box, clean_t, conf))

    deduped = _dedupe_ocr_results(filtered, iou_threshold=0.30)
    stats["dropped_dedupe"] = len(filtered) - len(deduped)
    stats["kept_after_ocr"] = len(deduped)

    logger.info(
        "[OCR_FILTER_STATS] tiles=%d raw=%d dropped_empty=%d dropped_low_conf(<%.2f)=%d "
        "dropped_dedupe(IoU>0.3)=%d low_conf_flagged(<0.7)=%d kept=%d",
        stats["tiles"], stats["raw_detected"], stats["dropped_empty"], min_conf,
        stats["dropped_low_conf"], stats["dropped_dedupe"], stats["low_conf_flagged"],
        stats["kept_after_ocr"],
    )
    return deduped, stats


def retry_ocr_crop_band(image_path: str, y1: float, y2: float, scale: float = 2.0, min_conf: float = 0.25) -> list:
    """Chạy lại OCR riêng cho một vùng y bị thiếu thuốc (crop + upscale x2)."""
    reader = get_ocr_reader()
    if reader is None:
        return []
    try:
        import cv2
        import numpy as np

        with open(image_path, "rb") as image_file:
            image = cv2.imdecode(np.frombuffer(image_file.read(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return []
        height, width = image.shape[:2]
        top = max(0, int(round(y1)))
        bottom = min(height, int(round(y2)))
        if bottom - top < 12:
            return []
        crop = image[top:bottom, :]
        enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        # Chỉ tăng tương phản nhẹ CLAHE (không double-sharpen để tránh vỡ nét chữ in nghiêng nhỏ)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        raw = _readtext_relaxed(
            reader,
            clahe,
            min_size=4,
            text_threshold=0.35,
            low_text=0.20,
            contrast_ths=0.05,
            adjust_contrast=0.7,
        )
        recovered = []
        for box, text, prob in raw:
            clean_t = str(text or "").strip()
            conf = float(prob or 0.0)
            if not clean_t or conf < min_conf:
                continue
            mapped = [[float(p[0]) / scale, top + float(p[1]) / scale] for p in box]
            xs = [p[0] for p in mapped]
            ys = [p[1] for p in mapped]
            recovered.append({
                "text": clean_t,
                "confidence": round(conf, 3),
                "low_confidence": conf < 0.70,
                "box": [[int(round(p[0])), int(round(p[1]))] for p in mapped],
                "x_min": min(xs),
                "x_max": max(xs),
                "y_min": min(ys),
                "y_max": max(ys),
                "y_center": sum(ys) / len(ys),
            })
        return recovered
    except Exception as exc:
        logger.warning("[OCR_BAND_RETRY] Lỗi chạy lại OCR vùng y=[%s..%s]: %s", y1, y2, exc)
        return []

def extract_ocr_parallel(image_path: str, doc_type: str = "auto") -> Dict[str, Any]:
    """
    [2.A] OCR Engine: Trích xuất text + bbox + confidence.
    Đối với đơn thuốc: chạy tiled OCR chồng lấn 15%, ngưỡng conf >= 0.3, dedupe IoU > 0.3 và log thống kê lọc.
    Đối với phiếu xét nghiệm: thêm thuật toán gom dòng/cột theo hàng ngang (table row grouping).
    """
    reader = get_ocr_reader()
    if reader is None:
        return {"success": False, "error": "EasyOCR engine chưa sẵn sàng", "lines": [], "rows": [], "raw_text": ""}

    start_t = time.time()
    filter_stats = None
    orientation_deg = 0
    try:
        if doc_type == "prescription":
            results, filter_stats = _run_tiled_prescription_ocr(reader, image_path, min_conf=0.30)
            reading_results = results
            is_prescription = True
        else:
            results = reader.readtext(image_path)
            rough_text = " ".join(str(item[1]) for item in results)
            import unicodedata
            rough_folded = "".join(
                ch for ch in unicodedata.normalize("NFKD", rough_text)
                if not unicodedata.combining(ch)
            ).replace("đ", "d").replace("Đ", "D").lower()
            is_prescription = (
                doc_type == "auto" and bool(re.search(
                    r"\b(?:don|toa)[\s|]{0,8}thuoc\b|\bchan\s*[dc]oan\b|\bphong\s*kham\b|\bc[\(\{o0]?ng\s*khoan\b",
                    rough_folded,
                ))
            )
            if is_prescription:
                results, filter_stats = _run_tiled_prescription_ocr(reader, image_path, min_conf=0.30)
                reading_results = results
            else:
                results, orientation_deg, reading_results = _retry_page_orientation(reader, image_path, results)
    except Exception as e:
        return {"success": False, "error": str(e), "lines": [], "rows": [], "raw_text": ""}

    if not results:
        duration = round(time.time() - start_t, 2)
        return {"success": True, "lines": [], "rows": [], "raw_text": "", "duration": duration, "filter_stats": filter_stats or {}}

    duration = round(time.time() - start_t, 2)

    # Bóc tách và định dạng tọa độ
    lines = []
    for item, reading_item in zip(results, reading_results):
        bbox, text, prob = item
        reading_box = reading_item[0]
        text = str(text or "").strip()
        if not text:
            continue
        xs = [p[0] for p in reading_box]
        ys = [p[1] for p in reading_box]
        conf_val = round(float(prob), 3)
        lines.append({
            "text": text,
            "confidence": conf_val,
            "low_confidence": conf_val < 0.70,
            "box": [[int(round(p[0])), int(round(p[1]))] for p in bbox],
            "x_min": min(xs),
            "x_max": max(xs),
            "y_min": min(ys),
            "y_max": max(ys),
            "y_center": sum(ys) / len(ys)
        })

    # Sắp xếp các đoạn nhận diện theo tọa độ hình học từ trên xuống dưới
    lines.sort(key=lambda item: item["y_center"])
    for line_index, line in enumerate(lines):
        line["line_index"] = line_index

    rows = _group_ocr_rows(lines)

    raw_text = "\n".join(r["text"] for r in rows) if rows else "\n".join(l["text"] for l in lines)
    avg_conf = round(sum(l["confidence"] for l in lines) / max(len(lines), 1), 3)

    return {
        "success": True,
        "duration_sec": duration,
        "total_lines": len(lines),
        "total_rows": len(rows),
        "avg_confidence": avg_conf,
        "orientation_deg": orientation_deg,
        "lines": lines,
        "rows": rows,
        "raw_text": raw_text,
        "filter_stats": filter_stats or {
            "tiles": 1,
            "raw_detected": len(lines),
            "dropped_empty": 0,
            "dropped_low_conf": 0,
            "dropped_dedupe": 0,
            "low_conf_flagged": sum(1 for l in lines if l["confidence"] < 0.70),
            "kept_after_ocr": len(lines),
        },
    }

