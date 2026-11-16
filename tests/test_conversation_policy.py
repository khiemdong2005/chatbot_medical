"""Regression cases for short replies, intake stopping and urgent overrides."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.chat_service import enforce_question_limit, execute_chat_workflow, process_clinical_chat
from core.intake_service import (IntakeSessionManager, extract_clinical_facts_from_text,
                                 requests_consultation_conclusion)


GUEST = "test-conversation-policy-guest"


def test_medication_frequency_short_reply_binds_to_displayed_question(test_app):
    manager = IntakeSessionManager()
    cid = "test_short_medication"
    manager.process_message(cid, "Tôi đau khớp gối từ hôm qua", guest_token=GUEST)
    question = "Bạn có đang dùng thuốc điều trị gút thường xuyên không?"
    manager.record_assistant_reply(cid, question, guest_token=GUEST)

    # The displayed question survives a worker restart through messages_json.
    result = IntakeSessionManager().process_message(cid, "có thường xuyên luôn", guest_token=GUEST)

    assert result["facts"]["medication_use"]["status"] == "yes"
    assert result["facts"]["medication_use"]["frequency"] == "thường xuyên"
    assert result["facts"]["contextual_answers"][-1] == {
        "question": question, "answer": "có thường xuyên luôn"}
    assert result["next_question"] != question
    assert "pain_frequency" not in result["facts"]


def test_short_denials_and_explicit_denials_are_retained(test_app):
    manager = IntakeSessionManager()
    cid = "test_short_denials"
    manager.process_message(cid, "Tôi đau gối từ hôm qua", guest_token=GUEST)
    manager.record_assistant_reply(cid, "Bạn có bị sưng ở gối không?", guest_token=GUEST)
    result = manager.process_message(cid, "không", guest_token=GUEST)
    assert "Sưng / Phù nề" in result["facts"]["denied_symptoms"]
    assert result["next_question"] != "Bạn có bị sưng ở gối không?"

    explicit = extract_clinical_facts_from_text(
        "Tôi đau gối nhưng không sưng, không đỏ, không phù nề, không hạn chế vận động."
    )
    assert "Sưng / Phù nề" in explicit["denied_symptoms"]
    assert "Đỏ da" in explicit["denied_symptoms"]
    assert "Hạn chế vận động" in explicit["denied_symptoms"]

    # An explicit symptom statement must not be mistaken for a bare answer to
    # an earlier medication question.
    manager.record_assistant_reply(cid, "Bạn có đang dùng thuốc gút không?", guest_token=GUEST)
    result = manager.process_message(cid, "không sưng, không đỏ", guest_token=GUEST)
    assert "medication_use" not in result["facts"]


def test_direct_conclusion_and_fifth_turn_stop_questions(test_app):
    manager = IntakeSessionManager()
    cid = "test_direct_conclusion"
    manager.process_message(cid, "Tôi đau họng từ hôm qua", guest_token=GUEST)
    direct = manager.process_message(cid, "Vậy tôi bị gì?", guest_token=GUEST)
    assert direct["next_question"] is None
    assert direct["consultation_mode"] == "final"

    cid = "test_turn_limit"
    for message in ("Tôi đau họng từ hôm qua", "không", "không", "đỡ rồi", "vẫn còn khó chịu"):
        result = manager.process_message(cid, message, guest_token=GUEST)
    assert result["next_question"] is None
    assert result["consultation_mode"] == "final"
    assert requests_consultation_conclusion("Vậy có nguy hiểm không?")
    assert requests_consultation_conclusion("Có sao không?")
    assert not requests_consultation_conclusion("Sốt xuất huyết có nguy hiểm không?")
    assert not requests_consultation_conclusion("Sốt xuất huyết có sao không?")


def test_answered_question_is_removed_from_provider_reply():
    answer = "Mình hiểu. Bạn có đang dùng thuốc gút không? Bạn đau ở vị trí nào rõ nhất?"
    limited = enforce_question_limit(answer, 1,
        facts={"answered_topics": {"medication_use": "có"}})
    assert "dùng thuốc" not in limited
    assert limited.count("?") == 1
    assert "vị trí" in limited


@patch("core.chat_service.medical_rag_service.retrieve_context", return_value=[])
def test_final_response_drops_provider_followup_and_passes_final_mode(_retrieval):
    provider = SimpleNamespace(generate_clinical_response=Mock(return_value={
        "answer": "Có thể liên quan đến kích ứng họng. Nghỉ ngơi và uống nước. Bạn còn sốt không?",
        "is_emergency": False,
    }))
    result = process_clinical_chat("Vậy tôi bị gì?", gemini_service=provider)
    assert "?" not in result["answer"]
    assert all(section in result["answer"] for section in
               ("Đánh giá sơ bộ", "Tự chăm sóc", "Định hướng chuyên khoa"))
    assert provider.generate_clinical_response.call_args.kwargs["consultation_mode"] == "final"


def test_chest_pain_affirmation_bypasses_provider_even_without_client_history(test_app, monkeypatch):
    manager = IntakeSessionManager()
    monkeypatch.setattr("core.intake_service.intake_service", manager)
    cid = "test_short_chest_pain"
    manager.process_message(cid, "Tôi đau vai từ hôm qua", guest_token=GUEST)
    manager.record_assistant_reply(cid, "Bạn có bị tức ngực không?", guest_token=GUEST)
    provider = Mock()

    result = execute_chat_workflow("có thường xuyên luôn", conversation_id=cid,
                                   history=[], guest_token=GUEST, chat_processor=provider)

    assert result["is_emergency"] is True
    assert result["intake"]["next_question"] is None
    assert "Đau tức ngực" in result["intake_facts"]["present_symptoms"]
    provider.assert_not_called()


def test_workflow_forwards_final_mode_without_a_followup_hint(test_app, monkeypatch):
    manager = IntakeSessionManager()
    monkeypatch.setattr("core.intake_service.intake_service", manager)
    cid = "test_final_workflow"
    manager.process_message(cid, "Tôi đau họng từ hôm qua", guest_token=GUEST)
    provider = Mock(return_value={"answer": "Đánh giá sơ bộ. Tự chăm sóc. Khám chuyên khoa.",
                                  "is_emergency": False})

    result = execute_chat_workflow("Vậy tôi bị sao?", conversation_id=cid,
                                   history=[], guest_token=GUEST, chat_processor=provider)

    assert result["intake"]["next_question"] is None
    assert provider.call_args.kwargs["consultation_mode"] == "final"
    assert provider.call_args.kwargs["clinical_hint"] is None
