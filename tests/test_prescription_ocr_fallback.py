from core.reconciliation_service import (
    extract_schema_from_ocr,
    is_plausible_medication_name,
    reconcile_parallel_results,
)
from core.grounding_service import normalize_drug_entity
from core.prescription_crop_service import detect_medication_bounds
from core.pipeline_orchestrator import _build_default_overlay_boxes
from unittest.mock import patch


def _row(*texts, confidence=0.9):
    return {
        "text": " | ".join(texts),
        "items": [{"text": text, "confidence": confidence} for text in texts],
    }


def _sample_ocr():
    rows = [
        _row('unreadable header"'),
        _row("ĐƠN THUỐC"),
        _row("Họ tên: TRẦN BÌNH"),
        _row("Chẩn đoán: đau bụng"),
        _row("1. YESOM 40 40mg", "Ngày uống 3 lần, mỗi lần 1 Viên", "Viên"),
        _row("2. SUCRATE GEL", "Ngày uống 3 lần, mỗi lần 1 Gói", "Gói"),
        _row("3. ARTHUR", "Ngày uống 3 lần, mỗi lần 1 Viên", "Viên"),
        _row("4. PAPAZE"),
        _row("5. BIOCID MH", "Ngày uống 3 lần, mỗi lần 1 Chai", "Chai"),
        _row("6. DIGLUMISAN", "Ngày uống 3 lần, mỗi lần 1 Ống", "Ống"),
        _row("Cộng khoản: 6"),
        _row("25/09/2014"),
        _row("Bác sĩ điều trị"),
        _row("Tái khám: 16/10/2014", "Nguyễn Văn An"),
    ]
    return {
        "raw_text": "\n".join(row["text"] for row in rows),
        "rows": rows,
        "lines": [item for row in rows for item in row["items"]],
    }


def test_obvious_ocr_fragments_are_not_medication_names():
    for value in ("09/2014", "2 Viên", "ÔNG", "Bác sĩ điều trị", "Cộng khoản: 6",
                  "Bệnh viện Bình Dân"):
        assert not is_plausible_medication_name(value)
    assert is_plausible_medication_name("YESOM 40")


def test_model_only_banitase_is_not_added_for_unrelated_ocr_fragment():
    ocr = _sample_ocr()
    # The table contains an unrelated short OCR fragment, while the model
    # hallucinates a catalog drug. That candidate has no row level evidence.
    ocr["rows"].insert(-4, _row("Anan", "100mg"))
    ocr["lines"] = [item for row in ocr["rows"] for item in row["items"]]
    ocr["raw_text"] = "\n".join(row["text"] for row in ocr["rows"])
    model = {"medications": [
        {"name": "YESOM 40"}, {"name": "SUCRATE GEL"},
        {"name": "ARTHUR"}, {"name": "PAPAZE"},
        {"name": "amylase protease"}, {"name": "DIGLUMISAN"},
        {"name": "Banitase 100mg"},
    ]}

    result = reconcile_parallel_results(ocr, model, "prescription")

    assert "Banitase 100mg" not in [med["name"] for med in result["medications"]]


def test_unmatched_banitase_is_rendered_as_ocr_text_for_manual_review():
    ocr = _sample_ocr()
    ocr["rows"].insert(-4, _row("Anan", "100mg"))
    ocr["lines"] = [item for row in ocr["rows"] for item in row["items"]]
    ocr["raw_text"] = "\n".join(row["text"] for row in ocr["rows"])
    fallback = {"medications": [{"name": "Banitase 100mg", "strength": "100mg",
                                 "raw_ocr_name": "Anan"}]}

    with patch("core.reconciliation_service.extract_schema_from_ocr", return_value=fallback):
        result = reconcile_parallel_results(ocr, {"medications": []}, "prescription")

    meds = result["medications"]
    assert len(meds) == 1
    assert meds[0]["name"] == "Anan"
    assert meds[0]["needs_review"] is True


def _six_numbered_prescription_rows(total=6):
    rows = [_row("Chẩn đoán: Viêm dạ dày")]
    entries = [
        ("YESOM 40 40mg (Esomeprazol 40mg)", "63 Viên", "3 lần", "1 Viên"),
        ("SUCRATE GEL (Sucralfate 1g (gói))", "63 Gói", "3 lần", "1 Gói"),
        ("ARTHUR (Trimebutine 200)", "63 Viên", "3 lần", "1 Viên"),
        ("PAPAZE (magnesi aluminometasilicate, na bicarbonate, cao scopolia, alpha amylase, beta amylase, protease)", "63 Viên", "3 lần", "1 Viên"),
        ("BIOCID MH 3.5+2g (Nhôm Hydroxide 3.5+2g, Magnesi Hydroxide 100ml)", "21 Chai", "3 lần", "1/3 Chai"),
        ("DIGLUMISAN (L-Arginine Hydrochloride 1000mg)", "63 Ống", "3 lần", "1 Ống"),
    ]
    for index, (name, quantity, freq, dose) in enumerate(entries, start=1):
        unit = dose.split()[-1]
        rows.append(_row(f"{index}.", name, quantity))
        rows.append(_row(f"Ngày uống {freq}, mỗi lần {dose}"))
    rows.extend([_row("Cộng khoản: " + str(total)), _row("Anan"), _row("Lời dặn: tái khám")])
    return rows


def test_numbered_sample_returns_six_and_never_banitase():
    rows = _six_numbered_prescription_rows()
    ocr = {"rows": rows, "lines": [item for row in rows for item in row["items"]],
           "raw_text": "\n".join(row["text"] for row in rows)}

    result = extract_schema_from_ocr(ocr, "prescription")
    names = [med["name"] for med in result["medications"]]

    assert len(names) == 6
    assert result["expected_medication_count"] == 6
    assert names == ["YESOM 40", "SUCRATE GEL", "ARTHUR", "PAPAZE", "BIOCID MH 3.5+2g", "DIGLUMISAN"]
    assert not any("banitase" in name.casefold() for name in names)
    assert [med["quantity"] for med in result["medications"]] == [
        "63 viên", "63 gói", "63 viên", "63 viên", "21 chai", "63 ống"
    ]
    assert [med["active_ingredient"] for med in result["medications"]] == [
        "Esomeprazol 40mg", "Sucralfate 1g (gói)", "Trimebutine 200",
        "magnesi aluminometasilicate, na bicarbonate, cao scopolia, alpha amylase, beta amylase, protease",
        "Nhôm Hydroxide 3.5+2g, Magnesi Hydroxide 100ml", "L-Arginine Hydrochloride 1000mg",
    ]
    assert result["medications"][2]["quantity"] == "63 viên"
    assert result["medications"][4]["dose"] == "1/3 chai"


def test_ocr_g_prefix_is_recovered_as_number_six():
    rows = [_row("Chẩn đoán: đau bụng")]
    for index in range(1, 6):
        rows.extend([_row(f"{index}. DRUG{index}", f"10 Viên"),
                     _row("Ngày uống 1 lần, mỗi lần 1 Viên")])
    rows.extend([_row("G. DIGLUMISAN", "63 Ống"),
                 _row("Cộng khoản: 6")])
    result = extract_schema_from_ocr({
        "rows": rows, "lines": [item for row in rows for item in row["items"]],
        "raw_text": "\n".join(row["text"] for row in rows),
    }, "prescription")
    assert len(result["medications"]) == 6
    assert result["medications"][-1]["source_ordinal"] == 6
    assert result["medications"][-1]["name"] == "DIGLUMISAN"


def test_admin_fields_use_their_anchor_row_and_prescription_year():
    rows = [
        _row("BỆNH VIỆN BÌNH DÂN | Phòng khám: Dịch Vụ 109 - (KTC)"),
        _row("Họ tên: NGUYEN VAN A | Phái: Nam | Tuổi: 49"),
        _row("Chẩn đoán: Viêm dạ dày cấp khác"),
        _row("Chẩn đoán: Viêm dạ dày cấp khác"),
        _row("Ngày khám: Ngày 25 tháng 9 năm 2014"),
        _row("1. YESOM 40 40mg", "63 Viên"),
        _row("Cộng khoản: 1"),
    ]
    parsed = extract_schema_from_ocr({
        "rows": rows, "lines": [item for row in rows for item in row["items"]],
        "raw_text": "\n".join(row["text"] for row in rows),
    }, "prescription")

    assert parsed["patient_name"] == "NGUYEN VAN A"
    assert parsed["gender"] == "Nam"
    assert parsed["age"] == "49"
    assert parsed["dob"] == "1965"
    assert parsed["facility"] == "BÌNH DÂN"
    assert parsed["clinic"] == "Dịch Vụ 109 - (KTC)"
    assert parsed["date"] == "25/9/2014"
    assert parsed["diagnosis"] == "Viêm dạ dày cấp khác"


def test_an_an_fragment_does_not_match_banitase():
    match = normalize_drug_entity("Anan")
    assert match["status"] == "unmatched"
    assert match["standard_name"] == "Anan"
    assert match["match_confidence"] < 85
    assert match["purpose"] == ""


def test_default_overlay_has_one_box_per_medicine_and_at_most_three_headers():
    meds = [{"medicine_id": f"MED_{i:03d}", "name": name,
             "source_line_indices": [i], "match_status": "matched",
             "needs_review": False, "ocr_confidence": 0.95}
            for i, name in enumerate(("YESOM 40", "SUCRATE GEL", "ARTHUR",
                                      "PAPAZE", "BIOCID MH", "DIGLUMISAN"), 1)]
    detail = [{"line_index": i, "medicine_id": f"MED_{i:03d}",
               "points": [[0.1, i / 10], [0.8, i / 10], [0.8, i / 10 + 0.02],
                          [0.1, i / 10 + 0.02]], "confidence": 0.95}
              for i in range(1, 7)]
    rows = [{"text": label, "items": [{"line_index": idx}]}
            for label, idx in (("Họ tên: NGUYEN VAN A", 20),
                               ("Chẩn đoán: Viêm dạ dày", 21),
                               ("Ngày khám 25/09/2014", 22))]
    detail.extend({"line_index": idx, "points": [[0.1, 0.1], [0.8, 0.1],
                                                   [0.8, 0.12], [0.1, 0.12]],
                   "confidence": 0.9} for idx in (20, 21, 22))
    boxes = _build_default_overlay_boxes(meds, detail, rows, 1600, 2200)

    assert len([box for box in boxes if box["kind"] == "medicine"]) == 6
    assert len(boxes) <= 12


def test_crop_region_stops_before_signature_and_footer():
    rows = [
        {"text": "Chẩn đoán: đau bụng", "y_min": 100, "y_max": 120, "items": []},
        {"text": "1. YESOM 40mg", "y_min": 140, "y_max": 160, "items": []},
        {"text": "Ngày uống 3 lần", "y_min": 170, "y_max": 190, "items": []},
        {"text": "Cộng khoản: 1", "y_min": 240, "y_max": 260, "items": []},
        {"text": "Lời dặn, chữ ký", "y_min": 300, "y_max": 330, "items": []},
    ]

    bounds = detect_medication_bounds([], rows, 400, 600)

    assert bounds is not None
    assert bounds[1] < rows[0]["y_min"]
    assert rows[3]["y_max"] < bounds[3] < rows[4]["y_min"]


def test_unnumbered_noise_is_ignored_and_missing_total_count_warns():
    rows = [_row("Chẩn đoán: đau bụng"), _row("Anan 100mg"),
            _row("1.", "YESOM 40mg", "10 Viên"),
            _row("Ngày uống 2 lần, mỗi lần 1 Viên"),
            _row("Cộng khoản: 2"), _row("Lời dặn: tái khám")]
    ocr = {"rows": rows, "lines": [item for row in rows for item in row["items"]],
           "raw_text": "\n".join(row["text"] for row in rows)}
    extracted = extract_schema_from_ocr(ocr, "prescription")
    reconciled = reconcile_parallel_results(ocr, {"medications": []}, "prescription")

    assert len(extracted["medications"]) == 1
    assert extracted["medications"][0]["name"].startswith("YESOM")
    assert reconciled["count_warning"] == "Có thể thiếu thuốc, vui lòng đối chiếu ảnh gốc"


def test_numbered_medicine_blocks_stop_at_cum_khoan():
    rows = _six_numbered_prescription_rows(total=2)
    ocr = {"rows": rows, "lines": [item for row in rows for item in row["items"]],
           "raw_text": "\n".join(row["text"] for row in rows)}
    reconciled = reconcile_parallel_results(ocr, {"medications": []}, "prescription")

    assert len(reconciled["medications"]) == 2
    assert "nhiều hơn Cộng khoản 2" in reconciled["count_warning"]


def test_fallback_keeps_six_drug_rows_without_inventing_quantities():
    result = extract_schema_from_ocr(_sample_ocr())
    medications = result["medications"]

    assert [med["name"] for med in medications] == [
        "YESOM 40", "SUCRATE GEL", "ARTHUR", "PAPAZE", "BIOCID MH", "DIGLUMISAN"
    ]
    assert all(med["days"] is None for med in medications)
    assert result["patient_name"] == "TRẦN BÌNH"
    assert result["date"] == "25/09/2014"
    assert result["doctor"] == "Nguyễn Văn An"
    assert result["facility"] == ""


def test_reconciliation_uses_ocr_medicine_rows_for_count_and_order():
    ocr = _sample_ocr()
    model = {
        "medications": [
            {"name": 'unreadable header"', "dose": "", "frequency": ""},
            {"name": "YESOM 40 40mg (Esomeprazole)", "dose": "1 Viên", "frequency": "3 lần/ngày"},
            {"name": "amylase protease", "dose": "", "frequency": ""},
            {"name": "09/2014", "dose": "", "frequency": ""},
        ]
    }
    result = reconcile_parallel_results(ocr, model, "prescription")

    assert [med["name"] for med in result["medications"]] == [
        "YESOM 40", "SUCRATE GEL", "ARTHUR", "PAPAZE", "BIOCID MH", "DIGLUMISAN"
    ]
    assert result["medications"][0]["dose"].casefold() == "1 viên"
    assert result["medications"][0]["needs_review"] is True
    assert result["medications"][0]["field_confidence"] < 0.95


def test_conflicting_header_values_use_labeled_ocr_and_offer_model_reading():
    ocr = _sample_ocr()
    model = {
        "patient_name": "PHẠM VĂN SAI",
        "doctor": "Lê Văn Khác",
        "date": "26/09/2014",
        "diagnosis": "Viêm họng",
        "medications": [],
    }
    result = reconcile_parallel_results(ocr, model, "prescription")

    assert result["patient_name"] == "TRẦN BÌNH"
    assert result["doctor"] == "Nguyễn Văn An"
    assert result["date"] == "25/09/2014"
    assert result["diagnosis"] == "đau bụng"
    assert result["header_alternatives"] == {
        "patient_name": ["PHẠM VĂN SAI"],
        "doctor": ["Lê Văn Khác"],
        "date": ["26/09/2014"],
        "diagnosis": ["Viêm họng"],
    }
    assert result["reconciliation_review"]["needs_review"] is True


def test_equivalent_header_spellings_do_not_create_conflict():
    result = reconcile_parallel_results(_sample_ocr(), {
        "patient_name": "Tran Binh", "doctor": "BS. Nguyễn Văn An",
        "date": "25/9/2014", "diagnosis": "Đau bụng", "medications": [],
    }, "prescription")

    assert result["patient_name"] == "Tran Binh"
    assert result["header_alternatives"] == {}


def test_one_letter_name_difference_stays_visible_for_review():
    result = reconcile_parallel_results(_sample_ocr(), {
        "patient_name": "TRẦN VINH", "medications": [],
    }, "prescription")

    assert result["patient_name"] == "TRẦN BÌNH"
    assert result["header_alternatives"]["patient_name"] == ["TRẦN VINH"]


def test_ocr_age_is_separate_from_birth_date():
    rows = [_row("ĐƠN THUỐC"), _row("Họ tên: TRẦN BÌNH"), _row("Phal", "NamTubi"), _row("Tuổi: 49")]
    ocr = {
        "raw_text": "\n".join(row["text"] for row in rows),
        "rows": rows,
        "lines": [item for row in rows for item in row["items"]],
    }
    result = extract_schema_from_ocr(ocr)
    assert result["age"] == "49"
    assert result["dob"] == ""
    assert result["gender"] == "Nam"


def test_medicine_count_follows_detected_body_rows():
    rows = [
        _row("ĐƠN THUỐC"),
        _row("Chẩn đoán: đau bụng"),
        _row("1. YESOM 40", "Viên"),
        _row("2. SUCRATE GEL", "Gói"),
        _row("Cộng khoản: 2"),
    ]
    ocr = {
        "raw_text": "\n".join(row["text"] for row in rows),
        "rows": rows,
        "lines": [item for row in rows for item in row["items"]],
    }
    model = {"medications": [
        {"name": "YESOM 40"}, {"name": "SUCRATE GEL"},
        {"name": "09/2014"}, {"name": "Một hoạt chất nằm trong ngoặc"},
    ]}

    result = reconcile_parallel_results(ocr, model, "prescription")
    assert [med["name"] for med in result["medications"]] == ["YESOM 40", "SUCRATE GEL"]


def test_single_febuxostat_row_does_not_turn_table_labels_into_medicines():
    rows = [
        _row("ĐƠN THUỐC"),
        _row("Tên bệnh nhân: NGUYỄN THÀNH KHIÊM"),
        _row("Chẩn đoán: M13.07 / M10"),
        _row("STT", "Tên thuốc", "Hàm lượng", "SL"),
        _row("1.", "Febuxostat (FORGOUT 40mg)", "21 Viên"),
        _row("Uống, sáng 1 viên"),
        _row("Cộng khoản: 1"),
    ]
    ocr = {"raw_text": "\n".join(row["text"] for row in rows), "rows": rows,
           "lines": [item for row in rows for item in row["items"]]}
    model = {"patient_name": "Tên bệnh nhân: NGUYỄN THÀNH KHIÊM",
             "medications": [{"name": "ĐƠN THUỐC"}, {"name": "MIO."},
                             {"name": "STT", "days": "21 viên"},
                             {"name": "Febuxostat", "strength": "40mg"}]}

    result = reconcile_parallel_results(ocr, model, "prescription")

    assert result["patient_name"] == "NGUYỄN THÀNH KHIÊM"
    assert len(result["medications"]) == 1
    assert result["medications"][0]["name"] == "Febuxostat"
    assert result["medications"][0]["active_ingredient"] == "FORGOUT 40mg"
    assert result["medications"][0]["strength"] == "40mg"
    assert result["medications"][0]["days"].casefold() == "21 viên"


def test_ordinal_without_same_row_medicine_name_is_not_a_valid_block():
    rows = [_row("ĐƠN THUỐC"), _row("Chẩn đoán: Gút"), _row("STT"),
            _row("1."), _row("Febuxostat 40mg", "21 Viên"),
            _row("Cộng khoản: 1")]
    ocr = {"raw_text": "\n".join(row["text"] for row in rows), "rows": rows}

    medications = extract_schema_from_ocr(ocr)["medications"]

    assert medications == []


def test_dispensed_quantity_uses_rightmost_number_not_dose():
    rows = [
        _row("ĐƠN THUỐC"),
        _row("Chẩn đoán: đau bụng"),
        _row("1. DIGLUMISAN", "Ngày uống mỗi lần 1/3 Chal", "63", "ONG"),
        _row("Cộng khoản: 1"),
    ]
    ocr = {"raw_text": "\n".join(row["text"] for row in rows), "rows": rows}
    medications = extract_schema_from_ocr(ocr)["medications"]
    assert len(medications) == 1
    assert medications[0]["days"] == "63 ống"


def test_model_facility_and_role_label_never_become_medication_or_doctor():
    # The diagnosis/section label can be lost in a low-resolution photo, so
    # position-based header filtering alone cannot remove this duplicate.
    rows = [_row('egahteasarsaan"'), _row("YESOM 40")]
    ocr = {
        "raw_text": "\n".join(row["text"] for row in rows),
        "rows": rows,
        "lines": [item for row in rows for item in row["items"]],
    }
    model = {
        "doctor": "điều trị",
        "facility": 'egahteasarsaan"',
        "medications": [
            {"name": 'egahteasarsaan"'},
            {"name": "YESOM 40"},
        ],
    }

    result = reconcile_parallel_results(ocr, model, "prescription")

    assert result["doctor"] == ""
    assert result["facility"] == ""
    assert result["medications"] == []


def test_valid_facility_and_named_doctor_remain_available_for_review():
    result = reconcile_parallel_results(
        {"raw_text": "", "rows": [], "lines": []},
        {"facility": "AcmeClinic", "doctor": "BS. Nguyễn Văn Hùng",
         "medications": [{"name": "YESOM 40"}]},
        "prescription",
    )
    assert result["facility"] == "AcmeClinic"
    assert result["doctor"] == "BS. Nguyễn Văn Hùng"


def test_low_confidence_labeled_diagnosis_is_kept_verbatim_for_review():
    rows = [
        _row("ĐƠN THUỐC"),
        _row("Chan doan: VIôm da dòy cóp khác", confidence=0.19),
        _row("YESOM 40", confidence=0.9),
        _row("Cộng khoản: 1"),
    ]
    ocr = {
        "raw_text": "\n".join(row["text"] for row in rows),
        "rows": rows,
        "lines": [item for row in rows for item in row["items"]],
    }

    result = extract_schema_from_ocr(ocr)
    assert result["diagnosis"] == "VIôm da dòy cóp khác"


def test_unreadable_diagnosis_is_not_invented():
    rows = [_row("Chan doan: ???", confidence=0.04)]
    ocr = {"raw_text": rows[0]["text"], "rows": rows, "lines": rows[0]["items"]}
    assert extract_schema_from_ocr(ocr)["diagnosis"] == ""
