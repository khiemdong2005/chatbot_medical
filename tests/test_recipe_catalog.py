import json
from pathlib import Path
import tempfile
import hashlib
import unittest
from unittest.mock import patch

from core import recipe_catalog as catalog
from core.nutrition_rules import prepare_nutrition_candidates
from core.nutrition_options import get_nutrition_options


def imported(index=1, title="Carrot soup"):
    return {"id": f"wikibooks_{index}", "title": title, "recipe_type": "food",
            "ingredients": [{"name": "2 carrots", "amount": "", "unit": ""}, {"name": "1 cup water", "amount": "", "unit": ""}],
            "steps": ["Boil the carrots in water until soft, then blend."],
            "categories": ["Soup recipes"], "source_url": "https://en.wikibooks.org/wiki/Cookbook:Carrot_Soup",
            "revision_url": "https://en.wikibooks.org/w/index.php?oldid=123", "revision_id": 123,
            "license": "CC-BY-SA-4.0"}


class RecipeCatalogTests(unittest.TestCase):
    def test_load_preserves_source_and_textual_quantities_and_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recipes.json"
            bad = imported(2)
            bad["source_url"] = "https://untrusted.example/recipe"
            path.write_text(json.dumps([imported(), imported(), bad]), encoding="utf-8")
            with patch.object(catalog, "DATA_PATH", path):
                catalog._read_catalog.cache_clear()
                rows = catalog.imported_recipes("food")
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["ingredients"][0]["name"], "2 carrots")
                self.assertEqual(rows[0]["ingredients"][0]["amount"], "")
                rows[0]["steps"].append("mutated")
                self.assertEqual(len(catalog.imported_recipes()[0]["steps"]), 1)
                self.assertEqual(catalog.catalog_stats()["total"], 1)
        catalog._read_catalog.cache_clear()

    def test_shortlist_is_bounded_and_uses_new_recipes(self):
        records = [{**imported(i, f"Soup {i}"), "imported": True} for i in range(50)]
        old = [{**imported(i+100, f"Original soup {i}"), "imported": False} for i in range(7)]
        selected = catalog.retrieve_candidates("sốt", old + records)
        self.assertEqual(len(selected), 32)
        self.assertLessEqual(sum(not r["imported"] for r in selected), 2)
        self.assertGreaterEqual(sum(r["imported"] for r in selected), 30)

    def test_shortlist_variety_keeps_accents_but_omits_repeated_titles(self):
        rows = [imported(1, "Canh gà"), imported(2, "Cánh gà"), imported(3, "canh gà")]
        selected = catalog.retrieve_candidates("bữa tối", rows)
        self.assertEqual(len(selected), 2)
        self.assertEqual({r["title"] for r in selected}, {"Canh gà", "Cánh gà"})

    def test_imported_soup_can_reach_known_context_without_human_review_claim(self):
        recipe = {**imported(), "imported": True}
        prepared = prepare_nutrition_candidates("sốt", [recipe])
        self.assertEqual(len(prepared["recipes"]), 1)
        self.assertEqual(prepared["recipes"][0]["metadata_review"], "automated_text_scan")
        self.assertEqual(prepared["recipes"][0]["ingredients"], recipe["ingredients"])

    def test_unknown_ingredient_still_blocks_declared_allergy(self):
        recipe = {**imported(), "imported": True}
        recipe["ingredients"].append({"name": "1 packet mystery sauce"})
        prepared = prepare_nutrition_candidates("sốt; dị ứng sữa", [recipe])
        self.assertEqual(prepared["recipes"], [])

    def test_incomplete_source_is_not_recommended_even_without_health_context(self):
        recipe = {**imported(), "imported": True,
                  "extraction_warnings": ["Source omits the water quantity unit."]}
        for query in ("sốt", "bữa tối"):
            with self.subTest(query=query):
                prepared = prepare_nutrition_candidates(query, [recipe])
                self.assertEqual(prepared["recipes"], [])
                self.assertEqual(prepared["excluded"][0]["id"], recipe["id"])

    def test_imported_ingredient_edit_cannot_reuse_old_allergy_scan(self):
        recipe = {**imported(), "imported": True}
        self.assertTrue(prepare_nutrition_candidates("sốt; dị ứng sữa", [recipe])["recipes"])
        recipe["ingredients"].append({"name": "1 cup milk", "amount": "", "unit": ""})
        self.assertEqual(prepare_nutrition_candidates("sốt; dị ứng sữa", [recipe])["recipes"], [])

    def test_bundled_dataset_is_large_attributed_and_matches_manifest(self):
        rows = catalog.imported_recipes()
        self.assertGreaterEqual(len(rows), 100)
        self.assertGreaterEqual(len(catalog.imported_recipes("drink")), 20)
        self.assertTrue(all(r["id"].startswith("vifoodrec_") and r.get("cuisine") == "VN"
                            and r.get("language") == "vi" and r.get("source_url")
                            and (r.get("source_attribution") or r.get("attribution")) for r in rows))
        self.assertEqual(catalog.catalog_stats()["total"], len(rows))
        self.assertEqual(catalog.catalog_stats()["cuisine"], "VN")
        manifest = json.loads(catalog.DATA_PATH.with_name("manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["total"], len(rows))
        self.assertEqual(manifest["sha256"]["recipes.json"], hashlib.sha256(catalog.DATA_PATH.read_bytes()).hexdigest())

    def test_vietnamese_catalog_checks_cuisine_and_exact_source_repository(self):
        row = {**imported(), "id": "vifoodrec_1", "title": "Cháo gà", "language": "vi", "cuisine": "VN",
               "license": "not_declared", "source_url": "https://github.com/" + catalog.VIFOODREC_REPOSITORY}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recipes.json"
            bad_source = {**row, "id": "vifoodrec_2", "source_url": row["source_url"] + "-impostor"}
            foreign = {**row, "id": "vifoodrec_3", "cuisine": "other"}
            path.write_text(json.dumps([row, bad_source, foreign]), encoding="utf-8")
            with patch.object(catalog, "DATA_PATH", path):
                rows = catalog.imported_recipes()
                self.assertEqual([r["id"] for r in rows], [row["id"]])
                self.assertEqual(rows[0]["source_provider"], "ViFoodRec")
                self.assertEqual(rows[0]["license"], "not_declared")
        catalog._read_catalog.cache_clear()

    def test_active_vietnamese_catalog_never_mixes_old_international_recipes(self):
        from core.nutrition_options import _get_general_options
        for kind in ("food", "drink"):
            with self.subTest(kind=kind):
                recipes = _get_general_options("sốt", kind)["recipes"]
                self.assertTrue(recipes)
                self.assertTrue(all(r["id"].startswith("vifoodrec_") and r["cuisine"] == "VN" for r in recipes))

    def test_retrieval_does_not_treat_fever_as_a_sauce_name(self):
        recipes = [{**imported(1), "title": "Đậu hũ sốt", "ingredients": [{"name": "Đậu hũ"}], "categories": []},
                   {**imported(2), "title": "Cháo gà", "ingredients": [{"name": "Gạo, thịt gà"}], "categories": []}]
        self.assertEqual(catalog.retrieve_candidates("sốt", recipes, limit=1)[0]["title"], "Cháo gà")

    @patch("core.nutrition_ai.select_recipes")
    def test_more_suggestions_excludes_previous_recipe_ids(self, provider):
        def choose(condition, kind, recipes, guidance):
            return {"needs_clarification": False, "clarification_question": "", "model": "mock",
                    "recipes": [{**r, "recommendation_reason": "Lựa chọn thử nghiệm từ nhóm ứng viên."} for r in recipes[:3]]}
        provider.side_effect = choose
        first = get_nutrition_options("sốt", "food")
        seen = [r["id"] for r in first["recipes"]]
        second = get_nutrition_options("sốt", "food", seen)
        self.assertFalse(set(seen) & {r["id"] for r in second["recipes"]})
        self.assertFalse({catalog.title_key(r) for r in first["recipes"]}
                         & {catalog.title_key(r) for r in second["recipes"]})
        self.assertTrue(first["has_more"])
        self.assertGreater(first["catalog_type_count"], 7)


if __name__ == "__main__":
    unittest.main()
