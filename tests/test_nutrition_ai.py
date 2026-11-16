import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.nutrition_ai import NutritionAIError, select_recipes, validate_selection
from core.nutrition_options import FOOD, DRINK, get_nutrition_options
from core.nutrition_rules import prepare_nutrition_candidates


def answer(recipe_id="oat_porridge", source_ids=None):
    return {"needs_clarification": False, "clarification_question": "", "recommendations": [
        {"recipe_id": recipe_id, "reason": "Món có kết cấu mềm từ yến mạch và chuối.",
         "caution": "Chỉ là lựa chọn tham khảo.", "source_ids": source_ids or []}]}


class NutritionAITests(unittest.TestCase):
    @staticmethod
    def clarification():
        return {"needs_clarification": True, "clarification_question": "Bạn muốn bổ sung thông tin nào?",
                "recipes": [], "model": "mock-model"}

    def test_model_cannot_change_original_recipe(self):
        payload = answer()
        payload["recommendations"][0]["ingredients"] = [{"name": "unsafe addition"}]
        result = validate_selection(payload, FOOD, 1)
        self.assertEqual(result["recipes"][0]["ingredients"], FOOD[0]["ingredients"])
        self.assertNotIn("recommendation_reason", FOOD[0])

    def test_unknown_ids_duplicate_ids_and_invalid_source_rejected(self):
        bad = [answer("invented_recipe"), answer(source_ids=[3])]
        duplicate = answer()
        duplicate["recommendations"] *= 2
        bad.append(duplicate)
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(NutritionAIError):
                validate_selection(payload, FOOD, 1)

    def test_vietnamese_source_title_cannot_be_rewritten_by_model(self):
        recipe = {**FOOD[0], "language": "vi"}
        payload = answer()
        payload["recommendations"][0]["display_title"] = "Tên mới có công dụng điều trị bị bịa"
        selected = validate_selection(payload, [recipe], 0)["recipes"][0]
        self.assertEqual(selected["display_title"], recipe["title"])
        self.assertEqual(selected["ingredients"], recipe["ingredients"])

    def test_clarification_requires_question_and_no_selected_recipes(self):
        payload = {"needs_clarification": True, "clarification_question": "Bạn cần tránh nguyên liệu nào?", "recommendations": []}
        self.assertEqual(validate_selection(payload, FOOD, 0)["recipes"], [])
        payload["recommendations"] = answer()["recommendations"]
        with self.assertRaises(NutritionAIError):
            validate_selection(payload, FOOD, 0)

    @patch.dict(os.environ, {"GEMINI_NUTRITION_API_KEY": "fake-test-only"})
    @patch("core.nutrition_ai.genai.Client")
    def test_provider_output_is_validated_and_client_closed(self, factory):
        client = factory.return_value
        client.models.generate_content.return_value = SimpleNamespace(text=json.dumps(answer()))
        result = select_recipes("ho", "food", FOOD, [])
        self.assertEqual(result["recipes"][0]["id"], "oat_porridge")
        client.close.assert_called_once()

    @patch.dict(os.environ, {"GEMINI_NUTRITION_API_KEY": "fake-test-only"})
    @patch("core.nutrition_ai.genai.Client")
    def test_provider_error_text_is_never_propagated(self, factory):
        factory.return_value.models.generate_content.side_effect = RuntimeError("private-key-and-request-content")
        with self.assertRaises(NutritionAIError) as captured:
            select_recipes("ho", "food", FOOD, [])
        self.assertEqual(str(captured.exception), "unavailable")

    @patch("core.nutrition_ai.select_recipes", side_effect=NutritionAIError("quota"))
    def test_fallback_reports_failure_and_keeps_allergy_filter(self, _):
        result = get_nutrition_options("mất ngủ; dị ứng trứng", "food")
        self.assertFalse(result["gemini_used"])
        self.assertEqual(result["provider_status"], "fallback_quota")
        self.assertNotIn("soft_egg", [r["id"] for r in result["recipes"]])

    @patch("core.nutrition_ai.select_recipes")
    def test_no_candidate_does_not_call_provider(self, provider):
        result = get_nutrition_options("ho; dị ứng thành phần chưa biết", "food")
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["recipes"], [])
        provider.assert_not_called()

    @patch("core.nutrition_ai.select_recipes")
    def test_fever_clarification_keeps_guided_options_for_both_types(self, provider):
        provider.return_value = self.clarification()
        for kind, catalog in (("food", FOOD), ("drink", DRINK)):
            with self.subTest(kind=kind):
                result = get_nutrition_options("sốt", kind)
                self.assertTrue(result["gemini_used"])
                self.assertTrue(result["needs_clarification"])
                self.assertEqual(result["provider_status"], "ai_clarification_with_options")
                self.assertEqual(result["recommendation_scope"], "guided_catalog")
                self.assertGreater(len(result["recipes"]), 0)
                self.assertLessEqual(len(result["recipes"]), 5)
                self.assertTrue(result["sources"])
                from core.recipe_catalog import imported_recipes
                known = {recipe["id"]: recipe for recipe in catalog + imported_recipes(kind)}
                for recipe in result["recipes"]:
                    self.assertIn(recipe["id"], known)
                    self.assertEqual(recipe["ingredients"], known[recipe["id"]]["ingredients"])
                    self.assertEqual(recipe["steps"], known[recipe["id"]]["steps"])

    @patch("core.nutrition_ai.select_recipes")
    def test_clarification_fallback_does_not_override_allergy_filter(self, provider):
        provider.return_value = self.clarification()
        for query, kind, excluded in (("sốt; dị ứng trứng", "food", "soft_egg"),
                                      ("sốt; dị ứng sữa", "drink", "warm_milk")):
            with self.subTest(query=query):
                result = get_nutrition_options(query, kind)
                self.assertEqual(result["provider_status"], "ai_clarification_with_options")
                self.assertGreater(len(result["recipes"]), 0)
                self.assertNotIn(excluded, {recipe["id"] for recipe in result["recipes"]})
        provider.reset_mock()
        result = get_nutrition_options("sốt; dị ứng thành phần chưa biết", "food")
        self.assertEqual(result["recipes"], [])
        self.assertEqual(result["provider_status"], "no_candidates")
        provider.assert_not_called()

    @patch("core.nutrition_ai.select_recipes")
    def test_unknown_and_ambiguous_clarifications_are_not_replaced_with_options(self, provider):
        provider.return_value = self.clarification()
        for query in ("tình trạng chưa biết", "tình trạng mơ hồ", "không sốt"):
            with self.subTest(query=query):
                result = get_nutrition_options(query, "food")
                self.assertTrue(result["needs_clarification"])
                self.assertEqual(result["recipes"], [])
                self.assertEqual(result["provider_status"], "ai_needs_clarification")

    @patch("core.nutrition_ai.select_recipes")
    def test_actual_ai_selection_remains_ranked(self, provider):
        selected = {**FOOD[1], "recommendation_reason": "Món súp dạng lỏng để tham khảo."}
        provider.return_value = {"needs_clarification": False, "clarification_question": "",
                                 "recipes": [selected], "model": "mock-model"}
        result = get_nutrition_options("sốt", "food")
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["provider_status"], "ai_ranked")
        self.assertEqual(result["recipes"], [selected])

    @patch("core.nutrition_ai.select_recipes")
    def test_avoidance_summary_survives_ai_success_clarification_and_failure(self, provider):
        expected = prepare_nutrition_candidates("sốt", FOOD)
        selected = {**FOOD[1], "recommendation_reason": "Món súp dạng lỏng để tham khảo."}
        success = {"needs_clarification": False, "clarification_question": "",
                   "recipes": [selected], "model": "mock-model"}
        for outcome, status in ((success, "ai_ranked"),
                                (self.clarification(), "ai_clarification_with_options"),
                                (NutritionAIError("quota"), "fallback_quota")):
            with self.subTest(status=status):
                provider.side_effect = outcome if isinstance(outcome, Exception) else None
                provider.return_value = outcome
                result = get_nutrition_options("sốt", "food")
                self.assertEqual(result["provider_status"], status)
                self.assertEqual(result["avoidance"], expected["avoidance"])
                self.assertEqual(result["avoidance_note"], expected["avoidance_note"])

    @patch("core.nutrition_ai.select_recipes")
    def test_avoidance_summary_survives_no_candidate_path(self, provider):
        query = "sốt; dị ứng thành phần chưa biết"
        expected = prepare_nutrition_candidates(query, FOOD)
        result = get_nutrition_options(query, "food")
        self.assertEqual(result["provider_status"], "no_candidates")
        self.assertEqual(result["recipes"], [])
        self.assertEqual(result["avoidance"], expected["avoidance"])
        self.assertEqual(result["avoidance_note"], expected["avoidance_note"])
        provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
