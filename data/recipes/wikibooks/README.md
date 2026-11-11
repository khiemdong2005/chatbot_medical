# Wikibooks Cookbook import

Text by Wikibooks contributors, **CC BY-SA 4.0**.

License: https://creativecommons.org/licenses/by-sa/4.0/

Source policy: https://en.wikibooks.org/wiki/Wikibooks:Copyrights

Each recipe retains its source page, revision link, author attribution and extraction changes. Adapted recipe text must retain attribution and the same license. Images are not included. `raw_pages.jsonl` preserves fetched wikitext; `recipes.json` contains extracted ingredients and directions. This is community cooking data, not evidence of medical suitability. Quantities stay as original English text; nutrition is not inferred.

## Extraction quality

`extraction_warnings` records unresolved template text or detected missing source units. Known unit templates such as `{{kg}}`, `{{g}}` and `{{l}}` are preserved as units. Unknown templates retain their name/arguments in readable form and are flagged instead of being silently deleted. Original source gaps are not repaired with guessed quantities. For example, the archived Rosół revision itself says “~1.5 cold water” without a unit; this remains visibly flagged.

The offline re-extraction retained the same 900 recipe IDs and found 9 records with warnings. The application's recommendation filter excludes these flagged records until they are reviewed. Rebuild from the unchanged archived revisions without network access using:

```console
python scripts/import_wikibooks_recipes.py --rebuild-existing
```
