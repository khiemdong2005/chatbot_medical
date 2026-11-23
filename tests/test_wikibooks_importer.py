import unittest

from scripts.import_wikibooks_recipes import clean, extract_sections, normalize_recipe


def page(text):
    return {"pageid": 123, "ns": 102, "title": "Cookbook:Source Test",
            "revisions": [{"revid": 456, "slots": {"main": {"content": text}}}]}


class WikibooksImporterTests(unittest.TestCase):
    def test_zero_argument_units_are_not_deleted(self):
        for unit, expected in (("l", "L"), ("kg", "kg"), ("g", "g"), ("ml", "ml")):
            with self.subTest(unit=unit):
                warnings = []
                self.assertEqual(clean("1.5 {{" + unit + "}} cold water", warnings), "1.5 " + expected + " cold water")
                self.assertEqual(warnings, [])

    def test_unknown_template_keeps_name_and_arguments_and_warns(self):
        warnings = []
        self.assertEqual(clean("Add {{special-measure|2|water}}.", warnings), "Add [Template: special-measure | 2 | water].")
        self.assertEqual(warnings, ["Unresolved wiki template: special-measure"])
        self.assertEqual(clean("Add {{unknown-unit}} water", warnings), "Add [Template: unknown-unit] water")

    def test_preserves_fraction_link_and_unit_inside_recipe_sections(self):
        sections = extract_sections("== Ingredients ==\n* {{frac|1|2}} {{l}} [[Cookbook:Milk|milk]]\n== Procedure ==\n# Add 2 {{g}} salt and warm the milk.")
        self.assertEqual(sections["ingredients"], ["1/2 L milk"])
        self.assertEqual(sections["steps"], ["Add 2 g salt and warm the milk."])
        self.assertEqual(sections["warnings"], [])

    def test_source_missing_water_unit_is_flagged_without_guess(self):
        source = "== Ingredients ==\n* 1 chicken\n== Procedure ==\n# Quarter the chicken and place in a pot with ~1.5 cold water."
        record, error = normalize_recipe(page(source), set())
        self.assertIsNone(error)
        self.assertIn("~1.5 cold water", record["steps"][0])
        self.assertNotIn("litre", record["steps"][0])
        self.assertTrue(any("without a stated unit" in warning for warning in record["extraction_warnings"]))

    def test_valid_water_units_do_not_get_missing_unit_warning(self):
        source = "== Ingredients ==\n* 1 onion\n== Procedure ==\n# Add 1.5 {{l}} cold water and simmer."
        record, error = normalize_recipe(page(source), set())
        self.assertIsNone(error)
        self.assertEqual(record["extraction_warnings"], [])
        self.assertIn("1.5 L cold water", record["steps"][0])

    def test_standalone_unexpanded_template_is_flagged(self):
        sections = extract_sections("== Ingredients ==\n* 1 onion\n{{special ingredient}}\n== Procedure ==\n# Cook the onion.")
        self.assertTrue(any("Standalone wiki template" in warning for warning in sections["warnings"]))


if __name__ == "__main__":
    unittest.main()
