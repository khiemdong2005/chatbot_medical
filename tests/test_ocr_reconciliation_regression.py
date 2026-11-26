"""Regression tests for prescription OCR auto-detect, body bounds, crop bounds, and reconciliation."""

from unittest.mock import MagicMock, patch

from core.ocr.ocr_parallel_service import extract_ocr_parallel
from core.ocr.prescription_crop_service import detect_medication_bounds
from core.ocr.reconciliation_service import (
    _prescription_body_bounds,
    extract_schema_from_ocr,
    reconcile_parallel_results,
)


def _row(*texts, y_min=0, y_max=30, xs=None, conf=0.9):
    items = []
    for idx, txt in enumerate(texts):
        x0 = xs[idx] if xs else 80 + idx * 250
        items.append({
            "text": txt,
            "confidence": conf,
            "x_min": x0,
            "x_max": x0 + 180,
            "y_min": y_min,
            "y_max": y_max,
            "y_center": (y_min + y_max) / 2.0,
            "box": [[x0, y_min], [x0 + 180, y_min], [x0 + 180, y_max], [x0, y_max]],
        })
    return {
        "text": " | ".join(texts),
        "items": items,
        "x_min": min(i["x_min"] for i in items),
        "x_max": max(i["x_max"] for i in items),
        "y_min": y_min,
        "y_max": y_max,
        "y_center": (y_min + y_max) / 2.0,
    }


def _binh_dan_noisy_rows():
    return [
        _row("0", "Phopo Kham", y_min=45, y_max=115, xs=[100, 350]),
        _row("ĐON THUÓC", y_min=135, y_max=205, xs=[700]),
        _row("Ho ten: TRAN TRUNG", "Phal : NamTubi : 49", y_min=460, y_max=528, xs=[100, 900]),
        _row("Chan coan: Vỉôm da", "doy", "chp khac", y_min=647, y_max=728, xs=[100, 600, 800]),
        _row("YESOM 40 4Omg (Esomcprazol 40m9)", "63", "Vien", y_min=779, y_max=856, xs=[120, 1450, 1650]),
        _row("Ngay", "uÓng", "3 lan, mỖí lán 1 Viên", y_min=830, y_max=911, xs=[120, 300, 500]),
        _row("2. SUCRATE GEL (Sucralíate 1g)", "63", "GÓI", y_min=903, y_max=979, xs=[100, 1450, 1650]),
        _row("Ngay", "uÓng", "3 I8n. mỎi Ián 1 GOI", y_min=956, y_max=1036, xs=[120, 300, 500]),
        _row("6. DIGLUMISAN (L-Arginine Hydrocioride 1OOOmg)", "63", "ONG", y_min=1527, y_max=1600, xs=[100, 1450, 1650]),
        _row("Ngay uong 3 lản, moi làn 1 ONG", y_min=1582, y_max=1657, xs=[120]),
        _row("C(ng khoản;6", y_min=1718, y_max=1787, xs=[120]),
        _row("25/09/2014", y_min=1795, y_max=1858, xs=[1450]),
        _row("Bác sĩ dỉèu tri", y_min=1859, y_max=1934, xs=[1400]),
    ]


def test_body_bounds_includes_unnumbered_first_drug_and_stops_at_noisy_cong_khoan():
    rows = _binh_dan_noisy_rows()
    start, end = _prescription_body_bounds(rows)
    body_texts = [r["text"] for r in rows[start:end]]

    assert any("YESOM 40" in t for t in body_texts), f"YESOM 40 excluded from body: {body_texts}"
    assert any("DIGLUMISAN" in t for t in body_texts)
    assert not any("C(ng khoản;6" in t for t in body_texts)
    assert not any("25/09/2014" in t for t in body_texts)


def test_body_bounds_lookback_skips_dosing_line_even_without_diagnosis_row():
    rows = [r for r in _binh_dan_noisy_rows() if "Chan coan" not in r["text"]]
    start, end = _prescription_body_bounds(rows)
    body_texts = [r["text"] for r in rows[start:end]]

    assert body_texts[0].startswith("YESOM 40"), f"Stopped early on dosing line: {body_texts}"
    assert not any("C(ng khoản;6" in t for t in body_texts)


def test_crop_bounds_ignores_zero_ordinal_and_includes_unnumbered_first_drug():
    rows = [r for r in _binh_dan_noisy_rows() if "Chan coan" not in r["text"]]
    lines = [it for r in rows for it in r["items"]]

    bounds = detect_medication_bounds(lines, rows, img_w=2000, img_h=2587)
    assert bounds is not None
    _x1, y1, _x2, y2 = bounds
    # Must start above YESOM 40 (y=779), NOT at 0 (row "0 | Phopo Kham") and NOT at 852 (chopping YESOM 40)
    assert 400 < y1 <= 779, f"Unexpected crop y1={y1}"
    assert 1650 <= y2 <= 1850, f"Unexpected crop y2={y2}"


def test_noisy_cong_khoan_sets_expected_count_and_never_bleeds_into_usage():
    rows = _binh_dan_noisy_rows()
    ocr = {
        "rows": rows,
        "lines": [it for r in rows for it in r["items"]],
        "raw_text": "\n".join(r["text"] for r in rows),
    }
    schema = extract_schema_from_ocr(ocr, doc_type="prescription")
    assert schema["expected_medication_count"] == 6

    dig = next(m for m in schema["medications"] if "DIGLUMISAN" in m["name"])
    assert "khoản" not in (dig.get("usage") or "").lower()
    assert "25/09/2014" not in (dig.get("usage") or "")


def test_reconcile_keeps_model_drug_when_ocr_missed_ordinal_and_blocks_noisy_usage():
    rows = [
        _row("ĐƠN THUÓC", y_min=100, y_max=150),
        _row("Họ tên: Nguyễn Thị Lợi", y_min=200, y_max=250),
        _row("2 Doc hoat TKS vien (loloov)", "2 Hop", y_min=400, y_max=450, xs=[100, 1400]),
        _row("5. Ginkobil (H/100v)", "90 Vien", y_min=600, y_max=650, xs=[100, 1400]),
        _row("0 bicarbonate cao sccpoiia 3lpha amylase beta", y_min=660, y_max=700, xs=[120]),
    ]
    ocr = {
        "rows": rows,
        "lines": [it for r in rows for it in r["items"]],
        "raw_text": "\n".join(r["text"] for r in rows),
    }
    model = {
        "patient_name": "Nguyễn Thị Lợi",
        "medications": [
            {"stt": 2, "name": "Độc hoạt TKS", "dose": "3v", "frequency": "3 lần / ngày", "quantity": "2 Hộp", "usage": ""},
            {"stt": 5, "name": "Ginkobil", "dose": "1v", "frequency": "3 lần / ngày", "quantity": "90 Viên", "usage": ""},
            {"stt": 9, "name": "Nguyễn Thị Lợi", "quantity": ""},
        ],
    }
    res = reconcile_parallel_results(ocr, model, doc_type="prescription")
    names = [m["name"] for m in res["medications"]]
    assert "Độc hoạt TKS" in names
    assert "Ginkobil" in names
    assert "Nguyễn Thị Lợi" not in names

    gink = next(m for m in res["medications"] if m["name"] == "Ginkobil")
    assert "bicarbonate" not in (gink.get("usage") or "").lower()


def test_auto_doc_type_recognizes_noisy_diacritic_don_thuoc_for_tiled_ocr():
    fake_reader = MagicMock()
    fake_reader.readtext.return_value = [
        ([[10, 10], [200, 10], [200, 50], [10, 50]], "ĐON THUÓC", 0.92),
    ]
    tiled_result = (
        [([[10, 10], [200, 10], [200, 50], [10, 50]], "1. YESOM 40", 0.95)],
        {"tiles": 2, "raw_detected": 1, "dropped_empty": 0, "dropped_low_conf": 0,
         "dropped_dedupe": 0, "low_conf_flagged": 0, "kept_after_ocr": 1},
    )
    with patch("core.ocr.ocr_parallel_service.get_ocr_reader", return_value=fake_reader), \
         patch("core.ocr.ocr_parallel_service._run_tiled_prescription_ocr", return_value=tiled_result) as mock_tiled:
        out = extract_ocr_parallel("dummy.jpg", doc_type="auto")
    assert mock_tiled.call_count == 1
    assert out["filter_stats"]["tiles"] == 2
