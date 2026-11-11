"""Synthetic provider-only tests: no live AI requests or patient database."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from core.chat_service import process_clinical_chat, retrieval_query
from core.gemini_service import (GeminiMedicalService, sanitize_history,
                                sanitize_health_context, reference_sources)


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

    def test_sources_are_actual_retrieval_metadata_and_untrusted_docs_are_data(self):
        document = {"title": "Cough", "source": "NLM", "source_url": "https://medlineplus.gov/cough.html",
                    "content": "UNTRUSTED-REFERENCE-INSTRUCTION"}
        service = provider({"answer": "Thông tin tham khảo.", "sources": [{"url": "https://invented.example"}],
                            "visual_findings": ["hallucinated without image"]})
        result = service.generate_clinical_response("ho", [], rag_docs=[document])
        self.assertEqual(result["sources"], [{"title": "Cough", "source": "NLM", "url": document["source_url"]}])
        self.assertEqual(result["visual_findings"], [])
        call = service.client.models.generate_content.call_args.kwargs
        self.assertIn("UNTRUSTED-REFERENCE-INSTRUCTION", call["contents"])
        self.assertNotIn("UNTRUSTED-REFERENCE-INSTRUCTION", call["config"].system_instruction)
        self.assertEqual(provider({"answer": "Chưa có nguồn.", "sources": [{"url": "https://invented.example"}]})
                         .generate_clinical_response("ho", [])["sources"], [])
        self.assertEqual(reference_sources([{"source_url": "javascript:alert(1)"}, {"source_url": "https://user:secret@example.com"}]), [])

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
        urgent = "Hãy gọi 115 hoặc đến khoa cấp cứu ngay."
        service = SimpleNamespace(generate_clinical_response=MagicMock(return_value={"answer": urgent, "is_emergency": True}))
        result = process_clinical_chat("Từ hôm qua.",
            history=[{"role": "assistant", "content": "Bạn bắt đầu khó chịu từ khi nào?"}],
            clinical_hint="Bạn đã đo nhiệt độ chưa?", gemini_service=service)
        self.assertTrue(result["is_emergency"])
        self.assertIn("115", result["answer"])
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

    def test_raw_provider_exception_never_reaches_logs(self):
        service = provider()
        service.client.models.generate_content.side_effect = RuntimeError("secret-key-and-synthetic-health-detail")
        with self.assertLogs("GeminiService", level="WARNING") as captured:
            self.assertIsNone(service.generate_clinical_response("synthetic message", []))
        self.assertNotIn("secret-key-and-synthetic-health-detail", " ".join(captured.output))


if __name__ == "__main__":
    unittest.main()
