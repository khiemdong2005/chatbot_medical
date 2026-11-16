from core.ocr_parallel_service import _group_ocr_rows


def _box(text, x, center_y, height):
    return {
        "text": text,
        "x_min": x,
        "y_min": center_y - height / 2,
        "y_max": center_y + height / 2,
        "y_center": center_y,
    }


def test_small_photo_keeps_adjacent_medicine_and_dosing_lines_separate():
    boxes = [
        _box("1.", 15, 101, 12),
        _box("Febuxostat 40mg", 50, 102, 12),
        _box("21 Viên", 250, 103, 12),
        _box("Uống sáng 1 viên", 50, 117, 12),
    ]

    rows = _group_ocr_rows(boxes)

    assert [row["text"] for row in rows] == [
        "1. | Febuxostat 40mg | 21 Viên", "Uống sáng 1 viên"
    ]


def test_high_resolution_scan_keeps_quantity_in_same_medicine_row():
    boxes = [
        _box("21 Viên", 1500, 520, 54),
        _box("Febuxostat 40mg", 200, 500, 54),
        _box("1.", 70, 508, 54),
        _box("Uống sáng 1 viên", 200, 590, 54),
    ]

    rows = _group_ocr_rows(boxes)

    assert [row["text"] for row in rows] == [
        "1. | Febuxostat 40mg | 21 Viên", "Uống sáng 1 viên"
    ]


def test_sideways_prescription_is_read_upright_with_boxes_mapped_back(tmp_path, monkeypatch):
    import cv2
    import numpy as np
    import core.ocr_parallel_service as service

    image_path = tmp_path / "sideways.png"
    cv2.imwrite(str(image_path), np.full((40, 80, 3), 255, dtype=np.uint8))

    def result(text, left, top, right, bottom):
        return ([[left, top], [right, top], [right, bottom], [left, bottom]], text, 0.99)

    class Reader:
        calls = 0

        def readtext(self, _image):
            self.calls += 1
            if self.calls == 2:  # 90 degrees clockwise makes the page upright.
                return [result("ĐƠN THUỐC", 5, 6, 25, 14),
                        result("1. Febuxostat 40mg", 5, 30, 30, 40)]
            return []

    monkeypatch.setattr(service, "get_ocr_reader", lambda: Reader())
    extracted = service.extract_ocr_parallel(str(image_path), doc_type="lab_test")

    assert extracted["orientation_deg"] == 90
    assert "Febuxostat" in extracted["raw_text"]
    assert extracted["rows"][0]["text"] == "ĐƠN THUỐC"
    heading = next(line for line in extracted["lines"] if line["text"] == "ĐƠN THUỐC")
    assert heading["box"][0] == [6, 34]
