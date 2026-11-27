"""Local Mon Ngon Moi Ngay recipe catalog and bounded candidate retrieval."""
from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

DATA_ROOT = Path(__file__).resolve().parents[2] / "data/recipes"
DATA_PATH = DATA_ROOT / "monngonmoingay_recipes_with_kcal.json"


def normalize(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", str(text).lower())
                             if unicodedata.category(c) != "Mn").replace("đ", "d").split())


def title_key(recipe):
    # Keep accents: canh and cánh, cháo and chảo describe different foods.
    return " ".join(unicodedata.normalize("NFC", str(recipe.get("title", ""))).casefold().split())


def _trusted_image_url(value):
    try:
        raw = str(value or "").strip()
        if not raw or "no-image.jpg" in raw.lower():
            return ""
        url = urlsplit(raw)
        if (url.scheme == "https" and url.hostname
                and (url.hostname == "monngonmoingay.com" or url.hostname.endswith(".monngonmoingay.com"))
                and not url.username and not url.password):
            return raw
    except (ValueError, TypeError):
        pass
    return ""


def _normalize_monngon_entry(entry, index):
    title = str(entry.get("ten_mon") or "").strip()
    if not title:
        return None
    raw_ings = [str(x).strip() for x in (entry.get("nguyen_lieu") or []) if isinstance(x, (str, int, float)) and str(x).strip()]
    so_che = [str(x).strip() for x in (entry.get("so_che") or []) if isinstance(x, (str, int, float)) and str(x).strip()]
    thuc_hien = [str(x).strip() for x in (entry.get("thuc_hien") or []) if isinstance(x, (str, int, float)) and str(x).strip()]
    steps = [f"Sơ chế: {s}" for s in so_che] + thuc_hien
    if not raw_ings or not steps:
        return None
    tags = [str(t).strip() for t in (entry.get("tags") or []) if isinstance(t, (str, int, float)) and str(t).strip()]
    kcal_raw = entry.get("kcal")
    kcal = kcal_raw if isinstance(kcal_raw, (int, float)) and not isinstance(kcal_raw, bool) and kcal_raw >= 0 else None
    khau_phan = str(entry.get("khau_phan") or "").strip()
    thoi_gian = str(entry.get("thoi_gian_thuc_hien") or "").strip()
    do_kho = str(entry.get("do_kho") or "").strip()
    image_url = _trusted_image_url(entry.get("hinh_anh"))
    return {
        "id": f"mnnm-{index}",
        "title": title,
        "ten_mon": title,
        "recipe_type": "food",
        "language": "vi",
        "cuisine": "VN",
        "imported": True,
        "source_provider": "Món Ngon Mỗi Ngày",
        "subtitle": "Món Việt chọn lọc · Món Ngon Mỗi Ngày",
        "cooking_time": thoi_gian or "Xem cách làm",
        "thoi_gian_thuc_hien": thoi_gian,
        "difficulty": do_kho,
        "do_kho": do_kho,
        "servings": khau_phan or "4 người",
        "khau_phan": khau_phan,
        "calories": kcal,
        "kcal": kcal,
        "image_link": image_url,
        "hinh_anh": image_url,
        "image_ok": bool(image_url),
        "categories": tags,
        "tags": tags,
        "ingredients": [{"name": item, "amount": "", "unit": ""} for item in raw_ings],
        "nguyen_lieu": raw_ings,
        "preparation_steps": so_che,
        "so_che": so_che,
        "thuc_hien": thuc_hien,
        "steps": steps,
        "benefit": "Công thức nấu ăn tham khảo từ Món Ngon Mỗi Ngày; chưa được xác minh công dụng hoặc mức độ phù hợp với bệnh cho từng món.",
        "avoid": ["Đối chiếu nguyên liệu, dị ứng và hướng dẫn ăn uống cá nhân trước khi dùng."],
    }


@lru_cache(maxsize=4)
def _read_catalog(path, version):
    if version is None:
        return []
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(raw, dict):
        raw = raw.get("recipes", [])
    result, ids = [], set()
    for index, entry in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("ten_mon"), str):
            recipe = _normalize_monngon_entry(entry, index)
            if not recipe or recipe["id"] in ids:
                continue
            ids.add(recipe["id"])
            result.append(recipe)
            continue
        # Fallback for synthetic unit-test records with canonical keys
        if (entry.get("id") in ids
                or not entry.get("id")
                or entry.get("recipe_type") != "food"
                or not isinstance(entry.get("title"), str) or not entry["title"].strip()
                or not entry.get("ingredients") or not entry.get("steps")
                or not isinstance(entry.get("ingredients"), list)
                or not isinstance(entry.get("steps"), list)
                or any(not isinstance(i, dict) or not isinstance(i.get("name"), str) or not i["name"].strip() for i in entry["ingredients"])
                or any(not isinstance(s, str) or not s.strip() for s in entry["steps"])):
            continue
        recipe = deepcopy(entry)
        recipe.setdefault("language", "vi")
        recipe.setdefault("cuisine", "VN")
        recipe.setdefault("subtitle", "Món Việt chọn lọc · Món Ngon Mỗi Ngày")
        if not recipe.get("cooking_time"):
            recipe["cooking_time"] = "Xem cách làm"
        recipe.setdefault("benefit", "Công thức nấu ăn tham khảo; chưa được xác minh công dụng hoặc mức độ phù hợp với bệnh cho từng món.")
        recipe.setdefault("avoid", ["Đối chiếu nguyên liệu, dị ứng và hướng dẫn ăn uống cá nhân trước khi dùng."])
        recipe["imported"] = True
        recipe.setdefault("source_provider", "Món Ngon Mỗi Ngày")
        ids.add(recipe["id"])
        result.append(recipe)
    return result


def _records(source=None):
    version = DATA_PATH.stat().st_mtime_ns if DATA_PATH.exists() else None
    return _read_catalog(str(DATA_PATH), version)


def imported_recipes(recipe_type=None, source=None):
    records = _records(source)
    return deepcopy([r for r in records if not recipe_type or r["recipe_type"] == recipe_type])


def catalog_stats():
    records = _records()
    providers = sorted({r["source_provider"] for r in records})
    vietnamese = bool(records) and all(r.get("cuisine") == "VN" for r in records)
    return {
        "imported_count": len(records),
        "food_count": sum(r["recipe_type"] == "food" for r in records),
        "total": len(records),
        "source": ", ".join(providers) if providers else "Món Ngon Mỗi Ngày",
        "cuisine": "VN" if vietnamese else "unspecified",
        "license": "not_declared",
    }


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
    """Phân loại vai trò món trong mâm cơm: main, soup, side, staple."""
    title = normalize(recipe.get("title", ""))
    cats = normalize(" ".join(recipe.get("categories", [])))
    if any(k in title for k in ["chao ", "sup ", "cháo", "súp", "oatmeal", "porridge", "congee", "mien ", "bun ", "pho ", "banh canh", "hu tieu", "com ", "mi ", "nui", "banh cuon", "banh uot", "banh mi", "xoi ", "khoai", "bap luoc", "ngo luoc", "san luoc"]):
        return "staple"
    if any(k in title for k in ["canh", "lau", "lẩu"]) or "canh" in cats:
        return "soup"
    if any(k in title for k in ["xao", "luoc", "goi", "nom", "salad", "xào", "luộc", "gỏi", "nộm", "rau"]) or any(k in cats for k in ["xao", "goi", "salad", "rau"]):
        return "side"
    if any(k in title for k in ["che ", "chè"]):
        return "dessert"
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
    if role == "staple" or any(k in title for k in ["chao", "sup", "cháo", "súp", "banh", "trung", "sua", "yen mach", "bun", "pho"]):
        meals.append("breakfast")
    if role in ("main", "soup", "side", "staple"):
        meals.append("lunch")
        meals.append("dinner")
    if role == "staple" or any(k in title for k in ["che", "chè", "sen", "sua", "sữa", "tra", "trà", "chao", "cháo"]):
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
