import json
import hashlib
from pathlib import Path
import unittest

from scripts.import_vifoodrec_recipes import classify_title, ingredient_lines, normalize_recipe, procedure_lines


def row(**changes):
    data = {"food_id": "123", "dish_name": "Canh bầu nấu tôm", "ingredients": "Bầu: 300g, Tôm: 100g, Muối, Nước: 1 lít",
            "cooking_method": "Đun sôi 1 lít nước. Cho tôm vào nấu chín, thêm bầu và nấu mềm.",
            "dish_type": "Món mặn", "serving_size": "4 người", "cooking_time": "25", "dish_tags": "canh, bầu",
            "image_link": "https://monngonmoingay.com/example.jpg", "calories": "999"}
    data.update(changes)
    return data


class ViFoodRecImporterTests(unittest.TestCase):
    def test_vietnamese_language_alone_does_not_select_foreign_dishes(self):
        for title in ("Pizza hải sản", "Cơm trộn Hàn Quốc", "Canh kim chi", "Mì Ý sốt bò bằm", "Sữa Matcha", "Cà phê Dalgona", "Lẩu thái cua đồng"):
            with self.subTest(title=title):
                self.assertIsNone(classify_title(title)[0])
        self.assertEqual(classify_title("Canh bầu nấu tôm")[0], "food")
        self.assertEqual(classify_title("Cá kho tộ")[0], "food")
        self.assertEqual(classify_title("Bánh cuốn nóng")[0], "food")
        self.assertIsNone(classify_title("Bánh cuộn trà xanh")[0])

    def test_drink_title_overrides_unreliable_source_type_and_che_stays_food(self):
        for title in ("Nước rau má đậu xanh", "Sữa đậu nành", "Sinh tố bơ", "Trà tắc mật ong"):
            self.assertEqual(normalize_recipe(row(dish_name=title, dish_type="Món mặn"))[0]["recipe_type"], "drink")
        self.assertEqual(classify_title("Chè đậu xanh")[0], "food")

    def test_no_inferred_quantities_or_missing_source_recipe_urls(self):
        source = row()
        recipe, reason = normalize_recipe(source)
        self.assertIsNone(reason)
        self.assertEqual(recipe["original_ingredients"], source["ingredients"])
        self.assertEqual(recipe["original_cooking_method"], source["cooking_method"])
        self.assertTrue(all(i["amount"] == i["unit"] == "" for i in recipe["ingredients"]))
        self.assertEqual(recipe["source_row_id"], "123")
        self.assertEqual(recipe["servings"], "4 người")
        self.assertEqual(recipe["license"], "not_declared")
        self.assertNotIn("calories", recipe)
        self.assertIn("foods.csv", recipe["source_url"])
        self.assertNotIn("example.jpg", recipe["source_url"])

    def test_split_preserves_descriptors_and_decimal_numbers(self):
        self.assertEqual(ingredient_lines("Gừng: 10g, đập dập, Muối"), ["Gừng: 10g, đập dập", "Muối"])
        steps = procedure_lines("Cho 1.5 lít nước và 1/2 muỗng muối. Đun sôi rồi thêm rau.")
        self.assertEqual(len(steps), 2)
        self.assertIn("1.5", steps[0])
        self.assertIn("1/2", steps[0])

    def test_display_repairs_duplicate_unit_and_omits_nonprocedural_health_claim(self):
        source = row(ingredients="Gạo: 50 g, Muối: 1 muỗnguỗng cà phê",
                     cooking_method="Nấu gạo với nước 20 phút., Thêm 1 muỗnguỗng cà phê muối. Bên cạnh đó, món này giúp giải cảm và rất tốt cho sức khỏe.")
        recipe, reason = normalize_recipe(source)
        self.assertIsNone(reason)
        self.assertEqual(recipe["original_ingredients"], source["ingredients"])
        self.assertEqual(recipe["original_cooking_method"], source["cooking_method"])
        self.assertIn("1 muỗng cà phê", recipe["ingredients"][1]["name"])
        self.assertEqual(recipe["steps"], ["Nấu gạo với nước 20 phút.", "Thêm 1 muỗng cà phê muối."])

    def test_hazardous_or_incomplete_rows_are_not_selected(self):
        for changes in ({"dish_name": "Tiết canh vịt"}, {"dish_name": "Gỏi cá sống"}, {"ingredients": "Thịt 100g, Rượu trắng 1 muỗng"},
                        {"dish_name": "Sữa bắp cho bé"}, {"ingredients": "nan"}, {"cooking_method": ""}, {"food_id": "../1"}):
            with self.subTest(changes=changes):
                self.assertIsNone(normalize_recipe(row(**changes))[0])

    def test_bundled_manifest_matches_actual_clean_source_and_retains_provenance(self):
        directory = Path(__file__).resolve().parents[1] / "data/recipes/vifoodrec"
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        recipes = json.loads((directory / "recipes.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["input_count"], 4000)
        self.assertEqual(manifest["total"], len(recipes))
        self.assertGreater(len(recipes), 500)
        self.assertGreater(sum(r["recipe_type"] == "drink" for r in recipes), 25)
        self.assertTrue(all(r["source_row_id"] and r["original_ingredients"] and r["paper_url"] and r["cuisine_basis"] for r in recipes))
        self.assertEqual(len({r["id"] for r in recipes}), len(recipes))
        for filename, digest in manifest["sha256"].items():
            self.assertEqual(digest, hashlib.sha256((directory / filename).read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
