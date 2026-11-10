"""Hard exclusions must remain effective even if the context is unrecognized."""
from copy import deepcopy
import unittest

from core.nutrition_options import FOOD, DRINK
from core.nutrition_rules import prepare_nutrition_candidates


class NutritionRulesTests(unittest.TestCase):
    def ids(self, query, recipes=None):
        result = prepare_nutrition_candidates(query, recipes if recipes is not None else FOOD + DRINK)
        return {recipe["id"] for recipe in result["recipes"]}

    def test_embedded_allergy_marker_never_silently_ignored(self):
        for query in ("tôi bị ho và dị ứng sữa", "ho dị ứng sữa", "ho, tôi dị ứng sữa", "tôi dị ứng sữa"):
            with self.subTest(query=query):
                result = prepare_nutrition_candidates(query, DRINK)
                self.assertIn("milk", result["allergies"])
                self.assertNotIn("warm_milk", {r["id"] for r in result["recipes"]})
                self.assertTrue(any(r["id"] == "warm_milk" for r in result["excluded"]))

    def test_embedded_egg_allergy_and_multiple_allergens(self):
        self.assertNotIn("soft_egg", self.ids("mất ngủ, tôi dị ứng trứng"))
        ids = self.ids("ho; dị ứng sữa và trứng")
        self.assertNotIn("warm_milk", ids)
        self.assertNotIn("soft_egg", ids)
        self.assertNotIn("tofu_pumpkin", self.ids("ho và tránh đậu nành"))
        self.assertNotIn("warm_soy", self.ids("dị ứng sữa đậu nành"))

    def test_negated_allergy_does_not_create_exclusion(self):
        for query in ("không dị ứng sữa", "ho; không dị ứng sữa", "tôi không dị ứng sữa", "ho và không dị ứng sữa", "tôi chưa bị dị ứng sữa"):
            with self.subTest(query=query):
                result = prepare_nutrition_candidates(query, DRINK)
                self.assertEqual(result["allergies"], [])
                self.assertIn("warm_milk", {r["id"] for r in result["recipes"]})

    def test_unsupported_or_ambiguous_constraints_fail_closed(self):
        for query in ("ho dị ứng hải sản", "ho; tôi dị ứng mè", "ho và dị ứng", "ho dị ứng sữa và không dị ứng trứng"):
            with self.subTest(query=query):
                result = prepare_nutrition_candidates(query, FOOD + DRINK)
                self.assertEqual(result["recipes"], [])
                self.assertEqual(len(result["excluded"]), len(FOOD + DRINK))

    def test_gluten_requires_verified_oats(self):
        ids = self.ids("ho; tránh gluten")
        self.assertFalse({"oat_porridge", "oat_drink", "barley_water"} & ids)
        self.assertIn("rice_carrot", ids)

    def test_unknown_and_changed_metadata_fail_closed_for_allergies(self):
        changed = deepcopy(FOOD[0])
        changed["ingredients"].append({"name": "Sữa tươi", "amount": 10, "unit": "ml"})
        unknown = {**deepcopy(FOOD[0]), "id": "unreviewed"}
        self.assertEqual(self.ids("ho dị ứng sữa", [changed, unknown]), set())

    def test_negated_or_multiple_contexts_are_not_diagnosed(self):
        for query in ("không mất ngủ", "ho và mất ngủ", "tôi bị ho và dị ứng sữa"):
            with self.subTest(query=query):
                self.assertFalse(prepare_nutrition_candidates(query, FOOD)["recognized"])
        self.assertTrue(prepare_nutrition_candidates("mất ngủ, tôi dị ứng trứng", FOOD)["recognized"])

    def test_does_not_mutate_catalog_and_keeps_attribution(self):
        before = deepcopy(FOOD)
        result = prepare_nutrition_candidates("nhiệt miệng", FOOD)
        self.assertEqual(FOOD, before)
        self.assertTrue(result["guidance"])
        self.assertTrue(all(g["source_url"].startswith("https://") for g in result["guidance"]))

    def test_fever_aliases_have_attributable_guidance_for_both_types(self):
        for query in ("sốt", "sot", "bị sốt", "tôi bị sốt", "sốt ăn gì", "sốt nên ăn gì", "fever"):
            for catalog in (FOOD, DRINK):
                with self.subTest(query=query, kind="food" if catalog is FOOD else "drink"):
                    result = prepare_nutrition_candidates(query, catalog)
                    self.assertTrue(result["recognized"])
                    self.assertTrue(result["guidance"])
                    self.assertTrue(result["recipes"])
                    self.assertTrue(all(g["source_url"].startswith("https://") for g in result["guidance"]))

    def test_fever_negation_and_combined_context_are_not_diagnosed(self):
        for query in ("không sốt", "không bị sốt", "không sốt nhưng mất ngủ", "sốt và mất ngủ"):
            with self.subTest(query=query):
                result = prepare_nutrition_candidates(query, FOOD)
                self.assertFalse(result["recognized"])

    def test_fever_avoidance_is_source_backed_alcohol_only(self):
        for catalog in (FOOD, DRINK):
            with self.subTest(kind="food" if catalog is FOOD else "drink"):
                result = prepare_nutrition_candidates("sốt", catalog)
                self.assertEqual(len(result["avoidance"]), 1)
                item = result["avoidance"][0]
                self.assertTrue("rượu" in item["title"].lower() or "alcohol" in item["title"].lower())
                for field in ("title", "reason", "source_title", "source_url", "level"):
                    self.assertIsInstance(item[field], str)
                    self.assertTrue(item[field].strip())
                self.assertIn(item["level"], ("avoid", "limit"))
                self.assertTrue(item["source_url"].startswith("https://"))
                self.assertTrue(result["avoidance_note"].strip())
                # Unsupported blanket food restrictions should not become
                # medical advice simply because the query contains fever.
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
        result = prepare_nutrition_candidates("ho; dị ứng sữa", DRINK)
        self.assertTrue(any("sữa" in item["title"].lower() for item in result["avoidance"]))
        self.assertNotIn("warm_milk", {recipe["id"] for recipe in result["recipes"]})
        for item in result["avoidance"]:
            self.assertTrue(item["reason"].strip())
            self.assertTrue(item["source_url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
