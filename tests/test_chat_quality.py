"""Synthetic provider-only tests: no live AI requests or patient database."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from core.chat_service import process_clinical_chat, retrieval_query
from core.gemini_service import (GeminiMedicalService, sanitize_history,
                                sanitize_health_context, reference_sources)
from core.llm_provider import _GroqHTTPError


def provider(response=None):
    service = object.__new__(GeminiMedicalService)
    service.api_key = "synthetic-test-key-never-transmitted"
    service.model = "gemini-flash-lite-latest"
    generate = MagicMock(return_value=SimpleNamespace(text=json.dumps(response or {"answer": "Bạn có thể nói rõ thêm không?"})))
    service.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    return service


class ChatQualityTests(unittest.TestCase):
    def test_retrieval_uses_present_symptoms_and_preserves_current_drug_question(self):
        facts = {"present_symptoms": ["Ho khan"], "denied_symptoms": ["Sốt / Thân nhiệt tăng", "Khó thở / Hụt hơi"]}
        query = retrieval_query("Ho khan 2 ngày, không sốt, không khó thở. Tôi nên làm gì?", facts)
        self.assertIn("Ho khan", query)
        self.assertNotIn("sốt", query.lower())
        self.assertNotIn("khó thở", query.lower())
        self.assertIn("amoxicillin", retrieval_query("Tôi có thể dùng amoxicillin không?", facts))

    def test_unknown_or_invalid_risk_score_never_becomes_reassuring_number(self):
        service = provider()
        for value in (None, "not_a_number", "NaN", float("inf"), True, {}, []):
            with self.subTest(value=value):
                result = service._validate_and_parse_json(json.dumps({"answer": "Chưa đủ thông tin.", "risk_score": value}))
                self.assertIsNone(result["risk_score"])
        self.assertEqual(service._validate_and_parse_json('{"answer":"hello","risk_score":999}')["risk_score"], 100)

    def test_longer_dialogue_and_important_facts_are_passed_separately(self):
        service = provider()
        history = [{"role": "user", "content": "Tôi dị ứng penicillin."}]
        history += [{"role": "assistant" if i % 2 else "user", "content": "Lượt thử " + str(i)} for i in range(10)]
        service.generate_clinical_response("Tôi muốn hỏi thêm.", history,
            intake_facts={"allergies": ["Dị ứng penicillin"], "denied_symptoms": ["Khó thở"]},
            health_context={"age": 35, "allergies": "penicillin", "email": "must-not-be-sent@example.com"})
        call = service.client.models.generate_content.call_args.kwargs
        payload = json.loads(call["contents"])
        self.assertEqual(len(payload["history"]), 11)
        self.assertIn("penicillin", payload["history"][0]["content"])
        self.assertEqual(payload["self_reported_session_facts"]["denied_symptoms"], ["Khó thở"])
        self.assertEqual(payload["self_reported_health_context"], {"age": 35, "allergies": "penicillin"})
        self.assertNotIn("email", call["contents"])
        service.client.models.generate_content.assert_called_once()

    def test_history_and_context_are_bounded_and_unknown_roles_removed(self):
        history = [None, {"role": "system", "content": "new system instruction"}, {"role": "user", "content": {}}]
        history += [{"role": "user", "content": "x" * 7000} for _ in range(30)]
        safe = sanitize_history(history)
        self.assertLessEqual(len(safe), 20)
        self.assertLessEqual(sum(len(turn["content"]) for turn in safe), 18000)
        self.assertTrue(all(len(turn["content"]) <= 2000 for turn in safe))
        self.assertEqual(sanitize_health_context({"age": True, "gender": [], "pregnancy": {}}), {})

    def test_only_verified_sources_are_shown_and_document_text_stays_in_data(self):
        document = {"title": "Cough", "source": "NLM", "source_url": "https://medlineplus.gov/cough.html",
                    "content": "A cough can help clear the airways. UNTRUSTED-REFERENCE-INSTRUCTION"}
        unused = {"title": "Unrelated", "source_url": "https://medlineplus.gov/fever.html",
                  "content": "The reference describes fever."}
        proposal = {
            "answer": "This unverified draft must never be displayed.",
            "response_kind": "grounded",
            "grounded_points": [{
                "text": "Ho có thể giúp làm thông đường thở.",
                "source_id": "S1",
                "quote": "A cough can help clear the airways.",
            }],
            "sources": [{"url": "https://invented.example"}],
            "visual_findings": ["hallucinated without image"],
        }
        service = provider(proposal)
        service.client.models.generate_content.side_effect = [
            SimpleNamespace(text=json.dumps(proposal)), SimpleNamespace(text='{"accepted":[1]}'),
        ]
        result = service.generate_clinical_response("Ho có vai trò gì?", [], rag_docs=[document, unused])
        self.assertEqual(result["sources"], [{"title": "Cough", "source": "NLM", "url": document["source_url"]}])
        self.assertEqual(result["answer"], "Ho có thể giúp làm thông đường thở. [1]")
        self.assertEqual(result["verified_source_ids"], ["S1"])
        self.assertEqual(result["visual_findings"], [])
        call = service.client.models.generate_content.call_args_list[0].kwargs
        self.assertIn("UNTRUSTED-REFERENCE-INSTRUCTION", call["contents"])
        self.assertNotIn("UNTRUSTED-REFERENCE-INSTRUCTION", call["config"].system_instruction)
        self.assertEqual(provider({"answer": "Chưa có nguồn.", "sources": [{"url": "https://invented.example"}]})
                         .generate_clinical_response("ho", [])["sources"], [])
        self.assertEqual(reference_sources([{"source_url": "javascript:alert(1)"}, {"source_url": "https://user:secret@example.com"}]), [])

    def test_invalid_or_unsupported_evidence_never_reaches_the_user(self):
        doc = {"source_url": "https://medlineplus.gov/cough.html",
               "content": "A cough can help clear the airways."}
        proposal = {"answer": "A draft.", "response_kind": "grounded", "grounded_points": [
            {"source_id": "S9", "text": "Fake source", "quote": doc["content"]},
            {"source_id": "S1", "text": "Fake excerpt", "quote": "This quote was made up."},
            {"source_id": "S1", "text": "A cough always means pneumonia.", "quote": doc["content"]},
        ]}
        service = provider(proposal)
        generate = service.client.models.generate_content
        generate.side_effect = [SimpleNamespace(text=json.dumps(proposal)),
                                SimpleNamespace(text='{"accepted":[]}')]
        result = service.generate_clinical_response("What is a cough?", [], rag_docs=[doc], lang="en")
        verified_payload = json.loads(generate.call_args.kwargs["contents"])
        self.assertEqual(len(verified_payload["points"]), 1)
        self.assertEqual(result["grounding_status"], "insufficient")
        self.assertEqual(result["sources"], [])
        self.assertNotIn("pneumonia", result["answer"])

    @patch("core.chat_service.medical_rag_service.retrieve_context", return_value=[
        {"source_url": "https://medlineplus.gov/cough.html", "content": "A cough can help clear the airways."},
    ])
    def test_verifier_outage_hides_draft_in_chat(self, _retrieval):
        proposal = {"answer": "Unverified draft.", "response_kind": "grounded", "grounded_points": [
            {"source_id": "S1", "text": "It helps clear the airways.", "quote": "A cough can help clear the airways."},
        ]}
        service = provider(proposal)
        service.client.models.generate_content.side_effect = [SimpleNamespace(text=json.dumps(proposal)), TimeoutError()]
        result = process_clinical_chat("What is a cough?", gemini_service=service, lang="en")
        self.assertTrue(result["degraded"])
        self.assertEqual(result["grounding_status"], "unavailable")
        self.assertEqual(result["sources"], [])
        self.assertNotIn("Unverified draft", result["answer"])

    @patch("core.chat_service.medical_rag_service.retrieve_context", return_value=[])
    def test_fact_question_search_ignores_previous_symptoms_and_followups(self, retrieval):
        service = provider({
            "answer": "A draft containing a diagnosis.",
            "response_kind": "clarify",
            "grounded_points": [],
            "follow_up_question": "Bạn có bị sốt không?",
        })
        result = process_clinical_chat("Bệnh gút là gì?", intake_facts={"present_symptoms": ["Đau bụng"]},
                                       clinical_hint="Bạn có bị sốt không?", gemini_service=service)
        self.assertEqual(retrieval.call_args.args[0], "Bệnh gút là gì?")
        self.assertEqual(result["grounding_status"], "insufficient")
        self.assertNotIn("?", result["answer"])

    @patch("core.chat_service.medical_rag_service.retrieve_context", return_value=[])
    def test_model_can_continue_personal_chat_without_references(self, _retrieval):
        for message, question in (
            ("tôi thấy hơi ngứa người", "Bạn ngứa ở một vùng hay khắp người?"),
            ("Mình thấy có gì đó lạ ở da.", "Bạn thấy thay đổi gì trên da?"),
        ):
            with self.subTest(message=message):
                service = provider({"response_kind": "clarify", "grounded_points": [],
                                    "follow_up_question": question})
                result = process_clinical_chat(message, gemini_service=service)
                self.assertEqual(result["answer"], question)
                self.assertEqual(result["grounding_status"], "clarification")
                self.assertEqual(result["sources"], [])
                service.client.models.generate_content.assert_called_once()

    @patch("core.chat_service.medical_rag_service.retrieve_context", return_value=[])
    def test_model_question_cannot_repeat_known_facts_or_disguise_advice(self, _retrieval):
        for question in ("Bạn bị ngứa từ khi nào?", "Bạn có nên uống cetirizine 10 mg không?"):
            with self.subTest(question=question):
                service = provider({"response_kind": "clarify", "grounded_points": [],
                                    "follow_up_question": question})
                result = process_clinical_chat("Tôi bị ngứa từ hôm qua", gemini_service=service)
                self.assertEqual(result["answer"], "Bạn có thấy nổi mẩn ở vùng ngứa không?")
                self.assertEqual(result["sources"], [])

    @patch("core.chat_service.medical_rag_service.retrieve_context", return_value=[])
    def test_safety_question_takes_priority_over_model_wording(self, _retrieval):
        service = provider({"response_kind": "clarify", "grounded_points": [],
                            "follow_up_question": "Bạn đau họng nhiều hơn vào lúc nào?"})
        result = process_clinical_chat(
            "Tôi bị sốt 38.5 độ và đau cổ họng hai hôm nay, nuốt đau", gemini_service=service
        )
        self.assertEqual(result["answer"], "Bạn có bị khó thở khi nghỉ ngơi không?")

    @patch("core.chat_service.medical_rag_service.retrieve_context", return_value=[
        {"title": "Cough", "source_url": "https://medlineplus.gov/cough.html",
         "content": "A cough can help clear the airways."},
    ])
    def test_verified_reply_can_include_a_brief_follow_up(self, _retrieval):
        proposal = {
            "response_kind": "grounded",
            "grounded_points": [{"source_id": "S1", "text": "Ho có thể giúp làm thông đường thở.",
                                 "quote": "A cough can help clear the airways."}],
            "follow_up_question": "Bạn có thấy ho ảnh hưởng đến giấc ngủ không?",
        }
        service = provider(proposal)
        service.client.models.generate_content.side_effect = [
            SimpleNamespace(text=json.dumps(proposal)), SimpleNamespace(text='{"accepted":[1]}'),
        ]
        result = process_clinical_chat("Tôi vẫn bị ho.", intake_facts={"present_symptoms": ["Ho"]},
                                       gemini_service=service)
        self.assertEqual(result["answer"], "Ho có thể giúp làm thông đường thở. [1]\n\nBạn có thấy ho ảnh hưởng đến giấc ngủ không?")
        self.assertEqual(result["sources"][0]["url"], "https://medlineplus.gov/cough.html")

    @patch("core.chat_service.medical_rag_service.retrieve_context")
    def test_personal_reports_keep_the_case_specific_question(self, retrieval):
        service = SimpleNamespace(generate_clinical_response=MagicMock(return_value={
            "answer": "Sốt là dấu hiệu cơ thể đang chống lại nhiễm trùng. [1]",
            "grounding_status": "verified", "verified_source_ids": ["S1"],
        }))
        examples = (
            ("Tôi bị sốt 38.5 độ và đau cổ họng hai hôm nay, nuốt đau", "khó thở"),
            ("Tôi bị ho từ hôm qua", "khó thở"),
            ("Tôi bị đau bụng từ sáng", "vị trí"),
            ("Tôi bị đau đầu", "từ khi nào"),
        )
        for message, expected in examples:
            with self.subTest(message=message):
                result = process_clinical_chat(message, gemini_service=service)
                self.assertIn(expected, result["answer"])
                self.assertEqual(result["answer"].count("?"), 1)
                self.assertNotIn("nhiễm trùng", result["answer"])
                self.assertEqual(result["grounding_status"], "clarification")
                self.assertEqual(result["sources"], [])
        retrieval.assert_not_called()
        first_call = service.generate_clinical_response.call_args_list[0].kwargs
        self.assertEqual(first_call["intake_facts"]["vitals"]["temperature"], "38.5°C")
        self.assertEqual(first_call["intake_facts"]["duration"], "hai hôm nay")

    def test_verifier_receives_case_context_for_short_patient_reply(self):
        doc = {"source_url": "https://medlineplus.gov/fever.html",
               "content": "A fever is a temporary increase in body temperature."}
        response = {
            "response_kind": "grounded",
            "grounded_points": [{"source_id": "S1", "text": "Sốt là tình trạng tăng thân nhiệt.",
                                 "quote": doc["content"]}],
        }
        service = provider(response)
        generate = service.client.models.generate_content
        generate.side_effect = [SimpleNamespace(text=json.dumps(response)), SimpleNamespace(text='{"accepted":[]}')]
        result = service.generate_clinical_response(
            "Từ hôm qua.", [{"role": "assistant", "content": "Bạn bị đau họng từ khi nào?"}],
            rag_docs=[doc], intake_facts={"present_symptoms": ["Đau rát họng / Nuốt đau"]},
        )
        context = json.loads(generate.call_args.kwargs["contents"])["clinical_context"]
        self.assertEqual(context["previous_question"], "Bạn bị đau họng từ khi nào?")
        self.assertEqual(context["patient_report"]["present_symptoms"], ["Đau rát họng / Nuốt đau"])
        self.assertEqual(result["grounding_status"], "acknowledged")
        self.assertNotIn("tăng thân nhiệt", result["answer"])
        self.assertNotIn("chưa tìm được tài liệu", result["answer"])

    def test_short_screening_reply_searches_with_conversation_context(self):
        history = [{"role": "user", "content": "Tôi bị đau họng từ hôm qua"},
                   {"role": "assistant", "content": "Bạn có bị khó thở không?"}]
        query = retrieval_query("hông", {}, history=history)
        self.assertIn("đau họng", query)
        self.assertIn("hông", query)
        # A long standalone message is not diluted with older turns.
        long_message = "Tôi bị ho khan kéo dài và hơi mệt vào buổi tối hôm nay"
        self.assertEqual(retrieval_query(long_message, {}, history=history), long_message)

    def test_empty_model_output_returns_valid_default_json(self):
        service = provider()
        service.client.models.generate_content.return_value = SimpleNamespace(text="")
        result = service.generate_clinical_response("lntv205@gmail.com", [], rag_docs=[])
        self.assertEqual(service.client.models.generate_content.call_count, 2)
        self.assertEqual(result["grounding_status"], "unrecognized_input")
        self.assertIn("không nhận diện được triệu chứng", result["answer"])
        self.assertFalse(result["degraded"])
        self.assertEqual(result["sources"], [])

    def test_off_topic_input_asks_for_symptoms_instead_of_refusing(self):
        response = {"response_kind": "clarify", "grounded_points": [], "follow_up_question": ""}
        service = provider(response)
        result = service.generate_clinical_response("lntv205@gmail.com", [], rag_docs=[])
        self.assertEqual(result["grounding_status"], "unrecognized_input")
        self.assertNotIn("chưa tìm được tài liệu", result["answer"])
        prompt = service.client.models.generate_content.call_args.kwargs["config"].system_instruction
        self.assertIn("OUTPUT CONTRACT", prompt)

    def test_screening_reply_is_acknowledged_not_refused(self):
        response = {"response_kind": "clarify", "grounded_points": [], "follow_up_question": ""}
        service = provider(response)
        service.client.models.generate_content.side_effect = [SimpleNamespace(text=json.dumps(response))]
        result = service.generate_clinical_response(
            "hông", [{"role": "user", "content": "Tôi bị đau họng"},
                     {"role": "assistant", "content": "Bạn có bị khó thở không?"}],
            rag_docs=[], intake_facts={"present_symptoms": ["Đau họng"], "denied_symptoms": ["Khó thở"]},
        )
        self.assertEqual(result["grounding_status"], "acknowledged")
        self.assertIn("Đau họng", result["answer"])
        self.assertIn("Khó thở", result["answer"])
        self.assertNotIn("chưa tìm được tài liệu", result["answer"])

    @patch("core.chat_service.medical_rag_service.retrieve_context", return_value=[])
    def test_outage_is_honest_does_not_prescribe_or_guess_visuals(self, retrieval):
        service = SimpleNamespace(generate_clinical_response=MagicMock(return_value=None))
        result = process_clinical_chat("Trẻ bị sốt và ho.", image_bytes=b"synthetic-image", gemini_service=service,
                                       health_context={"age": 1}, clinical_hint="Bé sốt từ khi nào?")
        self.assertTrue(result["degraded"])
        self.assertIsNone(result["risk_score"])
        self.assertEqual(result["differential_diagnosis"], [])
        self.assertEqual(result["visual_findings"], [])
        self.assertEqual(result["sources"], [])
        self.assertNotIn("500", result["answer"])
        self.assertIn("dịch vụ AI", result["answer"])

    @patch("core.chat_service.medical_rag_service.retrieve_context", return_value=[])
    def test_optional_intake_hint_cannot_suppress_urgent_model_guidance(self, retrieval):
        urgent = "Cần được đánh giá khẩn cấp tại cơ sở y tế."
        service = SimpleNamespace(generate_clinical_response=MagicMock(return_value={"answer": urgent, "is_emergency": True}))
        result = process_clinical_chat("Từ hôm qua.",
            history=[{"role": "assistant", "content": "Bạn bắt đầu khó chịu từ khi nào?"}],
            clinical_hint="Bạn đã đo nhiệt độ chưa?", gemini_service=service)
        self.assertTrue(result["is_emergency"])
        self.assertIn("khẩn cấp", result["answer"])
        self.assertNotEqual(result["answer"], "Bạn đã đo nhiệt độ chưa?")

    @patch("core.chat_service.medical_rag_service.retrieve_context", return_value=[])
    def test_chat_layer_does_not_trust_provider_citation_injections(self, retrieval):
        service = SimpleNamespace(generate_clinical_response=MagicMock(return_value={
            "answer": "Chưa đủ thông tin để đánh giá.", "sources": [{"url": "https://fabricated.example"}]}))
        result = process_clinical_chat("Tôi muốn hỏi về kết quả xét nghiệm.", gemini_service=service,
                                       intake_facts={"allergies": ["Dị ứng thuốc"]},
                                       health_context={"allergies": "penicillin"})
        self.assertEqual(result["sources"], [])
        kwargs = service.generate_clinical_response.call_args.kwargs
        self.assertEqual(kwargs["health_context"]["allergies"], "penicillin")
        self.assertEqual(kwargs["intake_facts"]["allergies"], ["Dị ứng thuốc"])

    @patch("core.chat_service.medical_rag_service.retrieve_context", return_value=[
        {"title": "Ho", "source": "MedlinePlus", "source_url": "https://medlineplus.gov/cough.html",
         "content": "Thông tin về ho."}])
    def test_fallback_does_not_present_retrieved_documents_as_citations(self, retrieval):
        service = SimpleNamespace(generate_clinical_response=MagicMock(return_value=None))
        result = process_clinical_chat("Tôi bị ho từ hôm qua", gemini_service=service)
        self.assertTrue(result["degraded"])
        self.assertEqual(result["sources"], [])

    def test_raw_provider_exception_never_reaches_logs(self):
        service = provider()
        service.client.models.generate_content.side_effect = _GroqHTTPError(
            401, "secret-key-and-synthetic-health-detail"
        )
        with self.assertLogs("GeminiService", level="WARNING") as captured:
            self.assertIsNone(service.generate_clinical_response("synthetic message", []))
        log = " ".join(captured.output)
        self.assertIn("HTTP 401", log)
        self.assertNotIn("secret-key-and-synthetic-health-detail", log)

    def test_groq_provider_resolves_endpoint_model_and_clean_payload(self):
        import os
        from google.genai import types
        from core.llm_provider import LLMProvider

        env_patch = {
            "AI_PROVIDER": "groq",
            "GROQ_API_KEY": "gsk_test_groq_key_123456",
            "GROQ_MODEL": "",
            "GROQ_CHAT_MODEL": "",
        }
        with patch.dict(os.environ, env_patch, clear=False):
            lp = LLMProvider()
            self.assertTrue(lp.is_groq_active())
            self.assertFalse(hasattr(lp, "is_openrouter_active"))
            self.assertEqual(lp.resolve_api_key(profile="chat"), "gsk_test_groq_key_123456")
            self.assertEqual(lp.get_default_model("chat"), "qwen/qwen3.8-27b")
            client = lp.get_client("gsk_test_groq_key_123456", profile="chat")
            self.assertEqual(client.models._endpoint(), "https://api.groq.com/openai/v1/chat/completions")

            cfg = types.GenerateContentConfig(
                system_instruction="Return JSON",
                response_mime_type="application/json",
            )
            with patch.object(client.models, "_post_completion", return_value={"choices": [{"message": {"content": "{}"}}]}) as post:
                res = client.models.generate_content(
                    model="llama-3.3-70b-versatile",
                    contents="hello",
                    config=cfg,
                )
            self.assertEqual(res.text, "{}")
            payload = post.call_args.args[0]
            self.assertEqual(payload["model"], "llama-3.3-70b-versatile")
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            self.assertNotIn("provider", payload)
            self.assertNotIn("reasoning", payload)

    def test_groq_404_falls_back_to_active_model(self):
        from core.llm_provider import LLMProvider, _GroqHTTPError

        client = LLMProvider().get_client("gsk_test_groq_key_123456", provider="groq", profile="chat")
        tried_models = []

        def fake_post(payload):
            tried_models.append(payload["model"])
            if payload["model"] == "llama-3.3-70b-versatile":
                raise _GroqHTTPError(404, "Groq HTTP 404")
            return {"choices": [{"message": {"content": '{"response_kind":"clarify"}'}}]}

        with patch.object(client.models, "_post_completion", side_effect=fake_post):
            res = client.models.generate_content(model="llama-3.3-70b-versatile", contents="hello")

        self.assertEqual(tried_models, ["llama-3.3-70b-versatile", "qwen/qwen3.8-27b"])
        self.assertEqual(res.text, '{"response_kind":"clarify"}')

    @patch("core.chat_service.medical_rag_service.retrieve_context", return_value=[])
    def test_facility_query_injects_verified_local_directory_reference(self, _retrieval):
        captured = {}

        def fake_generate(user_message, history, rag_docs=None, **kwargs):
            captured["rag_docs"] = rag_docs or []
            captured["mode"] = kwargs.get("consultation_mode")
            first_line = captured["rag_docs"][0]["content"].splitlines()[1]
            return {
                "answer": f"Bạn có thể tham khảo {first_line} [1]",
                "grounding_status": "verified",
                "verified_source_ids": ["S1"],
            }

        service = SimpleNamespace(generate_clinical_response=MagicMock(side_effect=fake_generate))
        result = process_clinical_chat(
            "Hôm nay tôi muốn đi khám tổng quát ở tp hcm thì bệnh viện nào oke",
            gemini_service=service,
        )
        self.assertEqual(captured["mode"], "informational")
        self.assertTrue(captured["rag_docs"])
        self.assertEqual(captured["rag_docs"][0]["source"], "MediMind Facilities Directory")
        self.assertEqual(result["grounding_status"], "verified")
        self.assertEqual(result["sources"][0]["url"], "https://medimind.vn/facilities")

    def test_safe_general_reference_fallback_labels_transparently_and_blocks_unsafe_prescriptions(self):
        safe_proposal = {
            "response_kind": "insufficient",
            "grounded_points": [],
            "general_guidance": "Khám sức khỏe tổng quát định kỳ thường gồm khám nội tổng quát, xét nghiệm máu, nước tiểu và chẩn đoán hình ảnh cơ bản tùy độ tuổi.",
            "follow_up_question": "",
            "is_emergency": False,
        }
        service = provider(safe_proposal)
        res = service.generate_clinical_response("Khám tổng quát gồm những hạng mục gì?", [], rag_docs=[], lang="vi")
        self.assertEqual(res["grounding_status"], "general_reference")
        self.assertEqual(res["sources"], [])
        self.assertIn("Thông tin tham khảo tổng quát", res["answer"])
        self.assertIn("xét nghiệm máu", res["answer"])

        # Unsafe antibiotic prescription inside general_guidance must be rejected
        unsafe_proposal = {
            "response_kind": "insufficient",
            "grounded_points": [],
            "general_guidance": "Bạn hãy mua và uống kháng sinh Amoxicillin 500mg ngày 3 viên trong 7 ngày để hết bệnh.",
            "follow_up_question": "",
            "is_emergency": False,
        }
        unsafe_service = provider(unsafe_proposal)
        unsafe_res = unsafe_service.generate_clinical_response("Đau họng uống gì?", [], rag_docs=[], lang="vi")
        self.assertEqual(unsafe_res["grounding_status"], "insufficient")
        self.assertNotIn("Amoxicillin", unsafe_res["answer"])

    def test_general_chat_questions_answer_directly_via_api(self):
        proposal = {
            "response_kind": "general_chat",
            "grounded_points": [],
            "general_guidance": "Hiện tại là 20:30, ngày 25/11/2026.",
            "follow_up_question": "",
            "is_emergency": False,
        }
        service = provider(proposal)
        res = service.generate_clinical_response("Bây giờ là mấy giờ", [], rag_docs=[], lang="vi")
        self.assertEqual(res["grounding_status"], "general_chat")
        self.assertEqual(res["answer"], "Hiện tại là 20:30, ngày 25/11/2026.")
        self.assertEqual(res["sources"], [])


if __name__ == "__main__":
    unittest.main()
