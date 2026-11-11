"""Local, attributed recipe catalog and bounded candidate retrieval."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit

DATA_ROOT = Path(__file__).resolve().parent.parent / "data/recipes"
DATA_PATH = DATA_ROOT / "vifoodrec/recipes.json"
WIKIBOOKS_DATA_PATH = DATA_ROOT / "wikibooks/recipes.json"
VIFOODREC_REPOSITORY = "QuocAn55/A-New-Dataset-and-Empirical-Evaluation-for-Vietnamese-Food-Recommendation-System"


def normalize(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", str(text).lower())
                             if unicodedata.category(c) != "Mn").replace("đ", "d").split())


def title_key(recipe):
    # Keep accents: canh and cánh, cháo and chảo describe different foods.
    return " ".join(unicodedata.normalize("NFC", str(recipe.get("title", ""))).casefold().split())


def _source_valid(entry):
    """Validate provenance, not medical suitability or cuisine authenticity."""
    try:
        url = urlsplit(str(entry.get("source_url", "")))
        if url.scheme != "https" or url.username or url.password or url.port not in (None, 443):
            return False
        if str(entry.get("id", "")).startswith("wikibooks_"):
            return (url.hostname == "en.wikibooks.org"
                    and entry.get("license") in ("CC-BY-SA-4.0", "CC BY-SA 4.0"))
        if str(entry.get("id", "")).startswith("vifoodrec_"):
            repo = "/".join(unquote(url.path).strip("/").split("/")[:2])
            return (url.hostname == "github.com" and repo.lower() == VIFOODREC_REPOSITORY.lower()
                    and entry.get("license") == "not_declared"
                    and entry.get("language") == "vi" and entry.get("cuisine") == "VN")
    except (ValueError, TypeError):
        pass
    return False


@lru_cache(maxsize=4)
def _read_catalog(path, version):
    if version is None:
        return []
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(raw, dict):
        raw = raw.get("recipes", [])
    result, ids = [], set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if (not _source_valid(entry)
                or entry.get("id") in ids
                or entry.get("recipe_type") not in ("food", "drink")
                or not isinstance(entry.get("title"), str) or not entry["title"].strip()
                or not entry.get("ingredients") or not entry.get("steps")
                or not isinstance(entry.get("ingredients"), list)
                or not isinstance(entry.get("steps"), list)
                or any(not isinstance(i, dict) or not isinstance(i.get("name"), str) or not i["name"].strip() for i in entry["ingredients"])
                or any(not isinstance(s, str) or not s.strip() for s in entry["steps"])):
            continue
        recipe = deepcopy(entry)
        vietnamese = recipe["id"].startswith("vifoodrec_")
        recipe.setdefault("subtitle", "Món Việt chọn lọc · công thức tiếng Việt" if vietnamese
                          else "Công thức Wikibooks · bản gốc tiếng Anh")
        if not recipe.get("cooking_time"):
            recipe["cooking_time"] = "Xem cách làm"
        recipe.setdefault("benefit", "Công thức nấu ăn tham khảo; chưa được xác minh công dụng hoặc mức độ phù hợp với bệnh cho từng món.")
        recipe.setdefault("avoid", ["Đối chiếu nguyên liệu, dị ứng và hướng dẫn ăn uống cá nhân trước khi dùng."])
        recipe["imported"] = True
        recipe["source_provider"] = "ViFoodRec" if vietnamese else "Wikibooks Cookbook"
        ids.add(recipe["id"])
        result.append(recipe)
    return result


def _records(source=None):
    # International records remain archived for reproducibility. They are not
    # silently used as the fallback for a Vietnamese catalog or empty filter.
    path = WIKIBOOKS_DATA_PATH if source == "wikibooks" else DATA_PATH
    version = path.stat().st_mtime_ns if path.exists() else None
    return _read_catalog(str(path), version)


def imported_recipes(recipe_type=None, source=None):
    records = _records(source)
    return deepcopy([r for r in records if not recipe_type or r["recipe_type"] == recipe_type])


def catalog_stats():
    records = _records()
    demo = 0 if records else 7
    providers = sorted({r["source_provider"] for r in records})
    vietnamese = bool(records) and all(r.get("cuisine") == "VN" for r in records)
    return {"imported_count": len(records), "food_count": demo + sum(r["recipe_type"] == "food" for r in records),
            "drink_count": demo + sum(r["recipe_type"] == "drink" for r in records),
            "total": 2 * demo + len(records), "source": ", ".join(providers) if providers else "Danh mục mẫu",
            "cuisine": "VN" if vietnamese else "unspecified",
            "license": "not_declared" if vietnamese else "CC BY-SA 4.0" if providers == ["Wikibooks Cookbook"] else "project_samples"}


EXPANSIONS = {
    "sot": "chao canh sup nuoc gao ga rau soup broth congee porridge rice chicken vegetable water",
    "ho": "chao canh sup nuoc le soup broth porridge water milk drink",
    "nhiet mieng": "chao canh sup mem sua soup puree porridge custard soft milk",
    "mat ngu": "chao canh hat sen dau xanh sua soup porridge oatmeal rice milk",
    "cang thang": "canh rau chao gao dau vegetable soup rice oats",
    "trao nguoc": "gao hap luoc rau rice steamed boiled vegetable",
    "ga": "chicken", "ca": "fish", "rau": "vegetable spinach carrot", "bi do": "pumpkin squash",
    "chao": "porridge congee", "sup": "soup", "sua": "milk", "nuoc": "water drink beverage",
    "dau hu": "tofu", "chuoi": "banana", "tao": "apple", "le": "pear",
}


def retrieve_candidates(condition, recipes, limit=32):
    """Text/metadata retrieval, not a clinical suitability score or diagnosis."""
    query = normalize(condition)
    expanded = query + " " + " ".join(v for k, v in EXPANSIONS.items() if re.search(r"\b" + re.escape(k) + r"\b", query))
    tokens = {t for t in re.findall(r"[a-z]{2,}", expanded) if t not in
              {"toi", "can", "muon", "the", "and", "for", "bi", "mon", "an", "uong", "sot", "ho", "mat", "ngu", "nhiet", "mieng"}}
    def score(recipe):
        title = normalize(recipe.get("title", ""))
        categories = normalize(" ".join(recipe.get("categories", [])))
        ingredients = normalize(" ".join(str(i.get("name", "")) for i in recipe.get("ingredients", [])))
        tags = recipe.get("rule_tags", [])
        value = sum(8 * bool(re.search(r"\b" + re.escape(t) + r"\b", title))
                    + 3 * bool(re.search(r"\b" + re.escape(t) + r"\b", categories))
                    + bool(re.search(r"\b" + re.escape(t) + r"\b", ingredients)) for t in tokens)
        if any(re.search(r"\b" + word + r"\b", query) for word in ("sot", "ho", "nhiet mieng")):
            value += 5 * ("soft" in tags or "liquid" in tags)
        return value
    ranked, seen_titles = [], set()
    for recipe in sorted(recipes, key=lambda r: (-score(r), r["id"])):
        key = title_key(recipe)
        if key not in seen_titles:
            ranked.append(recipe)
            seen_titles.add(key)
    # When there is enough relevant imported data, avoid filling the entire
    # shortlist with the same demonstration catalog on every request.
    imported = [r for r in ranked if r.get("imported")]
    if len(imported) >= 8:
        originals = [r for r in ranked if not r.get("imported")][:2]
        chosen = originals + imported[:max(0, limit - len(originals))]
        return sorted(chosen, key=lambda r: (-score(r), r["id"]))
    return ranked[:limit]
