from core.reconciliation_service import (
    extract_schema_from_ocr,
    is_plausible_medication_name,
    reconcile_parallel_results,
)


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
        _row("YESOM 40 40mg", "Ngày uống 3 lần, mỗi lần", "Viên"),
        _row("SUCRATE GEL", "Ngày uống 3 lần", "Gói"),
        _row("ARTHUR", "Ngày uống 3 lần", "Viên"),
        _row("PAPAZE", "Viên"),
        _row("amylase protease", "Ngày uống", "Viên"),
        _row("Magnesi Hydroxide", "BIOCID MH", "Chai"),
        _row("DIGLUMISAN", "Ngày uống 3 lần", "Ống"),
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


def test_fallback_keeps_six_drug_rows_without_inventing_quantities():
    result = extract_schema_from_ocr(_sample_ocr())
    medications = result["medications"]

    assert [med["name"] for med in medications] == [
        "YESOM 40", "SUCRATE GEL", "ARTHUR", "PAPAZE", "BIOCID MH", "DIGLUMISAN"
    ]
    assert all(med["days"] == "" for med in medications)
    assert all(med["dose"] == "" for med in medications)
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
    assert result["medications"][0]["dose"] == "1 Viên"
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
    assert result["medications"][0]["name"] == "Febuxostat (FORGOUT)"
    assert result["medications"][0]["strength"] == "40mg"
    assert result["medications"][0]["days"].casefold() == "21 viên"


def test_ordinal_in_separate_ocr_row_still_starts_a_medicine():
    rows = [_row("ĐƠN THUỐC"), _row("Chẩn đoán: Gút"), _row("STT"),
            _row("1."), _row("Febuxostat 40mg", "21 Viên"),
            _row("Cộng khoản: 1")]
    ocr = {"raw_text": "\n".join(row["text"] for row in rows), "rows": rows}

    medications = extract_schema_from_ocr(ocr)["medications"]

    assert len(medications) == 1
    assert medications[0]["name"] == "Febuxostat"
    assert medications[0]["days"].casefold() == "21 viên"


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
    assert [med["name"] for med in result["medications"]] == ["YESOM 40"]


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
