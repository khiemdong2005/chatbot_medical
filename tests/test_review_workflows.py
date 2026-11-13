"""Regression cases from the review of triage, intake, retrieval and OCR consent."""
import io
from unittest.mock import patch

import pytest

from core.intake_service import IntakeSessionManager
from core.triage import assess_emergency_risk
from core.rag_service import medical_rag_service


@pytest.mark.parametrize(("message", "expected"), [
    ("Tôi không bị khó thở hay đau ngực, chỉ thấy hơi mệt", False),
    ("Năm ngoái bố tôi bị liệt nửa người, giờ tôi thấy lo", False),
    ("Hôm qua tôi không tức ngực nhưng bây giờ tôi tức ngực", True),
    ("Bố tôi đang ngạt thở", True),
    ("Không tức ngực hay ngạt thở", False),
])
def test_red_flag_scope(message, expected):
    assert assess_emergency_risk(message)["is_emergency"] is expected


def test_abdominal_pain_follow_up(test_app):
    manager = IntakeSessionManager()
    with patch.object(medical_rag_service, "retrieve_context", return_value=[]):
        first = manager.process_message("opqrst", "Bác sĩ ơi tôi đau bụng quá", guest_token="review_test_guest")
        assert "vị trí" in first["next_question"]
        assert first["summary"]["part_b_system_assessment"]["triage_badge"] == "collecting"
        manager.process_message("opqrst", "quanh rốn", guest_token="review_test_guest")
        result = manager.process_message("opqrst", "đau quặn 2 ngày, lan ra lưng, 6/10", guest_token="review_test_guest")
        pain = result["summary"]["part_a_patient_facts"]["pain"]
        assert pain == {"location": "quanh rốn", "quality": "quặn", "radiation": "lan ra lưng", "severity": "6/10"}
        assert "2 ngày" in result["facts"]["duration"]


@pytest.mark.parametrize(("kind", "rows_key", "original", "edit"), [
    ("prescription", "medications", {"name": "QA", "strength": "50 mg"}, {"name": "QA", "strength": "5 mg"}),
    ("lab_test", "metrics", {"test_name": "QA", "result": "50", "reference_range": "1 - 9"},
     {"test_name": "QA", "result": "5", "reference_range": "1 - 9"}),
])
def test_review_then_validate(client, test_users, kind, rows_key, original, edit):
    import core.pipeline_orchestrator as pipe
    uid = test_users["user_a_id"]
    with client.session_transaction() as session:
        session["user_id"] = uid
    with (patch.object(pipe, "check_image_quality", return_value={"passed": True}),
          patch.object(pipe, "preprocess_lightweight", return_value={}),
          patch.object(pipe, "extract_ocr_parallel", return_value={"lines": [], "raw_text": ""}),
          patch.object(pipe, "extract_with_gemini_schema", return_value={"doc_type": kind, rows_key: [original]}),
          patch.object(pipe, "generate_clinical_interpretation", return_value={}) as interpret,
          patch.object(pipe, "validate_prescription_rules", wraps=pipe.validate_prescription_rules) as drug_check,
          patch.object(pipe, "validate_lab_rules", wraps=pipe.validate_lab_rules) as lab_check):
        scan = client.post("/api/prescription/scan", data={"file": (io.BytesIO(bytes.fromhex("89504e470d0a1a0a") + bytes(250)), "test.png")})
        draft = scan.get_json()
        assert draft["status"] == "review"
        assert not interpret.called and not drug_check.called and not lab_check.called
        assert draft["data"][rows_key][0][next(k for k in edit if edit[k] != original[k])] != ""
        doc_id = draft["document_id"]
        assert not client.get("/api/prescription/history").json["history"]
        detail = f"/api/prescription/history/{doc_id}"
        endpoint = f"/api/prescription/{doc_id}/confirm"
        assert client.get(detail).status_code == 404
        assert client.post(endpoint, json={rows_key: [edit]}).status_code == 400
        payload = {"confirmed": True, rows_key: [edit]}
        assert client.post(endpoint, json=payload).status_code == 200
        assert client.post(endpoint, json=payload).status_code == 409
        assert interpret.call_count == 1
        check = drug_check if kind == "prescription" else lab_check
        for field, value in edit.items():
            assert check.call_args.args[0][0][field] == value
        saved = client.get(detail).json["data"]
        for field, value in edit.items():
            assert saved[rows_key][0][field] == value
        if kind == "lab_test":
            assert saved[rows_key][0]["computed_flag"] == "Normal"
