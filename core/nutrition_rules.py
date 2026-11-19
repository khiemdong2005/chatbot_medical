"""Small, auditable candidate filters; these are not medical suitability labels.

The sources below describe general self-care or nutrition guidance. The recipe
metadata is manually checked against the local catalog, not supplied by Gemini.
Changing a recipe's ingredient list invalidates its metadata until reviewed.
"""
from copy import deepcopy
from functools import lru_cache
import re
import unicodedata
from typing import Any, Dict, List


def _normal(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value).lower().replace("_", " "))
    return " ".join("".join(c for c in text if unicodedata.category(c) != "Mn")
                    .replace("đ", "d").split())


@lru_cache(maxsize=4096)
def _scan_imported(names, title, categories, steps, recipe_type, language):
    """Cache only exact source text, never a user query or health information."""
    from core.recipe_features import analyze_imported_recipe
    return analyze_imported_recipe({"ingredients": [{"name": name} for name in names],
                                   "title": title, "categories": list(categories), "steps": list(steps),
                                   "recipe_type": recipe_type, "language": language})


def _imported_metadata(recipe):
    from core.recipe_features import analyze_imported_recipe
    ingredients = recipe.get("ingredients")
    categories, steps = recipe.get("categories", []), recipe.get("steps", [])
    if (not isinstance(ingredients, list) or not all(isinstance(i, dict) and isinstance(i.get("name"), str) for i in ingredients)
            or not isinstance(categories, list) or not all(isinstance(c, str) for c in categories)
            or not isinstance(steps, list) or not all(isinstance(s, str) for s in steps)):
        return analyze_imported_recipe(recipe)
    return _scan_imported(tuple(i["name"] for i in ingredients), str(recipe.get("title", "")),
                          tuple(categories), tuple(steps), str(recipe.get("recipe_type", "")),
                          str(recipe.get("language", "")))


SOURCES = {
    "mouth": {"source_title": "NHS: Mouth ulcers", "source_url": "https://www.nhs.uk/conditions/mouth-ulcers/"},
    "sleep": {"source_title": "NHS: Insomnia", "source_url": "https://www.nhs.uk/conditions/insomnia/"},
    "reflux": {"source_title": "NIDDK: Eating, Diet, & Nutrition for GER & GERD", "source_url": "https://www.niddk.nih.gov/health-information/digestive-diseases/acid-reflux-ger-gerd-adults/eating-diet-nutrition"},
    "cough": {"source_title": "NHS: Cough", "source_url": "https://www.nhs.uk/symptoms/cough/"},
    "fever": {"source_title": "MedlinePlus: Fever — eating and drinking", "source_url": "https://medlineplus.gov/ency/article/003090.htm"},
    "fever_alcohol": {"source_title": "NHS inform: Fever in adults", "source_url": "https://www.nhsinform.scot/illnesses-and-conditions/infections-and-poisoning/fever-in-adults/"},
    "balanced": {"source_title": "NHS: The Eatwell Guide", "source_url": "https://www.nhs.uk/live-well/eat-well/food-guidelines-and-food-labels/the-eatwell-guide/"},
    "allergy": {"source_title": "FDA: Have Food Allergies? Read the Label", "source_url": "https://www.fda.gov/consumers/consumer-updates/have-food-allergies-read-label"},
    "gluten": {"source_title": "NHS: Coeliac disease - Treatment", "source_url": "https://www.nhs.uk/conditions/coeliac-disease/treatment/"},
    "gout": {"source_title": "NHS hospital: Gout and diet", "source_url": "https://www.wsh.nhs.uk/CMS-Documents/Patient-leaflets/NutritionandDieteticService/6753-1-Gout-and-diet.pdf"},
    "diabetes": {"source_title": "NHS: Type 2 diabetes - Food and keeping active", "source_url": "https://www.nhs.uk/conditions/type-2-diabetes/food-and-keeping-active/"},
    "hypertension": {"source_title": "NHS: High blood pressure - Prevention", "source_url": "https://www.nhs.uk/conditions/high-blood-pressure-hypertension/prevention/"},
    "stomach": {"source_title": "NIDDK: Eating, Diet, & Nutrition for Gastritis", "source_url": "https://www.niddk.nih.gov/health-information/digestive-diseases/gastritis-gastropathy/eating-diet-nutrition"},
    "fatty_liver": {"source_title": "NIDDK: Eating, Diet, & Nutrition for NAFLD & NASH", "source_url": "https://www.niddk.nih.gov/health-information/liver-disease/nafld-nash/eating-diet-nutrition"},
}


def _guidance(key: str, text: str) -> Dict[str, str]:
    return {"text": text, **SOURCES[key]}


CONTEXTS = {
    "mouth": {
        "label": "Nhiệt miệng / loét miệng",
        "aliases": ("nhiet mieng", "loet mieng", "mouth ulcer", "mouth ulcers"),
        "guidance": [_guidance("mouth", "Khi loét miệng, đồ ăn mềm có thể dễ dùng hơn; hạn chế đồ cay, mặn, chua, thô cứng và đồ uống rất nóng nếu gây kích ứng.")],
    },
    "sleep": {
        "label": "Khó ngủ / mất ngủ",
        "aliases": ("mat ngu", "kho ngu", "insomnia"),
        "guidance": [_guidance("sleep", "Tránh trà, cà phê và rượu trước giờ ngủ; không ăn bữa lớn muộn vào ban đêm. Không có món trong danh mục được chứng minh là điều trị mất ngủ.")],
    },
    "reflux": {
        "label": "Trào ngược",
        "aliases": ("trao nguoc", "trao nguoc da day", "trao nguoc da day thuc quan", "gerd", "acid reflux"),
        "guidance": [_guidance("reflux", "Ở một số người trào ngược, đồ chua, cay, nhiều chất béo, bạc hà, chocolate, rượu và caffeine có thể gây triệu chứng; cần xét yếu tố kích thích riêng của mỗi người.")],
    },
    "cough": {
        "label": "Ho",
        "aliases": ("ho", "cough"),
        "guidance": [_guidance("cough", "Hướng dẫn tự chăm sóc khi ho có nhắc bổ sung dịch. Một từ 'ho' không xác định nguyên nhân và không tạo ra chế độ ăn điều trị riêng.")],
    },
    "fever": {
        "label": "Sốt",
        "aliases": ("sot", "bi sot", "toi bi sot", "sot an gi", "sot nen an gi", "fever"),
        "guidance": [_guidance("fever", "Khi sốt, hướng dẫn ăn uống nhấn mạnh bổ sung dịch; nước và súp là các lựa chọn được nêu. Có thể ăn nếu muốn và không cần ép ăn. Các công thức chỉ hỗ trợ ăn uống thông thường, không có tác dụng hạ sốt hay điều trị nguyên nhân. Không tự áp dụng chế độ của người lớn cho trẻ nhỏ hoặc người có hạn chế dịch.")],
    },
    "mood": {
        "label": "Tâm trạng căng thẳng",
        "aliases": ("stress", "cang thang", "tam trang cang thang"),
        "guidance": [_guidance("balanced", "Gợi ý theo tâm trạng chỉ là lựa chọn ăn uống thông thường. Hướng dẫn nền là ăn đa dạng và cân đối; không gán tác dụng chữa căng thẳng cho món ăn.")],
    },
    "gout": {
        "label": "Bệnh gút / tăng acid uric",
        "aliases": ("gut", "gout", "benh gut", "benh gout", "acid uric", "acid uric cao", "viem khop gut", "tang acid uric"),
        "guidance": [_guidance("gout", "Với gút, tránh nội tạng; hạn chế khẩu phần thịt đỏ và hải sản giàu purin, hạn chế rượu bia. Rau củ, kể cả rau có purin, không cần kiêng chỉ vì purin.")],
    },
    "diabetes": {
        "label": "Tiểu đường / đường huyết cao",
        "aliases": ("tieu duong", "dai thao duong", "duong huyet cao", "diabetes", "duong cao", "benh tieu duong", "benh dai thao duong"),
        "guidance": [_guidance("diabetes", "Người có đái tháo đường cần lưu ý tổng carbohydrate và khẩu phần, hạn chế đường thêm như đường cát, mật ong, sữa đặc và nước ngọt; ăn đa dạng, cân đối.")],
    },
    "hypertension": {
        "label": "Tăng huyết áp",
        "aliases": ("huyet ap cao", "tang huyet ap", "cao huyet ap", "hypertension", "high blood pressure", "benh cao huyet ap", "benh tang huyet ap"),
        "guidance": [_guidance("hypertension", "Người tăng huyết áp cần giảm muối và natri (hạn chế mắm, dưa muối, đồ hộp, thực phẩm chế biến sẵn); tăng cường rau củ quả và kiểm soát lối sống.")],
    },
    "stomach": {
        "label": "Đau dạ dày / viêm loét dạ dày",
        "aliases": ("dau da day", "viem da day", "loet da day", "dau bao tu", "viem loet da day", "gastritis", "benh dau da day", "benh da day"),
        "guidance": [_guidance("stomach", "Khi đau dạ dày, nên chọn thức ăn mềm, dễ tiêu; tránh món cay nóng (ớt, tiêu), chua gắt (chanh, giấm), đồ chiên rán nhiều dầu mỡ và rượu bia, cà phê để tránh kích thích niêm mạc dạ dày.")],
    },
    "fatty_liver": {
        "label": "Gan nhiễm mỡ",
        "aliases": ("gan nhiem mo", "benh gan nhiem mo", "fatty liver", "nafld", "masld"),
        "guidance": [_guidance("fatty_liver", "Hướng dẫn NIDDK về gan nhiễm mỡ không do rượu gợi ý ăn nhiều rau, trái cây và ngũ cốc nguyên hạt; hạn chế đường thêm và chất béo bão hòa, thay bằng chất béo chưa bão hòa; giảm rượu bia. Khẩu phần cần điều chỉnh theo hướng dẫn cá nhân.")],
    },
}
ALIASES = {alias: key for key, context in CONTEXTS.items() for alias in context["aliases"]}


def _avoid(title, reason, source_key, level="limit"):
    return {"title": title, "reason": reason, "level": level, **SOURCES[source_key]}


# These restrictions are authored from the cited guidance, not generated by the
# model or inferred from recipes omitted from the recommendation list.
AVOIDANCE = {
    "fever": [_avoid("Rượu, bia và đồ uống có cồn", "Nên tránh khi sốt vì có thể làm tình trạng mất nước nặng hơn.", "fever_alcohol", "avoid")],
    "mouth": [
        _avoid("Món cay, mặn hoặc chua", "Có thể gây xót và kích ứng vùng loét miệng; hạn chế nếu gây khó chịu.", "mouth"),
        _avoid("Món cứng, giòn hoặc thô ráp", "Có thể cọ xát vùng miệng đang đau; ưu tiên kết cấu mềm hơn.", "mouth"),
        _avoid("Đồ ăn, thức uống quá nóng", "Có thể kích ứng vùng miệng đang tổn thương; để nguội đến nhiệt độ dễ chịu.", "mouth"),
    ],
    "sleep": [
        _avoid("Cà phê, trà và đồ uống chứa caffeine", "NHS khuyên tránh trà, cà phê ít nhất 6 giờ trước khi ngủ.", "sleep"),
        _avoid("Rượu, bia gần giờ ngủ", "NHS khuyên tránh đồ uống có cồn ít nhất 6 giờ trước khi ngủ.", "sleep"),
        _avoid("Bữa ăn lớn muộn vào buổi tối", "Không ăn một bữa lớn sát giờ đi ngủ.", "sleep"),
    ],
    "reflux": [
        _avoid("Món cay, chua hoặc nhiều chất béo", "Có thể kích hoạt triệu chứng ở một số người; hạn chế khi xác định là yếu tố gây khó chịu của bạn.", "reflux"),
        _avoid("Cà phê/caffeine, rượu và chocolate", "Đây là các yếu tố có thể gây triệu chứng ở một số người bị trào ngược, không phải ai cũng cần kiêng giống nhau.", "reflux"),
        _avoid("Bạc hà và món có bạc hà", "Có thể là yếu tố kích thích trào ngược ở một số người; đối chiếu với triệu chứng cá nhân.", "reflux"),
    ],
    "gout": [
        _avoid("Nội tạng động vật", "Gan, cật và tim là nhóm rất giàu purin.", "gout", "avoid"),
        _avoid("Thịt đỏ và hải sản giàu purin", "Hạn chế khẩu phần và tần suất theo hướng dẫn cá nhân.", "gout"),
        _avoid("Rượu, bia", "Hạn chế, đặc biệt trong giai đoạn gút chưa được kiểm soát.", "gout"),
    ],
    "diabetes": [
        _avoid("Đường tinh luyện, mật ong, sữa đặc có đường", "Hạn chế đường thêm và xét tổng carbohydrate theo khẩu phần.", "diabetes"),
        _avoid("Nước ngọt, chè ngọt, bánh kẹo ngọt", "Thường có nhiều đường tự do; hạn chế theo kế hoạch ăn uống cá nhân.", "diabetes"),
    ],
    "hypertension": [
        _avoid("Mắm đậm đặc, dưa muối, cà muối", "Chứa hàm lượng muối/natri rất cao, gây giữ nước và tăng huyết áp.", "hypertension", "avoid"),
        _avoid("Thực phẩm chế biến sẵn (xúc xích, thịt nguội, đồ hộp)", "Nhiều muối natri và chất bảo quản; cần hạn chế khi bị tăng huyết áp.", "hypertension", "avoid"),
    ],
    "stomach": [
        _avoid("Món cay nóng (ớt, tiêu nồng)", "Gây kích ứng trực tiếp niêm mạc dạ dày và tăng cảm giác đau rát.", "stomach", "avoid"),
        _avoid("Món chua gắt (chanh, giấm, me chua, xoài chua)", "Làm tăng độ acid trong dạ dày, gây xót và làm chậm lành vết loét.", "stomach", "avoid"),
        _avoid("Đồ chiên rán nhiều dầu mỡ, rượu bia, cà phê", "Làm chậm tiêu hóa, kích thích tăng tiết acid dịch vị.", "stomach", "avoid"),
    ],
    "fatty_liver": [
        _avoid("Rượu, bia và đồ uống có cồn", "NIDDK khuyên giảm rượu vì rượu có thể làm tổn thương gan thêm.", "fatty_liver"),
        _avoid("Đồ ăn, thức uống nhiều đường thêm", "NIDDK khuyên hạn chế đường đơn, nhất là đồ uống ngọt; xem thành phần và khẩu phần thực tế.", "fatty_liver"),
        _avoid("Món nhiều chất béo bão hòa", "Ưu tiên thay chất béo bão hòa bằng chất béo chưa bão hòa theo hướng dẫn NIDDK; chưa có định lượng chất béo cho từng công thức.", "fatty_liver"),
    ],
}


def _meta(ingredients, allergens=(), gluten_uncertain=False, soft=False, liquid=False, fat_unknown=False, purine_high=False, sugar_high=False, sodium_high=False):
    return {"ingredients": frozenset(_normal(x) for x in ingredients),
            "allergens": frozenset(allergens), "gluten_uncertain": gluten_uncertain,
            "soft": soft, "liquid": liquid, "fat_unknown": fat_unknown,
            "caffeine": False, "alcohol": False, "acidic": False,
            "spicy": False, "mint": False, "fried": False,
            "purine_high": purine_high, "sugar_high": sugar_high, "sodium_high": sodium_high}


# Every listed recipe has been inspected. Unknown/modified recipes are not
# automatically classified from their title or from an LLM's assertion.
METADATA = {
    "fl_steamed_fish": _meta(["Cá diêu hồng", "Gừng", "Nước lọc"], allergens=("fish", "seafood"), soft=True),
    "fl_chicken_vegetables": _meta(["Thịt ức gà", "Bông cải xanh", "Cà rốt", "Nước lọc"], soft=True),
    "fl_tofu_tomato": _meta(["Đậu hũ non", "Cà chua", "Nước lọc"], allergens=("soy",), soft=True),
    "fl_winter_melon_soup": _meta(["Bí xanh", "Nấm rơm", "Nước lọc"], soft=True, liquid=True),
    "fl_steamed_greens": _meta(["Cải thìa", "Nước lọc"], soft=True),
    "fl_oat_vegetable_porridge": _meta(["Yến mạch", "Cà rốt", "Cải bó xôi", "Nước lọc"], gluten_uncertain=True, soft=True),
    "fl_brown_rice_chicken": _meta(["Gạo lứt", "Thịt ức gà", "Cải thìa", "Nước lọc"]),
    "oat_porridge": _meta(["Yến mạch", "Chuối chín", "Nước lọc"], gluten_uncertain=True, soft=True),
    "pumpkin_soup": _meta(["Bí đỏ", "Khoai tây", "Nước lọc"], soft=True),
    "rice_carrot": _meta(["Gạo tẻ", "Cà rốt", "Nước lọc"], soft=True),
    "soft_egg": _meta(["Trứng gà", "Nước ấm"], allergens=("egg",), soft=True),
    "sweet_potato": _meta(["Khoai lang", "Nước lọc"], soft=True),
    "chicken_congee": _meta(["Gạo tẻ", "Thịt ức gà", "Nước lọc"], soft=True),
    "tofu_pumpkin": _meta(["Đậu hũ non", "Bí đỏ", "Nước lọc"], allergens=("soy",), soft=True),
    "warm_water": _meta(["Nước uống"], liquid=True),
    "warm_milk": _meta(["Sữa tươi không đường"], allergens=("milk",), liquid=True, fat_unknown=True),
    "oat_drink": _meta(["Yến mạch", "Nước lọc"], gluten_uncertain=True, liquid=True),
    "cucumber_water": _meta(["Dưa leo", "Nước uống"], liquid=True),
    "warm_soy": _meta(["Sữa đậu nành không đường đã nấu chín"], allergens=("soy",), liquid=True),
    "pear_water": _meta(["Lê", "Nước lọc"], liquid=True),
    "barley_water": _meta(["Lúa mạch khô", "Nước lọc"], allergens=("gluten",), liquid=True),
}

ALLERGEN_NAMES = {"egg": "trứng", "milk": "sữa động vật", "soy": "đậu nành", "gluten": "gluten",
                  "shrimp": "tôm/tép", "crab": "cua/ghẹ", "shellfish": "hải sản có vỏ", "seafood": "hải sản",
                  "fish": "cá", "peanut": "đậu phộng/lạc", "tree_nut": "hạt cây", "sesame": "mè/vừng"}
ALLERGEN_ALIASES = {"trung": "egg", "trung ga": "egg", "trung vit": "egg", "egg": "egg", "eggs": "egg", "sua": "milk", "sua bo": "milk", "sua tuoi": "milk", "sua dong vat": "milk", "milk": "milk", "dau nanh": "soy", "dau hu": "soy", "sua dau nanh": "soy", "soy": "soy", "gluten": "gluten",
                    "tom": "shrimp", "tep": "shrimp", "shrimp": "shrimp", "prawn": "shrimp", "cua": "crab", "ghe": "crab", "crab": "crab", "hai san co vo": "shellfish", "so oc": "shellfish", "hai san": "seafood", "seafood": "seafood", "fish": "fish", "dau phong": "peanut", "lac": "peanut", "peanut": "peanut", "hat dieu": "tree_nut", "hanh nhan": "tree_nut", "oc cho": "tree_nut", "tree nuts": "tree_nut", "vung": "sesame", "sesame": "sesame"}


def _allergy_normal(value):
    # Keep cá/cà and mè/me distinct before folding accents.
    raw = str(value or "").lower()
    raw = re.sub(r"\bcá\b", "fish", raw)
    raw = re.sub(r"\bmè\b", "vung", raw)
    return _normal(raw)

PREFERENCES = {
    "no_added_sugar": (r"\b(?:it\s+duong|giam\s+duong|khong\s+(?:them\s+)?duong|khong\s+ngot|low\s+sugar)\b", "Ít/không thêm đường", "sugar_high"),
    "not_spicy": (r"\b(?:khong\s+cay|it\s+cay|tranh\s+ot)\b", "Không cay", "spicy"),
    "not_fried": (r"\b(?:it\s+dau\s+mo|khong\s+chien|khong\s+ran|it\s+beo)\b", "Ít dầu mỡ", "fried"),
    "low_salt": (r"\b(?:it\s+muoi|it\s+man|khong\s+man|giam\s+muoi)\b", "Ít muối", "sodium_high"),
}


def _query_preferences(query: str):
    remaining = _allergy_normal(query)
    found = []
    for code, (pattern, _label, _tag) in PREFERENCES.items():
        if re.search(pattern, remaining):
            found.append(code)
            remaining = re.sub(pattern, " ", remaining)
    remaining = re.sub(r"\b(?:va|voi|kem)\b\s*$", "", remaining)
    return remaining.strip(" ,;"), found


def _profile_food_allergies(value):
    """Parse food allergy names from a free-text profile; unknown food stays unresolved."""
    if not value:
        return set(), []
    raw = ",".join(str(item) for item in value) if isinstance(value, (list, tuple)) else str(value)
    if _normal(raw) in ("khong", "khong co", "khong di ung", "chua co", "none"):
        return set(), []
    codes, unresolved = set(), []
    for part in re.split(r"[,;\n/]|\s+(?:va|hoac)\s+", _allergy_normal(raw)):
        part = re.sub(r"^(?:(?:di\s+ung|thuc\s+pham|do\s+an|voi|bi)\s+)+", "", part).strip(" .:")
        if not part:
            continue
        code = ALLERGEN_ALIASES.get(part)
        if code:
            codes.add(code)
        elif not re.search(r"\b(?:thuoc|penicillin|aspirin|ibuprofen|khang\s+sinh|paracetamol)\b", part):
            unresolved.append(part[:80])
    return codes, unresolved


def _ingredient_allergens(recipe):
    names = " ; ".join(str(item.get("name", "")) for item in recipe.get("ingredients", []) if isinstance(item, dict))
    plain = _normal(names)
    hits = set()
    patterns = {
        "shrimp": r"tom|tep|shrimp|prawn", "crab": r"cua|ghe|crab",
        "shellfish": r"tom|tep|cua|ghe|muc|ngheu|ngao|hen|hau|so|oc|dau\s+hao|shrimp|prawn|crab|oyster|clam|mussel|squid",
        "peanut": r"dau\s+phong|lac|peanut|groundnut", "tree_nut": r"hat\s+dieu|hanh\s+nhan|oc\s+cho|cashew|almond|walnut",
        "sesame": r"me\s+(?:trang|den)|vung|dau\s+me|sesame|tahini",
    }
    for code, pattern in patterns.items():
        if re.search(r"\b(?:" + pattern + r")\b", plain):
            hits.add(code)
    fish = bool(re.search(r"\bcá\b|\bmắm\b|\bnước\s+mắm\b|\bfish\b|\bfish\s+sauce\b|\bsalmon\b|\btuna\b", names.lower()))
    if re.search(r"\bnước\s+tương\b|\bxì\s+dầu\b|\bsoy\s+sauce\b", names.lower()):
        hits.add("soy")
    if re.search(r"\bmè\b|\bvừng\b", names.lower()):
        hits.add("sesame")
    if fish:
        hits.add("fish")
    if fish or hits & {"shrimp", "crab", "shellfish"} or re.search(r"\bhai\s+san\b", plain):
        hits.add("seafood")
    return hits


def _parse_input(query: str):
    """Recognize exact condition clauses plus explicit allergy/avoid clauses.

    E.g. 'ho; dị ứng sữa' works; 'không mất ngủ' and 'ho và mất ngủ' do not
    become diagnoses. Unrecognized stated allergens block candidate selection.
    """
    normalized = _allergy_normal(query)
    clauses = [part.strip() for part in re.split(r"[;,\+]", normalized) if part.strip()]
    conditions, allergies, unsupported = [], set(), []
    allergy_continuation = False
    for clause in clauses:
        clause = clause.strip(" .!?:")
        markers = list(re.finditer(r"\b(?:di ung|kieng|tranh)\b", clause))
        if len(markers) > 1:
            # Do not guess the scope of mixed positive/negative constraints.
            unsupported.append(clause)
            allergy_continuation = False
            continue
        if markers:
            marker = markers[0]
            prefix = clause[:marker.start()].strip()
            negation = re.search(r"\b(?:khong|chua)(?:\s+(?:he|co|bi|con|can|phai))*$", prefix)
            condition_prefix = prefix[:negation.start()].strip() if negation else prefix
            condition_prefix = re.sub(r"\s*\b(?:va|nhung|con)\s*$", "", condition_prefix).strip()
            # First-person scaffolding is not a condition. Anything more
            # complex is kept unknown rather than substring-diagnosed.
            if condition_prefix not in ("", "toi", "toi bi", "toi co", "minh", "minh bi", "minh co"):
                conditions.append(condition_prefix)
            if negation:
                allergy_continuation = False
                continue
            names = re.sub(r"^voi\s+", "", clause[marker.end():].strip())
        elif allergy_continuation and clause in ALLERGEN_ALIASES:
            names = clause
        else:
            conditions.append(clause)
            allergy_continuation = False
            continue
        if names:
            for name in re.split(r"\s+(?:va|hoac)\s+|/", names):
                allergen = ALLERGEN_ALIASES.get(name.strip())
                if allergen:
                    allergies.add(allergen)
                else:
                    unsupported.append(name.strip())
            allergy_continuation = True
        else:
            unsupported.append("chưa nêu rõ chất cần tránh")
            allergy_continuation = False
    # Recognize multiple condition phrases if joined by conjunctions/commas
    parsed_contexts = []
    for cond in conditions:
        if re.search(r"\b(?:khong|chua)\s+(?:he|co|bi|con|can|phai)*", cond):
            continue
        subparts = re.split(r"(?:\b(?:va|voi|kem|cung)\b|\+)", cond)
        for part in subparts:
            p = part.strip(" .!?:")
            p = re.sub(r"^(?:toi|minh|nguoi\s+benh|benh\s+nhan)?\s*(?:bi|co|mac|bi\s+benh)?\s*", "", p).strip()
            ctx = ALIASES.get(p)
            if ctx and ctx not in parsed_contexts:
                parsed_contexts.append(ctx)

    return parsed_contexts, allergies, unsupported


_DISEASE_KEYWORDS = re.compile(
    r"\b(?:benh|viem|suy|ung\s+thu|hoi\s+chung|khoi\s+u|roi\s+loan|soi|xo\s+gan|gan\s+nhiem\s+mo|than\s+yeu|thieu\s+mau|mo\s+mau|cholesterol|triglyceride|tim\s+mach|dai\s+trang|ruot\s+kich\s+thich|ibs|celiac|coeliac|mang\s+thai|thai\s+ky|ckd|kidney|renal|liver|heart|cancer|anemia|anaemia|pregnan\w*|nhiem\s+trung|tai\s+bien|dot\s+quy|thoai\s+hoa|nhiem\s+doc|xuat\s+huyet|than\s+man|tuy\s+cap|khang\s+thuoc)\b",
    re.IGNORECASE
)


def _is_unmapped_disease(query: str, contexts: List[str]) -> bool:
    norm = _normal(query)
    aliases = []
    for ctx in contexts:
        aliases.extend(CONTEXTS[ctx]["aliases"])
    aliases = sorted(aliases, key=len, reverse=True)
    for alias in aliases:
        norm = re.sub(r"\b" + re.escape(alias) + r"\b", " ", norm)
    # Remove common conjunctions and filler words
    norm = re.sub(r"\b(?:va|voi|kem|cung|\+|toi|bi|mac|co|nguoi|benh\s+nhan|khong|chua|di\s+ung|kieng|tranh)\b", " ", norm)
    norm = " ".join(norm.split())
    return bool(_DISEASE_KEYWORDS.search(norm))


def _condition_exclusion(meta, contexts):
    """First pass: exclude recipe features outside supported condition guidance."""
    for ctx in contexts:
        if ctx == "mouth" and not (meta["soft"] or meta["liquid"]):
            return "Chưa xác minh món có kết cấu mềm hoặc dễ dùng khi miệng khó chịu."
        if ctx == "mouth" and (meta["spicy"] or meta["acidic"]):
            return "Có thành phần cay hoặc chua có thể gây kích ứng khi miệng khó chịu."
        if ctx == "fever" and not (meta["soft"] or meta["liquid"]):
            return "Chưa xác định món có kết cấu mềm hoặc dạng lỏng để ưu tiên khi sốt."
        if ctx == "sleep" and (meta["caffeine"] or meta["alcohol"]):
            return "Có caffeine hoặc rượu, không ưu tiên gần giờ ngủ."
        if ctx == "reflux" and any(meta.get(key) for key in ("acidic", "spicy", "mint", "fried", "caffeine", "alcohol", "fat_unknown")):
            return "Có yếu tố kích thích hoặc chưa rõ hàm lượng béo cần kiểm tra thêm khi trào ngược."
        if ctx == "gout" and (meta.get("purine_high") or meta.get("alcohol")):
            return "Món có nội tạng, thịt đỏ, hải sản giàu purin hoặc cồn nên không được ưu tiên trong gợi ý cho người bị gút."
        if ctx == "diabetes" and meta.get("sugar_high"):
            return "Có đường hoặc chất tạo ngọt thêm, cần kiểm soát đối với người tiểu đường."
        if ctx == "hypertension" and (meta.get("sodium_high") or meta.get("alcohol")):
            return "Có hàm lượng muối/natri cao hoặc cồn, không phù hợp cho người tăng huyết áp."
        if ctx == "stomach" and any(meta.get(key) for key in ("spicy", "acidic", "fried", "alcohol", "caffeine")):
            return "Có vị cay, chua gắt, chiên xào nhiều mỡ hoặc chất kích thích dễ kích ứng dạ dày."
        if ctx == "fatty_liver" and any(meta.get(key) for key in ("alcohol", "sugar_high", "fried", "saturated_fat_source")):
            return "Có cồn, đường thêm, cách chiên/xào hoặc nguyên liệu thường giàu chất béo bão hòa; chưa ưu tiên trong gợi ý tham khảo cho gan nhiễm mỡ."
    return None


def prepare_nutrition_candidates(condition: str, recipes: List[Dict[str, Any]], profile_allergies=None,
                                 fatty_liver_recipes=None) -> Dict[str, Any]:
    """Return copied candidates and attributable rules; never certify suitability.

    Supports single conditions as well as multiple co-morbidities.
    ``recognized`` means the input matches one or more supported context labels.
    """
    query = str(condition or "").strip()
    condition_query, preferences = _query_preferences(query)
    contexts, allergies, unsupported = _parse_input(condition_query)
    if "fatty_liver" in contexts and fatty_liver_recipes:
        # Imported dishes lack reviewed amounts of saturated fat and added
        # sugar. Keep this condition's automatic suggestions to authored recipes.
        recipes = list(fatty_liver_recipes)
    profile_codes, profile_unresolved = _profile_food_allergies(profile_allergies)
    allergies |= profile_codes
    unsupported.extend(profile_unresolved)

    guidance = []
    for ctx in contexts:
        guidance.extend(deepcopy(CONTEXTS[ctx]["guidance"]))

    limitations = ["Chỉ đối chiếu nguyên liệu và đặc tính đã khai báo; chưa tính nhu cầu dinh dưỡng, bệnh nền, thuốc, tuổi hay nguy cơ nhiễm chéo. Các món không được chứng nhận phù hợp về y khoa."]
    if "fatty_liver" in contexts:
        limitations.append("Nguồn NIDDK nói về gan nhiễm mỡ không do rượu; hệ thống chưa xác định nguyên nhân, mức độ bệnh gan hoặc chế độ ăn do bác sĩ chỉ định.")
    if not contexts:
        limitations.append("Chưa có quy tắc cho nội dung này hoặc nội dung còn mơ hồ; không suy ra bệnh từ từ khóa hay tâm trạng.")
    if allergies:
        guidance.append(_guidance("allergy", "Loại món có thành phần bạn nêu cần tránh. Với dị ứng, vẫn cần kiểm tra nhãn thực phẩm và nguy cơ nhiễm chéo khi chuẩn bị món."))
    if "gluten" in allergies:
        guidance.append(_guidance("gluten", "Lúa mạch chứa gluten; yến mạch cần được xác minh không nhiễm gluten. Danh mục hiện chưa có chứng nhận này nên không chọn món yến mạch khi bạn yêu cầu tránh gluten."))
    if unsupported:
        limitations.append("Chưa xác minh được dị ứng/thành phần cần tránh: " + ", ".join(unsupported) + ". Không tự động gợi ý món khi chưa kiểm tra được.")

    avoidance = []
    for ctx in contexts:
        avoidance.extend(deepcopy(AVOIDANCE.get(ctx, [])))

    for allergen in sorted(allergies):
        if allergen == "gluten":
            avoidance.append(_avoid("Thực phẩm chứa gluten và yến mạch chưa xác minh", "Bạn đã yêu cầu tránh gluten. Lúa mạch chứa gluten; yến mạch trong kho chưa được xác minh không nhiễm gluten.", "gluten", "avoid"))
        else:
            avoidance.append(_avoid("Thực phẩm chứa " + ALLERGEN_NAMES[allergen], "Bạn đã nêu cần tránh thành phần này. Kiểm tra nhãn và nguy cơ nhiễm chéo khi chế biến.", "allergy", "avoid"))
    avoidance_note = ("Các mục dưới đây là lưu ý có nguồn hoặc dựa trên thành phần bạn đã nêu cần tránh; không phải danh sách kiêng tuyệt đối cho mọi người."
                      if avoidance else "Chưa có danh sách thực phẩm cần kiêng riêng cho mô tả này. Hệ thống không tự tạo các món cấm khi chưa đủ căn cứ.")

    candidates, excluded = [], []
    for original in recipes:
        recipe = deepcopy(original)
        meta = METADATA.get(str(recipe.get("id", "")))
        if meta is None and recipe.get("imported"):
            meta = _imported_metadata(recipe)
        ingredients = recipe.get("ingredients")
        names = [_normal(item.get("name", "")) for item in ingredients if isinstance(item, dict)] if isinstance(ingredients, list) else []
        verified = bool(meta and names and len(names) == len(ingredients) and frozenset(names) == meta["ingredients"])
        reason = None
        if unsupported:
            reason = "Chưa kiểm tra được chất cần tránh đã nêu."
        elif recipe.get("extraction_warnings"):
            reason = "Công thức gốc hoặc phần trích xuất còn thiếu thông tin; chưa dùng để tự động gợi ý."
        elif meta and meta.get("unsafe_preparation"):
            reason = "Công thức có thành phần/cách chuẩn bị chưa phù hợp để tự động gợi ý trong ứng dụng này."
        elif not verified and (allergies or preferences or any(ctx in ("mouth", "sleep", "reflux", "fever", "gout", "diabetes", "hypertension", "stomach", "fatty_liver") for ctx in contexts)):
            reason = "Chưa có metadata nguyên liệu/đặc tính được rà soát cho công thức này."
        elif verified:
            # Preserve the requested order: condition rules, then profile/query
            # food allergies, then optional eating preferences.
            reason = _condition_exclusion(meta, contexts)
            if not reason:
                hits = allergies & (meta["allergens"] | _ingredient_allergens(recipe))
                if hits:
                    reason = "Có thành phần cần tránh: " + ", ".join(ALLERGEN_NAMES[x] for x in sorted(hits)) + "."
                elif "gluten" in allergies and meta["gluten_uncertain"]:
                    reason = "Chưa xác minh nguyên liệu yến mạch không nhiễm gluten."
            if not reason:
                for code in preferences:
                    if code == "not_fried" and (meta.get("fried") or meta.get("saturated_fat_source")):
                        reason = "Món có cách chiên rán hoặc chứa nguồn béo bão hòa/dầu mỡ; chưa phù hợp với yêu cầu ít dầu mỡ."
                        break
                    elif meta.get(PREFERENCES[code][2]):
                        reason = "Món chưa phù hợp với yêu cầu ăn uống bạn đã nhập."
                        break
        if reason:
            excluded.append({"id": recipe.get("id"), "title": recipe.get("title", ""), "reason": reason})
            continue
        if verified:
            recipe["rule_tags"] = [key for key in ("soft", "liquid") if meta[key]]
            recipe["declared_allergens"] = sorted(meta["allergens"] | _ingredient_allergens(recipe))
            if meta.get("automatic"):
                recipe["metadata_review"] = "automated_text_scan"
                recipe["metadata_note"] = "Nhãn nguyên liệu được quét tự động từ công thức gốc; chưa được xác minh y khoa hoặc xác nhận an toàn dị ứng."
        candidates.append(recipe)

    if "no_added_sugar" in preferences:
        def sugar_key(recipe):
            value = recipe.get("sugar")
            return (value is None or not isinstance(value, (int, float)), float(value) if isinstance(value, (int, float)) else float("inf"))
        candidates.sort(key=sugar_key)
    context_label = " + ".join(CONTEXTS[ctx]["label"] for ctx in contexts) if contexts else query
    return {"recipes": candidates, "guidance": guidance, "excluded": excluded,
            "avoidance": avoidance, "avoidance_note": avoidance_note,
            "recognized": bool(contexts),
            "is_unmapped_disease": _is_unmapped_disease(condition_query, contexts),
            "context_label": context_label,
            "contexts": contexts,
            "allergies": sorted(allergies), "profile_allergies": sorted(profile_codes),
            "profile_allergy_needs_review": bool(profile_unresolved),
            "query_preferences": [PREFERENCES[code][1] for code in preferences],
            "preference_codes": preferences, "limitations": limitations}
