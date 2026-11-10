# Nutrition recommendations

`POST /api/nutrition/options` accepts `condition` (up to 500 characters) and
`recipe_type` (`food` or `drink`). The condition is sent to Google Gemini.
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

1. Load the local catalog: 7 food recipes and 7 drinks. RecipeNLG is not imported.
2. Apply explicit ingredient/allergen metadata and a small set of source-linked
   general guidelines. Unknown constraints are not silently treated as safe.
3. Send only remaining recipes and relevant guidelines to Gemini. Gemini can
   select up to 5 existing IDs and provide short reasons, caveats and source IDs.
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

## Checks

```console
python -m unittest discover -s tests -p "test_nutrition_ai.py" -v
python -m unittest discover -s tests -p "test_nutrition_rules.py" -v
node --check static/js/nutrition-flow.js
```
