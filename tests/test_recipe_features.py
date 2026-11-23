from copy import deepcopy
import unittest

from core.recipe_features import analyze_imported_recipe, normalize_ingredient


def recipe(ingredients, title="Vegetable soup", steps=None, kind="food"):
    return {"id": "wikibooks_test", "title": title, "recipe_type": kind, "categories": [],
            "ingredients": [{"name": name, "amount": "", "unit": ""} for name in ingredients],
            "steps": steps or ["Boil the ingredients until cooked and soft."]}


class RecipeFeaturesTests(unittest.TestCase):
    def test_plain_vegetable_soup_has_useful_features_without_safety_claim(self):
        result = analyze_imported_recipe(recipe(["2 carrots, peeled", "1 potato", "500 ml water", "salt to taste"]))
        self.assertTrue(result["soft"])
        self.assertFalse(result["allergen_uncertain"])
        self.assertTrue(result["automatic"])
        self.assertTrue(result["nutrients_unknown"])
        self.assertNotIn("safe", result)

    def test_known_allergens_are_detected_from_ingredients(self):
        result = analyze_imported_recipe(recipe(["2 eggs", "1 cup milk", "100 g tofu", "1 cup wheat flour"]))
        self.assertEqual(result["allergens"], frozenset(("egg", "milk", "soy", "gluten")))

    def test_eggplant_and_plant_milk_do_not_become_animal_allergens(self):
        result = analyze_imported_recipe(recipe(["1 eggplant", "1 cup coconut milk", "200 ml soy milk"]))
        self.assertNotIn("egg", result["allergens"])
        self.assertNotIn("milk", result["allergens"])
        self.assertIn("soy", result["allergens"])

    def test_unknown_compound_and_flour_keep_uncertainty(self):
        for ingredient in ("vegetable stock", "2 tbsp mystery sauce", "1 cup flour", "1 cup zibblefruit"):
            with self.subTest(ingredient=ingredient):
                result = analyze_imported_recipe(recipe([ingredient]))
                self.assertTrue(result["allergen_uncertain"])

    def test_gluten_free_flour_not_labeled_gluten(self):
        result = analyze_imported_recipe(recipe(["1 cup rice flour", "1 cup almond flour"]))
        self.assertNotIn("gluten", result["allergens"])

    def test_oats_are_not_certified_gluten_free(self):
        self.assertTrue(analyze_imported_recipe(recipe(["1 cup oats"]))["gluten_uncertain"])

    def test_reflux_related_features_use_actual_ingredient_evidence(self):
        result = analyze_imported_recipe(recipe(["1 lemon", "1 hot pepper", "fresh mint", "1 tbsp butter"]))
        self.assertTrue(all(result[key] for key in ("acidic", "spicy", "mint", "fat_unknown")))

    def test_alcohol_caffeine_and_frying(self):
        result = analyze_imported_recipe(recipe(["1 cup coffee", "2 tbsp rum"], steps=["Fry ingredients in oil."]))
        self.assertTrue(result["alcohol"])
        self.assertTrue(result["caffeine"])
        self.assertTrue(result["fried"])
        self.assertFalse(result["soft"])

    def test_raw_egg_drinks_and_medicinal_titles_are_unsafe(self):
        for item in (recipe(["1 egg", "1 cup milk"], steps=["Mix and serve."], kind="drink"),
                     recipe(["1 cup water"], title="Oral rehydration solution"),
                     recipe(["100 g raw milk"], title="Yogurt")):
            self.assertTrue(analyze_imported_recipe(item)["unsafe_preparation"])

    def test_cooked_egg_and_meat_recipes_not_auto_rejected(self):
        self.assertFalse(analyze_imported_recipe(recipe(["1 egg"], title="Custard", steps=["Steam until fully cooked."]))["unsafe_preparation"])
        self.assertFalse(analyze_imported_recipe(recipe(["100 g chicken"], title="Chicken soup"))["unsafe_preparation"])

    def test_missing_recipe_parts_remain_unresolved(self):
        for item in ({"ingredients": [], "steps": []}, {"ingredients": [None], "steps": ["Boil."]}):
            self.assertTrue(analyze_imported_recipe(item)["unsafe_preparation"])
            self.assertTrue(analyze_imported_recipe(item)["allergen_uncertain"])

    def test_input_immutable_and_fingerprint_uses_full_normalized_text(self):
        item = recipe(["1 cup Milk", "2 Trứng gà"])
        before = deepcopy(item)
        result = analyze_imported_recipe(item)
        self.assertEqual(item, before)
        self.assertEqual(result["ingredients"], frozenset(("1 cup milk", "2 trung ga")))
        self.assertEqual(normalize_ingredient("  Yến  mạch "), "yen mach")


if __name__ == "__main__":
    unittest.main()
