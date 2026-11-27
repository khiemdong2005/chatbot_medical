"""Hard exclusions must remain effective even if the context is unrecognized."""
from copy import deepcopy
import unittest

from core.nutrition_rules import prepare_nutrition_candidates
from core.recipe_catalog import imported_recipes


def _sample_recipe(rid, title, ingredients, steps=None, language="vi"):
    return {
        "id": rid,
        "title": title,
        "recipe_type": "food",
        "language": language,
        "cuisine": "VN",
        "imported": True,
        "ingredients": [{"name": name, "amount": "", "unit": ""} for name in ingredients],
        "steps": steps or ["Nấu chín nguyên liệu và dùng ấm."],
        "categories": [],
    }


FOOD = [
    _sample_recipe("oat_porridge", "Cháo yến mạch chuối", ["Yến mạch 40g", "Chuối chín 1 quả", "Nước lọc 250ml"]),
    _sample_recipe("pumpkin_soup", "Súp bí đỏ", ["Bí đỏ 150g", "Khoai tây 80g", "Nước lọc 300ml"]),
    _sample_recipe("rice_carrot", "Cháo gạo cà rốt", ["Gạo tẻ 50g", "Cà rốt 60g", "Nước lọc 450ml"]),
    _sample_recipe("soft_egg", "Trứng hấp mềm", ["Trứng gà 1 quả", "Nước ấm 80ml"]),
    _sample_recipe("tofu_pumpkin", "Đậu hũ non bí đỏ", ["Đậu hũ non 100g", "Bí đỏ 100g", "Nước lọc 50ml"]),
]


class NutritionRulesTests(unittest.TestCase):
    def ids(self, query, recipes=None):
        result = prepare_nutrition_candidates(query, recipes if recipes is not None else FOOD)
        return {recipe["id"] for recipe in result["recipes"]}

    def test_embedded_allergy_marker_never_silently_ignored(self):
        for query in ("tôi bị ho và dị ứng trứng", "ho dị ứng trứng", "ho, tôi dị ứng trứng", "tôi dị ứng trứng"):
            with self.subTest(query=query):
                result = prepare_nutrition_candidates(query, FOOD)
                self.assertIn("egg", result["allergies"])
                self.assertNotIn("soft_egg", {r["id"] for r in result["recipes"]})
                self.assertTrue(any(r["id"] == "soft_egg" for r in result["excluded"]))

    def test_embedded_egg_allergy_and_multiple_allergens(self):
        self.assertNotIn("soft_egg", self.ids("mất ngủ, tôi dị ứng trứng"))
        ids = self.ids("ho; dị ứng đậu nành và trứng")
        self.assertNotIn("tofu_pumpkin", ids)
        self.assertNotIn("soft_egg", ids)
        self.assertNotIn("tofu_pumpkin", self.ids("ho và tránh đậu nành"))

    def test_negated_allergy_does_not_create_exclusion(self):
        for query in ("không dị ứng trứng", "ho; không dị ứng trứng", "tôi không dị ứng trứng", "ho và không dị ứng trứng", "tôi chưa bị dị ứng trứng"):
            with self.subTest(query=query):
                result = prepare_nutrition_candidates(query, FOOD)
                self.assertEqual(result["allergies"], [])
                self.assertIn("soft_egg", {r["id"] for r in result["recipes"]})

    def test_unsupported_or_ambiguous_constraints_fail_closed(self):
        for query in ("ho và dị ứng", "ho dị ứng sữa và không dị ứng trứng"):
            with self.subTest(query=query):
                result = prepare_nutrition_candidates(query, FOOD)
                self.assertEqual(result["recipes"], [])
                self.assertEqual(len(result["excluded"]), len(FOOD))
        self.assertIn("seafood", prepare_nutrition_candidates("ho dị ứng hải sản", FOOD)["allergies"])
        self.assertIn("sesame", prepare_nutrition_candidates("ho; tôi dị ứng mè", FOOD)["allergies"])

    def test_gluten_requires_verified_oats(self):
        ids = self.ids("ho; tránh gluten")
        self.assertNotIn("oat_porridge", ids)
        self.assertIn("rice_carrot", ids)

    def test_unknown_and_changed_metadata_fail_closed_for_allergies(self):
        changed = deepcopy(FOOD[0])
        changed["ingredients"].append({"name": "Sữa tươi 10ml", "amount": "", "unit": ""})
        unknown = _sample_recipe("unreviewed", "Món bí ẩn", ["Gia vị bí truyền không rõ thành phần"])
        self.assertEqual(self.ids("ho dị ứng sữa", [changed, unknown]), set())

    def test_negated_contexts_are_not_diagnosed(self):
        for query in ("không mất ngủ", "chưa bị mất ngủ"):
            with self.subTest(query=query):
                self.assertFalse(prepare_nutrition_candidates(query, FOOD)["recognized"])
        self.assertTrue(prepare_nutrition_candidates("mất ngủ, tôi dị ứng trứng", FOOD)["recognized"])

    def test_multi_condition_comorbidity_is_supported_and_intersects_restrictions(self):
        result = prepare_nutrition_candidates("gút và tiểu đường", FOOD)
        self.assertTrue(result["recognized"])
        self.assertEqual(result["contexts"], ["gout", "diabetes"])
        self.assertIn("Bệnh gút", result["context_label"])
        self.assertIn("Tiểu đường", result["context_label"])
        # Both NHS guidelines present
        self.assertTrue(any("gout" in g["source_url"].lower() for g in result["guidance"]))
        self.assertTrue(any("diabetes" in g["source_url"] for g in result["guidance"]))
        # Both avoidances present
        avoid_titles = {a["title"] for a in result["avoidance"]}
        self.assertTrue(any("purin" in t.lower() or "hải sản" in t.lower() for t in avoid_titles))
        self.assertTrue(any("đường" in t.lower() for t in avoid_titles))

    def test_does_not_mutate_catalog_and_keeps_attribution(self):
        before = deepcopy(FOOD)
        result = prepare_nutrition_candidates("nhiệt miệng", FOOD)
        self.assertEqual(FOOD, before)
        self.assertTrue(result["guidance"])
        self.assertTrue(all(g["source_url"].startswith("https://") for g in result["guidance"]))

    def test_mouth_filters_imported_irritants_before_model_or_fallback(self):
        recipes = [
            _sample_recipe("spicy_soup", "Canh chua cay", ["Ớt hiểm 2 trái", "Chanh 1 quả", "Nước lọc 300ml"]),
            _sample_recipe("sour_soup", "Súp tiêu cay", ["Tiêu xay 2 muỗng", "Giấm 2 muỗng", "Nước lọc 300ml"]),
            _sample_recipe("mild_congee", "Cháo gạo mềm", ["Gạo tẻ 50g", "Nước lọc 400ml"]),
        ]
        result = prepare_nutrition_candidates("nhiệt miệng", recipes)
        self.assertEqual({recipe["title"] for recipe in result["recipes"]}, {"Cháo gạo mềm"})
        self.assertEqual({recipe["title"] for recipe in result["excluded"]}, {"Canh chua cay", "Súp tiêu cay"})
        self.assertTrue(all("cay hoặc chua" in recipe["reason"] for recipe in result["excluded"]))
        self.assertEqual({recipe["title"] for recipe in prepare_nutrition_candidates("sốt", recipes)["recipes"]},
                         {"Canh chua cay", "Súp tiêu cay", "Cháo gạo mềm"})

    def test_fever_aliases_have_attributable_guidance_for_food(self):
        for query in ("sốt", "sot", "bị sốt", "tôi bị sốt", "sốt ăn gì", "sốt nên ăn gì", "fever"):
            with self.subTest(query=query):
                result = prepare_nutrition_candidates(query, FOOD)
                self.assertTrue(result["recognized"])
                self.assertTrue(result["guidance"])
                self.assertTrue(result["recipes"])
                self.assertTrue(all(g["source_url"].startswith("https://") for g in result["guidance"]))

    def test_fever_negations_are_not_diagnosed(self):
        for query in ("không sốt", "không bị sốt", "không sốt nhưng mất ngủ"):
            with self.subTest(query=query):
                result = prepare_nutrition_candidates(query, FOOD)
                self.assertFalse(result["recognized"])

    def test_fever_avoidance_is_source_backed_alcohol_only(self):
        result = prepare_nutrition_candidates("sốt", FOOD)
        self.assertEqual(len(result["avoidance"]), 1)
        item = result["avoidance"][0]
        self.assertTrue("rượu" in item["title"].lower() or "alcohol" in item["title"].lower())
        for field in ("title", "reason", "source_title", "source_url", "level"):
            self.assertIsInstance(item[field], str)
            self.assertTrue(item[field].strip())
        self.assertIn(item["level"], ("avoid", "limit"))
        self.assertTrue(item["source_url"].startswith("https://"))
        self.assertTrue(result["avoidance_note"].strip())
        text = " ".join((item["title"], item["reason"])).lower()
        for unsupported in ("đồ lạnh", "caffeine", "chiên", "dầu mỡ"):
            self.assertNotIn(unsupported, text)

    def test_condition_avoidance_lists_are_attributed(self):
        for query in ("nhiệt miệng", "mất ngủ", "trào ngược"):
            with self.subTest(query=query):
                result = prepare_nutrition_candidates(query, FOOD)
                self.assertTrue(result["avoidance"])
                for item in result["avoidance"]:
                    self.assertTrue(item["title"].strip())
                    self.assertTrue(item["reason"].strip())
                    self.assertTrue(item["source_title"].strip())
                    self.assertTrue(item["source_url"].startswith("https://"))
                    self.assertIn(item["level"], ("avoid", "limit"))

    def test_unknown_or_negated_context_does_not_invent_restrictions(self):
        for query in ("tình trạng chưa biết", "không sốt", "không bị sốt", "ho", "stress"):
            with self.subTest(query=query):
                result = prepare_nutrition_candidates(query, FOOD)
                self.assertEqual(result["avoidance"], [])
                self.assertIsInstance(result["avoidance_note"], str)
                self.assertTrue(result["avoidance_note"].strip())

    def test_declared_allergy_is_visible_in_avoidance_summary(self):
        result = prepare_nutrition_candidates("ho; dị ứng trứng", FOOD)
        self.assertTrue(any("trứng" in item["title"].lower() for item in result["avoidance"]))
        self.assertNotIn("soft_egg", {recipe["id"] for recipe in result["recipes"]})
        for item in result["avoidance"]:
            self.assertTrue(item["reason"].strip())
            self.assertTrue(item["source_url"].startswith("https://"))


    def test_gout_purges_high_purine_recipes_and_sets_avoidance(self):
        result = prepare_nutrition_candidates("gút", imported_recipes("food"))
        self.assertTrue(result["recognized"])
        self.assertTrue(result["avoidance"])
        for item in result["avoidance"]:
            self.assertTrue(item["source_url"].startswith("https://"))
        for recipe in result["recipes"]:
            title = recipe["title"].lower()
            for forbidden in ("hàu", "giò heo", "móng giò", "chân giò", "thịt bò"):
                self.assertNotIn(forbidden, title)
        self.assertFalse(any("măng" in item["title"].lower() for item in result["avoidance"]))

    def test_unmapped_complex_disease_flags_safeguard(self):
        for query in ("ung thư gan", "viêm tụy cấp", "suy hô hấp"):
            with self.subTest(query=query):
                result = prepare_nutrition_candidates(query, FOOD)
                self.assertFalse(result["recognized"])
                self.assertTrue(result["is_unmapped_disease"])

    def test_meal_and_dish_role_classification(self):
        from core.recipe_catalog import classify_dish_role, classify_meal_times
        main_dish = {"title": "Gà hấp hành", "recipe_type": "food", "categories": ["Món mặn"]}
        soup_dish = {"title": "Canh sườn hạt sen", "recipe_type": "food", "categories": ["Món canh"]}
        side_dish = {"title": "Rau cải xào nấm", "recipe_type": "food", "categories": ["Món xào"]}
        staple_dish = {"title": "Cháo nấm hạt sen", "recipe_type": "food", "categories": ["Món cháo"]}

        self.assertEqual(classify_dish_role(main_dish), "main")
        self.assertEqual(classify_dish_role(soup_dish), "soup")
        self.assertEqual(classify_dish_role(side_dish), "side")
        self.assertEqual(classify_dish_role(staple_dish), "staple")

        self.assertIn("breakfast", classify_meal_times(staple_dish, "staple"))
        self.assertIn("dinner", classify_meal_times(soup_dish, "soup"))

    def test_retrieve_candidates_dish_role_diversity(self):
        from core.recipe_catalog import retrieve_candidates, classify_dish_role
        candidates = retrieve_candidates("mất ngủ", imported_recipes("food"))
        roles = {classify_dish_role(c) for c in candidates}
        self.assertIn("main", roles)
        self.assertIn("soup", roles)
        self.assertGreaterEqual(len(roles), 3)

    def test_get_nutrition_options_enriches_meals_and_full_meal_set(self):
        from core.nutrition_options import get_nutrition_options
        result = get_nutrition_options("mất ngủ", "food")
        self.assertTrue(result["recipes"])
        for recipe in result["recipes"]:
            self.assertIn("meal_time", recipe)
            self.assertIn("meal_label", recipe)
            self.assertIn("dish_role", recipe)
            self.assertIn("dish_role_label", recipe)
            self.assertIn("key_nutrients", recipe)
            self.assertTrue(len(recipe["recommendation_reason"]) >= 20)

        fms = result.get("full_meal_set")
        self.assertIsNotNone(fms)
        self.assertTrue(fms.get("title"))
        self.assertTrue(fms.get("rationale"))
        self.assertGreaterEqual(len(fms.get("dishes", [])), 2)

    def test_nhiet_mieng_full_meal_set_has_no_duplicate_soups(self):
        from core.nutrition_options import get_nutrition_options
        result = get_nutrition_options("nhiệt miệng", "food")
        fms = result.get("full_meal_set")
        self.assertIsNotNone(fms)
        roles = [d["role"] for d in fms["dishes"]]
        self.assertIn("main", roles)
        self.assertIn("soup", roles)

        main_dish = next(d["recipe"] for d in fms["dishes"] if d["role"] == "main")
        soup_dish = next(d["recipe"] for d in fms["dishes"] if d["role"] == "soup")

        self.assertNotIn("canh", main_dish["title"].lower())
        self.assertNotEqual(main_dish["id"], soup_dish["id"])

        # Never 3 soups
        soup_titles = [d["recipe"]["title"] for d in fms["dishes"] if "canh" in d["recipe"]["title"].lower()]
        self.assertLessEqual(len(soup_titles), 1)

    def test_full_meal_set_and_single_dishes_do_not_overlap(self):
        from core.nutrition_options import get_nutrition_options
        from core.recipe_catalog import is_standalone_one_dish, title_key

        for cond in ("nhiệt miệng", "mất ngủ", "mệt mỏi"):
            with self.subTest(condition=cond):
                result = get_nutrition_options(cond, "food")
                fms = result.get("full_meal_set")
                self.assertIsNotNone(fms)
                fms_ids = {d["recipe"]["id"] for d in fms["dishes"]}
                fms_titles = {title_key(d["recipe"]) for d in fms["dishes"]}
                single_ids = {r["id"] for r in result["recipes"]}
                single_titles = {title_key(r) for r in result["recipes"]}

                overlap_ids = fms_ids & single_ids
                overlap_titles = fms_titles & single_titles
                self.assertEqual(len(overlap_ids), 0, f"Found duplicate IDs between full meal and singles: {overlap_ids}")
                self.assertEqual(len(overlap_titles), 0, f"Found duplicate titles between full meal and singles: {overlap_titles}")

                # Ensure single dishes are standalone one-dish meals
                for r in result["recipes"]:
                    self.assertTrue(is_standalone_one_dish(r), f"Dish '{r['title']}' is not a standalone one-dish meal")
                    self.assertTrue(r.get("recommendation_reason"), f"Dish '{r['title']}' missing recommendation_reason")
                    self.assertNotIn("none", str(r.get("recommendation_reason")).lower()[:10])

    def test_validate_selection_rejects_fake_3_soup_meal(self):
        from core.nutrition_ai import validate_selection
        # 3 soups passed into full_meal_set must be rejected
        catalog = [
            {"id": "soup_1", "title": "Canh Đậu Hũ Rau Củ"},
            {"id": "soup_2", "title": "Canh Mồng Tơi Chay"},
            {"id": "soup_3", "title": "Canh Hẹ Đậu Hũ"}
        ]
        val = {
            "needs_clarification": False,
            "clarification_question": "",
            "recommendations": [
                {"recipe_id": "soup_1", "display_title": "Canh Đậu Hũ", "reason": "Món canh thanh mát dễ nuốt khi cơ thể mệt mỏi.", "caution": "", "source_ids": []}
            ],
            "full_meal_set": {
                "title": "Mâm cơm",
                "meal_time": "dinner",
                "rationale": "Mâm cơm thanh mát đủ chất cho bữa tối.",
                "main_recipe_id": "soup_1",  # SOUP in main role
                "soup_recipe_id": "soup_2",
                "side_recipe_id": "soup_3"
            }
        }
        res = validate_selection(val, catalog, 0)
        # full_meal_set should be rejected because main is a soup
        self.assertNotIn("full_meal_set", res)

    def test_side_dish_rejects_duplicate_main_ingredients(self):
        from core.nutrition_options import _is_valid_side, _extract_main_ingredient_tags
        r_main = {
            "id": "vifoodrec_main_1",
            "title": "Nấm Đông Cô Nhồi Đậu Hũ Sốt Cà Chua",
            "ingredients": [{"name": "Đậu hũ non"}, {"name": "Nấm đông cô"}]
        }
        r_side_dup = {
            "id": "vifoodrec_side_1",
            "title": "Đậu Hũ Sốt Nấm Rau Củ Chay",
            "dish_role": "side",
            "ingredients": [{"name": "Đậu hũ"}, {"name": "Nấm rơm"}]
        }
        r_side_clean = {
            "id": "vifoodrec_side_2",
            "title": "Cải Thìa Xào Dầu Hào",
            "dish_role": "side",
            "ingredients": [{"name": "Cải thìa"}]
        }
        self.assertFalse(_is_valid_side(r_side_dup, main_r=r_main))
        self.assertTrue(_is_valid_side(r_side_clean, main_r=r_main))


if __name__ == "__main__":
    unittest.main()
