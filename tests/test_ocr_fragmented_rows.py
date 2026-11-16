"""Rows split into boxes must remain readable without joining the next line."""

from core.ocr_parallel_service import _group_ocr_rows


def _box(text, x_min, x_max, y_center, height):
    top, bottom = y_center - height / 2, y_center + height / 2
    return {"text": text, "x_min": x_min, "x_max": x_max,
            "y_min": top, "y_max": bottom, "y_center": y_center,
            "box": [[x_min, top], [x_max, top], [x_max, bottom], [x_min, bottom]]}


def test_split_drug_name_strength_and_quantity_stay_on_one_row():
    boxes = [
        _box("120mg", 210, 280, 113, 12),
        _box("1. Althax", 20, 130, 100, 20),
        _box("[KINT]", 140, 200, 110, 12),
        _box("20 Viên", 480, 550, 112, 12),
        _box("Cách dùng: uống sáng", 20, 260, 139, 14),
    ]

    rows = _group_ocr_rows(boxes)

    assert [row["text"] for row in rows] == [
        "1. Althax | [KINT] | 120mg | 20 Viên", "Cách dùng: uống sáng"
    ]
    assert rows[0]["union_bbox"] == [[20, 90.0], [550, 90.0], [550, 119.0], [20, 119.0]]
    assert rows[0]["items"][0]["box"] == boxes[1]["box"]


def test_tall_box_does_not_absorb_next_line_in_same_column():
    rows = _group_ocr_rows([
        _box("4. Gastsus", 30, 170, 100, 40),
        _box("Cách dùng", 30, 160, 118, 12),
    ])

    assert [row["text"] for row in rows] == ["4. Gastsus", "Cách dùng"]


def test_fragmented_strength_tail_stays_with_heading():
    rows = _group_ocr_rows([
        _box("4. Gastsus [KDNT]", 25, 190, 200, 20),
        _box("96mg)10ml", 260, 350, 213, 12),
        _box("Uống sau ăn", 25, 150, 235, 12),
    ])

    assert [row["text"] for row in rows] == [
        "4. Gastsus [KDNT] | 96mg)10ml", "Uống sau ăn"
    ]
