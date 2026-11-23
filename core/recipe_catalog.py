"""Local, attributed recipe catalog and bounded candidate retrieval."""
from copy import deepcopy
from functools import lru_cache
import json
import math
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


def _parse_servings_count(servings_value) -> int:
    """Parse number of servings from strings like '4 người', clamped to 1..12."""
    match = re.search(r"(\d+)", str(servings_value or ""))
    if not match:
        return 1
    return max(1, min(12, int(match.group(1))))


def normalize_drink_calories(recipe) -> None:
    """Calibrate drink calories to a realistic per-glass (250ml) estimate (40-180 kcal)."""
    if not isinstance(recipe, dict) or recipe.get("recipe_type") != "drink":
        return
    raw_cal = recipe.get("calories")
    servings_count = _parse_servings_count(recipe.get("servings"))
    raw_per_serving = (
        float(raw_cal) / servings_count
        if isinstance(raw_cal, (int, float)) and not isinstance(raw_cal, bool) and math.isfinite(raw_cal) and raw_cal > 0
        else 150.0
    )
    ing_text = normalize(" ".join(str(i.get("name", "")) for i in recipe.get("ingredients", []) if isinstance(i, dict)))
    text = normalize(recipe.get("title", "")) + " " + ing_text

    if re.search(r"\b(?:sua\s+dac|nuoc\s+cot\s+dua|kem\s+(?:tuoi|vanilla|cheese)|whipping|pho\s+mai|cheese|tran\s+chau|sau\s+rieng|base\s+rich|tra\s+sua|bo\s+sap)\b", text):
        lo, hi = 130, 180
    elif re.search(r"\b(?:sua\s+(?:tuoi|chua|dau|hat|gao|bap|ngo)|yakult|dau\s+(?:xanh|nanh|den|do|phong)|hat\s+(?:sen|chia)|gao\s+lut|yen\s+mach|sinh\s+to|xoai|mit|sa\s+po\s+che|chuoi)\b", text):
        lo, hi = 95, 155
    elif re.search(r"\b(?:duong|mat\s+ong|siro|mut|tao|cam|quyt|thanh\s+long|dua\s+(?:hau|gang|luoi)|nho|dao|dau|oi|thom|khom|le|coc|chanh\s+day|xi\s+muoi|hong\s+tao|long\s+nhan)\b", text):
        lo, hi = 60, 115
    else:
        lo, hi = 40, 70

    if lo <= raw_per_serving <= hi:
        calibrated = round(raw_per_serving)
    else:
        ratio = max(0.0, min(1.0, (raw_per_serving - 50.0) / 250.0))
        calibrated = round(lo + ratio * (hi - lo))
    recipe["calories"] = int(max(lo, min(hi, calibrated)))
    recipe["calories_basis"] = "per_serving"
    recipe["serving_unit"] = "1 ly"


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
        if recipe["recipe_type"] == "drink":
            normalize_drink_calories(recipe)
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
    "sot": "chao canh sup nuoc gao ga nac rau cu thanh nhiet dau xanh soup broth congee porridge chicken vegetable water bun pho",
    "ho": "chao canh sup nuoc le soup broth porridge water milk drink",
    "nhiet mieng": "chao canh sup mem sua dau hu ca ga bot san rau ngot mong toi bi dao thanh nhiet soft tofu soup congee bun pho banh canh",
    "mat ngu": "hat sen cu sen dau hu dau phu ca ga nac nam rau cai bo xoi bi do khoai chuoi yen mach dau xanh canh chao com bun pho lotus tofu mushroom fish chicken",
    "cang thang": "ca hoi ca nac ga nam hat sen chuoi rau xanh dau hu yen mach canh xao bun pho com vegetable soup fish oats",
    "met moi": "ga nac ca bo chao bun pho com mi truyen nang luong dam vitamin rau xanh chanh gung sam hat sen soup oats",
    "trao nguoc": "gao hap luoc rau yen mach khoai tay khoai lang ca nac ga hap bi do canh steamed boiled vegetable",
    "gut": "can tay dua leo anh dao cherry tra xanh bi dao bi xanh cam buoi chanh tao trung bap cai ca chua cai thia bong cai ca rot khoai tay bi do chao mien com canh rau cu celery cucumber cherry green tea vitamin egg vegetable cabbage soup congee",
    "tieu duong": "rau xanh ca nac ga nac dau hu kho qua bi dao bi xanh canh xao vegetable fish chicken",
    "hypertension": "can tay rau cai ca nac nam cu cai ca chua dau xanh canh xao celery vegetable fish",
    "stomach": "chao sup khoai tay bi do dau hu non ca hap ga luoc chuoi mem soup congee steamed soft bun",
    "ga": "chicken", "ca": "fish", "rau": "vegetable spinach carrot", "bi do": "pumpkin squash",
    "chao": "porridge congee", "sup": "soup", "sua": "milk", "nuoc": "water drink beverage",
    "dau hu": "tofu", "chuoi": "banana", "tao": "apple", "le": "pear",
}

STANDALONE_PATTERN = re.compile(
    r'(?<!bó\s)\b(bún|phở|hủ tiếu|hủ tíu|hu tieu|mì|miến|bánh canh|cơm tấm|cơm chiên|cơm rang|cơm gà|cơm gạo lứt|cơm trộn|cơm hến|cơm lam|cơm sườn|cơm thố|cơm niêu|cháo|súp|bánh mì|xôi|bánh cuốn|bánh ướt|bánh xèo|bánh khọt|bánh hỏi|mì quảng|cao lầu|nui|bò kho|lẩu|pasta|spaghetti|sandwich|burger)\b',
    re.IGNORECASE
)


def is_standalone_one_dish(recipe):
    """Kiểm tra món ăn có phải món đơn lẻ trọn vị (One-dish meal: bún, phở, mì, miến, cơm tấm, cháo, súp, bánh mì, xôi...)
    chứ không phải món thành phần trong mâm cơm (canh suông, rau luộc, món mặn ăn cơm) hay món chè ngọt/tráng miệng."""
    if not recipe:
        return False
    if recipe.get("recipe_type") == "drink":
        return True
    title = str(recipe.get("title", "")).strip()
    if title.lower().startswith("canh ") or title.lower().startswith("canh:"):
        return False
    t_lower = title.lower()
    if any(k in t_lower for k in ["chè ", " chè", "chè:", "bột báng", "sợi bánh canh", "làm sợi", "sâm bổ lượng", "bánh ít", "bánh chuối", "bánh bò", "bánh ngọt", "pudding", "caramel"]):
        return False
    cleaned = re.sub(r"bó\s+xôi", "", title, flags=re.I)
    cleaned = re.sub(r"mì\s+căn", "", cleaned, flags=re.I)
    return bool(STANDALONE_PATTERN.search(cleaned))


def classify_dish_role(recipe):
    """Phân loại vai trò món trong mâm cơm: main, soup, side, staple, drink."""
    if recipe.get("recipe_type") == "drink":
        return "drink"
    title = normalize(recipe.get("title", ""))
    cats = normalize(" ".join(recipe.get("categories", [])))
    if any(k in title for k in ["chao ", "sup ", "cháo", "súp", "oatmeal", "porridge", "congee", "mien ", "bun ", "pho ", "banh canh", "hu tieu", "com ", "mi ", "nui", "banh cuon", "banh uot", "banh mi", "xoi ", "khoai", "bap luoc", "ngo luoc", "san luoc"]):
        return "staple"
    if any(k in title for k in ["canh", "lau", "lẩu"]) or "canh" in cats:
        return "soup"
    if any(k in title for k in ["xao", "luoc", "goi", "nom", "salad", "xào", "luộc", "gỏi", "nộm", "rau"]) or any(k in cats for k in ["xao", "goi", "salad", "rau"]):
        return "side"
    if any(k in title for k in ["che ", "tra ", "sua ", "chè", "trà", "sữa"]):
        return "drink"
    veg_keywords = ["cai", "cải", "bi ", "bí ", "bau ", "bầu ", "muop", "mướp", "bong cai", "bông cải", "nam", "nấm", "ca tim", "cà tím", "dau bap", "đậu bắp", "su hao", "su hào", "su su", "cu cai", "củ cải", "ngo sen", "ngó sen", "dau hu", "đậu hũ", "dau phu", "đậu phụ"]
    meat_keywords = ["thit", "thịt", "heo", "lon", "lợn", "bo ", "bò ", "ga ", "gà ", "vit", "vịt", "ca ", "cá ", "tom", "tôm", "cua", "muc", "mực", "oc ", "ốc ", "suon", "sườn", "gio ", "giò ", "luon", "lươn", "ech", "ếch"]
    if any(k in title for k in veg_keywords) and not any(k in title for k in meat_keywords):
        return "side"
    return "main"


def classify_meal_times(recipe, role=None):
    """Xác định các bữa ăn phù hợp cho món: breakfast, lunch, dinner, snack."""
    if role is None:
        role = classify_dish_role(recipe)
    title = normalize(recipe.get("title", ""))
    meals = []
    if role in ("staple", "drink") or any(k in title for k in ["chao", "sup", "cháo", "súp", "banh", "trung", "sua", "yen mach", "bun", "pho"]):
        meals.append("breakfast")
    if role in ("main", "soup", "side", "staple"):
        meals.append("lunch")
        meals.append("dinner")
    if role in ("drink", "staple") or any(k in title for k in ["che", "chè", "sen", "sua", "sữa", "tra", "trà", "chao", "cháo"]):
        meals.append("snack")
    return list(dict.fromkeys(meals)) or ["lunch", "dinner"]


def retrieve_candidates(condition, recipes, limit=32, sort_by_sugar=False):
    """Text/metadata retrieval with dish role diversity for balanced meals."""
    query = normalize(condition)
    expanded = query + " " + " ".join(v for k, v in EXPANSIONS.items() if re.search(r"\b" + re.escape(k) + r"\b", query))
    tokens = {t for t in re.findall(r"[a-z]{2,}", expanded) if t not in
              {"toi", "can", "muon", "the", "and", "for", "bi", "mon", "an", "uong", "sot", "ho", "mat", "ngu", "nhiet", "mieng", "dau", "mo", "it", "khong", "tranh", "giam", "nhieu"}}
    is_gout = bool(re.search(r"\b(?:gut|gout|acid\s+uric)\b", query))
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
        if is_gout:
            if "gout_friendly" in tags:
                value += 25
            if "purine_moderate_legume" in tags:
                value -= 22
            if recipe.get("recipe_type") == "food":
                if re.search(r"\b(?:banh\s+(?:ran|xep|chung|tet|tro|it|bo|chuoi)|ngo\s+chien|dua\s+mon|nuoc\s+mam)\b", title):
                    value -= 25
            elif recipe.get("recipe_type") == "drink":
                if re.search(r"\b(?:tra\s+sua|kem\s+cheese|pho\s+mai|ca\s+phe|tran\s+chau|sau\s+rieng|sua\s+dac)\b", title + " " + ingredients):
                    value -= 25
                if re.search(r"\b(?:can\s+tay|dua\s+leo|anh\s+dao|cherry|tra\s+xanh|bi\s+dao|tao|cam|buoi)\b", title):
                    value += 18
        return value
    def priority_key(recipe):
        if sort_by_sugar:
            sugar = recipe.get("sugar")
            known = isinstance(sugar, (int, float)) and not isinstance(sugar, bool) and math.isfinite(sugar)
            return (not known, sugar if known else float("inf"), -score(recipe), recipe["id"])
        return (-score(recipe), recipe["id"])
    ranked, seen_titles = [], set()
    for recipe in sorted(recipes, key=priority_key):
        key = title_key(recipe)
        if key not in seen_titles:
            ranked.append(recipe)
            seen_titles.add(key)

    # Đảm bảo phân bổ đa dạng vai trò món (món chính, canh, rau, tinh bột) cho food
    first_type = recipes[0].get("recipe_type") if recipes else "food"
    if first_type == "food" and len(ranked) >= 16:
        by_role = {}
        for r in ranked:
            role = classify_dish_role(r)
            by_role.setdefault(role, []).append(r)
        
        quotas = {"main": 8, "soup": 6, "side": 6, "staple": 10, "drink": 2}
        diverse_candidates = []
        selected_ids = set()
        for role, quota in quotas.items():
            for r in by_role.get(role, [])[:quota]:
                if r["id"] not in selected_ids:
                    diverse_candidates.append(r)
                    selected_ids.add(r["id"])
        
        if len(diverse_candidates) < limit:
            for r in ranked:
                if r["id"] not in selected_ids:
                    diverse_candidates.append(r)
                    selected_ids.add(r["id"])
                    if len(diverse_candidates) >= limit:
                        break

        # Interleave roles to ensure balanced dish representation in top slots: main, soup, side, staple, drink
        role_order = ["main", "soup", "side", "staple", "drink"]
        role_lists = {role: [r for r in diverse_candidates if classify_dish_role(r) == role] for role in role_order}
        for role in role_lists:
            role_lists[role].sort(key=priority_key)
            
        interleaved = []
        max_depth = max(len(l) for l in role_lists.values()) if role_lists else 0
        for i in range(max_depth):
            for role in role_order:
                if i < len(role_lists[role]):
                    interleaved.append(role_lists[role][i])

        imported = [r for r in interleaved if r.get("imported")]
        if len(imported) >= 8:
            originals = [r for r in ranked if not r.get("imported")][:2]
            chosen = originals + [r for r in interleaved if r.get("imported")][:max(0, limit - len(originals))]
            if len(chosen) < limit:
                chosen_ids = {r["id"] for r in chosen}
                for r in ranked:
                    if r.get("imported") and r["id"] not in chosen_ids:
                        chosen.append(r)
                        chosen_ids.add(r["id"])
                        if len(chosen) >= limit:
                            break
                if len(chosen) < limit:
                    for r in ranked:
                        if r["id"] not in chosen_ids:
                            chosen.append(r)
                            chosen_ids.add(r["id"])
                            if len(chosen) >= limit:
                                break
            return chosen
        return interleaved[:limit]

    # When there is enough relevant imported data, avoid filling the entire
    # shortlist with the same demonstration catalog on every request.
    imported = [r for r in ranked if r.get("imported")]
    if len(imported) >= 8:
        originals = [r for r in ranked if not r.get("imported")][:2]
        chosen = originals + imported[:max(0, limit - len(originals))]
        return sorted(chosen, key=priority_key)
    return ranked[:limit]
