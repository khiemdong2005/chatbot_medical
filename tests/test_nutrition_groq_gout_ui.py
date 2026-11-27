"""Unit tests for Nutrition Groq config, strict Gout clinical rules, copywriting, and dynamic meal tag."""

import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from core.circuit_breaker import reset_all_circuit_breakers
from core.llm_provider import LLMProvider, _GroqHTTPError, _GroqModels
from core.nutrition_ai import NutritionAIError, select_recipes, validate_selection
from core.nutrition_options import (
    _resolve_meal_slot,
    get_nutrition_options,
)
from core.nutrition_rules import has_gout_forbidden_ingredients, prepare_nutrition_candidates
from core.recipe_catalog import imported_recipes, retrieve_candidates

REPO_ROOT = Path(__file__).resolve().parent.parent


class NutritionGroqGoutUITests(unittest.TestCase):
    def setUp(self):
        reset_all_circuit_breakers()

    def tearDown(self):
        reset_all_circuit_breakers()

    @patch.dict(
        os.environ,
        {
            "AI_PROVIDER": "groq",
            "NUTRITION_AI_PROVIDER": "",
            "GROQ_API_KEY": "gsk_test_only_1234567890",
            "GROQ_NUTRITION_MODEL": "llama-3.3-70b-versatile",
        },
        clear=False,
    )
    def test_select_recipes_uses_groq_and_compacts_32_candidates(self):
        foods = prepare_nutrition_candidates("Gút", imported_recipes("food"))["recipes"][:32]
        fake_response = {
            "needs_clarification": False,
            "clarification_question": "",
            "recommendations": [
                {
                    "recipe_id": foods[0]["id"],
                    "display_title": foods[0]["title"],
                    "meal_time": "lunch",
                    "dish_role": "main",
                    "key_nutrients": "Chất xơ",
                    "reason": "Món ăn từ rau củ ít purin hỗ trợ kiểm soát acid uric an toàn.",
                    "caution": "Chỉ là gợi ý tham khảo.",
                    "source_ids": [],
                }
            ],
        }

        with patch("core.llm_provider.llm_provider.generate_json", return_value=fake_response) as gen_json:
            result = select_recipes("Gút", "food", foods, [])

        self.assertEqual(result["recipes"][0]["id"], foods[0]["id"])
        kwargs = gen_json.call_args.kwargs
        self.assertEqual(kwargs["provider"], "groq")
        self.assertTrue(kwargs["json_mode"])
        self.assertEqual(kwargs["model"], "llama-3.3-70b-versatile")
        payload = json.loads(kwargs["contents"])
        self.assertEqual(len(payload["candidates"]), 18)
        self.assertLess(len(kwargs["contents"]), 12000)

    def test_groq_model_falls_back_on_404_and_413_and_strips_think_tags(self):
        for code in (404, 413):
            with self.subTest(code=code):
                model = _GroqModels("gsk_test_only_1234567890")
                calls = []

                def fake_post(req_payload):
                    calls.append(req_payload["model"])
                    if len(calls) == 1:
                        raise _GroqHTTPError(code, f"Groq HTTP {code}")
                    return {"choices": [{"message": {"content": '{"ok": true}'}}]}

                with patch.object(model, "_post_completion", side_effect=fake_post):
                    resp = model.generate_content(model="llama-3.3-70b-versatile", contents="{}")

                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0], "llama-3.3-70b-versatile")
                self.assertEqual(calls[1], "qwen/qwen3.8-27b")
                self.assertEqual(json.loads(resp.text), {"ok": True})

        provider = LLMProvider()

        class ThinkClient:
            class models:
                @staticmethod
                def generate_content(model, contents, config=None):
                    class R:
                        text = '<think>reasoning trace</think>```json\n{"status": "parsed"}\n```'
                    return R()

        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_only_1234567890"}, clear=False), \
             patch.object(provider, "resolve_api_key", return_value="gsk_test_only_1234567890"), \
             patch.object(provider, "get_client", return_value=ThinkClient()):
            parsed = provider.generate_json(
                contents="{}",
                model="qwen/qwen3.8-27b",
                provider="groq",
                api_key="gsk_test_only_1234567890",
            )
        self.assertEqual(parsed, {"status": "parsed"})

    def test_validate_selection_trims_excess_items_while_rejecting_invalid_ids(self):
        foods = imported_recipes("food")[:7]
        recs = [
            {
                "recipe_id": r["id"],
                "reason": "Món ăn ít purin giàu chất xơ phù hợp chế độ ăn nhẹ nhàng.",
                "caution": None if idx == 0 else "",
                "source_ids": [],
            }
            for idx, r in enumerate(foods)
        ]
        res = validate_selection({"needs_clarification": False, "recommendations": recs}, foods, 0)
        self.assertEqual(len(res["recipes"]), 6)

        with self.assertRaises(NutritionAIError):
            validate_selection({"needs_clarification": False, "recommendations": []}, foods, 0)
        with self.assertRaises(NutritionAIError):
            validate_selection(
                {
                    "needs_clarification": False,
                    "recommendations": [
                        {
                            "recipe_id": foods[0]["id"],
                            "reason": "Lý do hợp lệ đủ dài cho bài kiểm tra.",
                            "caution": "",
                            "source_ids": [2],
                        }
                    ],
                },
                foods,
                1,
            )

    def test_drinks_removed_from_catalog(self):
        self.assertEqual(imported_recipes("drink"), [])

    def test_strict_gout_filter_excludes_poultry_beef_organs_seafood_and_legumes(self):
        for query in ("Gút", "Acid Uric"):
            with self.subTest(query=query):
                prepared = prepare_nutrition_candidates(query, imported_recipes("food"))
                self.assertTrue(prepared["recognized"])
                self.assertEqual(prepared["contexts"], ["gout"])
                self.assertTrue(prepared["recipes"])

                for recipe in prepared["recipes"]:
                    self.assertFalse(
                        has_gout_forbidden_ingredients(recipe),
                        f"Unsafe recipe leaked into {query}: {recipe['title']}",
                    )
                    tags = recipe.get("rule_tags", [])
                    self.assertNotIn("purine_moderate_legume", tags)

                avoid_titles = " ".join(a["title"].lower() for a in prepared["avoidance"])
                self.assertIn("gia cầm", avoid_titles)
                self.assertIn("đậu", avoid_titles)
                self.assertNotIn("măng", avoid_titles)

        # Explicitly verify dangerous items with chicken/seafood are excluded
        excluded_list = prepare_nutrition_candidates("Gút", imported_recipes("food"))["excluded"]
        self.assertGreater(len(excluded_list), 1000)

    def test_gout_food_and_low_sugar_comorbidity_yield_clean_full_meal_set(self):
        with patch("core.nutrition_ai.select_recipes") as mock_select:
            def fake_select(condition, recipe_type, recipes, guidance, personalization=None):
                chosen = []
                for r in recipes[:5]:
                    item = dict(r)
                    item["recommendation_reason"] = (
                        "Sử dụng rau xanh và nguyên liệu ít purin, hỗ trợ kiểm soát acid uric an toàn cho người bệnh Gút."
                    )
                    item["ai_caution"] = "Loại trừ thịt gà, thịt bò, nội tạng, hải sản và các loại đậu."
                    item["source_ids"] = [0] if guidance else []
                    chosen.append(item)
                return {
                    "needs_clarification": False,
                    "clarification_question": "",
                    "recipes": chosen,
                    "model": "groq-test",
                }

            mock_select.side_effect = fake_select
            for query in ("Gút", "gút, ít đường"):
                with self.subTest(query=query):
                    res = get_nutrition_options(query, "food")
                    self.assertEqual(res["provider_status"], "ai_ranked")
                    self.assertTrue(res["ai_used"])
                    self.assertEqual(
                        res["notice"],
                        "MediMind đã chọn lọc các món ăn an toàn và phù hợp nhất với yêu cầu và hồ sơ sức khỏe của bạn.",
                    )
                    self.assertNotIn("ứng viên đã qua lọc", res["notice"])
                    fms = res.get("full_meal_set")
                    self.assertIsNotNone(fms)
                    all_returned = list(res["recipes"]) + [d["recipe"] for d in fms["dishes"]]
                    for dish in all_returned:
                        self.assertFalse(has_gout_forbidden_ingredients(dish), f"Leaked dish: {dish['title']}")
                        reason = dish["recommendation_reason"].lower()
                        self.assertNotIn("món có kết cấu mềm", reason)
                        self.assertTrue("purin" in reason or "acid uric" in reason or "gút" in reason, reason)

    def test_resolve_meal_slot_by_query_or_system_hour(self):
        self.assertEqual(_resolve_meal_slot("Gút", now_hour=8), ("breakfast", "Bữa sáng"))
        self.assertEqual(_resolve_meal_slot("Gút", now_hour=12), ("lunch", "Bữa trưa"))
        self.assertEqual(_resolve_meal_slot("Gút", now_hour=15), ("snack", "Bữa phụ"))
        self.assertEqual(_resolve_meal_slot("Gút", now_hour=19), ("dinner", "Bữa tối"))
        self.assertEqual(_resolve_meal_slot("Gút, bữa sáng", now_hour=19), ("breakfast", "Bữa sáng"))
        self.assertEqual(_resolve_meal_slot("Gút, bữa trưa", now_hour=8), ("lunch", "Bữa trưa"))

    def test_ui_tab_rename_food_only_copywriting_and_dynamic_meal_tag(self):
        html = (REPO_ROOT / "frontend/templates/index.html").read_text(encoding="utf-8")
        app_js = (REPO_ROOT / "frontend/static/js/app.js").read_text(encoding="utf-8")
        flow_js = (REPO_ROOT / "frontend/static/js/nutrition-flow.js").read_text(encoding="utf-8")
        css = (REPO_ROOT / "frontend/static/css/nutrition-flow.css").read_text(encoding="utf-8")

        self.assertIn("Dinh dưỡng &amp; Pha chế", html)
        self.assertNotIn("Pha chế dinh dưỡng", html)
        self.assertIn('nav_doctor: "Dinh dưỡng & Pha chế"', app_js)
        self.assertIn('dock_doctor: "Dinh dưỡng & Pha chế"', app_js)
        self.assertIn('home_c2_title: "Dinh dưỡng & Pha chế"', app_js)
        self.assertNotIn("Pha chế dinh dưỡng", app_js)

        for marker in (
            'id="nf-results-icon"',
            'id="nf-results-title-text"',
            'id="nf-results-subtitle"',
            'class="nf-results-topbar"',
            'class="nf-results-header-row"',
        ):
            self.assertIn(marker, html)

        self.assertIn("function updateResultsHeader()", flow_js)
        self.assertIn("function _resolveFullMealTag(fms, nowDate = new Date())", flow_js)
        self.assertIn("const mealLabel = _resolveFullMealTag(fms);", flow_js)
        self.assertNotIn("AI đã chọn", flow_js)
        self.assertIn(
            "MediMind đã chọn lọc các món ăn an toàn và phù hợp nhất với yêu cầu và hồ sơ sức khỏe của bạn.",
            flow_js,
        )
        self.assertNotIn('data-nf-type="drink"', html)
        self.assertNotIn("nf-tab-drink", flow_js)
        self.assertNotIn("nf-panel-drink", flow_js)

        for rule in (
            "#doctor-tab #nf-results.nf-stage",
            "#doctor-tab .nf-results-topbar",
            "#doctor-tab .nf-results-header-row",
            "#doctor-tab .nf-results-icon",
            "#doctor-tab .nf-purine-badge",
        ):
            self.assertIn(rule, css)


if __name__ == "__main__":
    unittest.main()
