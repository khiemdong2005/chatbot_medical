"""OCR quality passes must preserve low-confidence source evidence."""

import cv2
import numpy as np

from core.ocr_parallel_service import _dedupe_ocr_results, _read_prescription_variants, extract_ocr_parallel


def _ocr_item(text, confidence, box):
    return (box, text, confidence)


def test_contrast_retry_keeps_low_confidence_unique_text(tmp_path):
    image_path = tmp_path / "small-prescription.png"
    cv2.imwrite(str(image_path), np.full((80, 120, 3), 245, dtype=np.uint8))
    low_confidence_result = _ocr_item(
        "ALTHAX", 0.42, [[20, 30], [90, 30], [90, 44], [20, 44]],
    )

    class Reader:
        def readtext(self, _image):
            return [_ocr_item("SUCARAFATE GEL", 0.54,
                              [[40, 60], [150, 60], [150, 82], [40, 82]])]

    results = _read_prescription_variants(Reader(), str(image_path), [low_confidence_result])

    assert [item[1] for item in results] == ["ALTHAX", "SUCARAFATE GEL"]
    assert results[0][2] == 0.42
    assert results[1][2] == 0.54
    assert results[1][0][0][0] == 20  # 2x upscale mapped back to source pixels.


def test_parallel_ocr_exposes_stable_line_index_for_each_bbox(tmp_path, monkeypatch):
    import core.ocr_parallel_service as service

    image_path = tmp_path / "ocr-index.png"
    cv2.imwrite(str(image_path), np.full((60, 120, 3), 255, dtype=np.uint8))

    class Reader:
        def readtext(self, _image):
            return [
                _ocr_item("One line", 0.91, [[2, 2], [50, 2], [50, 12], [2, 12]]),
                _ocr_item("Another line", 0.62, [[2, 25], [70, 25], [70, 35], [2, 35]]),
            ]

    monkeypatch.setattr(service, "get_ocr_reader", lambda: Reader())
    extracted = extract_ocr_parallel(str(image_path), doc_type="lab_test")

    assert [line["line_index"] for line in extracted["lines"]] == [0, 1]
    assert all(len(line["box"]) == 4 and "confidence" in line for line in extracted["lines"])


def test_prescription_ocr_runs_once_and_nms_keeps_highest_confidence_duplicate(tmp_path, monkeypatch):
    import core.ocr_parallel_service as service

    image_path = tmp_path / "single-pass.png"
    cv2.imwrite(str(image_path), np.full((60, 120, 3), 255, dtype=np.uint8))

    class Reader:
        calls = 0

        def readtext(self, _image):
            self.calls += 1
            return [
                _ocr_item("ĐƠN THUỐC", 0.95, [[2, 2], [80, 2], [80, 15], [2, 15]]),
                _ocr_item("ĐƠN THUỐC", 0.66, [[3, 3], [81, 3], [81, 16], [3, 16]]),
            ]

    reader = Reader()
    monkeypatch.setattr(service, "get_ocr_reader", lambda: reader)
    result = service.extract_ocr_parallel(str(image_path), doc_type="prescription")

    assert reader.calls == 1
    assert len(result["lines"]) == 1
    assert result["lines"][0]["confidence"] == 0.95
