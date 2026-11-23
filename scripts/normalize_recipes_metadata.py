"""Offline Data Pipeline: Data Engineering & Metadata Normalization for ViFoodRec (Phase 1.1).

Produces data/recipes/vifoodrec/recipes_metadata.json with:
- Strict 9-role Meal Classification (primary_role, secondary_roles, eligible_combo_roles)
- Per-Allergen Assessment for Big 11 allergens (status, evidence, uncertainty_reason)
- Robust false-positive and false-negative prevention
- Deterministic and reproducible execution
"""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "recipes" / "vifoodrec"
RAW_RECIPES_PATH = DATA_DIR / "recipes.json"
FOODS_TAGS_PATH = DATA_DIR / "foods_tags.json"
OUTPUT_METADATA_PATH = DATA_DIR / "recipes_metadata.json"

METADATA_VERSION = "1.1.0"
DATASET_VERSION = "vifoodrec_clean_paclic2024"

# -----------------------------------------------------------------------------
# 1. TEXT NORMALIZATION UTILS
# -----------------------------------------------------------------------------

def strip_accents(text: str) -> str:
    """Normalize Vietnamese unicode string and strip tone marks."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFD", str(text).lower())
    without_marks = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return without_marks.replace("đ", "d")

def clean_text(text: str) -> str:
    """Normalize whitespace and lowercased string."""
    return " ".join(str(text or "").strip().lower().split())

# -----------------------------------------------------------------------------
# 2. ALLERGEN TAXONOMY & PER-ALLERGEN ASSESSMENT RULES
# -----------------------------------------------------------------------------

BIG_11_ALLERGENS = [
    "shrimp", "crab", "squid_octopus", "fish", "mollusk",
    "peanut", "sesame", "egg", "cow_milk", "soy", "wheat_gluten"
]

ALLERGEN_DETECTION_RULES = {
    "shrimp": {
        "positive": [
            (r"\btôm\s+(sú|thẻ|đất|đồng|bạc|khô|càng|tươi|hùm)\b", "Tôm các loại"),
            (r"\bmắm\s+(tôm|tép)\b", "Mắm tôm / mắm tép"),
            (r"\btôm\b", "Tôm"),
            (r"\btép(?!\s+tỏi)\b", "Tép (loại trừ tép tỏi)")
        ]
    },
    "crab": {
        "positive": [
            (r"\bcua\s+(đồng|biển|gạch|thịt|lột)\b", "Cua các loại"),
            (r"\bghẹ\b", "Ghẹ"),
            (r"\briêu\s+cua\b", "Riêu cua"),
            (r"\bcua\b", "Cua")
        ]
    },
    "squid_octopus": {
        "positive": [
            (r"\bmực\s+(ống|lá|trứng|khô|nang|sữa|sim)\b", "Mực"),
            (r"\bbạch\s+tuộc\b", "Bạch tuộc"),
            (r"\bmực\b", "Mực")
        ]
    },
    "fish": {
        "positive": [
            (r"\bnước\s+mắm\b", "Nước mắm"),
            (r"\bmắm\s+(cá|nêm|ruốc|chẽm|sặc|linh|lóc)\b", "Mắm cá / mắm nêm"),
            (r"\bchả\s+cá\b", "Chả cá"),
            (r"\bcá\s+(lóc|hồi|thu|ngừ|ba\s*sa|diêu\s*hồng|bớp|chép|mè|trắm|nục|quả|trê|kèo|linh|chim|cam|trích|mòi|bống|cơm|đuối|chẽm)\b", "Cá"),
            (r"\bcá\b", "Cá")
        ]
    },
    "mollusk": {
        "positive": [
            (r"\bdầu\s+hào\b", "Dầu hào (chiết xuất hàu)"),
            (r"\bhàu(\s+sữa)?\b", "Hàu"),
            (r"\bnghêu\b|\bngao\b", "Nghêu / ngao"),
            (r"\bsò\s+(huyết|lông|điệp|méo)\b", "Sò"),
            (r"\bhến\b", "Hến"),
            (r"\bchem\s+chép\b", "Chem chép"),
            (r"\bbào\s+ngư\b", "Bào ngư"),
            (r"\bvẹm\b", "Vẹm xanh"),
            (r"(?<!xoắn\s)(?<!bánh\s)\bốc\s+(hương|bươu|mít|móng\s+tay|len|mỡ|gạo|nhồi|lát)\b", "Ốc"),
            (r"(?<!xoắn\s)(?<!bánh\s)\bốc\b(?!\s*vít)", "Ốc (loại trừ bánh ốc / xoắn ốc)")
        ]
    },
    "peanut": {
        "positive": [
            (r"\bđậu\s+phộng\b|\blạc\b", "Đậu phộng / lạc"),
            (r"\bbơ\s+đậu\s+phộng\b", "Bơ đậu phộng"),
            (r"\bdầu\s+phộng\b", "Dầu phộng")
        ]
    },
    "sesame": {
        "positive": [
            (r"\bdầu\s+mè\b|\bdầu\s+vừng\b", "Dầu mè"),
            (r"\b(hạt\s+)?mè\s+(trắng|đen|rang)\b", "Mè (vừng)"),
            (r"(?<!cá\s)\bmè\b", "Mè (loại trừ cá mè)"),
            (r"\bvừng\b", "Vừng"),
            (r"\bchí\s+mà\s+phù\b", "Chí mà phù (chè mè đen)")
        ]
    },
    "egg": {
        "positive": [
            (r"\btrứng\s+(gà|vịt|cút|muối|bắc\s+thảo)\b", "Trứng gia cầm"),
            (r"\b(lòng\s+đỏ|lòng\s+trắng)\s+trứng\b", "Lòng đỏ / trắng trứng"),
            (r"\b(sốt\s+)?mayonnaise\b", "Sốt Mayonnaise (chứa lòng đỏ trứng)"),
            (r"\btrứng\b", "Trứng")
        ]
    },
    "cow_milk": {
        "positive": [
            (r"\bsữa\s+(tươi|đặc|bò|bột|chua|thanh\s+trùng|tiệt\s+trùng)\b", "Sữa bò"),
            (r"\bphô\s*mai\b|\bpho\s*mát\b|\bcheese\b", "Phô mai"),
            (r"\bbơ\s+(lạt|động\s+vật|anchor|thơm)\b", "Bơ sữa bò"),
            (r"\b(whipping\s+cream|kem\s+tươi|váng\s+sữa)\b", "Kem tươi / váng sữa"),
            (r"\btrà\s+sữa\b", "Trà sữa (chế phẩm từ sữa)"),
            (r"\byaourt\b|\byogurt\b", "Sữa chua")
        ]
    },
    "soy": {
        "positive": [
            (r"\bđậu\s+(nành|phụ|hũ)\b|\btàu\s+hũ(\s+ky)?\b", "Đậu nành / đậu phụ"),
            (r"\bnước\s+tương\b|\bxì\s+dầu\b", "Nước tương / xì dầu"),
            (r"\btương\s+(hột|bần|cự\s+đà|đen)\b", "Tương đậu nành"),
            (r"\bchao\b", "Chao đậu"),
            (r"\bváng\s+đậu\b", "Váng đậu")
        ]
    },
    "wheat_gluten": {
        "positive": [
            (r"\bbột\s+m[iì]\b", "Bột mì"),
            (r"\bbánh\s+m[iì]\b", "Bánh mì"),
            (r"\bmì\s+căn\b", "Mì căn (gluten lúa mì nguyên chất)"),
            (r"\bbột\s+chiên\s+(giòn|xù)\b", "Bột chiên giòn / chiên xù (nền bột mì)"),
            (r"\bmì\s+(trứng|tôm|vàng|gói)\b", "Mì sợi bột mì"),
            (r"\b(hoành\s+thánh|sủi\s+cảo)\b", "Vỏ hoành thánh (bột mì)")
        ]
    }
}

# Ambiguous ingredient indicators that create cross-contamination or hidden allergen uncertainty
PREMIXED_UNCERTAINTY_TRIGGERS = [
    (r"\bdầu\s+hào\b", ["wheat_gluten", "soy"], "Dầu hào thương mại thường dùng tinh bột lúa mì làm chất tạo sệt và đạm đậu nành thủy phân"),
    (r"\b(nước\s+tương|xì\s+dầu)\b", ["wheat_gluten"], "Nước tương truyền thống và công nghiệp thường lên men cùng lúa mì"),
    (r"\b(hạt\s+nêm|bột\s+nêm|viên\s+súp|gia\s+vị\s+nêm\s+sẵn)\b", ["soy", "fish", "wheat_gluten"], "Hạt nêm và gia vị tổng hợp có thể chứa chiết xuất nấm men, đạm đậu nành, cá hoặc maltodextrin từ lúa mì"),
    (r"\b(xúc\s+xích|chả\s+lụa|lạp\s+xưởng|bò\s+viên|cá\s+viên)\b", ["soy", "wheat_gluten", "egg"], "Thực phẩm chế biến sẵn thường trộn bột mì, đạm đậu nành hoặc lòng trắng trứng làm chất kết dính"),
    (r"\b(nước\s+sốt\s+tổng\s+hợp|sốt\s+chấm|xốt\s+pha\s+sẵn)\b", ["peanut", "sesame", "soy"], "Sốt pha sẵn có nguy cơ chứa bơ đậu phộng, dầu mè hoặc tương đậu ẩn")
]

# -----------------------------------------------------------------------------
# 3. INGREDIENT NORMALIZATION SLUGS
# -----------------------------------------------------------------------------

INGREDIENT_NORMALIZATION_MAP = [
    (r"\b(thịt lợn|thịt heo|thịt ba chỉ|sườn heo|sườn non|nạc dăm|giò heo|chân giò|thịt băm|tai heo)\b", "pork", "meat"),
    (r"\b(thịt bò|bắp bò|thăn bò|nạm bò|gầu bò|bò xay|bò bít tết)\b", "beef", "meat"),
    (r"\b(thịt bê)\b", "veal", "meat"),
    (r"\b(xúc xích|lạp xưởng|thịt nguội|dăm bông|bacon|thịt hun khói)\b", "sausage", "meat"),
    (r"\b(thịt gà|ức gà|(?<!nấm\s)đùi gà|cánh gà|chân gà|lòng gà|(?<!trứng\s)(?:gà ta|gà ác|gà thả vườn|gà chọi|gà tre|gà mía))\b", "chicken", "poultry"),
    (r"\b(thịt vịt|đùi vịt|lòng vịt)\b", "duck", "poultry"),
    (r"\b(thịt chim|chim cút)\b", "quail", "poultry"),
    (r"\b(thịt dê)\b", "goat", "meat"),
    (r"\b(lươn)\b", "eel", "fish"),
    (r"\b(ếch)\b", "frog", "meat"),
    (r"\b(tôm sú|tôm thẻ|tôm đất|tôm bạc|tôm đồng|tôm khô|tép)\b", "shrimp", "seafood"),
    (r"\b(cua đồng|cua biển|ghẹ|thịt cua)\b", "crab", "seafood"),
    (r"\b(mực ống|mực lá|mực khô|mực trứng|bạch tuộc)\b", "squid_octopus", "seafood"),
    (r"\b(cá lóc|cá quả|cá chuối)\b", "snakehead_fish", "fish"),
    (r"\b(cá hồi)\b", "salmon", "fish"),
    (r"\b(cá diêu hồng|cá rô phi)\b", "tilapia", "fish"),
    (r"\b(cá basa|cá ba sa|cá tra)\b", "catfish", "fish"),
    (r"\b(cá thu)\b", "mackerel", "fish"),
    (r"\b(cá ngừ)\b", "tuna", "fish"),
    (r"\b(cá chép)\b", "carp", "fish"),
    (r"\b(nghêu|ngao)\b", "clam", "seafood"),
    (r"\b(sò huyết|sò lông|sò điệp)\b", "scallop_cockle", "seafood"),
    (r"\b(ốc bươu|ốc hương|ốc móng tay|ốc len)\b", "snail", "seafood"),
    (r"\b(hàu sữa|hàu)\b", "oyster", "seafood"),
    (r"\b(hến)\b", "mussel", "seafood"),
    (r"\b(rau muống)\b", "morning_glory", "vegetable"),
    (r"\b(cải bó xôi|rau bina|rau chân vịt)\b", "spinach", "vegetable"),
    (r"\b(cải ngọt|cải thìa|cải bẹ xanh|cải thảo|cải xanh|bắp cải|cải rổ)\b", "cabbage_greens", "vegetable"),
    (r"\b(bí xanh|bí đao)\b", "winter_melon", "vegetable"),
    (r"\b(bí đỏ|bí ngô)\b", "pumpkin", "vegetable"),
    (r"\b(khổ qua|mướp đắng)\b", "bitter_melon", "vegetable"),
    (r"\b(mướp hương|mướp)\b", "sponge_gourd", "vegetable"),
    (r"\b(bầu|quả bầu)\b", "gourd", "vegetable"),
    (r"\b(cà chua)\b", "tomato", "vegetable"),
    (r"\b(dưa leo|dưa chuột)\b", "cucumber", "vegetable"),
    (r"\b(cà tím)\b", "eggplant", "vegetable"),
    (r"\b(cà rốt)\b", "carrot", "vegetable"),
    (r"\b(củ cải trắng|củ cải)\b", "radish", "vegetable"),
    (r"\b(su su)\b", "chayote", "vegetable"),
    (r"\b(su hào)\b", "kohlrabi", "vegetable"),
    (r"\b(bông cải xanh|súp lơ xanh|súp lơ)\b", "broccoli", "vegetable"),
    (r"\b(đậu bắp)\b", "okra", "vegetable"),
    (r"\b(nấm rơm|nấm đùi gà|nấm kim châm|nấm hương|nấm bào ngư|mộc nhĩ|nấm mèo)\b", "mushroom", "vegetable"),
    (r"\b(măng tươi|măng khô|măng chua)\b", "bamboo_shoot", "vegetable"),
    (r"\b(giá đỗ|giá)\b", "bean_sprout", "vegetable"),
    (r"\b(ngó sen|củ sen)\b", "lotus_root", "vegetable"),
    (r"\b(đậu phụ|đậu hũ|tàu hũ)\b", "tofu", "legume"),
    (r"\b(đậu phộng|lạc)\b", "peanut", "nut"),
    (r"\b(hạt sen)\b", "lotus_seed", "seed"),
    (r"\b(mè|vừng)\b", "sesame", "seed"),
    (r"\b(gạo tẻ|gạo trắng|cơm trắng)\b", "rice", "grain"),
    (r"\b(gạo lứt|gạo lức)\b", "brown_rice", "grain"),
    (r"\b(gạo nếp|nếp)\b", "glutinous_rice", "grain"),
    (r"\b(bún tươi|bún khô|bún gạo)\b", "rice_vermicelli", "grain"),
    (r"\b(bánh phở|phở tươi|phở khô)\b", "rice_noodle", "grain"),
    (r"\b(bánh canh)\b", "tapioca_noodle", "grain"),
    (r"\b(miến dong|miến)\b", "glass_noodle", "grain"),
    (r"\b(mì trứng|mì sợi|mì vàng)\b", "egg_noodle", "grain"),
    (r"\b(khoai lang)\b", "sweet_potato", "root_tuber"),
    (r"\b(khoai tây)\b", "potato", "root_tuber"),
    (r"\b(khoai môn|khoai sọ)\b", "taro", "root_tuber"),
    (r"\b(bắp(?!\s+(?:cải|chuối))|ngô)\b", "corn", "grain"),
    (r"\b(trứng gà)\b", "chicken_egg", "egg"),
    (r"\b(trứng vịt)\b", "duck_egg", "egg"),
    (r"\b(trứng cút)\b", "quail_egg", "egg"),
    (r"\b(sữa tươi|sữa đặc)\b", "cow_milk", "dairy"),
    (r"\b(phô mai|pho mát)\b", "cheese", "dairy"),
    (r"\b(bơ lạt|bơ thực vật)\b", "butter", "dairy"),
    (r"\b(hành lá|hành tây|hành tím)\b", "onion", "spice_herb"),
    (r"\b(tỏi)\b", "garlic", "spice_herb"),
    (r"\b(gừng)\b", "ginger", "spice_herb"),
    (r"\b(sả)\b", "lemongrass", "spice_herb"),
    (r"\b(ớt|ớt chuông)\b", "chili", "spice_herb"),
    (r"\b(tiêu|hạt tiêu)\b", "black_pepper", "spice_herb"),
    (r"\b(nước mắm(?!\s+chay))\b", "fish_sauce", "spice_herb"),
    (r"\b(nước tương|xì dầu)\b", "soy_sauce", "spice_herb")
]

COOKING_METHOD_PATTERNS = {
    "steaming": [r"\bhấp(?!\s+dẫn)\b", r"(?<!ớt\s)(?<!tiêu\s)\bchưng(?!\s+(?:hửng|cất))\b", r"\bđồ\s+(?:xôi|chõ)\b"],
    "boiling": [r"\bluộc\b", r"\bninh\b", r"\bhầm\b", r"\bchần\b"],
    "braising": [r"\bkho\b", r"\brim\b", r"\bram\b", r"\bcà\s+ri\b", r"\bragu\b", r"\bsốt\s+vang\b"],
    "stir_frying": [r"\bxào\b", r"\bcháy cạnh\b", r"\báp chảo\b", r"\bquay\s+chảo\b"],
    "deep_frying": [r"\bchiên\b", r"\brán\b", r"\bchao dầu\b", r"\bxối mỡ\b"],
    "grilling": [r"\bnướng\b", r"\bquay(?!\s+chảo)\b", r"\bđút lò\b"],
    "soup_cooking": [r"\bnấu canh\b", r"\bnấu lẩu\b", r"\blẩu\b", r"\bnấu súp\b"],
    "raw_fresh": [r"\bgỏi\b", r"\bnộm\b", r"\bsalad\b", r"\b(?:gỏi\s+cuốn|bánh\s+tráng\s+cuốn|nem\s+cuốn|phở\s+cuốn)\b", r"\b(?:rau|bún|mì|miến|nộm|gỏi)\s+trộn\b"]
}

TITLE_PRIMARY_PATTERNS = [
    (r"\b(chả\s+lụa|há\s+cảo|xíu\s+mại|bánh\s+bao|bánh\s+bèo|bánh\s+nậm|bánh\s+giò|hấp)\b", "steaming"),
    (r"\b(chiên|rán|xối\s+mỡ|chao\s+dầu)\b", "deep_frying"),
    (r"\b(xào|áp\s+chảo)\b", "stir_frying"),
    (r"\b(nướng|quay(?!\s+chảo)|đút\s+lò)\b", "grilling"),
    (r"\b(kho|rim|ram|cà\s+ri|ragu|sốt\s+vang)\b", "braising"),
    (r"\b(canh|lẩu|súp)\b", "soup_cooking"),
    (r"\b(cơm\s+gà(?!\s+(?:xối\s+mỡ|chiên|rán|nướng))|luộc|hầm|ninh|tiềm)\b", "boiling"),
    (r"\b(gỏi|nộm|salad)\b", "raw_fresh"),
]

# -----------------------------------------------------------------------------
# 4. CLASSIFICATION REVIEWS & COMBO ELIGIBILITY
# -----------------------------------------------------------------------------

# Standalone patterns (Complete One-Dish Meals)
STANDALONE_PATTERNS = [
    r"\bphở\b", r"\bbún\b", r"\bmiến\b", r"\bhủ t[ií]ếu\b", r"\bbánh canh\b",
    r"\bcháo\b", r"\bmì\b", r"\bmỳ\b", r"\bnui\b", r"\bhoành thánh\b",
    r"\bsủi cảo\b", r"\bbánh cuốn\b", r"\bbánh ướt\b",
    r"\bcơm\s+(chiên|rang|tấm|thập cẩm|gà|bò|niêu|hến|lam|sườn)\b",
    r"\b(bún chả|bún riêu|bún bò|bún cá|bún mọc|bún đậu)\b",
    r"\blẩu\b"  # Hotpot is a standalone communal meal
]

MANUAL_OVERRIDES = {
    "vifoodrec_2901": {
        "primary_role": "staple", "secondary_roles": [],
        "eligible_combo_roles": [],
        "reason": "Khoai lang luộc đã có bản khẩu phần tham chiếu trong danh mục tinh bột"
    },
    # Non-standalone despite matching keywords:
    "vifoodrec_1949": {
        "primary_role": "staple", "secondary_roles": [],
        "eligible_combo_roles": ["staple"],
        "reason": "Bún Tươi Xào Nấm Bông Hẹ (phần tinh bột xào)"
    },
    "vifoodrec_1375": {
        "primary_role": "snack", "secondary_roles": [],
        "eligible_combo_roles": ["snack"],
        "reason": "Cơm Nguội Bọc Trứng Cút Chiên Xù (món ăn chơi)"
    },
    "vifoodrec_1461": {
        "primary_role": "main_dish", "secondary_roles": [],
        "eligible_combo_roles": ["main_dish"],
        "reason": "Xúc Xích Chiên Bơ Khoai Tây Nghiền (món đạm chính)"
    },
    "vifoodrec_1753": {
        "primary_role": "snack", "secondary_roles": [],
        "eligible_combo_roles": ["snack"],
        "reason": "Cốm Từ Cơm Nguội"
    },
    # Tricky meat-in-vegetable dishes
    "vifoodrec_23": {
        "primary_role": "main_dish", "secondary_roles": ["vegetable"],
        "eligible_combo_roles": ["main_dish"],
        "reason": "Thịt bê xào cải rổ: món xào thịt đạm chính, không thế chỗ rau thanh trong combo"
    },
    "vifoodrec_4": {
        "primary_role": "main_dish", "secondary_roles": ["vegetable", "snack"],
        "eligible_combo_roles": ["main_dish"],
        "reason": "Gỏi ngó sen tôm thịt: lượng đạm tôm thịt cao, đóng vai trò món chính hoặc khai vị"
    }
}

def classify_recipe(recipe: Dict[str, Any], historical_tags: List[str]) -> Tuple[str, List[str], List[str], float, str, bool]:
    """Classify recipe into:
    - primary_role: one of the 9 roles
    - secondary_roles: list of secondary roles
    - eligible_combo_roles: which roles this dish can serve as in a 4-part combo (MUST NOT be standalone)
    - confidence: float
    - source: str
    - review_required: bool
    """
    rec_id = recipe.get("id", "")
    title = clean_text(recipe.get("title", ""))
    recipe_type = recipe.get("recipe_type", "food")
    cats = [clean_text(c) for c in recipe.get("categories", [])]
    cats_str = " ".join(cats)

    # 1. Manual Overrides
    if rec_id in MANUAL_OVERRIDES:
        o = MANUAL_OVERRIDES[rec_id]
        return o["primary_role"], o["secondary_roles"], o["eligible_combo_roles"], 1.0, f"manual_override: {o['reason']}", False

    # 2. Deceptive keywords replacement
    cleaned_title = re.sub(r"\bcải\s+bó\s+xôi\b", "rau_cai_bina", title, flags=re.I)
    cleaned_title = re.sub(r"\bmì\s+căn\b", "dam_seitan", cleaned_title, flags=re.I)
    cleaned_lower = cleaned_title.lower()

    # Savory check: dishes with savory meat/fish/cooking verbs are NOT beverages or desserts
    has_savory_marker = any(re.search(pat, cleaned_lower) for pat in [
        r"\bthịt\b", r"\bcá\b", r"\btôm\b", r"\bmực\b", r"\bsườn\b", r"\bgà\b",
        r"\bvịt\b", r"\bbò\b", r"\bchả\b", r"\bkho\b", r"\bchiên\b", r"\brán\b",
        r"\bxào\b", r"\bhấp\b", r"\bquay\b", r"\bnướng\b", r"\brim\b", r"\blẩu\b"
    ])

    # 3. Beverages
    bev_keywords = [r"\btrà\b", r"\bsinh tố\b", r"\bnước ép\b", r"\bcà phê\b", r"\bcocktail\b", r"\bsmoothie\b", r"\bnước uống\b", r"\btrà sữa\b"]
    if recipe_type == "drink" or "đồ uống" in cats_str or "đồ uống" in historical_tags:
        if not has_savory_marker:
            return "beverage", [], [], 0.98, "beverage_classification", False
    if any(re.search(pat, cleaned_lower) for pat in bev_keywords) and not has_savory_marker:
        return "beverage", [], [], 0.95, "title_beverage", False

    # 4. Desserts
    dessert_patterns = [
        r"\bchè\b", r"\bpudding\b", r"\bcaramel\b", r"\bthạch rau câu\b",
        r"\bkem\b", r"\bbánh ngọt\b", r"\bsâm bổ lượng\b", r"\bbánh chuối\b",
        r"\bbánh bò\b", r"\byaourt\b", r"\bsữa chua hoa quả\b"
    ]
    if (any(re.search(pat, cleaned_lower) for pat in dessert_patterns) or "món tráng miệng" in historical_tags) and not has_savory_marker:
        if re.search(r"\bchè\s+(xanh|vằng|dây)\b", cleaned_lower):
            return "beverage", [], [], 0.95, "tea_beverage", False
        return "dessert", [], [], 0.95, "dessert_keywords", False

    # 5. Standalone Dishes (CRITICAL: Phở, Bún, Miến, Bánh canh, Hủ tiếu, Cháo, Lẩu, Cơm chiên/tấm)
    # A standalone dish MUST NEVER have eligible_combo_roles for soup or main_dish!
    is_standalone = False
    for pat in STANDALONE_PATTERNS:
        if re.search(pat, cleaned_lower):
            is_standalone = True
            break

    # Also check Bánh mì
    if re.search(r"\bbánh\s+m[iì]\b", cleaned_lower):
        if any(k in cleaned_lower for k in ["kẹp", "thịt", "chảo", "xíu mại", "pate"]):
            return "standalone", [], [], 0.95, "banh_mi_standalone", False
        else:
            return "snack", [], ["snack"], 0.88, "banh_mi_snack", False

    if is_standalone:
        sec = ["soup"] if any(k in cleaned_lower for k in ["bánh canh", "cháo", "phở", "bún", "hủ tiếu", "lẩu"]) else []
        # CRITICAL: eligible_combo_roles is EMPTY! Standalone dishes are NEVER inserted as combo components!
        return "standalone", sec, [], 0.96, "standalone_dish_pattern", False

    # 6. Soup Dishes (Món canh ăn cơm)
    if re.search(r"\bcanh\b", cleaned_lower) or re.search(r"\bsúp\b", cleaned_lower):
        return "soup", [], ["soup"], 0.95, "soup_pattern", False

    # 7. Vegetable Dishes & Meat-Vegetable Hybrids
    veg_words = [
        r"\brau\b", r"\bcải\b", r"\bluộc\b", r"\bbí xanh\b", r"\bbí đao\b", r"\bmướp\b",
        r"\bbầu\b", r"\bđậu bắp\b", r"\bbông cải\b", r"\bsúp lơ\b", r"\bsu su\b",
        r"\bsu hào\b", r"\bcủ cải\b", r"\bnấm\b", r"\bdưa chua\b", r"\bdưa góp\b",
        r"\bkim chi\b", r"\bsalad\b", r"\bnộm\b", r"\bgỏi\b", r"\brau muống\b",
        r"\brau dền\b", r"\bmồng tơi\b", r"\bngót\b", r"\bxà lách\b", r"\bdưa leo\b"
    ]
    has_veg = any(re.search(pat, cleaned_lower) for pat in veg_words)
    heavy_meat_words = [
        r"\bthịt\b", r"\bbò\b", r"\bbe\b", r"\bsườn\b", r"\bcá\b", r"\bgà\b",
        r"\bvịt\b", r"\btôm\b", r"\bmực\b", r"\bba chỉ\b", r"\bthịt băm\b"
    ]
    has_meat = any(re.search(pat, cleaned_lower) for pat in heavy_meat_words)

    if has_veg and has_meat:
        # Meat-forward stir-fry or salad: e.g. "Rau muống xào bò", "Thịt bò xào cần tây", "Bông cải xào thịt"
        # In a meal combo, this fills the MAIN PROTEIN role (main_dish), NOT the pure vegetable role!
        if re.search(r"\bxào\s+(bò|thịt|mực|tôm|tim|cật|gà)\b", cleaned_lower) or re.search(r"\b(thịt|bò|bê|gà|mực|tôm)\s+xào\b", cleaned_lower):
            return "main_dish", ["vegetable"], ["main_dish"], 0.90, "meat_forward_vegetable_stirfry", False
        # If gỏi / nộm with prominent meat/seafood (e.g. Gỏi gà bắp cải, Gỏi tôm thịt)
        if any(re.search(pat, cleaned_lower) for pat in [r"\bgỏi\s+gà\b", r"\bgỏi\s+bò\b", r"\bgỏi\s+tôm\b", r"\bgỏi\s+sứa\b"]):
            return "main_dish", ["vegetable", "snack"], ["main_dish"], 0.88, "protein_rich_salad", False
        # General vegetable with meat seasoning
        if any(cleaned_lower.startswith(p) for p in ["rau ", "cải ", "bông cải ", "mướp ", "bí ", "bầu ", "su su ", "đậu bắp "]):
            return "vegetable", ["main_dish"], ["vegetable"], 0.85, "vegetable_with_light_protein", False

    if has_veg and not has_meat:
        return "vegetable", [], ["vegetable"], 0.95, "pure_vegetable_dish", False

    # 8. Main Dish (Món đạm chính / Món mặn ăn cơm)
    main_protein_words = [
        r"\bkho\b", r"\brim\b", r"\bchao\b", r"\bchiên\b", r"\brán\b", r"\bnướng\b",
        r"\bxào\b", r"\bhấp\b", r"\bsốt\b", r"\bthịt\b", r"\bcá\b", r"\btôm\b",
        r"\bsườn\b", r"\bgà\b", r"\bbò\b", r"\bvịt\b", r"\btrứng\b", r"\bchả\b",
        r"\bmực\b", r"\bếch\b", r"\blươn\b", r"\bcua\b", r"\bghẹ\b", r"\bốc\b"
    ]
    if any(re.search(pat, cleaned_lower) for pat in main_protein_words):
        return "main_dish", [], ["main_dish"], 0.90, "protein_main_dish_pattern", False

    # 9. Snack / Ăn chơi
    if "Món ăn chơi / Món cuốn" in historical_tags or any(re.search(pat, cleaned_lower) for pat in [r"\băn vặt\b", r"\bnem rán\b", r"\bchả giò\b", r"\bkhô gà\b", r"\bbánh tráng\b"]):
        return "snack", ["main_dish"], ["snack"], 0.85, "snack_appetizer", False

    # 10. Fallback based on historical tags
    if "Món canh" in historical_tags:
        return "soup", [], ["soup"], 0.78, "historical_tag_fallback", False
    if "Món rau" in historical_tags:
        return "vegetable", [], ["vegetable"], 0.78, "historical_tag_fallback", False
    if "Món mặn" in historical_tags:
        return "main_dish", [], ["main_dish"], 0.78, "historical_tag_fallback", False

    # Other dishes are NOT eligible for combo roles!
    return "other", [], [], 0.50, "unclassified_fallback", True

# -----------------------------------------------------------------------------
# 5. PER-ALLERGEN ASSESSMENT ENGINE
# -----------------------------------------------------------------------------

def evaluate_recipe_allergens(recipe: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], List[str], List[str], str]:
    """Evaluate each of the Big 11 allergens independently.
    
    Returns:
        (allergen_assessments, allergen_tags, allergen_unknown_tags, global_status)
    """
    raw_ings = recipe.get("ingredients", [])
    title = recipe.get("title", "")
    orig_ings = str(recipe.get("original_ingredients", "") or "")

    full_text_parts = [title, orig_ings]
    for item in raw_ings:
        if isinstance(item, dict):
            full_text_parts.append(str(item.get("name", "")))
        elif isinstance(item, str):
            full_text_parts.append(item)
    full_text = " ".join(full_text_parts).lower()

    assessments = {}
    known_present_allergens = []
    unknown_allergens = []

    # 1. Direct positive evidence detection
    for allergen, rule in ALLERGEN_DETECTION_RULES.items():
        found_evidence = None
        for pat, desc in rule["positive"]:
            m = re.search(pat, full_text)
            if m:
                found_evidence = m.group(0)
                break

        if found_evidence:
            assessments[allergen] = {
                "status": "known_present",
                "evidence": found_evidence,
                "uncertainty_reason": None
            }
            known_present_allergens.append(allergen)
        else:
            assessments[allergen] = {
                "status": "assessed_not_detected",
                "evidence": None,
                "uncertainty_reason": None
            }

    # 2. Premixed / Compound ingredient uncertainty triggers
    for trig_pat, affected_allergens, reason in PREMIXED_UNCERTAINTY_TRIGGERS:
        if re.search(trig_pat, full_text):
            for a in affected_allergens:
                # Only elevate to unknown if not already confirmed known_present
                if assessments[a]["status"] == "assessed_not_detected":
                    assessments[a]["status"] = "unknown"
                    assessments[a]["uncertainty_reason"] = reason
                    if a not in unknown_allergens:
                        unknown_allergens.append(a)

    # 3. Overall allergen status
    if not raw_ings or len(full_text.strip()) < 10:
        global_status = "unknown"
        for a in BIG_11_ALLERGENS:
            if assessments[a]["status"] == "assessed_not_detected":
                assessments[a]["status"] = "unknown"
                assessments[a]["uncertainty_reason"] = "Thiếu danh sách nguyên liệu chi tiết"
                if a not in unknown_allergens:
                    unknown_allergens.append(a)
    elif known_present_allergens:
        global_status = "known_present"
    elif unknown_allergens:
        global_status = "unknown"
    else:
        global_status = "assessed_not_detected"

    return (
        assessments,
        sorted(known_present_allergens),
        sorted(unknown_allergens),
        global_status
    )

def extract_normalized_ingredients_and_groups(recipe: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Extract normalized ingredient slugs and groups."""
    raw_ings = recipe.get("ingredients", [])
    title = recipe.get("title", "")
    orig_ings = str(recipe.get("original_ingredients", "") or "")

    full_text_parts = [title, orig_ings]
    for item in raw_ings:
        if isinstance(item, dict):
            full_text_parts.append(str(item.get("name", "")))
        elif isinstance(item, str):
            full_text_parts.append(item)
    full_text = " ".join(full_text_parts).lower()

    normalized_ingredients: Set[str] = set()
    ingredient_groups: Set[str] = set()

    for pat, slug, group in INGREDIENT_NORMALIZATION_MAP:
        if re.search(pat, full_text):
            normalized_ingredients.add(slug)
            ingredient_groups.add(group)

    return sorted(list(normalized_ingredients)), sorted(list(ingredient_groups))

def extract_cooking_methods(recipe: Dict[str, Any]) -> Tuple[Optional[str], List[str], List[str]]:
    """Detect cooking methods from title, original_cooking_method, and steps.
    
    Returns:
        (primary_cooking_method, secondary_cooking_methods, all_cooking_methods)
    """
    title = recipe.get("title", "").lower()
    method_field = str(recipe.get("original_cooking_method", "") or "").lower()
    steps_list = recipe.get("steps", [])
    steps_text = " ".join(steps_list).lower()
    full_text = f"{title} {method_field} {steps_text}"

    detected: Set[str] = set()
    for method_name, pats in COOKING_METHOD_PATTERNS.items():
        if any(re.search(p, full_text) for p in pats):
            detected.add(method_name)

    # Specific check: if title explicitly states a dish is 'trộn' (e.g. bún trộn, gỏi trộn)
    if re.search(r"\btrộn\b", title) and not any(k in title for k in ("bột", "nhân", "sốt")):
        detected.add("raw_fresh")

    # 1. Primary method determination from title
    primary: Optional[str] = None
    for pat, method in TITLE_PRIMARY_PATTERNS:
        if re.search(pat, title):
            primary = method
            break

    # 2. If title didn't specify, check last/finishing cooking steps vs intermediate steps
    if not primary and detected:
        for step in reversed(steps_list):
            s_low = step.lower()
            for m in ["stir_frying", "braising", "deep_frying", "grilling", "steaming", "boiling", "soup_cooking", "raw_fresh"]:
                if m in detected and any(re.search(p, s_low) for p in COOKING_METHOD_PATTERNS[m]):
                    primary = m
                    break
            if primary:
                break

    if not primary and detected:
        primary = sorted(list(detected))[0]

    secondary = sorted(list(detected - {primary})) if primary else []
    return primary, secondary, sorted(list(detected))

def parse_servings_number(servings_str: Optional[str]) -> Optional[float]:
    """Parse servings text into numeric float."""
    if not servings_str:
        return None
    s = str(servings_str).lower().strip()
    m_range = re.search(r"(\d+)\s*[-–]\s*(\d+)", s)
    if m_range:
        return (float(m_range.group(1)) + float(m_range.group(2))) / 2.0
    m_single = re.search(r"(\d+(?:\.\d+)?)", s)
    if m_single:
        return float(m_single.group(1))
    return None

def process_single_recipe_metadata(recipe: Dict[str, Any], historical_tags: List[str]) -> Dict[str, Any]:
    """Process single recipe into Phase 1.1 compliant metadata structure."""
    rec_id = recipe.get("id")
    primary_role, sec_roles, combo_roles, conf, source, review_req = classify_recipe(recipe, historical_tags)
    allergen_assessments, allergen_tags, allergen_unknowns, allergen_status = evaluate_recipe_allergens(recipe)
    norm_ings, ing_groups = extract_normalized_ingredients_and_groups(recipe)
    pri_method, sec_methods, cooking_methods = extract_cooking_methods(recipe)

    # Nutrition assessment
    servings_num = parse_servings_number(recipe.get("servings"))
    cals = recipe.get("calories")
    p = recipe.get("protein")
    f_val = recipe.get("fat")
    s = recipe.get("sugar")

    cal_per_serving = round(cals / servings_num, 1) if (cals and servings_num and servings_num > 0) else None

    macro_reliable = True
    if cals and p is not None and f_val is not None and s is not None:
        min_est = 4 * p + 9 * f_val + 4 * s
        if min_est > cals * 1.15:
            macro_reliable = False

    return {
        "id": rec_id,
        "title": recipe.get("title", ""),
        "meal_role": primary_role,  # backwards-compatible alias
        "primary_role": primary_role,
        "secondary_roles": sec_roles,
        "eligible_combo_roles": combo_roles,
        "classification_confidence": conf,
        "classification_source": source,
        "review_required": review_req,
        "normalized_ingredients": norm_ings,
        "ingredient_groups": ing_groups,
        "allergen_tags": allergen_tags,
        "allergen_unknown_tags": allergen_unknowns,
        "allergen_status": allergen_status,
        "allergen_assessments": allergen_assessments,
        "primary_cooking_method": pri_method,
        "secondary_cooking_methods": sec_methods,
        "cooking_methods": cooking_methods,
        "servings_numeric": servings_num,
        "calories_per_serving": cal_per_serving,
        "macro_consistency": macro_reliable,
        "nutrition_verified": False,
        "nutrition_basis": "source_dish_record_whole_recipe",
        "has_carbohydrate_data": False,
        "metadata_version": METADATA_VERSION,
        "dataset_version": DATASET_VERSION
    }

def run_normalization() -> Dict[str, Any]:
    """Main execution function to normalize metadata for the whole dataset."""
    print("=" * 80)
    print("PHASE 1.1: RUNNING METADATA QUALITY ASSURANCE & NORMALIZATION")
    print("=" * 80)

    if not RAW_RECIPES_PATH.exists():
        raise FileNotFoundError(f"Raw recipes dataset not found at: {RAW_RECIPES_PATH}")

    with open(RAW_RECIPES_PATH, "r", encoding="utf-8") as f:
        recipes = json.load(f)

    historical_tags_by_id = {}
    if FOODS_TAGS_PATH.exists():
        with open(FOODS_TAGS_PATH, "r", encoding="utf-8") as f:
            tags_data = json.load(f)
            for item in tags_data:
                historical_tags_by_id[item.get("id")] = item.get("tag", [])

    print(f"Loaded {len(recipes)} raw recipes from {RAW_RECIPES_PATH}")

    metadata_list = []
    role_dist = {}
    combo_eligibility_dist = {}
    allergen_status_dist = {}
    review_req_count = 0

    for r in recipes:
        r_id = r.get("id")
        h_tags = historical_tags_by_id.get(r_id, [])
        meta = process_single_recipe_metadata(r, h_tags)
        metadata_list.append(meta)

        role = meta["primary_role"]
        role_dist[role] = role_dist.get(role, 0) + 1

        for c_role in meta["eligible_combo_roles"]:
            combo_eligibility_dist[c_role] = combo_eligibility_dist.get(c_role, 0) + 1

        status = meta["allergen_status"]
        allergen_status_dist[status] = allergen_status_dist.get(status, 0) + 1

        if meta["review_required"]:
            review_req_count += 1

    # Write output to sidecar file
    OUTPUT_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata_list, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated metadata sidecar with {len(metadata_list)} items.")
    print(f"Saved to: {OUTPUT_METADATA_PATH}")

    print("\n[Primary Meal Role Distribution]")
    for r, count in sorted(role_dist.items(), key=lambda x: x[1], reverse=True):
        pct = (count / len(metadata_list)) * 100
        print(f"  - {r:<15}: {count:>5} ({pct:>5.1f}%)")

    print("\n[Combo Role Eligibility Counts]")
    for c_role, count in sorted(combo_eligibility_dist.items(), key=lambda x: x[1], reverse=True):
        print(f"  - Can serve as {c_role:<12}: {count:>5} recipes")

    standalone_in_combo = sum(1 for m in metadata_list if m["primary_role"] == "standalone" and m["eligible_combo_roles"])
    print(f"  - Standalone dishes appearing in combo roles: {standalone_in_combo} (Must be 0!)")

    print("\n[Allergen Status Distribution]")
    for s, count in sorted(allergen_status_dist.items(), key=lambda x: x[1], reverse=True):
        pct = (count / len(metadata_list)) * 100
        print(f"  - {s:<25}: {count:>5} ({pct:>5.1f}%)")

    print(f"\nItems flagged review_required: {review_req_count} ({(review_req_count/len(metadata_list))*100:.1f}%)")

    return {
        "total_processed": len(metadata_list),
        "role_distribution": role_dist,
        "combo_eligibility_distribution": combo_eligibility_dist,
        "allergen_status_distribution": allergen_status_dist,
        "review_required_count": review_req_count
    }

if __name__ == "__main__":
    run_normalization()
