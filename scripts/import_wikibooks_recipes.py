"""Download openly licensed Cookbook recipe text, retaining revision provenance.

Only text is imported. Images have separate licenses and are not downloaded.
The extracted data remains CC BY-SA 4.0; no medical suitability is inferred.
"""
import argparse
from collections import Counter, deque
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import random
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "recipes" / "wikibooks"
API = "https://en.wikibooks.org/w/api.php"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
UA = "MediMindRecipeImporter/1.0 (local educational prototype; source attribution retained)"


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def request(session, **params):
    params.update(action="query", format="json", formatversion=2, maxlag=5)
    cache_dir = OUTPUT / "api_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / (hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest() + ".json")
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    for attempt in range(3):
        try:
            time.sleep(5)
            response = session.get(API, params=params, timeout=25)
            if response.status_code == 429:
                wait = min(50, max(15, int(response.headers.get("Retry-After", "20"))))
                print(f"API rate limit; pausing {wait} seconds before retry", flush=True)
                time.sleep(wait)
            response.raise_for_status()
            body = response.json()
            if "error" in body:
                raise RuntimeError(body["error"].get("code", "api_error"))
            cache_path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
            return body
        except (requests.RequestException, ValueError, RuntimeError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def category_members(session, category, member_type="page", limit=10000):
    continuation = {}
    rows = []
    while len(rows) < limit:
        data = request(session, list="categorymembers", cmtitle=category,
                       cmtype=member_type, cmlimit=500, **continuation)
        rows.extend(data.get("query", {}).get("categorymembers", []))
        continuation = data.get("continue", {})
        if not continuation:
            break
    return rows[:limit]


def beverage_members(session):
    queue = deque([("Category:Recipes for beverages", 0)])
    seen, pages = set(), {}
    while queue:
        category, depth = queue.popleft()
        if category in seen:
            continue
        seen.add(category)
        print(f"Listing {category}", flush=True)
        for row in category_members(session, category):
            if row.get("ns") == 102:
                pages[row["pageid"]] = row
        if depth < 2:
            for row in category_members(session, category, "subcat", 80):
                queue.append((row["title"], depth + 1))
    return pages


UNIT_TEMPLATES = {
    "g": "g", "kg": "kg", "mg": "mg", "ml": "ml", "cl": "cl",
    "dl": "dl", "l": "L", "oz": "oz", "lb": "lb", "lbs": "lbs",
    "tsp": "tsp", "tbsp": "tbsp", "cup": "cup", "cups": "cups",
    "pint": "pint", "quart": "quart", "gal": "gal", "cm": "cm", "mm": "mm",
}


def clean_template(match, warnings=None):
    parts = [part.strip() for part in match.group(1).split("|")]
    name, args = parts[0].lower(), parts[1:]
    if not args and name in UNIT_TEMPLATES:
        return UNIT_TEMPLATES[name]
    if name == "!" and not args:
        return "|"
    if name in ("frac", "fraction"):
        return "/".join(args) if len(args) == 2 else " ".join(args)
    if name in ("c", "cookbook", "ingredient", "i"):
        return args[-1] if args else ""
    if name in ("unit", "convert"):
        return " ".join(a for a in args if "=" not in a)
    if name in ("nowrap", "small", "lang", "w"):
        return args[-1] if args else ""
    # Unknown names may encode an important unit/ingredient. Preserve readable
    # source markup rather than silently deleting it or just keeping its args.
    if warnings is not None:
        warnings.append("Unresolved wiki template: " + parts[0])
    return "[Template: " + " | ".join(parts) + "]"


def clean(text, warnings=None):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref\b[^>]*>.*?</ref\s*>|<ref\b[^>]*/>", "", text, flags=re.S | re.I)
    text = re.sub(r"\[\[(?:File|Image|Category):.*?\]\]", "", text, flags=re.I)
    for _ in range(8):
        replaced = re.sub(r"\{\{([^{}]*)\}\}", lambda match: clean_template(match, warnings), text)
        if replaced == text:
            break
        text = replaced
    text = re.sub(r"\[\[([^]|]+)\|([^]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[(?:Cookbook:)?([^]]+)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\s+([^]]+)\]", r"\1", text)
    text = re.sub(r"\[https?://[^]]+\]", "", text)
    text = text.replace("'''", "").replace("''", "")
    text = BeautifulSoup(text, "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def extract_sections(wikitext):
    groups = {"ingredients": [], "steps": [], "warnings": []}
    mode, base_level, subgroup = None, 0, ""
    for line in wikitext.splitlines():
        heading = re.match(r"^(={2,6})\s*(.*?)\s*\1\s*$", line.strip())
        if heading:
            level = len(heading.group(1))
            label = clean(heading.group(2))
            normal = label.lower()
            new_mode = ("ingredients" if re.match(r"^(ingredients?\b|you will need\b|what you need\b)", normal)
                        else "steps" if re.match(r"^(procedure\b|preparation\b|directions?\b|method\b|instructions?\b)", normal)
                        else None)
            if new_mode:
                mode, base_level, subgroup = new_mode, level, ""
            elif mode and level > base_level:
                subgroup = label
            else:
                mode, subgroup = None, ""
            continue
        if not mode:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith(("{|", "|", "!", "[[Category:")):
            continue
        if stripped.startswith("{{"):
            groups["warnings"].append("Standalone wiki template inside " + mode + " could not be expanded: " + stripped[:160])
            continue
        if mode == "ingredients" and not stripped.startswith(("*", ";", ":")):
            continue
        entry = clean(re.sub(r"^[*#;:]+\s*", "", stripped), groups["warnings"])
        if not entry or len(entry) < 2 or "{{" in entry or "}}" in entry:
            continue
        if subgroup:
            entry = subgroup + ": " + entry
        if mode == "steps" and not stripped.startswith(("#", "*", ":")):
            # Preserve prose directions, but drop navigation/template residue.
            if len(entry) < 15 or entry.startswith(("Category:", "Cookbook:")):
                continue
        groups[mode].append(entry)
    return groups


EXCLUDED_TITLE = re.compile(r"\b(?:oral rehydration|ors solution|cough syrup|medicine|medical|supplement|infant formula|baby formula|poison|cannabis|cocktail|liqueur|liquor|vodka|whisky|whiskey|rum punch|wine|beer|mead|raw milk)\b", re.I)
ALCOHOL = re.compile(r"\b(?:vodka|whisky|whiskey|brandy|liqueur|liquor|rum|gin|tequila|wine|beer|mead|schnapps|absinthe|sherry|vermouth|sake)\b", re.I)


def normalize_recipe(page, beverage_ids):
    title = page.get("title", "")
    if page.get("ns") != 102 or title.count("/") > 2:
        return None, "not_recipe_namespace"
    revisions = page.get("revisions", [])
    if not revisions:
        return None, "no_revision"
    revision = revisions[0]
    wikitext = revision.get("slots", {}).get("main", {}).get("content", "")
    if wikitext.lstrip().lower().startswith("#redirect"):
        return None, "redirect"
    plain_title = title.removeprefix("Cookbook:")
    if EXCLUDED_TITLE.search(plain_title):
        return None, "excluded_title"
    sections = extract_sections(wikitext)
    ingredients, steps = sections["ingredients"], sections["steps"]
    warnings = list(dict.fromkeys(sections["warnings"]))
    for step in steps:
        if re.search(r"\b\d+(?:[.,]\d+)?\s+(?:(?:cold|hot|warm|boiling)\s+)?water\b", step, re.I):
            warnings.append("Source instruction has a water quantity without a stated unit; verify the source before preparing: " + step[:180])
    warnings = list(dict.fromkeys(warnings))
    if not 1 <= len(ingredients) <= 50 or not 1 <= len(steps) <= 60:
        return None, "missing_or_oversized_sections"
    if any(len(item) > 1200 for item in ingredients + steps):
        return None, "oversized_entry"
    if any(ALCOHOL.search(item) for item in ingredients):
        return None, "alcohol_ingredient"
    categories = sorted({c["title"].removeprefix("Category:") for c in page.get("categories", [])})
    category_text = " ".join(categories) + " " + wikitext[:1000]
    drink = page["pageid"] in beverage_ids or bool(re.search(r"Recipes for (?:beverages|drinks|plant milk)|category\s*=\s*(?:Beverage|Drink) recipes", category_text, re.I))
    if drink and re.search(r"(?:alcoholic beverages|cocktails|recipes for (?:beer|wine|mead|liqueurs?))", " ".join(categories), re.I):
        return None, "alcohol_category"
    if drink and any(re.search(r"\b(?:egg|eggs|yolk|yolks|eggwhite|egg white)\b", item, re.I) for item in ingredients):
        return None, "egg_beverage"
    if drink and (any(re.search(r"\byeast\b", item, re.I) for item in ingredients)
                  or re.search(r"\bferment(?:ed|ation|ing)?\b", " ".join(steps), re.I)):
        return None, "fermented_beverage"
    if re.search(r"\b(?:raw|unpasteuri[sz]ed)\s+(?:milk|egg|eggs|chicken|pork|beef|fish)\b", " ".join(ingredients), re.I):
        return None, "raw_animal_ingredient"
    time_match = re.search(r"\|\s*time\s*=\s*([^|}\n]+)", wikitext[:2500], re.I)
    servings_match = re.search(r"\|\s*servings\s*=\s*([^|}\n]+)", wikitext[:2500], re.I)
    url = "https://en.wikibooks.org/wiki/" + quote(title.replace(" ", "_"), safe=":/()")
    record = {
        "id": "wikibooks_" + str(page["pageid"]), "title": plain_title,
        "recipe_type": "drink" if drink else "food", "language": "en",
        "ingredients": [{"name": line, "amount": "", "unit": ""} for line in ingredients],
        "steps": steps, "categories": categories,
        "cooking_time": clean(time_match.group(1)) if time_match else "",
        "servings": clean(servings_match.group(1)) if servings_match else "",
        "source_url": url, "revision_url": "https://en.wikibooks.org/w/index.php?oldid=" + str(revision["revid"]),
        "revision_id": revision["revid"], "source_title": title, "source_name": "Wikibooks Cookbook",
        "license": "CC-BY-SA-4.0", "license_url": LICENSE_URL,
        "attribution": "Wikibooks contributors — " + title,
        "changes": "Ingredients and procedure sections extracted; wiki markup removed. Original English retained; amounts not standardized.",
        "extraction_warnings": warnings,
    }
    return record, None


def rebuild_existing():
    """Re-extract retained IDs from the archived revisions without networking."""
    target = OUTPUT / "recipes.json"
    previous = json.loads(target.read_text(encoding="utf-8"))
    retained_ids = {record["id"] for record in previous}
    beverage_ids = {int(record["id"].split("_")[-1]) for record in previous if record["recipe_type"] == "drink"}
    pages = {}
    for line in (OUTPUT / "raw_pages.jsonl").read_text(encoding="utf-8").splitlines():
        page = json.loads(line)
        record_id = "wikibooks_" + str(page["pageid"])
        if record_id in retained_ids:
            pages[record_id] = page
    rebuilt = []
    for old in previous:
        if old["id"] not in pages:
            raise RuntimeError("Retained recipe has no archived source: " + old["id"])
        record, reason = normalize_recipe(pages[old["id"]], beverage_ids)
        if reason:
            raise RuntimeError("Offline rebuild would drop a retained ID: " + old["id"] + ": " + reason)
        rebuilt.append(record)
    assert [record["id"] for record in rebuilt] == [record["id"] for record in previous]
    write_json(target, rebuilt)
    manifest_path = OUTPUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(status="complete", total=len(rebuilt), counts=dict(Counter(record["recipe_type"] for record in rebuilt)),
                    extraction_version=2, reprocessed_at=datetime.now(timezone.utc).isoformat(),
                    records_with_extraction_warnings=sum(bool(record["extraction_warnings"]) for record in rebuilt))
    manifest["sha256"] = {name: hashlib.sha256((OUTPUT / name).read_bytes()).hexdigest() for name in ("recipes.json", "raw_pages.jsonl")}
    write_json(manifest_path, manifest)
    print(json.dumps({"offline_rebuilt": len(rebuilt), "counts": manifest["counts"],
                      "records_with_extraction_warnings": manifest["records_with_extraction_warnings"]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=900)
    parser.add_argument("--scan", type=int, default=2400)
    parser.add_argument("--rebuild-existing", action="store_true", help="Re-extract the current recipe IDs from raw_pages.jsonl without network calls")
    args = parser.parse_args()
    if args.rebuild_existing:
        rebuild_existing()
        return
    if not 1 <= args.limit <= 1000:
        parser.error("limit must be 1..1000")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    print("Listing official beverage recipes...", flush=True)
    drinks = beverage_members(session)
    print(f"Beverage category pages: {len(drinks)}", flush=True)
    all_pages = [r for r in category_members(session, "Category:Recipes", limit=5000) if r.get("ns") == 102]
    # Cover the alphabet rather than taking only the first few letters.
    if len(all_pages) > args.scan:
        indices = sorted({round(i * (len(all_pages) - 1) / (args.scan - 1)) for i in range(args.scan)})
        all_pages = [all_pages[i] for i in indices]
    random.Random(20261111).shuffle(all_pages)
    priority = [r for r in all_pages if re.search(r"\b(?:soup|porridge|congee|broth|stew|puree|purée)\b", r["title"], re.I)]
    priority_ids = {r["pageid"] for r in priority}
    ordered = list(drinks.values()) + [r for r in priority if r["pageid"] not in drinks] + [r for r in all_pages if r["pageid"] not in drinks and r["pageid"] not in priority_ids]
    records, rejected, seen = [], Counter(), set()
    raw_path = OUTPUT / "raw_pages.jsonl"
    with raw_path.open("w", encoding="utf-8") as raw_file:
        for offset in range(0, len(ordered), 50):
            batch = ordered[offset:offset + 50]
            data = request(session, prop="revisions|categories", pageids="|".join(str(p["pageid"]) for p in batch),
                           rvprop="ids|content", rvslots="main", cllimit=50)
            for page in data.get("query", {}).get("pages", []):
                raw_file.write(json.dumps(page, ensure_ascii=False) + "\n")
                record, reason = normalize_recipe(page, drinks)
                if reason:
                    rejected[reason] += 1
                elif record["id"] not in seen:
                    records.append(record)
                    seen.add(record["id"])
            print(f"Fetched {min(offset + 50, len(ordered))}/{len(ordered)} pages; accepted {len(records)}", flush=True)
            # Keep real parsed data available while a rate-limited import runs.
            checkpoint = records[:args.limit]
            write_json(OUTPUT / "recipes.json", checkpoint)
            write_json(OUTPUT / "manifest.json", {
                "source": "Wikibooks Cookbook", "api": API, "status": "import_in_progress",
                "license": "CC-BY-SA-4.0", "license_url": LICENSE_URL,
                "copyright_policy": "https://en.wikibooks.org/wiki/Wikibooks:Copyrights",
                "counts": dict(Counter(r["recipe_type"] for r in checkpoint)),
                "total": len(checkpoint), "rejected": dict(rejected),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "images_downloaded": False})
            if len(records) >= args.limit:
                records = records[:args.limit]
                break
    target = OUTPUT / "recipes.json"
    write_json(target, records)
    assert len({r["id"] for r in records}) == len(records)
    assert all(r["ingredients"] and r["steps"] and r["revision_id"] and r["source_url"].startswith("https://en.wikibooks.org/") for r in records)
    manifest = {
        "source": "Wikibooks Cookbook", "api": API, "status": "complete", "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "license": "CC-BY-SA-4.0", "license_url": LICENSE_URL,
        "copyright_policy": "https://en.wikibooks.org/wiki/Wikibooks:Copyrights",
        "attribution": "Wikibooks contributors; individual page and revision links included in each record.",
        "counts": dict(Counter(r["recipe_type"] for r in records)), "total": len(records),
        "rejected": dict(rejected), "images_downloaded": False,
        "sha256": {name: hashlib.sha256((OUTPUT / name).read_bytes()).hexdigest() for name in ("recipes.json", "raw_pages.jsonl")},
        "limitations": ["Community recipes, not medically reviewed.", "Original English, textual quantities, no inferred nutrient values.", "Extraction does not certify cooking safety, allergen absence, or disease suitability."]
    }
    write_json(OUTPUT / "manifest.json", manifest)
    (OUTPUT / "README.md").write_text("# Wikibooks Cookbook import\n\nText by Wikibooks contributors, **CC BY-SA 4.0**.\n\nLicense: https://creativecommons.org/licenses/by-sa/4.0/\n\nSource policy: https://en.wikibooks.org/wiki/Wikibooks:Copyrights\n\nEach recipe retains its source page, revision link, author attribution and extraction changes. Adapted recipe text must retain attribution and the same license. Images are not included. `raw_pages.jsonl` preserves fetched wikitext; `recipes.json` contains extracted ingredients and directions. This is community cooking data, not evidence of medical suitability. Quantities stay as original English text; nutrition is not inferred.\n", encoding="utf-8")
    print(json.dumps({"total": len(records), "counts": manifest["counts"], "rejected": dict(rejected)}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
