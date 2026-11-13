# ViFoodRec: local research import

Source: [author repository](https://github.com/QuocAn55/A-New-Dataset-and-Empirical-Evaluation-for-Vietnamese-Food-Recommendation-System), `Data/Clean Dataset/foods.csv`.

Reference: [A New Dataset and Empirical Evaluation for Vietnamese Food Recommendation System, PACLIC 2024](https://aclanthology.org/2024.paclic-1.4/).

The paper describes a 5,509-dish collection. The author's currently published **clean table contains 4,000 rows**. Only the foods table is downloaded; ratings, user information and images are not downloaded.

## Provenance and permissions

ViFoodRec's authors collected the underlying recipes from **Cooky** and **Món Ngon Mỗi Ngày**. Each extracted record retains the author repository/table link, food ID, paper, attribution and a description of the extraction changes. The table has no per-recipe page URL; the importer does not invent one from an image filename.

**No explicit reuse license was found in the repository.** The paper describes free access for the research community. The local integration is a research prototype; this is not a claim of permission for production redistribution or commercial use. `license` remains `not_declared`. Underlying publishers' image licenses have not been verified, so image URLs are metadata only.

## Selection and transformations

`scripts/import_vifoodrec_recipes.py` deterministically selects familiar Vietnamese home-cooking families (e.g. cháo, canh, cơm, bún, phở, nem, chả) or combinations of common local ingredients and preparations, plus explicitly named beverages. It rejects explicit international dishes, alcohol, certain raw/fermented recipes, recipes making medical/infant-feeding claims, missing parts and exact duplicates. **This title heuristic is not an independent certification of a dish's geographic origin.** Vietnamese-language text alone is not sufficient to select a recipe.

The `dish_type` column only distinguishes `Món mặn`/`Món chay`; it even labels some beverages as `Món mặn`, so it is not trusted for food/drink classification. Drink titles are classified separately. Chè and other spoon-eaten desserts remain food.

Ingredient comma/semicolon separators and procedure sentence boundaries are split for presentation, with descriptor-only ingredient fragments joined to their predecessor. Original complete ingredient and procedure text is retained for comparison. Amounts remain within the original ingredient text; they are not converted to grams, standardized or assumed to be one serving. Serving size is the original table value. Numeric cooking times are displayed in minutes, following the source field definition.

The table's nutrient values and promotional health descriptions are **not used** as verified clinical facts. The import has no disease-suitability labels and must pass the separate ingredient/context filters before any recommendation. The app's deterministic scans and Gemini ranking do not certify safety.

Rebuild from the already downloaded source:

```console
python scripts/import_vifoodrec_recipes.py --offline
```

Refresh from the author's foods table:

```console
python scripts/import_vifoodrec_recipes.py
```
