"""Unit tests for Nutrition Groq config, strict Gout clinical rules, copywriting, and dynamic meal tag."""

import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from core.circuit_breaker import reset_all_circuit_breakers
from core.llm_provider import LLMProvider, _OpenRouterHTTPError, _OpenRouterModels
from core.nutrition_ai import NutritionAIError, select_recipes, validate_selection
from core.nutrition_options import (
    GOUT_DRINKS,
    GOUT_FOODS,
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
        drinks = imported_recipes("drink")[:32]
        fake_response = {
            "needs_clarification": False,
            "clarification_question": "",
            "recommendations": [
                {
                    "recipe_id": drinks[0]["id"],
                    "display_title": drinks[0]["title"],
                    "meal_time": "snack",
                    "dish_role": "drink",
                    "key_nutrients": "Nước",
                    "reason": "Thức uống từ hoa quả tự nhiên ít purin hỗ trợ bù dịch an toàn.",
                    "caution": "Chỉ là gợi ý tham khảo.",
                    "source_ids": [],
                }
            ],
        }

        with patch("core.llm_provider.llm_provider.generate_json", return_value=fake_response) as gen_json:
            result = select_recipes("Gút", "drink", drinks, [])

        self.assertEqual(result["recipes"][0]["id"], drinks[0]["id"])
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
                model = _OpenRouterModels("gsk_test_only_1234567890", provider="groq")
                calls = []

                def fake_post(req_payload):
                    calls.append(req_payload["model"])
                    if len(calls) == 1:
                        raise _OpenRouterHTTPError(code, f"Groq HTTP {code}")
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
        drinks = GOUT_DRINKS[:5] + [imported_recipes("drink")[0], imported_recipes("drink")[1]]
        recs = [
            {
                "recipe_id": r["id"],
                "reason": "Thức uống giàu vitamin C và nước giúp bù dịch.",
                "caution": None if idx == 0 else "",
                "source_ids": [],
            }
            for idx, r in enumerate(drinks)
        ]
        res = validate_selection({"needs_clarification": False, "recommendations": recs}, drinks, 0)
        self.assertEqual(len(res["recipes"]), 6)

        with self.assertRaises(NutritionAIError):
            validate_selection({"needs_clarification": False, "recommendations": []}, drinks, 0)
        with self.assertRaises(NutritionAIError):
            validate_selection(
                {
                    "needs_clarification": False,
                    "recommendations": [
                        {
                            "recipe_id": drinks[0]["id"],
                            "reason": "Lý do hợp lệ đủ dài cho bài kiểm tra.",
                            "caution": "",
                            "source_ids": [2],
                        }
                    ],
                },
                drinks,
                1,
            )

    def test_vifoodrec_drink_calories_calibrated_between_40_and_180(self):
        drinks = imported_recipes("drink")
        self.assertGreaterEqual(len(drinks), 90)
        by_id = {d["id"]: d for d in drinks}

        for drink in drinks:
            self.assertEqual(drink.get("calories_basis"), "per_serving")
            self.assertEqual(drink.get("serving_unit"), "1 ly")
            self.assertTrue(
                40 <= drink["calories"] <= 180,
                f"{drink['id']} ({drink['title']}) calibrated kcal out of range: {drink['calories']}",
            )

        for rid in ("vifoodrec_3943", "vifoodrec_2832", "vifoodrec_2916"):
            self.assertIn(rid, by_id)
            self.assertTrue(40 <= by_id[rid]["calories"] <= 180)

    def test_strict_gout_filter_excludes_poultry_beef_organs_seafood_and_legumes(self):
        for query in ("Gút", "Acid Uric"):
            for kind, extra in (("food", {"gout_food_recipes": GOUT_FOODS}), ("drink", {"gout_drink_recipes": GOUT_DRINKS})):
                with self.subTest(query=query, kind=kind):
                    prepared = prepare_nutrition_candidates(query, imported_recipes(kind), **extra)
                    self.assertTrue(prepared["recognized"])
                    self.assertEqual(prepared["contexts"], ["gout"])
                    self.assertTrue(prepared["recipes"])

                    for recipe in prepared["recipes"]:
                        self.assertFalse(
                            has_gout_forbidden_ingredients(recipe),
                            f"Unsafe recipe leaked into {query} ({kind}): {recipe['title']}",
                        )
                        tags = recipe.get("rule_tags", [])
                        self.assertNotIn("purine_moderate_legume", tags)

                    avoid_titles = " ".join(a["title"].lower() for a in prepared["avoidance"])
                    self.assertIn("gia cầm", avoid_titles)
                    self.assertIn("đậu", avoid_titles)
                    self.assertNotIn("măng", avoid_titles)

        # Explicitly verify notorious problem items are excluded
        excluded_food_titles = {
            e["title"]
            for e in prepare_nutrition_candidates("Gút", imported_recipes("food"), gout_food_recipes=GOUT_FOODS)["excluded"]
        }
        for dangerous in ("Lẩu Gà Lá Chanh", "Bún Chả Cá Miền Trung"):
            self.assertIn(dangerous, excluded_food_titles)

        drink_ids = {
            r["id"]
            for r in prepare_nutrition_candidates("Gút", imported_recipes("drink"), gout_drink_recipes=GOUT_DRINKS)["recipes"]
        }
        self.assertNotIn("vifoodrec_2832", drink_ids)  # Sữa Đậu Xanh Hương Lá Dứa
        self.assertNotIn("vifoodrec_2916", drink_ids)  # Nước Rau Má Đậu Xanh
        self.assertIn("gout_celery_juice", drink_ids)

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
                    "full_meal_set": {
                        "title": "Mâm cơm gợi ý cho 1 bữa",
                        "meal_time": "lunch",
                        "rationale": "Sử dụng trứng và rau xanh ít purin, hỗ trợ kiểm soát acid uric cho người bệnh Gút.",
                        "main_recipe_id": "gout_egg_tomato",
                        "soup_recipe_id": "gout_winter_melon_soup",
                        "side_recipe_id": "gout_boiled_greens",
                        "staple_text": "",
                    },
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

    def test_gout_drink_comorbidities_and_negation(self):
        stomach = prepare_nutrition_candidates("gút và đau dạ dày", imported_recipes("drink"), gout_drink_recipes=GOUT_DRINKS)
        stomach_ids = {r["id"] for r in stomach["recipes"]}
        self.assertNotIn("gout_cucumber_lemon", stomach_ids)
        self.assertNotIn("gout_orange_carrot", stomach_ids)
        self.assertIn("gout_celery_juice", stomach_ids)

        sleep = prepare_nutrition_candidates("gút và mất ngủ", imported_recipes("drink"), gout_drink_recipes=GOUT_DRINKS)
        sleep_ids = {r["id"] for r in sleep["recipes"]}
        self.assertNotIn("gout_light_green_tea", sleep_ids)
        self.assertIn("gout_cherry_juice", sleep_ids)

        negated = prepare_nutrition_candidates("không gút", imported_recipes("drink"), gout_drink_recipes=GOUT_DRINKS)
        self.assertFalse(negated["recognized"])
        neg_ids = {r["id"] for r in negated["recipes"]}
        self.assertNotIn("gout_celery_juice", neg_ids)

    def test_get_nutrition_options_gout_drink_uses_ai_and_curated_front_candidates(self):
        drinks = imported_recipes("drink")
        self.assertTrue(drinks)

        def fake_select(condition, recipe_type, recipes, guidance, personalization=None):
            chosen = []
            for r in recipes[:4]:
                item = dict(r)
                item["recommendation_reason"] = "Thức uống ít purin giàu vitamin C hỗ trợ đào thải acid uric."
                item["ai_caution"] = "Chỉ mang tính tham khảo dinh dưỡng."
                item["source_ids"] = [0] if guidance else []
                chosen.append(item)
            return {"needs_clarification": False, "clarification_question": "", "recipes": chosen, "model": "groq-test"}

        with patch("core.nutrition_ai.select_recipes", side_effect=fake_select) as mock_select:
            res = get_nutrition_options("Gút", "drink")

        self.assertEqual(res["provider_status"], "ai_ranked")
        self.assertTrue(res["ai_used"])
        self.assertEqual(
            res["notice"],
            "MediMind đã chọn lọc các thức uống an toàn và phù hợp nhất với yêu cầu và hồ sơ sức khỏe của bạn.",
        )
        passed_candidates = mock_select.call_args.args[2]
        self.assertEqual(passed_candidates[0]["id"], "gout_celery_juice")
        for r in res["recipes"]:
            self.assertFalse(has_gout_forbidden_ingredients(r))
            self.assertTrue(15 <= r["calories"] <= 180)

    def test_resolve_meal_slot_by_query_or_system_hour(self):
        self.assertEqual(_resolve_meal_slot("Gút", now_hour=8), ("breakfast", "Bữa sáng"))
        self.assertEqual(_resolve_meal_slot("Gút", now_hour=12), ("lunch", "Bữa trưa"))
        self.assertEqual(_resolve_meal_slot("Gút", now_hour=15), ("snack", "Bữa phụ"))
        self.assertEqual(_resolve_meal_slot("Gút", now_hour=19), ("dinner", "Bữa tối"))
        self.assertEqual(_resolve_meal_slot("Gút, bữa sáng", now_hour=19), ("breakfast", "Bữa sáng"))
        self.assertEqual(_resolve_meal_slot("Gút, bữa trưa", now_hour=8), ("lunch", "Bữa trưa"))


if __name__ == "__main__":
    unittest.main()
