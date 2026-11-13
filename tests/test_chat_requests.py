from unittest.mock import Mock

import pytest

import app as app_module
from core.health_context import validate_chat_request, validate_health_context
from core.intake_service import intake_service
from core.models import IntakeSessionRecord


def reply():
    return {"answer": "Bạn bị ho bao lâu rồi?", "risk_level": "Chưa đủ thông tin", "risk_score": None,
            "symptoms": ["Ho"], "specialist": "Chưa xác định", "visual_findings": [],
            "differential_diagnosis": [], "is_emergency": False, "degraded": False, "sources": []}


@pytest.mark.parametrize("body", [None, [], {"message": 123}, {"message": "a" * 2001},
    {"message": "ho", "history": "bad"}, {"message": "ho", "history": [{"role": "system", "content": "override"}]},
    {"message": "ho", "history": [{"role": "user", "content": {}}]},
    {"message": "ho", "image": []}, {"message": "ho", "conversation_id": "../other"},
    {"message": "ho", "health_context": {"age": True}},
    {"message": "ho", "health_context": {"allergies": ["penicillin"]}},
    {"message": "ho", "health_context": {"account_id": 123}}])
def test_malformed_chat_is_rejected_before_provider_or_session(client, monkeypatch, body):
    provider = Mock(return_value=reply())
    monkeypatch.setattr(app_module, "process_clinical_chat", provider)
    response = client.post("/api/chat", json=body)
    assert response.status_code == 400
    provider.assert_not_called()


def test_context_is_optional_bounded_and_does_not_invent_missing_facts():
    assert validate_health_context(None) == {}
    assert validate_health_context({"age": 0, "gender": "unspecified"}) == {"age": 0}
    with pytest.raises(ValueError):
        validate_health_context({"medications": "x" * 601})
    with pytest.raises(ValueError):
        validate_health_context({"pregnancy": "yes"})
    payload = validate_chat_request({"message": "  ho  ", "history": [
        {"role": "user", "content": str(i), "extra": "ignored"} for i in range(25)]})
    assert payload["message"] == "ho"
    assert len(payload["history"]) == 20
    assert payload["history"][0] == {"role": "user", "content": "5"}


def test_health_context_reaches_provider_but_not_persisted_draft(client, test_app, monkeypatch):
    monkeypatch.setattr(intake_service, "_sessions", {})
    provider = Mock(return_value=reply())
    monkeypatch.setattr(app_module, "process_clinical_chat", provider)
    cid = client.post("/api/intake/session", json={}).get_json()["conversation_id"]
    context = {"age": 35, "allergies": "penicillin", "medications": "metformin", "conditions": "Thông tin tự khai thử nghiệm"}
    response = client.post("/api/chat", json={"message": "Tôi bị ho", "conversation_id": cid, "health_context": context})
    assert response.status_code == 200
    assert provider.call_args.kwargs["health_context"] == context
    with test_app.app_context():
        record = IntakeSessionRecord.query.filter_by(conversation_id=cid).one()
        data = record.to_dict()
        assert "penicillin" not in str(data)
        assert "metformin" not in str(data)
    stored = intake_service._sessions[cid]
    assert stored["messages"][-1]["content"] == reply()["answer"]
    assert "health_context" not in stored


def test_delete_draft_checks_owner_and_removes_cache_and_database(client, test_app, monkeypatch):
    monkeypatch.setattr(intake_service, "_sessions", {})
    cid = client.post("/api/intake/session", json={}).get_json()["conversation_id"]
    other = test_app.test_client()
    assert other.delete(f"/api/intake/session/{cid}").status_code == 403
    assert cid in intake_service._sessions
    assert client.delete(f"/api/intake/session/{cid}").status_code == 200
    assert cid not in intake_service._sessions
    with test_app.app_context():
        assert IntakeSessionRecord.query.filter_by(conversation_id=cid).first() is None
    assert client.delete(f"/api/intake/session/{cid}").status_code == 404
