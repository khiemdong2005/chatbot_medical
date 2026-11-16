# Nutrition recommendations

`POST /api/nutrition/options` accepts `condition` (up to 500 characters) and
`recipe_type` (`food` or `drink`), and optionally `exclude_recipe_ids` (up to
5000 IDs already displayed) for more suggestions. The condition is sent to Google Gemini.
There is no patient profile, chat history or credential in the prompt.

## Configuration

Keep credentials only in the ignored `.env` file:

```dotenv
GEMINI_NUTRITION_API_KEY=your_key_here
GEMINI_NUTRITION_MODEL=gemini-flash-lite-latest
```

If the nutrition key is absent, the service can use `GEMINI_API_KEY`.
The separate nutrition key does not replace existing chatbot configuration.

## Pipeline

1. Load the Vietnamese home-cooking selection under
   `data/recipes/vifoodrec/recipes.json`. The author's clean `foods.csv` has
   4000 rows; the 5509 figure in the paper refers to the earlier collection.
   The current deterministic import retains 2462 recipes (2367 food,95 drink).
   International recipe names, unresolved cuisine, alcohol, fermented recipes,
   risky raw dishes and medical/infant recipe titles are excluded. Cuisine is
   a documented familiar-home-cooking heuristic, not certified geographic origin.
   Wikibooks remains an archive and is not mixed into active suggestions.
   If the active dataset is missing, only the original 14 clearly counted sample
   recipes are available; an empty food/drink filter never adds foreign recipes.
2. Apply explicit ingredient/allergen metadata and a small set of source-linked
   general guidelines. Unknown constraints are not silently treated as safe.
3. Retrieve at most 32 related candidates using ingredient/category text and
   Vietnamese and English search expansions, after filtering. Repeated titles
   are collapsed for variety; already displayed IDs and their titles are excluded
   from further batches. Gemini selects up to 5 existing IDs with short reasons,
   caveats and source IDs. Vietnamese titles cannot be rewritten by the model.
4. Validate the JSON, IDs, duplicates, source IDs and required fields. Recipe
   ingredients, amounts and instructions always come from the local catalog.
5. Show a clarification question when needed. For an explicitly recognized
   context (including fever) with remaining candidates, show up to five general
   filtered options alongside the optional question, labeled as not AI-ranked.
   Unknown/ambiguous contexts and unresolved ingredient constraints are not
   overridden by this preview. On provider failure, expose
   `gemini_used=false` and a `fallback_*` status with a clearly labeled filtered
   catalog. Never claim fallback items were ranked by AI.

The response always includes `avoidance` and `avoidance_note`. These come from
source-linked rules or the user's explicit ingredient restrictions, not Gemini.
They remain available on provider failure or clarification, and are displayed
both below the results and in recipe details. Omitted recipes are not implicitly
classified as prohibited foods. Unknown contexts do not get invented restrictions.

The provider request has a 25-second timeout and one attempt. Raw provider
exceptions are not logged or returned because they can include private details.

## Limits

Rules cover a small collection of explicit contexts and declared allergens.
They do not establish a diagnosis or clinical suitability, calculate a personal
meal plan, check medications, or certify cross-contamination safety. Retrieval
from the project's ChromaDB is not part of this pipeline yet. Guidance URLs
are supplied by the server, not invented by the model. Model explanations
still need human review; a structured JSON response does not certify medical
accuracy.

Imported ingredient features are deterministic bilingual text scans, not
expert-reviewed medical labels. Vietnamese texture terms preserve accents:
canh/cánh and cháo/chảo are different. Unknown compound ingredients and ambiguous
butter/avocado wording block explicit allergy requests. Exact source features
are cached; user health queries are not cached. Original ingredient quantities
and preparation stay unaltered; they are not converted to grams, per-serving
amounts or inferred nutrient values. Source nutrient/promotional descriptions
are not used as verified benefits. Imported recipes use a clearly labeled generic
illustration; dataset photo URLs are not fetched or shown.
The raw recipe prose remains stored for audit. Displayed text repairs the known
duplicated `muỗnguỗng` unit typo and omits standalone health advertising that
contains no preparation instruction; ingredient amounts are not changed.

The ViFoodRec paper describes free research access. The author repository has no
explicit data reuse license, so the manifest and UI use `not_declared`, not an
invented open license. This integration is a local research prototype; production
redistribution rights are not verified. Each record retains the author dataset
reference and row ID. The source CSV does not have original recipe URLs, so the
UI labels its link as a research dataset, not an original cooking article.
Raw `foods.csv` is ignored by Git and retained locally for reproducibility.

Sources:
- https://aclanthology.org/2024.paclic-1.4/
- https://github.com/QuocAn55/A-New-Dataset-and-Empirical-Evaluation-for-Vietnamese-Food-Recommendation-System

To rebuild from the downloaded source or refresh it:

```console
python scripts/import_vifoodrec_recipes.py
python scripts/import_vifoodrec_recipes.py --offline
```

## Checks

```console
python -m unittest discover -s tests -p "test_nutrition_ai.py" -v
python -m unittest discover -s tests -p "test_nutrition_rules.py" -v
python -m unittest discover -s tests -p "test_recipe_catalog.py" -v
python -m unittest discover -s tests -p "test_recipe_features*.py" -v
python -m unittest discover -s tests -p "test_vifoodrec_importer.py" -v
node --check static/js/nutrition-flow.js
```
