"""Regression cases for short replies, intake stopping and urgent overrides."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from core.chat_service import (enforce_question_limit, execute_chat_workflow,
                               process_clinical_chat)
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


def test_direct_conclusion_stops_questions_without_an_arbitrary_turn_limit(test_app):
    manager = IntakeSessionManager()
    cid = "test_direct_conclusion"
    manager.process_message(cid, "Tôi đau họng từ hôm qua", guest_token=GUEST)
    direct = manager.process_message(cid, "Vậy tôi bị gì?", guest_token=GUEST)
    assert direct["next_question"] is None
    assert direct["consultation_mode"] == "final"

    cid = "test_turn_limit"
    for message in ("Tôi đau họng từ hôm qua", "không", "có", "đỡ rồi", "vẫn còn khó chịu"):
        result = manager.process_message(cid, message, guest_token=GUEST)
    assert result["next_question"] is None
    assert result["consultation_mode"] == "collecting"
    assert requests_consultation_conclusion("Vậy có nguy hiểm không?")
    assert requests_consultation_conclusion("Có sao không?")
    assert not requests_consultation_conclusion("Sốt xuất huyết có nguy hiểm không?")
    assert not requests_consultation_conclusion("Sốt xuất huyết có sao không?")

    cid = "test_late_report"
    for _ in range(5):
        manager.process_message(cid, "Sốt xuất huyết là gì?", guest_token=GUEST)
    late_report = manager.process_message(cid, "Tôi đang đau bụng", guest_token=GUEST)
    assert late_report["consultation_mode"] == "collecting"
    assert "vị trí" in late_report["next_question"]


@pytest.mark.parametrize("question", [
    "Tôi có nên đi khám không?", "Giờ cần làm gì?", "Vậy bước tiếp theo là gì?",
    "Tôi đau bụng từ hôm qua, có cần đi khám ngay không?", "Do I need to see a doctor?",
])
def test_direct_requests_for_next_steps_are_recognized(question):
    assert requests_consultation_conclusion(question)
    assert not requests_consultation_conclusion("Đau họng là gì?")


@pytest.mark.parametrize("message", [
    "Tôi sốt 38.5 độ và đau cổ họng hai hôm nay",
    "Toi sot 38,5 do va co hong dau hai hom nay",
])
def test_natural_throat_variants_keep_reported_temperature_and_duration(message):
    facts = extract_clinical_facts_from_text(message)
    assert facts["present_symptoms"] == ["Sốt / Thân nhiệt tăng", "Đau rát họng / Nuốt đau"]
    assert not facts["denied_symptoms"]
    assert facts["vitals"]["temperature"] == "38.5°C"
    assert facts["duration"] in ("hai hôm nay", "hai hom nay")


def test_contrastive_negation_applies_only_to_its_clause():
    facts = extract_clinical_facts_from_text("Tôi không sốt nhưng đau cổ họng")
    assert facts["present_symptoms"] == ["Đau rát họng / Nuốt đau"]
    assert facts["denied_symptoms"] == ["Sốt / Thân nhiệt tăng"]


@pytest.mark.parametrize("message", [
    "Tôi thấy hơi ngứa người", "Tôi ngứa khắp người", "I feel itchy", "I'm itching",
])
def test_itching_is_captured_without_inferring_a_rash(message):
    facts = extract_clinical_facts_from_text(message)
    assert facts["present_symptoms"] == ["Ngứa"]
    assert facts["denied_symptoms"] == []


def test_itching_and_rash_negations_stay_independent():
    itching = extract_clinical_facts_from_text("Tôi ngứa toàn thân nhưng không nổi mẩn")
    assert itching["present_symptoms"] == ["Ngứa"]
    assert itching["denied_symptoms"] == ["Phát ban da / Nổi mề đay"]

    rash = extract_clinical_facts_from_text("No itching but I have a rash")
    assert rash["present_symptoms"] == ["Phát ban da / Nổi mề đay"]
    assert rash["denied_symptoms"] == ["Ngứa"]


def test_itching_intake_asks_for_an_unreported_detail(test_app):
    manager = IntakeSessionManager()
    cid = "test_itching_followup"
    first = manager.process_message(cid, "Tôi thấy hơi ngứa người", guest_token=GUEST)
    assert first["next_question"] == "Bạn bị ngứa từ khi nào?"
    after_duration = manager.process_message(cid, "Hôm nay", guest_token=GUEST)
    assert after_duration["next_question"] == "Bạn có thấy nổi mẩn ở vùng ngứa không?"
    after_rash = manager.process_message(cid, "Không", guest_token=GUEST)
    assert after_rash["next_question"] is None
    assert after_rash["facts"]["present_symptoms"] == ["Ngứa"]
    assert after_rash["facts"]["denied_symptoms"] == ["Phát ban da / Nổi mề đay"]

    english = manager.process_message("test_itching_known_duration", "I've been itchy since yesterday",
                                      lang="en", guest_token=GUEST)
    assert english["next_question"] == "Have you noticed a rash where it itches?"


def test_painful_swallowing_does_not_establish_inability_to_swallow(test_app):
    manager = IntakeSessionManager()
    cid = "test_swallowing_ability"
    first = manager.process_message(cid, "Tôi sốt 38.5 độ và đau cổ họng hai hôm nay, nuốt đau", guest_token=GUEST)
    assert first["next_question"] == "Bạn có bị khó thở khi nghỉ ngơi không?"
    after_breathing = manager.process_message(cid, "không", guest_token=GUEST)
    assert after_breathing["next_question"] == "Bạn còn nuốt được nước bọt không?"
    after_swallowing = manager.process_message(cid, "có", guest_token=GUEST)
    assert "Đau rát họng / Nuốt đau" in after_swallowing["facts"]["present_symptoms"]
    assert "Không nuốt được nước bọt" in after_swallowing["facts"]["denied_symptoms"]
    assert "tức ngực" in after_swallowing["next_question"]


def test_short_temperature_binds_only_to_displayed_celsius_question(test_app):
    manager = IntakeSessionManager()
    cid = "test_short_temperature"
    first = manager.process_message(cid, "Tôi sốt từ hôm qua", guest_token=GUEST)
    assert "nhiệt độ" in first["next_question"].lower()
    result = manager.process_message(cid, "38,5", guest_token=GUEST)
    assert result["facts"]["vitals"]["temperature"] == "38.5°C"
    assert result["facts"]["answered_topics"]["temperature"] == "38,5"
    assert "khó thở" in result["next_question"]


def test_english_duration_followup_uses_reported_time_and_language(test_app):
    manager = IntakeSessionManager()
    cid = "test_short_english_duration"
    first = manager.process_message(cid, "My throat hurts", lang="en", guest_token=GUEST)
    assert first["next_question"] == "When did your symptoms start?"
    result = manager.process_message(cid, "Two days ago", lang="en", guest_token=GUEST)
    assert result["facts"]["duration"].casefold() == "two days ago"
    assert result["next_question"] == "Do you have difficulty breathing while resting?"


def test_no_intake_question_does_not_force_repeated_final_assessment(test_app):
    manager = IntakeSessionManager()
    cid = "test_no_question_still_collecting"
    first = manager.process_message(cid, "Tôi mệt từ hôm qua", guest_token=GUEST)
    assert first["consultation_mode"] == "collecting"

    follow_up = manager.process_message(cid, "Tôi vừa uống cà phê", guest_token=GUEST)
    assert follow_up["consultation_mode"] == "collecting"


def test_direct_health_question_does_not_reopen_pending_intake(test_app):
    manager = IntakeSessionManager()
    cid = "test_direct_health_question"
    initial = manager.process_message(cid, "Tôi đau bụng", guest_token=GUEST)
    symptoms = list(initial["facts"]["present_symptoms"])
    result = manager.process_message(cid, "Đơn thuốc uống trước hay sau ăn?", guest_token=GUEST)
    assert result["consultation_mode"] == "informational"
    assert result["next_question"] is None
    assert result["facts"]["present_symptoms"] == symptoms


def test_clinical_readiness_can_finish_early(test_app):
    manager = IntakeSessionManager()
    result = manager.process_message("test_ready_abdominal", "Tôi đau bụng âm ỉ quanh rốn 2 ngày nay.",
                                     guest_token=GUEST)
    assert result["consultation_mode"] == "final"
    assert result["next_question"] is None
    assert result["summary"]["ready_to_finalize"] is True


def test_general_definition_preserves_emergency_check_for_ambiguous_symptoms(test_app):
    manager = IntakeSessionManager()
    definition = manager.process_message("test_red_flag_definition", "Đau tức ngực là gì?", guest_token=GUEST)
    assert definition["consultation_mode"] == "informational"
    assert definition["summary_available"] is False
    assert definition["summary"]["ready_to_finalize"] is False

    symptoms = manager.process_message("test_red_flag_possible_symptom", "Đau tức ngực và khó thở nguyên nhân nào?",
                                       guest_token=GUEST)
    assert symptoms["status"] == "emergency"


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
    assert result["answer"] == "Có thể liên quan đến kích ứng họng. Nghỉ ngơi và uống nước."
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
