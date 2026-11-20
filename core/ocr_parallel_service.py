import base64
import json
import os
import re
import subprocess
import tempfile
import time
from statistics import median
from typing import Dict, Any, List
from core.ocr_extractor import get_ocr_reader

_WINRT_OCR_SCRIPT = r"""
$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function AwaitWinRT($WinRtTask, $ResultType) {
  $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
  $netTask = $asTask.Invoke($null, @($WinRtTask))
  $netTask.Wait(-1) | Out-Null
  return $netTask.Result
}
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$imgPath = [System.IO.Path]::GetFullPath($env:MEDIMIND_WINRT_OCR_IMAGE)
$file = AwaitWinRT ([Windows.Storage.StorageFile]::GetFileFromPathAsync($imgPath)) ([Windows.Storage.StorageFile])
$stream = AwaitWinRT ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
try {
  $decoder = AwaitWinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = AwaitWinRT ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
  if ($null -eq $engine) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
  }
  if ($null -eq $engine) { [Console]::Error.WriteLine('WINRT_ENGINE_UNAVAILABLE'); exit 2 }
  $ocrRes = AwaitWinRT ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  $linesOut = @()
  foreach ($line in $ocrRes.Lines) {
    $wordsOut = @()
    foreach ($w in $line.Words) {
      $r = $w.BoundingRect
      $wordsOut += [PSCustomObject]@{
        text = [string]$w.Text
        x = [int][Math]::Round($r.X)
        y = [int][Math]::Round($r.Y)
        w = [int][Math]::Max(1, [Math]::Round($r.Width))
        h = [int][Math]::Max(1, [Math]::Round($r.Height))
      }
    }
    $linesOut += [PSCustomObject]@{ words = $wordsOut }
  }
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  ConvertTo-Json -InputObject $linesOut -Depth 4 -Compress
} finally {
  if ($stream) { $stream.Dispose() }
}
"""


class _WindowsWinrtReader:
    """Built-in Windows 10/11 WinRT OCR adapter used locally when EasyOCR is absent."""

    def __init__(self):
        self.last_error = None

    def readtext(self, image_or_path) -> list:
        self.last_error = None
        temp_path = None
        target_path = image_or_path
        if not isinstance(image_or_path, str):
            import cv2
            fd, temp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            cv2.imwrite(temp_path, image_or_path)
            target_path = temp_path
        try:
            env = os.environ.copy()
            env["MEDIMIND_WINRT_OCR_IMAGE"] = os.path.abspath(str(target_path))
            encoded_cmd = base64.b64encode(_WINRT_OCR_SCRIPT.encode("utf-16le")).decode("ascii")
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_cmd],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=12,
                env=env,
            )
            if proc.returncode != 0:
                stderr_msg = (proc.stderr or "").strip()
                if "WINRT_ENGINE_UNAVAILABLE" in stderr_msg:
                    self.last_error = "Windows WinRT OCR không tìm thấy gói ngôn ngữ nhận diện."
                else:
                    self.last_error = f"Windows WinRT OCR lỗi thực thi (exit={proc.returncode})."
                return []
            if not proc.stdout.strip():
                return []
            raw = proc.stdout.strip()
            idx = raw.find("[")
            if idx < 0:
                idx = raw.find("{")
            if idx < 0:
                return []
            parsed = json.loads(raw[idx:])
            if isinstance(parsed, dict):
                parsed = [parsed]
            results = []
            for line in parsed:
                words = sorted(line.get("words") or [], key=lambda item: item.get("x", 0))
                if not words:
                    continue
                groups = []
                cur = [words[0]]
                for w in words[1:]:
                    prev = cur[-1]
                    gap = w["x"] - (prev["x"] + prev["w"])
                    col_gap = max(24.0, 2.2 * max(prev["h"], w["h"], 10))
                    if gap > col_gap:
                        groups.append(cur)
                        cur = [w]
                    else:
                        cur.append(w)
                groups.append(cur)
                for grp in groups:
                    text = " ".join(w["text"] for w in grp).strip()
                    if not text:
                        continue
                    x1 = min(w["x"] for w in grp)
                    y1 = min(w["y"] for w in grp)
                    x2 = max(w["x"] + w["w"] for w in grp)
                    y2 = max(w["y"] + w["h"] for w in grp)
                    box = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
                    results.append((box, text, 0.90))
            return results
        except subprocess.TimeoutExpired:
            self.last_error = "Windows WinRT OCR quá thời gian xử lý."
            return []
        except Exception as exc:
            self.last_error = f"Windows WinRT OCR lỗi: {type(exc).__name__}"
            return []
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


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

def extract_ocr_parallel(image_path: str, doc_type: str = "auto") -> Dict[str, Any]:
    """
    [2.A] OCR Engine: Trích xuất text + bbox + confidence.
    Đối với phiếu xét nghiệm: thêm thuật toán gom dòng/cột theo hàng ngang (table row grouping).
    """
    reader = get_ocr_reader()
    engine_name = "easyocr"
    if reader is None:
        if os.name == "nt":
            reader = _WindowsWinrtReader()
            engine_name = "winrt"
        else:
            engine_name = "none"
    if reader is None:
        return {
            "success": False,
            "engine": engine_name,
            "error": "Không có bộ máy OCR cục bộ nào sẵn sàng (EasyOCR/WinRT).",
            "lines": [],
            "rows": [],
            "raw_text": "",
        }

    start_t = time.time()
    try:
        results = reader.readtext(image_path)
    except Exception as e:
        return {"success": False, "engine": engine_name, "error": str(e), "lines": [], "rows": [], "raw_text": ""}

    if not results and getattr(reader, "last_error", None):
        return {
            "success": False,
            "engine": engine_name,
            "error": reader.last_error,
            "lines": [],
            "rows": [],
            "raw_text": "",
        }

    results, orientation_deg, reading_results = _retry_page_orientation(reader, image_path, results)
    if not results:
        duration = round(time.time() - start_t, 2)
        return {"success": True, "engine": engine_name, "lines": [], "rows": [], "raw_text": "", "duration": duration}

    rough_text = " ".join(str(item[1]) for item in results)
    is_prescription = doc_type == "prescription" or (
        doc_type == "auto"
        and bool(re.search(r"(?:đơn|don)[\s|]{0,8}(?:thuốc|thuoc)", rough_text, re.IGNORECASE))
    )
    if is_prescription and orientation_deg == 0:
        results = _recover_small_prescription_details(reader, image_path, results)
        reading_results = results
    duration = round(time.time() - start_t, 2)

    # Bóc tách và định dạng tọa độ
    lines = []
    for item, reading_item in zip(results, reading_results):
        bbox, text, prob = item
        reading_box = reading_item[0]
        text = text.strip()
        if not text:
            continue
        xs = [p[0] for p in reading_box]
        ys = [p[1] for p in reading_box]
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

    rows = _group_ocr_rows(lines)

    raw_text = "\n".join(r["text"] for r in rows) if rows else "\n".join(l["text"] for l in lines)
    avg_conf = round(sum(l["confidence"] for l in lines) / max(len(lines), 1), 3)

    return {
        "success": True,
        "engine": engine_name,
        "duration_sec": duration,
        "total_lines": len(lines),
        "total_rows": len(rows),
        "avg_confidence": avg_conf,
        "orientation_deg": orientation_deg,
        "lines": lines,
        "rows": rows,
        "raw_text": raw_text
    }

