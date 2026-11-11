from copy import deepcopy
import json
from pathlib import Path
import unittest

from core.recipe_features import analyze_imported_recipe, normalize_ingredient


def recipe(ingredients, title="Cháo rau củ", steps=None, kind="food"):
    return {"id": "vifoodrec_test", "language": "vi", "title": title,
            "recipe_type": kind, "categories": [],
            "ingredients": [{"name": name, "amount": "", "unit": ""} for name in ingredients],
            "steps": steps or ["Nấu các nguyên liệu với nước đến khi chín mềm."]}


class VietnameseRecipeFeaturesTests(unittest.TestCase):
    def test_known_vietnamese_allergens_detected_from_actual_ingredient_names(self):
        item = recipe(["Sữa đặc: 2 muỗng canh", "Trứng vịt: 2 quả",
                       "Đậu hũ non: 100 g", "Bột mì: 40 g"])
        self.assertEqual(analyze_imported_recipe(item)["allergens"], {"milk", "egg", "soy", "gluten"})

    def test_yogurt_cheese_and_unqualified_accented_milk(self):
        for ingredient in ("Sữa chua: 1 hũ", "Phô mai: 30 g", "Sữa: 200 ml", "Bơ lạt: 5 g"):
            with self.subTest(ingredient=ingredient):
                self.assertIn("milk", analyze_imported_recipe(recipe([ingredient]))["allergens"])

    def test_plant_milks_coconut_and_jellyfish_are_not_dairy(self):
        for ingredient in ("Sữa dừa: 200 ml", "Sữa hạnh nhân: 200 ml",
                           "Sữa đậu nành: 200 ml", "Nước cốt dừa: 20 ml", "Sứa tươi: 100 g"):
            with self.subTest(ingredient=ingredient):
                self.assertNotIn("milk", analyze_imported_recipe(recipe([ingredient]))["allergens"])
        self.assertIn("soy", analyze_imported_recipe(recipe(["Sữa đậu nành: 200 ml"]))["allergens"])

    def test_mung_beans_and_rice_flour_are_not_soy_or_wheat(self):
        result = analyze_imported_recipe(recipe(["Đậu xanh: 30 g", "Bột gạo: 50 g", "Bột năng: 10 g"]))
        self.assertFalse(result["allergens"])
        self.assertFalse(result["allergen_uncertain"])

    def test_soy_sauce_retains_compound_product_and_gluten_uncertainty(self):
        result = analyze_imported_recipe(recipe(["Nước tương: 1 muỗng canh"]))
        self.assertIn("soy", result["allergens"])
        self.assertTrue(result["allergen_uncertain"])
        self.assertTrue(result["gluten_uncertain"])

    def test_plain_vietnamese_ingredients_are_recognized_but_unknown_products_are_not(self):
        good = analyze_imported_recipe(recipe(["Gạo tẻ: 50 g", "Cà rốt: 30 g", "Nước lọc: 500 ml", "Muối: 1 nhúm"]))
        self.assertFalse(good["allergen_uncertain"])
        for ingredient in ("Hạt nêm Aji-ngon: 1 muỗng", "Nước sốt đặc biệt: 30 ml",
                           "Bột chưa rõ loại: 50 g", "Cây zibblefruit: 20 g"):
            with self.subTest(ingredient=ingredient):
                self.assertTrue(analyze_imported_recipe(recipe([ingredient]))["allergen_uncertain"])

    def test_vietnamese_soup_and_porridge_have_texture_evidence(self):
        soup = analyze_imported_recipe(recipe(["Rau ngót: 100 g", "Nước lọc: 500 ml"], title="Canh rau ngót"))
        self.assertTrue(soup["liquid"])
        self.assertTrue(soup["soft"])
        self.assertTrue(analyze_imported_recipe(recipe(["Gạo tẻ: 50 g"], title="Cháo trắng"))["soft"])

    def test_vietnamese_diacritics_distinguish_wings_and_pans_from_soup_and_porridge(self):
        for title in ("Cánh gà nướng", "Cánh gà chiên nước mắm", "Trứng trên chảo nóng", "Bánh mì chảo", "Súp lơ xanh xào thịt bò"):
            with self.subTest(title=title):
                result = analyze_imported_recipe(recipe(["Thịt gà: 100 g"], title=title))
                self.assertFalse(result["liquid"])
                self.assertFalse(result["soft"])
        for title in ("Canh gà", "Cháo gà", "Súp gà"):
            result = analyze_imported_recipe(recipe(["Thịt gà: 100 g"], title=title))
            self.assertTrue(result["soft"])

    def test_ambiguous_butter_is_not_treated_as_milk_free(self):
        for ingredient in ("Bơ 10 g", "Bơ 10 Gr", "Thịt bò và bơ 20 g"):
            with self.subTest(ingredient=ingredient):
                self.assertTrue(analyze_imported_recipe(recipe([ingredient]))["allergen_uncertain"])
        self.assertIn("milk", analyze_imported_recipe(recipe(["Bơ lạt 10 g"]))["allergens"])

    def test_actual_vifoodrec_butter_and_broccoli_regressions(self):
        path = Path(__file__).resolve().parent.parent / "data/recipes/vifoodrec/recipes.json"
        if not path.exists():
            self.skipTest("ViFoodRec import is not installed")
        rows = {r["id"]: r for r in json.loads(path.read_text(encoding="utf-8-sig"))}
        butter = analyze_imported_recipe(rows["vifoodrec_2667"])
        self.assertTrue(butter["allergen_uncertain"] or "milk" in butter["allergens"])
        broccoli = analyze_imported_recipe(rows["vifoodrec_2169"])
        self.assertFalse(broccoli["liquid"])
        self.assertFalse(broccoli["soft"])

    def test_frying_is_detected_and_does_not_become_soft_food(self):
        for method in ("Chiên cá đến khi chín vàng.", "Xào rau trên lửa lớn.", "Rán trứng đến chín."):
            with self.subTest(method=method):
                result = analyze_imported_recipe(recipe(["Trứng gà: 1 quả"], title="Trứng mềm", steps=[method]))
                self.assertTrue(result["fried"])
                self.assertFalse(result["soft"])
                self.assertFalse(result["unsafe_preparation"])

    def test_vietnamese_animal_ingredients_require_a_cooking_step(self):
        raw = recipe(["Trứng gà: 1 quả", "Sữa tươi: 200 ml"], title="Sữa trứng", kind="drink", steps=["Đánh tan và rót ra ly."])
        self.assertTrue(analyze_imported_recipe(raw)["unsafe_preparation"])
        for method in ("Hấp trứng đến chín hoàn toàn.", "Luộc gà đến chín.", "Hầm thịt đến mềm.", "Kho cá trên lửa nhỏ."):
            self.assertFalse(analyze_imported_recipe(recipe(["Thịt gà: 100 g"], steps=[method]))["unsafe_preparation"])

    def test_raw_vegetable_drinks_do_not_mistake_ca_rot_for_fish(self):
        item = recipe(["Cà rốt: 100 g", "Cà chua: 100 g", "Nước lọc: 100 ml"],
                      title="Nước ép rau củ", kind="drink", steps=["Rửa sạch, cho vào máy ép và dùng ngay."])
        result = analyze_imported_recipe(item)
        self.assertFalse(result["unsafe_preparation"])
        self.assertTrue(result["acidic"])

    def test_caffeine_uses_tea_or_coffee_not_every_ingredient_with_ca(self):
        for ingredient in ("Cà phê: 10 g", "Trà xanh: 5 g", "Trà đen: 5 g", "Bột ca cao: 5 g"):
            with self.subTest(ingredient=ingredient):
                self.assertTrue(analyze_imported_recipe(recipe([ingredient], kind="drink"))["caffeine"])
        for ingredient in ("Cà rốt: 100 g", "Trà hoa cúc: 5 g", "Trà gừng: 5 g", "Trà atiso: 5 g"):
            with self.subTest(ingredient=ingredient):
                self.assertFalse(analyze_imported_recipe(recipe([ingredient], kind="drink"))["caffeine"])
        self.assertTrue(analyze_imported_recipe(recipe(["Trà hoa cúc và trà xanh: 5 g"], kind="drink"))["caffeine"])

    def test_spicy_acidic_mint_and_alcohol_are_detected_without_generic_fish_sauce_false_positive(self):
        result = analyze_imported_recipe(recipe(["Ớt xiêm: 2 trái", "Chanh: 1 quả", "Bạc hà: 3 lá", "Rượu trắng: 5 ml"]))
        self.assertTrue(all(result[key] for key in ("spicy", "acidic", "mint", "alcohol")))
        plain = analyze_imported_recipe(recipe(["Nước mắm: 1 muỗng", "Ớt chuông: 1 quả", "Mè trắng: 5 g"]))
        self.assertFalse(plain["acidic"])
        self.assertFalse(plain["spicy"])
        self.assertTrue(analyze_imported_recipe(recipe(["Me: 20 g"]))["acidic"])

    def test_vietnamese_raw_dishes_and_medicinal_labels_are_not_automatic_options(self):
        for title in ("Tiết canh", "Gỏi cá", "Nước chữa bệnh", "Nước hạ sốt"):
            with self.subTest(title=title):
                self.assertTrue(analyze_imported_recipe(recipe(["Nước lọc: 200 ml"], title=title))["unsafe_preparation"])

    def test_shelf_stable_processed_ingredients_remain_unresolved_and_no_nutrients_inferred(self):
        result = analyze_imported_recipe(recipe(["Xúc xích: 2 cây", "Nước dùng: 300 ml"]))
        self.assertTrue(result["allergen_uncertain"])
        self.assertTrue(result["nutrients_unknown"])
        self.assertNotIn("safe", result)

    def test_fingerprint_and_original_vietnamese_quantities_are_preserved(self):
        item = recipe(["Gạo tẻ: 50 g", "Cà rốt: 1/2 củ"])
        before = deepcopy(item)
        result = analyze_imported_recipe(item)
        self.assertEqual(item, before)
        self.assertEqual(result["ingredients"], frozenset(normalize_ingredient(i["name"]) for i in item["ingredients"]))


if __name__ == "__main__":
    unittest.main()
