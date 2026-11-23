"""The scan should recover small type from the original when preprocessing loses it."""

import pytest
from PIL import Image

import core.pipeline_orchestrator as pipe


def _ocr(*texts, confidence=0.9):
    rows = [{"text": text, "items": [{"text": part.strip()}
                                   for part in text.split("|")]} for text in texts]
    lines = [{"text": text, "box": [[10, 10], [110, 10], [110, 30], [10, 30]]}
             for text in texts]
    return {"success": True, "rows": rows, "lines": lines,
            "raw_text": "\n".join(texts), "avg_confidence": confidence}


def _setup_images(tmp_path, monkeypatch):
    original = tmp_path / "original.png"
    processed = tmp_path / "processed.png"
    Image.new("RGB", (400, 600), "white").save(original)
    Image.new("RGB", (400, 600), "white").save(processed)
    monkeypatch.setattr(pipe, "check_image_quality", lambda *a, **kw: {"passed": True})
    monkeypatch.setattr(pipe, "preprocess_lightweight", lambda *a, **kw: {
        "processed_path": str(processed), "orig_shape": (400, 600),
        "to_original": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    })
    return original, processed


def test_local_transcription_preserves_unreadable_rows_without_inferred_values(tmp_path, monkeypatch):
    original, processed = _setup_images(tmp_path, monkeypatch)
    scan = _ocr(
        "ĐƠN THUỐC", "STT | Tên thuốc | SL",
        "1 | Amoxicillin 500mg | 20 Viên",
        "Uống sáng | 1 viên",
        "2 | Paracetamoi (acetaminophen) (Tatanol [5O0mgl) | 14 Viên",
        "Cộng khoản; 2",
    )
    scan["rows"][4]["items"][1]["confidence"] = 0.58
    calls = []
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda path, **kw: calls.append(path) or scan)

    def unexpected_api(*args, **kwargs):
        pytest.fail("Source-only transcription must not use a generative API")

    monkeypatch.setattr(pipe, "extract_with_gemini_schema", unexpected_api)
    monkeypatch.setattr(pipe, "_structure_ocr_text_with_groq", unexpected_api)
    result = pipe.process_prescription_transcription(str(original))

    assert calls == [str(processed)]
    assert not result["medication_count_mismatch"]
    first, second = result["medications"]
    assert first["name"] == "Amoxicillin"
    assert first["dose"] == "1 viên"
    assert first["frequency"] == ""
    assert first["days"] == "20 Viên"
    assert second["name"] == second["strength"] == second["dose"] == second["frequency"] == ""
    assert second["stt"] == "2"
    assert second["raw_ocr_name"].startswith("Paracetamoi")
    assert second["days"] == "14 Viên"
    assert second["needs_review"] is True


def test_local_transcription_keeps_product_marked_rows_and_ignores_fragments(tmp_path, monkeypatch):
    original, _ = _setup_images(tmp_path, monkeypatch)
    scan = _ocr(
        "ĐƠN THUỐC", "STT | Tên thuốc | SL",
        "1 Althax [KDNTI | 20 Vin",
        "JO(mg | Jonon",
        "524 | Cha",
        "Cclimned | Aouwg | [KDNT] WUmg | 10 Ven",
        "Cộng khoản: 2",
    )
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda path, **kw: scan)

    result = pipe.process_prescription_transcription(str(original))

    assert not result["medication_count_mismatch"]
    names = result["medications"]
    assert [med["name"] for med in names] == ["Althax", "Cclimned"]
    assert names[0]["stt"] == "1"
    assert not names[0]["quantity"]
    assert not names[1]["quantity"]


@pytest.mark.parametrize(("reread", "expected_name"), [
    ("Naproxen (Ameproxen 500 [500mgl)", "Naproxen"),
    ("Naproxol (Ameproxen 500 [500mgl)", ""),
    ("", ""),
])
def test_vietocr_rereads_uncertain_name_cell_without_replacing_conflicting_text(
        tmp_path, monkeypatch, reread, expected_name):
    original, processed = _setup_images(tmp_path, monkeypatch)
    scan = _ocr(
        "ĐƠN THUỐC", "STT | Tên thuốc | SL",
        "1 | Amoxicillin 500mg | 20 Viên",
        "2 | Naproxen (Ameproxen 500 [soOmgl) | 7 Viên",
        "Cộng khoản: 2",
    )
    clear_box = [[20, 25], [210, 25], [210, 52], [20, 52]]
    uncertain_box = [[20, 65], [210, 65], [210, 92], [20, 92]]
    scan["rows"][2]["items"][1]["box"] = clear_box
    scan["rows"][3]["items"][1].update(box=uncertain_box, confidence=0.45)
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda path, **kw: scan)
    crops = []

    def reader(path):
        assert path == str(processed)
        return lambda box: crops.append(box) or reread

    monkeypatch.setattr(pipe, "reread_name_cells", reader)

    result = pipe.process_prescription_transcription(str(original))

    assert crops == [uncertain_box]
    first, second = result["medications"]
    assert first["name"] == "Amoxicillin"
    assert second["name"] == expected_name
    assert second["vietocr_text"] == reread
    assert second["days"] == "7 Viên"
    assert second["strength"] == second["dose"] == ""
    assert second["needs_review"] is True


def test_scan_uses_original_image_when_processed_ocr_loses_drug_row(tmp_path, monkeypatch):
    from core import prescription_crop_service

    original, processed = _setup_images(tmp_path, monkeypatch)
    scans = {
        str(processed): _ocr("ĐƠN THUỐC", "Họ tên: TRẦN BÌNH"),
        str(original): _ocr("ĐƠN THUỐC", "Họ tên: TRẦN BÌNH", "Chẩn đoán: Gút",
                            "1. Febuxostat 40mg | 21 Viên", "Cộng khoản: 1"),
    }
    calls = []
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda path, **kw: (
        calls.append(path) or scans[path]))
    crop_sources = []
    monkeypatch.setattr(prescription_crop_service, "crop_and_upscale_medication_region",
                        lambda path, ocr: crop_sources.append((path, ocr)))
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: None)

    result = pipe.process_medical_document_pipeline(str(original), doc_type_hint="prescription")

    assert calls == [str(processed), str(original)]
    assert crop_sources == [(str(original), scans[str(original)])]
    assert [item["name"] for item in result["data"]["medications"]] == ["Febuxostat"]
    assert result["boxes"][0]["points"][0] == [10 / 400, 10 / 600]


def test_clear_processed_ocr_does_not_repeat_expensive_pass(tmp_path, monkeypatch):
    original, processed = _setup_images(tmp_path, monkeypatch)
    good = _ocr("ĐƠN THUỐC", "Họ tên: TRẦN BÌNH", "Chẩn đoán: Gút",
                "1. Amlodipine 5mg | 7 Viên",
                "2. Metformin 500mg | 14 Viên | Hẹn tái khám ngày 01/10",
                "Cộng khoản: 2")
    calls = []
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda path, **kw: (
        calls.append(path) or good))
    vision_calls = []
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda path, **kw: (
        vision_calls.append(path) or {"doc_type": "prescription", "medications": []}))

    result = pipe.process_medical_document_pipeline(str(original), doc_type_hint="prescription")

    assert calls == [str(processed)]
    assert vision_calls == [str(processed)]
    assert [row["name"] for row in result["data"]["medications"]] == ["Amlodipine", "Metformin"]
    assert result["medication_count_mismatch"] is False


@pytest.mark.parametrize("printed_total", ["Tổng số khoản: | 2", "Cộng khoản; 2"])
def test_scan_warns_when_reconciled_medication_count_disagrees_with_printed_total(tmp_path, monkeypatch, printed_total):
    original, processed = _setup_images(tmp_path, monkeypatch)
    scans = {
        str(processed): _ocr("ĐƠN THUỐC", "Chẩn đoán: đau họng",
                            "1. Febuxostat 40mg | 21 Viên", printed_total),
        str(original): _ocr("ĐƠN THUỐC", "Chẩn đoán: đau họng", "1. Febuxostat 40mg | 21 Viên"),
    }
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda path, **kw: scans[path])
    vision_calls = []
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda path, **kw: (
        vision_calls.append(path) or {"doc_type": "prescription", "medications": []}))

    result = pipe.process_medical_document_pipeline(str(original), doc_type_hint="prescription")

    assert result["medication_count_mismatch"] is True
    assert "Đọc được 1 dòng thuốc. Đơn ghi tổng cộng 2 dòng." in result["extraction_warning"]
    assert [row["name"] for row in result["medications"]] == ["Febuxostat"]
    assert vision_calls == [str(processed)]


def test_missing_row_retry_runs_after_vision_and_uses_same_result(tmp_path, monkeypatch):
    original, processed = _setup_images(tmp_path, monkeypatch)
    partial_rows = (
        "ĐƠN THUỐC", "Họ tên: TRẦN BÌNH", "Chẩn đoán: Gút",
        "1. Amlodipine 5mg | 7 Viên",
    )
    scans = {
        str(processed): _ocr(*partial_rows, "Cộng khoản; 2"),
        str(original): _ocr(*partial_rows, "2. Metformin 500mg | 14 Viên", "Cộng khoản: 2"),
    }
    calls = []
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda path, **kw: (
        calls.append(("ocr", path)) or scans[path]))
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda path, **kw: (
        calls.append(("vision", path)) or {"doc_type": "prescription", "medications": []}))

    result = pipe.process_medical_document_pipeline(str(original), doc_type_hint="prescription")

    assert calls == [("ocr", str(processed)), ("vision", str(processed)), ("ocr", str(original))]
    assert [row["name"] for row in result["data"]["medications"]] == ["Amlodipine", "Metformin"]
    assert result["medication_count_mismatch"] is False


def test_ocr_medication_total_excludes_dispensed_quantities():
    assert pipe._ocr_medication_totals(
        "Tổng cộng: 21 viên\nCộng khoản: 1.000\nCộng khoản; 5 | Viên"
    ) == set()


def test_masked_scan_does_not_send_unmasked_original_to_model(tmp_path, monkeypatch):
    original, processed = _setup_images(tmp_path, monkeypatch)
    masked = tmp_path / "masked.png"
    Image.new("RGB", (400, 600), "white").save(masked)
    calls = []
    monkeypatch.setattr(pipe, "mask_pii_on_image", lambda *a, **kw: str(masked))
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda *a, **kw: _ocr("ĐƠN THUỐC"))
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda path, **kw: (
        calls.append(path) or None))

    result = pipe.process_medical_document_pipeline(
        str(original), doc_type_hint="prescription", mask_pii=True)

    assert calls == [str(masked)]
    assert result["data"]["medications"] == []
    assert "Chưa đọc được dòng thuốc" in result["extraction_warning"]


def test_review_keeps_model_name_and_original_ocr_spelling(tmp_path, monkeypatch):
    original, _processed = _setup_images(tmp_path, monkeypatch)
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda *a, **kw: _ocr(
        "ĐƠN THUỐC", "Chẩn đoán: đau họng", "1. Cclimned 500mg | 20 Viên",
        "Cộng khoản: 1",
    ))
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: {
        "doc_type": "prescription", "medications": [{"name": "Cefimed", "strength": "500mg"}],
    })

    result = pipe.process_medical_document_pipeline(str(original), doc_type_hint="prescription")

    medicine = result["data"]["medications"][0]
    assert medicine["name"] == "Cefimed"
    assert medicine["raw_ocr_name"] == "Cclimned"
    assert medicine["needs_review"] is True


def test_review_maps_medicine_anchor_to_original_image(tmp_path, monkeypatch):
    original, _processed = _setup_images(tmp_path, monkeypatch)
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda *a, **kw: _ocr(
        "ĐƠN THUỐC", "1. Althax 120mg",
    ))
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: None)
    monkeypatch.setattr(pipe, "reconcile_parallel_results", lambda *a, **kw: {
        "medications": [{"name": "Althax", "needs_review": True,
                         "anchor_evidence_text": "1. Althax 120mg",
                         "anchor_box": [[20, 40], [120, 40], [120, 60], [20, 60]]}],
    })

    result = pipe.process_medical_document_pipeline(str(original), doc_type_hint="prescription")

    medicine = result["data"]["medications"][0]
    assert medicine["anchor_evidence_text"] == "1. Althax 120mg"
    assert medicine["anchor_points"] == [
        [20 / 400, 40 / 600], [120 / 400, 40 / 600],
        [120 / 400, 60 / 600], [20 / 400, 60 / 600],
    ]


def test_unexpected_model_payload_falls_back_to_ocr(tmp_path, monkeypatch):
    original, processed = _setup_images(tmp_path, monkeypatch)
    good = _ocr("ĐƠN THUỐC", "Họ tên: TRẦN BÌNH", "Chẩn đoán: Gút",
                "1. Febuxostat 40mg | 21 Viên", "Cộng khoản: 1")
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda *a, **kw: good)
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: ["bad schema"])

    result = pipe.process_medical_document_pipeline(str(original), doc_type_hint="prescription")

    assert result["extraction_source"] == "ocr_only"
    assert [item["name"] for item in result["data"]["medications"]] == ["Febuxostat"]


def test_model_type_correction_rescores_ocr_images(tmp_path, monkeypatch):
    original, processed = _setup_images(tmp_path, monkeypatch)
    scans = {
        str(processed): _ocr("ĐƠN THUỐC"),
        str(original): _ocr("PHIẾU XÉT NGHIỆM", "Họ tên: TRẦN BÌNH",
                            "Glucose | 7.8 | mmol/L | 3.9 - 6.4 | High"),
    }
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda path, **kw: scans[path])
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: {
        "doc_type": "lab_test", "metrics": []})

    result = pipe.process_medical_document_pipeline(str(original), doc_type_hint="prescription")

    assert result["doc_type"] == "lab_test"
    assert result["data"]["metrics"][0]["test_name"] == "Glucose"
