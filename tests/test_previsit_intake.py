import json

from core.intake_service import intake_service
from core.models import IntakeSessionRecord, db


def previsit(client, action, **data):
    return client.post(f"/api/intake/{action}", json={"flow": "previsit", **data})


def test_previsit_resumes_questions_and_confirms_guest_draft_after_sign_in(client, test_users, monkeypatch):
    state = previsit(client, "session").get_json()
    cid = state["conversation_id"]
    assert state["next_question"] == "Bạn đang thấy thế nào?"
    assert state["transcript"] == []
    assert state["can_skip"] is False
    assert previsit(client, "message", conversation_id=cid, skip=True).status_code == 400

    def say(message):
        return previsit(client, "message", conversation_id=cid, message=message).get_json()

    state = say("Tôi bị đau bụng từ tối qua")
    assert state["next_question"] == "Bạn đau ở vị trí nào rõ nhất?"
    assert state["summary"]["part_a_patient_facts"]["duration"] == "tối qua"
    assert previsit(
        client, "message", conversation_id=cid, expected_version=state["version"] - 1, message="Sai lượt"
    ).status_code == 409
    state = say("Bên phải")
    assert state["facts"]["pain"]["location"] == "Bên phải"
    assert state["facts"]["contextual_answers"] == []
    assert "cảm giác" in state["next_question"]
    assert state["transcript"] == [
        {"role": "assistant", "text": "Bạn đang thấy thế nào?"},
        {"role": "user", "text": "Tôi bị đau bụng từ tối qua"},
        {"role": "assistant", "text": "Bạn đau ở vị trí nào rõ nhất?"},
        {"role": "user", "text": "Bên phải"},
    ]

    intake_service.clear()
    resumed = previsit(client, "session", conversation_id=cid).get_json()
    assert resumed["next_question"] == state["next_question"]
    assert resumed["version"] == state["version"]
    assert resumed["transcript"] == state["transcript"]

    state = say("Đau âm ỉ")
    assert state["summary"]["ready_to_finalize"] is False
    assert "đỡ hơn" in state["next_question"]
    state = say("Vẫn như cũ")
    for _ in range(4):
        assert state["can_skip"] is True
        skipped_question = state["next_question"]
        state = previsit(client, "message", conversation_id=cid, skip=True).get_json()
        assert state["transcript"][-2:] == [
            {"role": "assistant", "text": skipped_question},
            {"role": "user", "text": "Đã bỏ qua"},
        ]
    assert state["status"] == "ready_for_review"
    assert state["summary"]["ready_to_finalize"] is True
    assert state["next_question"] is None
    assert state["summary"]["part_a_patient_facts"]["patient_reported_history"] == {
        topic: {"status": "skipped", "text": ""} for topic in ("medications", "allergies", "conditions")
    }
    assert any(item["answer"] == "Vẫn như cũ" for item in state["facts"]["contextual_answers"])

    assert client.post("/api/auth/login", json={
        "email": test_users["user_a_email"], "password": "MatKhauUserA123@"
    }).status_code == 200
    assert previsit(client, "session", conversation_id=cid).status_code == 200
    assert previsit(client, "update-fact", conversation_id=cid, field="allergies", value=6).status_code == 400
    assert previsit(
        client, "update-fact", conversation_id=cid, expected_version=state["version"] - 1,
        field="chief_complaint", value="Sửa từ phiên cũ"
    ).status_code == 409
    edited = previsit(
        client, "update-fact", conversation_id=cid,
        expected_version=state["version"],
        field="chief_complaint", value="Đau bụng bên phải từ tối qua"
    ).get_json()
    assert edited["status"] == "ready_for_review"
    assert edited["transcript"] == state["transcript"]
    summary = edited["summary"]
    payload = {
        "conversation_id": cid, "save_to_record": True, "version": summary["version"],
        "reviewed_facts": summary["part_a_patient_facts"]
    }

    def reject_record_commit():
        raise RuntimeError("Simulated consultation write failure")

    with monkeypatch.context() as patch:
        patch.setattr("core.db_utils.commit_or_rollback", reject_record_commit)
        failed = client.post("/api/intake/confirm-summary", json=payload)
    assert failed.status_code == 500
    intake_service.clear()
    assert previsit(client, "session", conversation_id=cid).get_json()["status"] == "ready_for_review"
    assert client.get("/api/consultations").get_json()["consultations"] == []

    saved = client.post("/api/intake/confirm-summary", json=payload)
    assert saved.status_code == 200
    assert previsit(client, "session", conversation_id=cid).get_json()["status"] == "confirmed"


def test_previsit_safety_question_resumes_and_cannot_be_skipped(client, test_app):
    cid = previsit(client, "session").get_json()["conversation_id"]
    warning = previsit(client, "message", conversation_id=cid, message="Tôi không chắc có tức ngực").get_json()
    assert warning["needs_red_flag_confirmation"] is True
    assert warning["can_skip"] is False
    reopened = previsit(client, "session", conversation_id=cid).get_json()
    assert reopened["next_question"] == warning["next_question"]
    assert reopened["transcript"] == [
        {"role": "assistant", "text": "Bạn đang thấy thế nào?"},
        {"role": "user", "text": "Tôi không chắc có tức ngực"},
    ]
    assert previsit(client, "message", conversation_id=cid, skip=True).status_code == 400
    assert previsit(client, "message", conversation_id=cid, message="Không rõ").get_json()["needs_red_flag_confirmation"]
    urgent = previsit(client, "message", conversation_id=cid, message="Có").get_json()
    assert urgent["status"] == "emergency"
    assert urgent["next_question"] is None
    assert urgent["transcript"][-4:] == [
        {"role": "assistant", "text": warning["next_question"]},
        {"role": "user", "text": "Không rõ"},
        {"role": "assistant", "text": warning["next_question"]},
        {"role": "user", "text": "Có"},
    ]
    assert urgent["answer"] not in [turn["text"] for turn in urgent["transcript"]]
    assert previsit(client, "session", conversation_id=cid).get_json()["answer"] == urgent["answer"]

    other = test_app.test_client()
    other.environ_base["HTTP_ORIGIN"] = "http://localhost:5000"
    assert previsit(other, "session", conversation_id=cid).status_code == 403
    assert previsit(other, "session", conversation_id="missing-draft").status_code == 404


def test_previsit_message_can_retry_without_losing_or_duplicating_chat(client, monkeypatch):
    state = previsit(client, "session", lang="en").get_json()
    cid = state["conversation_id"]
    payload = {"conversation_id": cid, "message": "I have felt tired since yesterday",
               "expected_version": state["version"], "lang": "en"}

    def reject_message_commit():
        raise RuntimeError("Simulated chat write failure")

    with monkeypatch.context() as patch:
        patch.setattr("core.db_utils.commit_or_rollback", reject_message_commit)
        failed = previsit(client, "message", **payload)
    assert failed.status_code == 503
    resumed = previsit(client, "session", conversation_id=cid, lang="en").get_json()
    assert resumed["transcript"] == []
    assert resumed["version"] == state["version"]

    saved = previsit(client, "message", **payload).get_json()
    assert saved["transcript"] == [
        {"role": "assistant", "text": "How are you feeling?"},
        {"role": "user", "text": payload["message"]},
    ]


def test_previsit_older_draft_keeps_answers_with_only_recorded_questions(client, test_app):
    cid = previsit(client, "session").get_json()["conversation_id"]
    text = "Tôi bị đau bụng từ tối qua"
    draft = previsit(client, "message", conversation_id=cid, message=text).get_json()
    with test_app.app_context():
        record = IntakeSessionRecord.query.filter_by(conversation_id=cid).one()
        messages = json.loads(record.messages_json)
        del messages[0]["previsit_question"]
        record.messages_json = json.dumps(messages)
        db.session.commit()
    intake_service.clear()

    reopened = previsit(client, "session", conversation_id=cid).get_json()
    assert reopened["transcript"] == [{"role": "user", "text": text}]
    assert reopened["next_question"] == draft["next_question"]


def test_previsit_history_preserves_colloquial_denials_and_recalculates_an_edit(client, test_app, monkeypatch):
    cid = previsit(client, "session").get_json()["conversation_id"]
    for message in ("Đau âm ỉ ở bụng dưới từ tối qua", "Vẫn như cũ", "Không ảnh hưởng",
                    "chưa uống thuốc", "hong", "chưa luôn"):
        state = previsit(client, "message", conversation_id=cid, message=message).get_json()
    assert state["status"] == "ready_for_review"
    facts = state["summary"]["part_a_patient_facts"]
    assert facts["symptoms_present"] == ["Đau bụng"]
    assert facts["pain"]["location"] == "bụng dưới"
    assert facts["pain"]["quality"] == "âm ỉ"
    assert facts["patient_reported_history"] == {
        "medications": {"status": "denied", "text": "chưa uống thuốc"},
        "allergies": {"status": "denied", "text": "hong"},
        "conditions": {"status": "denied", "text": "chưa luôn"},
    }
    assert facts["current_medications"] == "chưa uống thuốc"

    # Simulate a draft written before history had structured fields.
    with test_app.app_context():
        record = IntakeSessionRecord.query.filter_by(conversation_id=cid).one()
        stored_facts = json.loads(record.facts_json)
        del stored_facts["patient_reported_history"]
        stored_facts["contextual_answers"].append({
            "question": "Bạn có dị ứng với thuốc hay chất nào không?", "answer": "hong"
        })
        record.facts_json = json.dumps(stored_facts)
        db.session.commit()
    intake_service.clear()

    state = previsit(client, "session", conversation_id=cid).get_json()
    assert state["summary"]["part_a_patient_facts"]["patient_reported_history"]["allergies"] == {
        "status": "denied", "text": "hong"
    }
    state = previsit(
        client, "update-fact", conversation_id=cid, expected_version=state["version"],
        field="contextual_answers", value=[]
    ).get_json()
    assert state["summary"]["part_a_patient_facts"]["patient_reported_history"]["allergies"]["text"] == "hong"
    edit = {"conversation_id": cid, "expected_version": state["version"], "field": "patient_reported_history",
            "value": {"allergies": {"text": "Không rõ"}, "conditions": {"text": "Không có bệnh nền"}}}

    def reject_edit_commit():
        raise RuntimeError("Simulated edit write failure")

    with monkeypatch.context() as patch:
        patch.setattr("core.db_utils.commit_or_rollback", reject_edit_commit)
        assert previsit(client, "update-fact", **edit).status_code == 503
    after_error = previsit(client, "session", conversation_id=cid).get_json()
    assert after_error["version"] == state["version"]
    assert after_error["summary"]["part_a_patient_facts"]["patient_reported_history"]["allergies"]["text"] == "hong"

    state = previsit(client, "update-fact", **edit).get_json()
    assert state["summary"]["part_a_patient_facts"]["patient_reported_history"] == {
        "allergies": {"status": "unknown", "text": "Không rõ"},
        "conditions": {"status": "denied", "text": "Không có bệnh nền"},
    }
