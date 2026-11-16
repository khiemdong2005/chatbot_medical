"""Prescription OCR layouts observed in table scans and noisy phone photos."""

from core.reconciliation_service import (
    _merge_medication_rows, extract_schema_from_ocr,
    is_plausible_medication_name, reconcile_parallel_results,
)


def _row(*items, y=None, xs=None):
    cells = [{"text": text, **({"x_min": xs[index]} if xs else {})}
             for index, text in enumerate(items)]
    return {"text": " | ".join(items), "items": cells,
            **({"y_center": y} if y is not None else {})}


def _ocr(rows):
    return {"rows": rows, "lines": [cell for row in rows for cell in row["items"]],
            "raw_text": "\n".join(row["text"] for row in rows)}


def test_quantity_clustering_with_heading_still_yields_one_real_drug():
    rows = [
        _row("ĐƠN THUỐC", y=70, xs=[300]),
        _row("Chẩn đoán: Gút", y=250, xs=[200]),
        _row("STT", "Tên thuỗc", "Hàm lượng", "21 Viên", y=294, xs=[263, 660, 788, 1182]),
        _row("Febuxostat (FORGOUT [Aomgl", y=319, xs=[337]),
        _row("Uống_sáng", "viên", y=356, xs=[336, 485]),
        _row("Cộng khoản: 1", y=391, xs=[233]),
    ]
    result = reconcile_parallel_results(_ocr(rows), {
        "medications": [{"name": "ĐƠN THUỐC"}, {"name": "MIO."}, {"name": "STT"}],
    }, "prescription")

    assert [item["name"] for item in result["medications"]] == ["Febuxostat"]
    assert result["medications"][0]["days"] == "21 viên"
    assert result["medications"][0]["strength"] == ""


def test_noisy_table_keeps_unnumbered_drug_rows_between_numbered_rows():
    rows = [
        _row("ĐON THUÓC"),
        _row("Chn 8oun", "WCIK IOA", "IVDD"),
        _row("Scotols( Shunorac) 2OOmg (IVI00v)", "60Vicn"),
        _row("Ivx 2 Kan nohn(au aw)"),
        _row("2 Dxk hoat TKS vỉén (Lvloov)", "2 Hon"),
        _row("Jvr} lan  \"kà) (souen)"),
        _row("3.Dai Lin gio(iiOoV)", "2 Vien"),
        _row("Buralon", "na(sau ann"),
        _row("Rhcumatin (Ch40v)", "Char"),
        _row("Jvx3 lan / nàv (sau &n)"),
        _row("5, Ginkobil (iVioOv)", "90 Vien"),
        _row("Ivx} lan / nKùy ( sauàn)"),
        _row("JEX ( IC0v)", "Vien"),
        _row("Iv", "lan / \"gY) ( sau &n)"),
        _row("7.Can xon bôp Visn", "Chai"),
        _row("roa", "ung", "dav"),
    ]
    medications = extract_schema_from_ocr(_ocr(rows))["medications"]

    assert len(medications) == 7
    assert [med["name"].split()[0].lower() for med in medications] == [
        "scotols(", "dxk", "dai", "rhcumatin", "ginkobil", "jex", "can"
    ]
    assert medications[0]["days"] == "60 Viên"
    reconciled = reconcile_parallel_results(_ocr(rows),
                                           {"medications": [{"name": med["name"]} for med in medications]},
                                           "prescription")
    assert [med["name"] for med in reconciled["medications"]] == [med["name"] for med in medications]


def test_model_recovers_ocr_parser_miss_only_with_medicine_body_evidence():
    rows = [_row("ĐƠN THUỐC"), _row("Chẩn đoán: đau bụng"),
            _row("1. Paracetamol 500mg", "20 Viên"),
            _row("Amoxicillin 250mg", "10 Viên"),
            _row("Cộng khoản: 2")]
    ocr = _ocr(rows)
    # Emulate an OCR parser which only recognized the first line.
    from unittest.mock import patch
    from core import reconciliation_service as service

    original = service.extract_schema_from_ocr

    def partial_extract(data, doc_type="prescription"):
        parsed = original(data, doc_type)
        parsed["medications"] = parsed["medications"][:1]
        return parsed

    with patch.object(service, "extract_schema_from_ocr", side_effect=partial_extract):
        result = reconcile_parallel_results(ocr, {
            "medications": [{"name": "Paracetamol"}, {"name": "Amoxicillin"},
                            {"name": "Aspirin"}, {"name": "STT"}],
        }, "prescription")

    assert [med["name"] for med in result["medications"]] == ["Paracetamol", "Amoxicillin"]


def test_numbered_quantity_in_following_row_is_not_a_second_drug():
    rows = [_row("ĐƠN THUỐC"), _row("Chẩn đoán: đau họng"),
            _row("1. Cefuroxime 500mg"), _row("SL: 20 Viên"),
            _row("Uống sáng 1 viên"), _row("Cộng khoản: 1")]

    medications = extract_schema_from_ocr(_ocr(rows))["medications"]

    assert len(medications) == 1
    assert medications[0]["name"] == "Cefuroxime"
    assert medications[0]["days"] == "20 viên"


def test_low_confidence_ocr_name_is_flagged_for_review():
    rows = [_row("ĐƠN THUỐC"), _row("Chẩn đoán: đau họng"),
            _row("1. Amoxicillin 500mg", "20 Viên"), _row("Cộng khoản: 1")]
    ocr = _ocr(rows)
    for line in ocr["lines"]:
        line["confidence"] = 0.25 if "Amoxicillin" in line["text"] else 0.95

    result = reconcile_parallel_results(ocr, {"medications": [{"name": "Amoxicillin"}]}, "prescription")

    assert len(result["medications"]) == 1
    assert result["medications"][0]["needs_review"] is True


def test_model_spelling_can_replace_noisy_ocr_without_hiding_original():
    ocr = [{"name": "Cclimned", "strength": "", "usage": 'Cahdur | {ur" YWvC'}]
    model = [{"name": "Cefimed", "strength": "500mg", "usage": "Uống sau ăn"}]

    merged = _merge_medication_rows(ocr, model)

    assert merged[0]["name"] == "Cefimed"
    assert merged[0]["raw_ocr_name"] == "Cclimned"
    assert merged[0]["strength"] == "500mg"
    assert merged[0]["usage"] == "Uống sau ăn"
    assert merged[0]["needs_review"] is True


def test_conflicting_strength_is_not_silently_overwritten():
    merged = _merge_medication_rows(
        [{"name": "Cefimed", "strength": "250mg"}],
        [{"name": "Cefimed", "strength": "500mg"}],
    )

    assert merged[0]["strength"] == "250mg"
    assert merged[0]["needs_review"] is True


def test_unreadable_ocr_strength_shows_model_value_and_original_for_review():
    merged = _merge_medication_rows(
        [{"name": "Cefimed", "strength": "SOmgml"}],
        [{"name": "Cefimed", "strength": "50mg"}],
    )

    assert merged[0]["strength"] == "50mg"
    assert merged[0]["raw_ocr_strength"] == "SOmgml"
    assert merged[0]["needs_review"] is True


def test_garbled_usage_label_is_replaced_by_model_reading():
    merged = _merge_medication_rows(
        [{"name": "Cefimed", "usage": "Cahdur"}],
        [{"name": "Cefimed", "usage": "Uống sau ăn"}],
    )

    assert merged[0]["usage"] == "Uống sau ăn"
    assert merged[0]["needs_review"] is True


def test_garbled_instruction_labels_cannot_be_drug_names():
    assert not is_plausible_medication_name("Cha")
    assert not is_plausible_medication_name("Cahdur")
    assert not is_plausible_medication_name("Cong Chicu")
