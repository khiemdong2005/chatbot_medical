"""Searchable, paginated view of the supplied Mon Ngon Moi Ngay recipe file."""
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit


DATA_PATH = Path(__file__).resolve().parents[2] / "data/recipes/monngonmoingay_recipes_with_kcal.json"
HEALTH_TAGS = {
    "Ăn kiêng / Giảm mỡ": ("ăn kiêng", "giảm khối mỡ thừa của cơ thể"),
    "Cân bằng dinh dưỡng": ("cân bằng dinh dưỡng",),
    "Ăn chay": ("ăn chay",),
    "Tăng năng lượng": ("tăng năng lượng",),
    "Tốt cho xương & cơ": ("tốt cho xương", "hỗ trợ xây dựng khối cơ xương"),
    "Phục hồi sức khỏe": ("hỗ trợ miễn dịch", "hồi phục sau cảm"),
}
ALLERGY_TERMS = {
    "Tôm": ("tôm", "shrimp", "prawn"),
    "Hải sản": ("tôm", "cua", "ghẹ", "cá", "mực", "bạch tuộc", "sò", "nghêu", "hến", "ốc", "hàu", "hải sản", "seafood"),
    "Trứng": ("trứng", "egg"),
    "Thịt bò": ("thịt bò", "bò ", "beef"),
    "Đậu phộng": ("đậu phộng", "lạc", "peanut"),
    "Phô mai / Sữa": ("phô mai", "sữa", "bơ sữa", "kem tươi", "cheese", "milk", "cream"),
    "Nấm": ("nấm", "mushroom"),
}
MEAL_TAGS = {"Bữa sáng", "Bữa trưa", "Bữa tối", "Ăn vặt"}
METHOD_TAGS = {"Chiên", "Món xào", "Hấp/Tiềm", "Canh/Súp", "Gỏi/Trộn", "Nướng", "Kho"}


def normalize(value):
    value = unicodedata.normalize("NFD", str(value or "").casefold())
    return " ".join("".join(char for char in value if unicodedata.category(char) != "Mn").replace("đ", "d").split())


@lru_cache(maxsize=1)
def _recipes(version):
    if version is None:
        return ()
    try:
        entries = json.loads(DATA_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return ()
    result = []
    for index, item in enumerate(entries if isinstance(entries, list) else []):
        if not isinstance(item, dict) or not isinstance(item.get("ten_mon"), str):
            continue
        recipe = {key: item.get(key) for key in (
            "url", "ten_mon", "khau_phan", "thoi_gian_thuc_hien", "do_kho", "hinh_anh",
            "nguyen_lieu", "so_che", "thuc_hien", "tags", "kcal")}
        for key in ("nguyen_lieu", "so_che", "thuc_hien", "tags"):
            recipe[key] = [str(value) for value in recipe[key] if isinstance(value, (str, int, float))] if isinstance(recipe[key], list) else []
        recipe["id"] = f"mnnm-{index}"
        recipe["kcal"] = recipe["kcal"] if isinstance(recipe["kcal"], (int, float)) and not isinstance(recipe["kcal"], bool) else None
        recipe["image_ok"] = _trusted_url(recipe["hinh_anh"], "monngonmoingay.com")
        recipe["source_ok"] = _trusted_url(recipe["url"], "monngonmoingay.com")
        recipe["_search"] = normalize(" ".join([recipe["ten_mon"], *recipe["nguyen_lieu"]]))
        recipe["_tags"] = {normalize(tag) for tag in recipe["tags"]}
        result.append(recipe)
    return tuple(result)


def _trusted_url(value, host):
    try:
        parsed = urlsplit(str(value or ""))
        return parsed.scheme == "https" and parsed.hostname and (parsed.hostname == host or parsed.hostname.endswith("." + host)) and not parsed.username and not parsed.password
    except ValueError:
        return False


def _contains_term(text, term):
    normalized_term = normalize(term)
    return bool(normalized_term and re.search(r"(?<!\w)" + re.escape(normalized_term) + r"(?!\w)", text))


def search_recipes(args):
    try:
        page = max(1, min(10000, int(args.get("page", 1))))
        per_page = max(1, min(24, int(args.get("per_page", 18))))
        kcal_min = float(args.get("kcal_min", 0))
        kcal_max = float(args.get("kcal_max", 1000000))
    except (TypeError, ValueError):
        page, per_page, kcal_min, kcal_max = 1, 18, 0, 1000000
    query = normalize(args.get("q", ""))[:160]
    objective = args.get("objective", "all")
    meal = args.get("meal", "all")
    method = args.get("method", "all")
    raw_excluded = args.getlist("exclude") if hasattr(args, "getlist") else (args.get("exclude") or [])
    if isinstance(raw_excluded, str):
        raw_excluded = [raw_excluded]
    excluded = {value for value in raw_excluded if value in ALLERGY_TERMS}
    sort = args.get("sort", "relevance")
    recipes = _recipes(DATA_PATH.stat().st_mtime_ns if DATA_PATH.exists() else None)
    matches = []
    for recipe in recipes:
        if query and query not in recipe["_search"]:
            continue
        if objective in HEALTH_TAGS and not any(normalize(tag) in recipe["_tags"] for tag in HEALTH_TAGS[objective]):
            continue
        if meal in MEAL_TAGS and normalize(meal) not in recipe["_tags"]:
            continue
        if method in METHOD_TAGS and normalize(method) not in recipe["_tags"]:
            continue
        kcal = recipe["kcal"]
        if kcal is None or kcal < kcal_min or kcal > kcal_max:
            continue
        searchable = recipe["_search"] + " " + " ".join(recipe["_tags"])
        if any(any(_contains_term(searchable, term) for term in ALLERGY_TERMS[label]) for label in excluded):
            continue
        matches.append(recipe)
    if sort in ("kcal_asc", "kcal_desc"):
        matches.sort(key=lambda item: item["kcal"], reverse=sort == "kcal_desc")
    elif query:
        matches.sort(key=lambda item: (
            normalize(item["ten_mon"]) != query,
            not normalize(item["ten_mon"]).startswith(query),
            not _contains_term(normalize(item["ten_mon"]), query),
            normalize(item["ten_mon"]),
        ))
    start = (page - 1) * per_page
    items = [{key: value for key, value in recipe.items() if not key.startswith("_")} for recipe in matches[start:start + per_page]]
    return {"items": items, "total": len(matches), "page": page, "per_page": per_page,
            "pages": (len(matches) + per_page - 1) // per_page, "catalog_total": len(recipes)}
