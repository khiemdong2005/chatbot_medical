"""
Unit tests cho hệ thống đọc đơn thuốc đa bố cục (Layout A + Layout B),
sử dụng dữ liệu OCR giả lập dạng JSON (không commit ảnh đơn thật).
"""

import numpy as np
from core.reconciliation_service import (
    VIETNAM_CLINICAL_KB,
    _prescription_body_bounds,
    extract_schema_from_ocr,
    reconcile_parallel_results,
)
from core.pipeline_orchestrator import _build_default_overlay_boxes
from core.grounding_service import normalize_drug_entity


def _make_item(text, x_min, x_max, y_min, y_max, confidence=0.92, line_index=0):
    return {
        "text": text,
        "confidence": confidence,
        "box": [[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max]],
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "y_center": (y_min + y_max) / 2.0,
        "line_index": line_index,
    }


def _make_row(items):
    ordered = sorted(items, key=lambda it: it["x_min"])
    return {
        "y_center": round(sum(it["y_center"] for it in ordered) / len(ordered), 1),
        "text": " | ".join(it["text"] for it in ordered),
        "items": ordered,
        "x_min": min(it["x_min"] for it in ordered),
        "x_max": max(it["x_max"] for it in ordered),
        "y_min": min(it["y_min"] for it in ordered),
        "y_max": max(it["y_max"] for it in ordered),
    }


def _build_layout_b_ocr_json():
    """Giả lập dữ liệu OCR JSON của đơn Layout B (BV Xây Dựng, Phòng khám Nội 4, 7 thuốc)."""
    idx = 0

    def it(text, x1, x2, y1, y2, conf=0.92):
        nonlocal idx
        idx += 1
        return _make_item(text, x1, x2, y1, y2, confidence=conf, line_index=idx)

    rows = [
        _make_row([it("BỆNH VIỆN XÂY DỰNG", 240, 680, 120, 155)]),
        _make_row([it("PHÒNG KHÁM: Nội 4", 240, 660, 165, 200)]),
        _make_row([it("Họ tên:", 80, 200, 270, 305)]),
        _make_row([it("Địa chỉ:", 80, 200, 325, 360)]),
        _make_row([it("Chẩn đoán: Eczema phản ứng giai đoạn cấp tính.", 80, 960, 395, 435)]),
        # 1. Ducray Kelual DS (không dấu chấm sau số 1, tách box x | 1 | lọ)
        _make_row([
            it("1", 120, 145, 470, 505),
            it("Ducray Kelual DS", 220, 560, 470, 505),
            it("x", 820, 845, 470, 505),
            it("1", 940, 965, 470, 505),
            it("lọ", 1070, 1110, 470, 505),
        ]),
        _make_row([it("Tắm gội 3 lần/ tuần, cách ngày. Các ngày khác dùng sữa tắm.", 220, 1250, 525, 560)]),
        # 2. Silkron
        _make_row([
            it("2", 120, 145, 595, 630),
            it("Silkron", 220, 380, 595, 630),
            it("x", 820, 845, 595, 630),
            it("3", 940, 965, 595, 630),
            it("tube", 1070, 1140, 595, 630),
        ]),
        _make_row([it("Bôi tại chỗ 2 lần/ ngày, sáng, chiều x 2 tuần.", 220, 980, 645, 680)]),
        # 3. EMOLEUM LIPID BALM
        _make_row([
            it("3", 120, 145, 720, 755),
            it("EMOLEUM LIPID BALM", 220, 650, 720, 755),
            it("x", 820, 845, 720, 755),
            it("1", 940, 965, 720, 755),
            it("tube", 1070, 1140, 720, 755),
        ]),
        _make_row([it("Xoa tại chỗ 3 lần/ ngày, sáng, chiều, tối. Dùng sau các thuốc khác 30 phút", 220, 1360, 770, 805)]),
        # 4. Halcort 6
        _make_row([
            it("4", 120, 145, 835, 870),
            it("Halcort 6", 220, 420, 835, 870),
            it("x", 820, 845, 835, 870),
            it("30", 930, 975, 835, 870),
            it("viên", 1070, 1140, 835, 870),
        ]),
        _make_row([it("Uống 3 viên/ lần/ ngày, buổi sáng, sau ăn no.", 220, 990, 890, 925)]),
        # 5. Destidin 5mg
        _make_row([
            it("5", 120, 145, 960, 995),
            it("Destidin 5mg", 220, 460, 960, 995),
            it("x", 820, 845, 960, 995),
            it("30", 930, 975, 960, 995),
            it("viên", 1070, 1140, 960, 995),
        ]),
        _make_row([it("Uống 1 viên/ ngày, buổi tối.", 220, 780, 1010, 1045)]),
        # 6. Mardekin
        _make_row([
            it("6", 120, 145, 1070, 1105),
            it("Mardekin", 220, 410, 1070, 1105),
            it("x", 820, 845, 1070, 1105),
            it("1", 940, 965, 1070, 1105),
            it("hộp", 1070, 1135, 1070, 1105),
        ]),
        _make_row([it("Uống 2 viên/ lần x 2 lần/ ngày, sáng, chiều. Sau ăn.", 220, 1100, 1125, 1160)]),
        # 7. HB DIGIC
        _make_row([
            it("7", 120, 145, 1180, 1215),
            it("HB DIGIC", 220, 420, 1180, 1215),
            it("x", 820, 845, 1180, 1215),
            it("60", 930, 975, 1180, 1215),
            it("viên", 1070, 1140, 1180, 1215),
        ]),
        _make_row([it("Uống 2 viên/ lần x 2 lần/ ngày, sáng, chiều. Sau ăn.", 220, 1100, 1230, 1265)]),
        # Kết thúc vùng thuốc tại "Lời dặn" (không có Cộng khoản)
        _make_row([it("Lời dặn:", 220, 390, 1350, 1385)]),
        _make_row([it("Đọc kỹ đơn thuốc trước khi sử dụng.", 220, 860, 1400, 1435)]),
        _make_row([it("Hà Nội, ngày 22 tháng 11 năm 2018", 510, 1170, 1715, 1755)]),
        _make_row([it("Bác sỹ khám bệnh", 670, 1020, 1775, 1810)]),
    ]
    lines = [item for row in rows for item in row["items"]]
    return {
        "rows": rows,
        "lines": lines,
        "raw_text": "\n".join(row["text"] for row in rows),
    }


def _build_layout_a_ocr_json():
    """Giả lập dữ liệu OCR JSON của đơn Layout A (BV Bình Dân, 6 thuốc, 'G.' -> 6, ARTHUR = 63 viên)."""
    idx = 0

    def it(text, x1, x2, y1, y2, conf=0.93):
        nonlocal idx
        idx += 1
        return _make_item(text, x1, x2, y1, y2, confidence=conf, line_index=idx)

    rows = [
        _make_row([it("BỆNH VIỆN BÌNH DÂN", 120, 500, 50, 85), it("Phòng khám: Dịch Vụ 109 - (KTC)", 600, 1200, 50, 85)]),
        _make_row([it("Họ tên: TRẦN TRUNG", 80, 520, 120, 155), it("Phái: Nam", 620, 800, 120, 155), it("Tuổi: 49", 850, 1000, 120, 155)]),
        _make_row([it("Ngày khám: 25/09/2014", 80, 480, 170, 200)]),
        _make_row([it("Chẩn đoán: Viêm dạ dày cấp khác", 80, 760, 220, 255)]),
        _make_row([it("1.", 70, 95, 300, 330), it("YESOM 40 40mg (Esomeprazol 40mg)", 120, 820, 300, 330), it("63", 1220, 1270, 300, 330), it("Viên", 1290, 1370, 300, 330)]),
        _make_row([it("Ngày uống 3 lần, mỗi lần 1 Viên", 120, 620, 340, 370)]),
        _make_row([it("2.", 70, 95, 390, 420), it("SUCRATE GEL (Sucralfate 1g gói)", 120, 820, 390, 420), it("63", 1220, 1270, 390, 420), it("Gói", 1290, 1370, 390, 420)]),
        _make_row([it("Ngày uống 3 lần, mỗi lần 1 Gói", 120, 620, 430, 460)]),
        _make_row([it("3.", 70, 95, 480, 510), it("ARTHUR", 120, 260, 480, 510), it("(Trimebutine 200)", 280, 560, 480, 510), it("63", 1220, 1270, 480, 510), it("Viên", 1290, 1370, 480, 510)]),
        _make_row([it("Ngày uống 3 lần, mỗi lần 1 Viên", 120, 620, 520, 550)]),
        _make_row([it("4.", 70, 95, 570, 600), it("PAPAZE", 120, 300, 570, 600), it("63", 1220, 1270, 570, 600), it("Viên", 1290, 1370, 570, 600)]),
        _make_row([it("Ngày uống 3 lần, mỗi lần 1 Viên", 120, 620, 610, 640)]),
        _make_row([it("5.", 70, 95, 660, 690), it("BIOCID MH", 120, 340, 660, 690), it("21", 1220, 1270, 660, 690), it("Chai", 1290, 1370, 660, 690)]),
        _make_row([it("Ngày uống 3 lần, mỗi lần 1/3 Chai", 120, 640, 700, 730)]),
        _make_row([it("G.", 70, 95, 750, 780), it("DIGLUMISAN", 120, 360, 750, 780), it("63", 1220, 1270, 750, 780), it("Ống", 1290, 1370, 750, 780)]),
        _make_row([it("Ngày uống 3 lần, mỗi lần 1 Ống", 120, 620, 790, 820)]),
        _make_row([it("Cộng khoản: 6", 80, 320, 860, 895)]),
    ]
    lines = [item for row in rows for item in row["items"]]
    return {
        "rows": rows,
        "lines": lines,
        "raw_text": "\n".join(row["text"] for row in rows),
    }


def test_layout_b_extracts_all_7_drugs_and_quantities():
    ocr = _build_layout_b_ocr_json()
    parsed = extract_schema_from_ocr(ocr, doc_type="prescription")
    meds = parsed["medications"]

    assert len(meds) == 7, f"Expected 7 meds, got {len(meds)}: {[m['name'] for m in meds]}"
    assert [m["source_ordinal"] for m in meds] == [1, 2, 3, 4, 5, 6, 7]

    expected = [
        ("Ducray Kelual DS", "1 lọ", "Dùng ngoài"),
        ("Silkron", "3 tuýp", "Dùng ngoài da"),
        ("EMOLEUM LIPID BALM", "1 tuýp", "Dùng ngoài da"),
        ("Halcort 6", "30 viên", "Đường uống"),
        ("Destidin", "30 viên", "Đường uống"),
        ("Mardekin", "1 hộp", "Đường uống"),
        ("HB DIGIC", "60 viên", "Đường uống"),
    ]
    for med, (exp_name, exp_qty, exp_route) in zip(meds, expected):
        assert med["name"] == exp_name
        assert med["quantity"] == exp_qty
        assert med["route"] == exp_route
        assert med["huong_dan"], f"Missing verbatim huong_dan for {med['name']}"

    # Kiểm tra hành chính Layout B
    assert parsed["patient_name"] == ""
    assert parsed["dob"] == ""
    assert parsed["clinic"] == "Nội 4"
    assert "XÂY DỰNG" in parsed["facility"].upper()
    assert parsed["date"] == "22/11/2018"
    assert "Eczema phản ứng giai đoạn cấp tính" in parsed["diagnosis"]


def test_layout_a_still_passes_with_6_drugs_G_as_6_and_arthur_63():
    ocr = _build_layout_a_ocr_json()
    parsed = extract_schema_from_ocr(ocr, doc_type="prescription")
    meds = parsed["medications"]

    assert len(meds) == 6, f"Expected 6 meds, got {len(meds)}: {[m['name'] for m in meds]}"
    names = [m["name"] for m in meds]
    assert not any("banitase" in n.lower() for n in names)
    assert [m["source_ordinal"] for m in meds] == [1, 2, 3, 4, 5, 6]

    arthur = next(m for m in meds if "ARTHUR" in m["name"].upper())
    assert arthur["quantity"] == "63 viên"
    assert arthur["active_ingredient"] == "Trimebutine 200"

    biocid = next(m for m in meds if "BIOCID" in m["name"].upper())
    assert biocid["dose"] == "1/3 chai"
    assert biocid["quantity"] == "21 chai"

    diglumisan = next(m for m in meds if "DIGLUMISAN" in m["name"].upper())
    assert diglumisan["source_ordinal"] == 6
    assert diglumisan["quantity"] == "63 ống"

    # Năm sinh = 2014 - 49 = 1965
    assert parsed["dob"] == "1965"

    # Đảm bảo trimebutine không còn nằm trong keyword của Banitase
    for entry in VIETNAM_CLINICAL_KB:
        if "banitase" in entry["name"].lower():
            assert "trimebutine" not in entry["keywords"]


def test_ordinal_without_dot_is_recognized_as_drug_1():
    ocr = {
        "rows": [
            _make_row([_make_item("Chẩn đoán: Viêm da", 80, 400, 100, 130, line_index=1)]),
            _make_row([_make_item("1  Ducray Kelual DS", 120, 560, 180, 215, line_index=2),
                       _make_item("x 1 lọ", 900, 1050, 180, 215, line_index=3)]),
            _make_row([_make_item("Lời dặn: Tái khám sau 2 tuần", 120, 600, 260, 295, line_index=4)]),
        ],
        "lines": [],
        "raw_text": "Chẩn đoán: Viêm da\n1  Ducray Kelual DS | x 1 lọ\nLời dặn: Tái khám sau 2 tuần",
    }
    ocr["lines"] = [it for r in ocr["rows"] for it in r["items"]]
    parsed = extract_schema_from_ocr(ocr, doc_type="prescription")
    assert len(parsed["medications"]) == 1
    assert parsed["medications"][0]["source_ordinal"] == 1
    assert parsed["medications"][0]["name"] == "Ducray Kelual DS"
    assert parsed["medications"][0]["quantity"] == "1 lọ"


def test_right_column_quantity_not_mistaken_for_ordinal():
    ocr = {
        "rows": [
            _make_row([_make_item("Chẩn đoán: Viêm dạ dày", 80, 450, 100, 130, line_index=1)]),
            _make_row([
                _make_item("1", 110, 135, 180, 210, line_index=2),
                _make_item("Halcort 6", 200, 400, 180, 210, line_index=3),
                _make_item("30", 950, 995, 180, 210, line_index=4),
                _make_item("viên", 1040, 1110, 180, 210, line_index=5),
            ]),
            # Một dòng chỉ có số ở cột phải (vd OCR tách riêng số 60) KHÔNG được nhận thành STT
            _make_row([_make_item("60", 950, 995, 230, 260, line_index=6)]),
            _make_row([_make_item("Uống 3 viên/ lần/ ngày, buổi sáng", 200, 820, 265, 295, line_index=7)]),
        ],
        "lines": [],
        "raw_text": "",
    }
    ocr["lines"] = [it for r in ocr["rows"] for it in r["items"]]
    ocr["raw_text"] = "\n".join(r["text"] for r in ocr["rows"])
    parsed = extract_schema_from_ocr(ocr, doc_type="prescription")
    assert len(parsed["medications"]) == 1
    assert parsed["medications"][0]["name"] == "Halcort 6"
    assert parsed["medications"][0]["source_ordinal"] == 1


def test_drug_not_in_db_gets_not_in_db_status_not_error():
    match = normalize_drug_entity("Ducray Kelual DS")
    assert match["status"] == "unmatched"
    # Khi OCR confidence >= 0.70 và tên hợp lệ >= 4 chữ cái -> card_status phải là not_in_db
    ocr_conf = 0.92
    med_name = "Ducray Kelual DS"
    is_clear = ocr_conf >= 0.70 and len(med_name.replace(" ", "")) >= 4
    card_status = "matched" if match["status"] == "matched" else ("not_in_db" if is_clear else "uncertain")
    assert card_status == "not_in_db"


def test_body_bounds_ends_at_loi_dan_without_cong_khoan():
    ocr = _build_layout_b_ocr_json()
    start, end = _prescription_body_bounds(ocr["rows"])
    body_texts = [r["text"] for r in ocr["rows"][start:end]]
    assert any("Ducray Kelual DS" in t for t in body_texts)
    assert any("HB DIGIC" in t for t in body_texts)
    assert not any("Lời dặn" in t for t in body_texts)
    assert not any("Hà Nội" in t for t in body_texts)


def test_overlay_box_centers_lie_inside_original_paper():
    ocr = _build_layout_b_ocr_json()
    parsed = extract_schema_from_ocr(ocr, doc_type="prescription")
    meds = parsed["medications"]
    for idx, m in enumerate(meds, start=1):
        m["medicine_id"] = f"MED_{idx:03d}"
        m["card_status"] = "not_in_db"

    # Giả lập kích thước ảnh gốc 1600 x 2000 và hệ số upscale 1.0
    orig_w, orig_h = 1600.0, 2000.0
    line_to_med = {
        int(li): m["medicine_id"]
        for m in meds for li in m.get("source_line_indices", [])
    }
    detail_boxes = []
    for ln in ocr["lines"]:
        pts = [[p[0] / orig_w, p[1] / orig_h] for p in ln["box"]]
        detail_boxes.append({
            "text": ln["text"],
            "line_index": ln["line_index"],
            "confidence": ln["confidence"],
            "bbox": pts,
            "points": pts,
            "medicine_id": line_to_med.get(ln["line_index"]),
            "status": "not_in_db",
        })

    boxes = _build_default_overlay_boxes(meds, detail_boxes, ocr["rows"], orig_w, orig_h)
    med_boxes = [b for b in boxes if b.get("kind") == "medicine"]
    assert len(med_boxes) == 7
    assert len(boxes) <= 12

    for box in med_boxes:
        xs = [p[0] for p in box["bbox"]]
        ys = [p[1] for p in box["bbox"]]
        cx = (min(xs) + max(xs)) / 2.0
        cy = (min(ys) + max(ys)) / 2.0
        assert 0.0 < cx < 1.0, f"Center x={cx} out of paper bounds for {box['id']}"
        assert 0.0 < cy < 1.0, f"Center y={cy} out of paper bounds for {box['id']}"


def test_dosing_line_starting_with_number_is_not_a_drug_and_spelling_normalized():
    """Dòng liều dùng bị OCR rớt chữ 'Uống' (vd: '3 viên/ lần/ ngày; buổi sáng; sau ànno:')
    không được tách thành thuốc riêng và phải được chuẩn hóa chính tả tiếng Việt."""
    ocr = {
        "rows": [
            _make_row([_make_item("Chẩn đoán: Eczema", 80, 420, 100, 130, line_index=1)]),
            _make_row([
                _make_item("4", 120, 145, 200, 235, line_index=2),
                _make_item("Halcort 6", 220, 420, 200, 235, line_index=3),
                _make_item("x", 820, 845, 200, 235, line_index=4),
                _make_item("30", 930, 975, 200, 235, line_index=5),
                _make_item("viên", 1070, 1140, 200, 235, line_index=6),
            ]),
            _make_row([
                _make_item("3 viên/ lần/ ngày; buổi", 220, 720, 255, 290, line_index=7),
                _make_item("sáng; sau ànno:", 730, 990, 255, 290, line_index=8),
            ]),
            _make_row([_make_item("Lời dặn:", 220, 380, 340, 375, line_index=9)]),
        ],
        "lines": [],
        "raw_text": "",
    }
    ocr["lines"] = [it for r in ocr["rows"] for it in r["items"]]
    ocr["raw_text"] = "\n".join(r["text"] for r in ocr["rows"])
    parsed = extract_schema_from_ocr(ocr, doc_type="prescription")
    meds = parsed["medications"]

    assert len(meds) == 1, f"Expected 1 drug (Halcort 6), got {[m['name'] for m in meds]}"
    assert meds[0]["name"] == "Halcort 6"
    assert meds[0]["dose"] == "3 viên"
    assert meds[0]["frequency"] == "1 lần/ngày"
    assert "sau ăn no." in meds[0]["huong_dan"]
    assert "ànno" not in meds[0]["huong_dan"]

