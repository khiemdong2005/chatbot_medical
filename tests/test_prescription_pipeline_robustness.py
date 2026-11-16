"""The scan should recover small type from the original when preprocessing loses it."""

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


def test_scan_uses_original_image_when_processed_ocr_loses_drug_row(tmp_path, monkeypatch):
    original, processed = _setup_images(tmp_path, monkeypatch)
    scans = {
        str(processed): _ocr("ĐƠN THUỐC", "Họ tên: TRẦN BÌNH"),
        str(original): _ocr("ĐƠN THUỐC", "Họ tên: TRẦN BÌNH", "Chẩn đoán: Gút",
                            "1. Febuxostat 40mg | 21 Viên", "Cộng khoản: 1"),
    }
    calls = []
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda path, **kw: (
        calls.append(path) or scans[path]))
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: None)

    result = pipe.process_medical_document_pipeline(str(original), doc_type_hint="prescription")

    assert calls == [str(processed), str(original)]
    assert [item["name"] for item in result["data"]["medications"]] == ["Febuxostat"]
    assert result["boxes"][0]["points"][0] == [10 / 400, 10 / 600]


def test_clear_processed_ocr_does_not_repeat_expensive_pass(tmp_path, monkeypatch):
    original, processed = _setup_images(tmp_path, monkeypatch)
    good = _ocr("ĐƠN THUỐC", "Họ tên: TRẦN BÌNH", "Chẩn đoán: Gút",
                "1. Febuxostat 40mg | 21 Viên", "Cộng khoản: 1")
    calls = []
    monkeypatch.setattr(pipe, "extract_ocr_parallel", lambda path, **kw: (
        calls.append(path) or good))
    monkeypatch.setattr(pipe, "extract_with_gemini_schema", lambda *a, **kw: None)

    result = pipe.process_medical_document_pipeline(str(original), doc_type_hint="prescription")

    assert calls == [str(processed)]
    assert len(result["data"]["medications"]) == 1


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
