"""
MediMind Production Meal Planner
Kiến trúc 4 tầng chuẩn Production:
  1. Tính BMR / TDEE (Mifflin-St Jeor) & Target Calories thông minh.
  2. Bộ lọc nguyên liệu Python trên danh mục Món Ngon Mỗi Ngày và các công thức chuyên biệt đã chọn lọc.
  3. Chuẩn hóa Calo theo khẩu phần 1 người (chia servings) + phân loại món ăn chuẩn + gán ảnh thật 100%.
  4. AI Ranker (Groq key rotation) xếp hạng thực đơn hài hòa khẩu vị & giải thích lâm sàng (có Python fallback).
"""
import json
import logging
import os
import random
import re
from itertools import product
import unicodedata
from urllib.parse import urlsplit
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("MediMindNutritionPlanner")

BAD_RECIPE_KEYWORDS = (
    "làm sợi", "cơm mẻ", "cách luộc", "cách làm", "cách nấu", "cách chế biến", "bí quyết",
    "nước chấm", "mắm nêm", "tương ớt", "sa tế", "mứt ", "chè ", "bánh bò",
    "kem ", "trà sữa", "bột ", "bánh flan", "rau câu", "sữa chua", "sốt chấm",
    "chuối chiên", "bánh chuối", "bánh bí đỏ", "bánh khoai", "bánh tiêu", "bánh rán",
    "bánh quẩy", "xôi chiên", "bánh kẹp", "snack", "khoai chiên", "khoai tây chiên",
    "lắc mayo", "bánh giò", "caramel", "bánh canh ngọt", "bánh mì gấu", "papparoti",
    "bông lan", "hương quế", "bơ mật ong", "xôi xoài", "xôi mít",
)

SINGLE_DISH_KEYWORDS = (
    "phở", "bún ", "miến ", "hủ tiếu", "mì quảng", "mì xào", "mì nước", "bánh canh", "cháo ",
    "xôi ", "bánh mì", "bánh cuốn", "cơm chiên", "cơm tấm", "cơm trộn", "cơm hến", "cơm gà", "cơm gạo lứt",
)

BREAKFAST_KEYWORDS = (
    "cháo", "phở", "bún", "hủ tiếu", "mì ", "xôi", "bánh mì",
    "bánh cuốn", "yến mạch", "bánh canh",
)

SIDE_KEYWORDS = (
    "luộc", "gỏi ", "nộm ", "salad", "rau ", "cải ", "bí đỏ um",
    "đậu hũ", "bông cải", "mướp", "khổ qua",
)


def _strip_accents(text: str) -> str:
    s = unicodedata.normalize("NFD", str(text or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").strip()


def compute_bmr_tdee(
    height_cm: float,
    weight_kg: float,
    age: int,
    gender: str,
    activity_level: str,
    goal: str = "",
) -> Dict[str, Any]:
    """Công thức Mifflin-St Jeor chuẩn cho người trưởng thành."""
    g = _strip_accents(gender)
    is_male = g in ("nam", "male", "m")
    bmr = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age + (5.0 if is_male else -161.0)

    act = _strip_accents(activity_level)
    if "tinh tai" in act or "it van dong" in act:
        factor = 1.2
    elif "rat nang" in act or "chuyen nghiep" in act:
        factor = 1.9
    elif "nang" in act or "nhieu" in act:
        factor = 1.725
    elif "nhe" in act:
        factor = 1.375
    else:
        factor = 1.55  # Vận động vừa

    tdee = round(bmr * factor)
    bmr_r = round(bmr)

    g_norm = _strip_accents(goal)
    if "giam can" in g_norm:
        recommended = max(1200, tdee - 400)
    elif "tang co" in g_norm or "tang can" in g_norm:
        recommended = tdee + 300
    else:
        recommended = tdee

    return {
        "bmr": bmr_r,
        "tdee": tdee,
        "activity_factor": factor,
        "recommended_calories": recommended,
    }


def parse_servings_count(recipe: Dict[str, Any]) -> int:
    if recipe.get("calories_basis") == "per_serving":
        return 1
    srv = str(recipe.get("servings") or "")
    m = re.search(r"(\d+)", srv)
    if m:
        limit = 100 if recipe.get("calories_basis") == "whole_recipe" else 20
        return max(1, min(limit, int(m.group(1))))
    return 1


def per_person_calories(recipe: Dict[str, Any], is_combo_dish: bool = False) -> int:
    raw = float(recipe.get("calories") or 0)
    if raw <= 0:
        return 110 if is_combo_dish else 260
    n = parse_servings_count(recipe)
    if recipe.get("calories_basis") == "whole_recipe":
        return max(1, round(raw / n)) if n > 1 else round(raw)
    if is_combo_dish:
        # Món trong mâm cơm (chia sẻ cho N người trong bữa gia đình)
        return max(35, round(raw / n)) if n > 1 else round(raw)
    # Món lẻ độc lập: nếu lượng calo > 700 và công thức nấu nhiều người -> chia theo servings
    if raw > 700 and n > 1:
        return max(180, round(raw / n))
    return round(raw)


def _split_allergies(allergies_str: str) -> Tuple[str, List[str]]:
    """Tách dị ứng chuẩn (ALLERGEN_ALIASES) và nguyên liệu cần tránh tự do (thịt heo, thịt bò, ớt...)."""
    from core.nutrition_rules import ALLERGEN_ALIASES

    raw = str(allergies_str or "").strip()
    if not raw:
        return "", []

    known_parts = []
    custom_terms = []
    for chunk in re.split(r"[,;/\n]+|\s+(?:và|va|&)\s+", raw, flags=re.IGNORECASE):
        clean_chunk = re.sub(r"^(?:dị ứng|bị dị ứng|kiêng|tránh|không ăn)\s+", "", chunk.strip(), flags=re.IGNORECASE).strip()
        if not clean_chunk:
            continue
        norm = _strip_accents(clean_chunk)
        # Dùng bộ lọc nguyên liệu chính xác cho hải sản/thịt/cơm/gạo để tránh nutrition_rules.py
        # loại nhầm các món chay/phở/bún không liên quan
        if norm in ALLERGEN_ALIASES and norm not in ("hai san", "seafood", "tom", "cua", "ca"):
            known_parts.append(norm)
        else:
            custom_terms.append(norm)
    return ", ".join(known_parts), custom_terms


_CUSTOM_SYNONYMS = {
    "thit heo": ["heo", "lon", "thit heo", "thit lon", "ba chi", "suon", "gio heo", "chan gio", "thit bam", "thit xay", "cha lua", "gio lua", "ba roi", "than heo", "nac heo"],
    "heo": ["heo", "lon", "thit heo", "thit lon", "ba chi", "suon", "gio heo", "chan gio", "than heo", "nac heo"],
    "thit lon": ["heo", "lon", "thit heo", "thit lon", "ba chi", "suon", "gio heo"],
    "thit bo": ["thit bo", "bo vien", "gau bo", "bap bo", "thit be"],
    "thit ga": ["thit ga", "uc ga", "dui ga", "canh ga", "ga ta"],
    "thit": ["heo", "lon", "thit heo", "thit lon", "thit bo", "thit ga", "thit vit", "thit bam", "thit xay", "ba chi", "suon"],
    "com": ["com", "com trang", "gao", "xoi", "chao", "tam"],
    "gao": ["gao", "com", "xoi", "chao", "bun", "pho", "hu tieu", "banh canh", "banh cuon", "bot gao"],
    "hai san": ["hai san", "tom", "cua", "ghe", "muc", "bach tuoc", "ngheu", "so", "oc", "hau", "bao ngu", "so diep", "tom kho", "mam tom", "mam tep", "cha ca", "thanh cua", "nuoc mam", "ca hoi", "ca thu", "ca ngu", "ca basa", "ca loc", "ca ro", "ca chep", "ca nuc", "ca com", "ca thac lac", "ca dieu hong", "luon"],
    "seafood": ["hai san", "tom", "cua", "ghe", "muc", "ngheu", "so", "oc", "hau", "nuoc mam", "ca hoi", "ca thu", "ca ngu"],
    "tom": ["tom", "tep", "tom kho", "mam tom", "cha tom"],
    "cua": ["cua", "ghe", "thanh cua"],
    "ca": ["ca hoi", "ca thu", "ca ngu", "ca basa", "ca loc", "ca ro", "ca chep", "ca nuc", "ca com", "ca thac lac", "ca dieu hong", "cha ca", "nuoc mam"],
}


def _matches_custom_avoid(recipe: Dict[str, Any], custom_terms: List[str]) -> bool:
    if not custom_terms:
        return False
    ing_list = recipe.get("ingredients") or []
    ing_names = " ".join(
        str(i.get("name") if isinstance(i, dict) else i) for i in ing_list
    )
    haystack = _strip_accents(
        " ".join([
            str(recipe.get("title") or ""),
            ing_names,
            str(recipe.get("original_ingredients") or ""),
        ])
    )
    for term in custom_terms:
        expanded = _CUSTOM_SYNONYMS.get(term, [term])
        for kw in expanded:
            if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", haystack):
                return True
    return False


def _is_clean_meal_recipe(recipe: Dict[str, Any]) -> bool:
    t = (recipe.get("title") or "").lower().strip()
    if not t:
        return False
    return not any(bad in t for bad in BAD_RECIPE_KEYWORDS)


def classify_dish(recipe: Dict[str, Any]) -> str:
    role = (recipe.get("dish_role") or "").lower()
    if role in ("main", "soup", "side", "staple"):
        return role
    t = (recipe.get("title") or "").lower().strip()
    if t.startswith(("canh ", "súp ", "soup ")):
        return "soup"
    if "lẩu" in t or any(k in t for k in SINGLE_DISH_KEYWORDS):
        return "single"
    if any(k in t for k in SIDE_KEYWORDS):
        return "side"
    return "main"


def _is_breakfast_friendly(recipe: Dict[str, Any]) -> bool:
    t = (recipe.get("title") or "").lower().strip()
    if "lẩu" in t:
        return False
    return any(k in t for k in BREAKFAST_KEYWORDS)


def _is_light_snack(recipe: Dict[str, Any]) -> bool:
    title = _strip_accents(recipe.get("title") or "").lower().strip()
    snack_keywords = (
        "an vat", "sua chua", "yaourt", "trai cay", "hoa qua", "goi cuon",
        "salad", "bap luoc", "khoai luoc", "rau cau", "banh flan", "hat rang",
        "soup", "sup", "che dau", "che hat sen",
    )
    return any(keyword in title for keyword in snack_keywords)


def _is_stir_fried(recipe: Dict[str, Any]) -> bool:
    title = _strip_accents(recipe.get("title") or "").lower()
    tags = " ".join(str(tag) for tag in (recipe.get("tags") or recipe.get("categories") or []))
    return "xao" in title or "mon xao" in _strip_accents(tags).lower()


class _ImageResolver:
    """Đảm bảo 100% món ăn & đồ uống đều có ảnh thật đúng loại trong static/images/recipes/."""

    def __init__(self, all_recipes_with_img: List[Dict[str, Any]]):
        self.food_pool = []
        self.drink_pool = []
        for r in all_recipes_with_img:
            img = r.get("image_link") or ""
            if not img.startswith("/static/"):
                continue
            disk_path = img.lstrip("/").replace("/", os.sep)
            if not os.path.exists(disk_path):
                continue
            entry = (r.get("title") or "", _strip_accents(r.get("title") or ""), img)
            if r.get("recipe_type") == "drink":
                self.drink_pool.append(entry)
            else:
                self.food_pool.append(entry)
        self.default_food_img = self.food_pool[0][2] if self.food_pool else "/static/images/recipes/canonical_staple_com_trang.jpg"
        self.default_drink_img = self.drink_pool[0][2] if self.drink_pool else self.default_food_img

    def resolve(self, recipe: Optional[Dict[str, Any]], fallback_title: str = "") -> str:
        if recipe:
            img = recipe.get("image_link") or recipe.get("source_image_url") or ""
            if img.startswith("/static/"):
                disk_path = img.lstrip("/").replace("/", os.sep)
                if os.path.exists(disk_path):
                    return img
            try:
                parsed_image = urlsplit(img)
                if (parsed_image.scheme == "https"
                        and parsed_image.hostname in ("monngonmoingay.com", "www.monngonmoingay.com")
                        and not parsed_image.username and not parsed_image.password):
                    return img
            except ValueError:
                pass
        is_drink = bool(recipe and recipe.get("recipe_type") == "drink")
        title = (recipe.get("title") if recipe else "") or fallback_title
        norm = _strip_accents(title)
        if not is_drink:
            if "gao lut" in norm:
                return "/static/images/recipes/canonical_staple_com_gao_lut.jpg"
            if "com trang" in norm or norm.startswith("com "):
                return "/static/images/recipes/canonical_staple_com_trang.jpg"

        pool = self.drink_pool if is_drink else self.food_pool
        stop = {"mon", "it", "khong", "voi", "cua", "cho", "duong", "pha", "loang", "tuoi", "nhat"}
        tokens = [w for w in norm.split() if len(w) >= 2 and w not in stop]
        best_score = 0
        best_img = ""
        for _, p_norm, p_img in pool:
            score = sum(1 for tk in tokens if tk in p_norm)
            if score > best_score:
                best_score = score
                best_img = p_img
        if best_img and best_score >= 1:
            return best_img

        return self.default_drink_img if is_drink else self.default_food_img


def _ai_rank_meal_plan(
    user_summary: str,
    target_calories: int,
    meals_meta: List[Tuple[str, int, str]],
    single_candidates: List[Dict[str, Any]],
    main_candidates: List[Dict[str, Any]],
    soup_candidates: List[Dict[str, Any]],
    side_candidates: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Dùng Groq (xoay 3 key) chọn món hợp khẩu vị từ tập đã lọc sạch lâm sàng."""
    raw_keys = ",".join([
        os.getenv("GROQ_API_KEYS") or "",
        os.getenv("GROQ_BACKUP_API_KEY") or "",
        os.getenv("GROQ_API_KEY") or "",
    ])
    keys = []
    for k in raw_keys.split(","):
        ks = k.strip()
        if ks and ks not in keys:
            keys.append(ks)
    if not keys:
        return None

    def _fmt(items: List[Dict[str, Any]], is_combo: bool, limit: int) -> str:
        lines = []
        for r in items[:limit]:
            lines.append(f"- {r['id']} | {r['title']} | {per_person_calories(r, is_combo)} kcal")
        return "\n".join(lines)

    slots_desc = ", ".join([f"{name} (~{cal} kcal)" for name, cal, _ in meals_meta])
    prompt = (
        f"Bạn là chuyên gia dinh dưỡng lâm sàng.\n"
        f"Hồ sơ người dùng: {user_summary}. Mục tiêu ngày: {target_calories} kcal.\n"
        f"Các bữa cần chọn món lẻ: {slots_desc}.\n\n"
        f"DANH SÁCH MÓN LẺ AN TOÀN:\n{_fmt(single_candidates, False, 12)}\n\n"
        f"DANH SÁCH MÓN CHÍNH (CHO COMBO):\n{_fmt(main_candidates, True, 10)}\n\n"
        f"DANH SÁCH MÓN CANH (CHO COMBO):\n{_fmt(soup_candidates, True, 8)}\n\n"
        f"DANH SÁCH MÓN RAU/PHỤ (CHO COMBO):\n{_fmt(side_candidates, True, 8)}\n\n"
        "Hãy chọn đúng ID từ các danh sách trên để ghép thực đơn hợp lý (không chọn trùng ID). "
        "Chỉ trả về JSON thuần hợp lệ đúng cấu trúc sau (không dùng dấu ... hay markdown):\n"
        '{"meal_ids": ["id1", "id2", "id3"], "combo1": {"main": "id_main1", "soup": "id_soup1", "side": "id_side1"}, '
        '"combo2": {"main": "id_main2", "soup": "id_soup2", "side": "id_side2"}, "rationale": "1 câu giải thích ngắn bằng tiếng Việt"}'
    )

    try:
        from google.genai import types
        from core.llm_provider import llm_provider
        model = (os.getenv("GROQ_NUTRITION_MODEL") or os.getenv("GROQ_CHAT_MODEL") or "openai/gpt-oss-20b").strip()
        cfg = types.GenerateContentConfig(temperature=0.65, max_output_tokens=600, response_mime_type="application/json")
        for gk in keys:
            try:
                client = llm_provider.get_client(gk, timeout_seconds=10, provider="groq", profile="nutrition")
                resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
                txt = (getattr(resp, "text", None) or "").strip()
                if not txt:
                    continue
                m = re.search(r"\{.*\}", txt, re.DOTALL)
                if m:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, dict) and parsed.get("meal_ids"):
                        return parsed
            except Exception as err:
                logger.warning("AI nutrition ranker key %s... failed: %s", gk[:10], err)
                continue
    except Exception as err:
        logger.warning("AI nutrition ranker unavailable: %s", err)
    return None


def build_production_meal_plan(payload: Dict[str, Any]) -> Dict[str, Any]:
    from core.nutrition_options import (
        FOOD, DRINK, FATTY_LIVER_FOOD, GOUT_FOODS, GOUT_DRINKS, _get_general_options
    )
    from core.nutrition_rules import prepare_nutrition_candidates

    metrics = payload.get("user_metrics") or {}
    conditions = payload.get("medical_conditions") or []
    allergies = str(payload.get("allergies") or "").strip()
    prefs = payload.get("preferences") or {}

    try:
        height = max(80.0, min(250.0, float(metrics.get("height") or 165)))
        weight = max(20.0, min(250.0, float(metrics.get("weight") or 60)))
        age = max(5, min(120, int(metrics.get("age") or 25)))
    except (TypeError, ValueError):
        height, weight, age = 165.0, 60.0, 25

    gender = str(metrics.get("gender") or "Nam").strip()
    activity = str(metrics.get("activity_level") or "Vận động vừa").strip()
    goal = str(metrics.get("goal") or "").strip()

    energy = compute_bmr_tdee(height, weight, age, gender, activity, goal)
    bmr = energy["bmr"]
    tdee = energy["tdee"]

    try:
        meals_per_day = max(2, min(4, int(prefs.get("meals_per_day") or 3)))
    except (TypeError, ValueError):
        meals_per_day = 3

    raw_target = prefs.get("target_calories")
    if raw_target is not None and str(raw_target).strip() != "":
        try:
            target_calories = max(500, min(6000, int(raw_target)))
        except (TypeError, ValueError):
            target_calories = energy["recommended_calories"]
    else:
        target_calories = energy["recommended_calories"]

    calorie_warning = ""
    if target_calories < 1200 or target_calories < round(bmr * 0.85):
        calorie_warning = (
            f"Mức {target_calories} kcal/ngày thấp hơn ngưỡng khuyến nghị so với BMR ({bmr} kcal) và TDEE ({tdee} kcal). "
            "Cần có theo dõi của bác sĩ/chuyên gia dinh dưỡng nếu áp dụng dài ngày."
        )

    clean_conds = [str(c).strip() for c in conditions if str(c).strip() and str(c).strip() != "Không có"]
    cond_query = ", ".join(clean_conds) if clean_conds else "bữa ăn cân bằng dinh dưỡng"

    all_food_raw = _get_general_options(cond_query, "food")["recipes"]
    all_drink_raw = _get_general_options(cond_query, "drink")["recipes"]
    img_resolver = _ImageResolver(all_food_raw + all_drink_raw)

    # Giữ các công thức chuyên biệt đã chọn lọc bên cạnh kho món Món Ngon Mỗi Ngày.
    combined_food = list(all_food_raw)
    existing_ids = {r.get("id") for r in combined_food}
    for extra in FATTY_LIVER_FOOD:
        if extra.get("id") not in existing_ids:
            combined_food.append(dict(extra))
            existing_ids.add(extra.get("id"))

    known_allergies, custom_avoid_terms = _split_allergies(allergies)

    prep_food = prepare_nutrition_candidates(
        cond_query, combined_food, known_allergies,
        fatty_liver_recipes=None, gout_food_recipes=GOUT_FOODS,
    )
    prep_drink = prepare_nutrition_candidates(
        cond_query, all_drink_raw, known_allergies,
        gout_drink_recipes=GOUT_DRINKS,
    )

    if prep_food.get("is_unmapped_disease"):
        return {
            "success": True,
            "status": "clarification_needed",
            "message": f"Bệnh lý '{cond_query}' cần chế độ dinh dưỡng chuyên biệt theo chỉ định trực tiếp của bác sĩ.",
        }

    clean_food_pool = [
        r for r in (prep_food.get("recipes") or [])
        if _is_clean_meal_recipe(r) and not _matches_custom_avoid(r, custom_avoid_terms)
    ]
    if not clean_food_pool:
        clean_food_pool = [
            r for r in (prep_food.get("recipes") or [])
            if not _matches_custom_avoid(r, custom_avoid_terms)
        ]

    if not clean_food_pool:
        return {
            "success": True,
            "status": "clarification_needed",
            "message": (
                f"Không tìm thấy món ăn nào trong kho hiện tại đáp ứng đồng thời '{cond_query}' "
                f"và thành phần cần tránh '{allergies}'. Bạn hãy thử dùng từ khóa dị ứng cụ thể hơn "
                "(ví dụ: 'tôm, cua' hoặc 'thịt bò, thịt heo' thay vì chữ 'thịt' chung chung)."
            ),
        }

    # Gắn ảnh thật cho toàn bộ món ăn & đồ uống
    for r in clean_food_pool:
        r["image_link"] = img_resolver.resolve(r)

    drink_pool = [
        dr for dr in (prep_drink.get("recipes") or [])
        if not any(b in (dr.get("title") or "").lower() for b in ("trà sữa", "kem cheese", "siro", "soda", "trân châu"))
        and not _matches_custom_avoid(dr, custom_avoid_terms)
    ]
    if not drink_pool:
        drink_pool = list(prep_drink.get("recipes") or [])
    for dr in drink_pool:
        dr["image_link"] = img_resolver.resolve(dr)

    # Phân nhóm rõ ràng
    singles = [r for r in clean_food_pool if classify_dish(r) == "single"]
    mains = [r for r in clean_food_pool if classify_dish(r) == "main" and "lẩu" not in (r.get("title") or "").lower()]
    soups = [r for r in clean_food_pool if classify_dish(r) == "soup"]
    sides = [r for r in clean_food_pool if classify_dish(r) == "side"]
    # Nếu ít món lẻ, bổ sung từ mains hợp lý
    single_pool = singles if len(singles) >= meals_per_day else (singles + mains)

    if meals_per_day == 2:
        splits = [("Bữa trưa", 0.50, "lunch"), ("Bữa tối", 0.50, "dinner")]
    elif meals_per_day == 4:
        splits = [("Bữa sáng", 0.25, "breakfast"), ("Bữa trưa", 0.35, "lunch"), ("Bữa phụ chiều", 0.15, "snack"), ("Bữa tối", 0.25, "dinner")]
    else:
        splits = [("Bữa sáng", 0.30, "breakfast"), ("Bữa trưa", 0.40, "lunch"), ("Bữa tối", 0.30, "dinner")]

    pool_by_id = {r["id"]: r for r in clean_food_pool}
    user_summary = f"{gender}, {age} tuổi, {height}cm, {weight}kg, {activity}, mục tiêu {goal or 'cân bằng'}, bệnh: {cond_query}, tránh: {allergies or 'không'}"

    # Sắp xếp gần mức calo rồi xáo trộn nhẹ trong nhóm Top-K để mỗi lần gợi ý luôn đa dạng
    avg_meal_cal = round(target_calories / meals_per_day)
    single_sorted = sorted(single_pool, key=lambda r: abs(per_person_calories(r, False) - avg_meal_cal))
    single_for_ai = list(single_sorted[:18])
    random.shuffle(single_for_ai)

    mains_pool = list(mains[:16])
    soups_pool = list(soups[:12])
    sides_pool = list(sides[:12])
    random.shuffle(mains_pool)
    random.shuffle(soups_pool)
    random.shuffle(sides_pool)

    ai_choice = _ai_rank_meal_plan(
        user_summary, target_calories, splits,
        single_for_ai, mains_pool, soups_pool, sides_pool,
    )

    ai_meal_ids = (ai_choice or {}).get("meal_ids") or []
    single_ids = {r["id"] for r in single_pool}
    used_ids = set()
    meals_out = []
    total_actual = 0

    for idx, (meal_name, ratio, slot) in enumerate(splits):
        meal_target = round(target_calories * ratio)
        eligible = [r for r in (clean_food_pool if slot == "snack" else single_pool) if r["id"] not in used_ids]
        if slot == "breakfast":
            breakfast_options = [r for r in eligible if _is_breakfast_friendly(r)]
            if breakfast_options:
                eligible = breakfast_options
        if slot == "snack":
            low_calorie = [r for r in eligible if per_person_calories(r, False) <= 400]
            if len(low_calorie) >= 5:
                eligible = low_calorie
            ranked = sorted(
                eligible,
                key=lambda r: (not _is_light_snack(r), per_person_calories(r, False), abs(per_person_calories(r, False) - meal_target)),
            )
        else:
            ranked = sorted(eligible, key=lambda r: abs(per_person_calories(r, False) - meal_target))

        chosen = None
        if idx < len(ai_meal_ids):
            candidate = pool_by_id.get(ai_meal_ids[idx])
            if candidate and candidate["id"] in single_ids and candidate["id"] not in used_ids:
                breakfast_ok = slot != "breakfast" or not eligible or _is_breakfast_friendly(candidate)
                snack_ok = slot != "snack" or (
                    _is_light_snack(candidate) and per_person_calories(candidate, False) <= 400
                )
                if breakfast_ok and snack_ok:
                    chosen = candidate

        if chosen and all(r["id"] != chosen["id"] for r in ranked):
            ranked.insert(0, chosen)
        elif chosen:
            ranked.remove(chosen)
            ranked.insert(0, chosen)

        # Return several individually selectable alternatives for each meal slot.
        options = ranked[:5]
        if chosen and chosen not in options:
            options = [chosen] + options[:4]
        if not options:
            fallback = clean_food_pool[:5]
            if slot == "breakfast":
                breakfast_fallback = [r for r in fallback if _is_breakfast_friendly(r)]
                if breakfast_fallback:
                    fallback = breakfast_fallback
            options = fallback
        if not options:
            continue

        used_ids.update(r["id"] for r in options)
        primary = options[0]
        primary_calories = per_person_calories(primary, False)
        total_actual += primary_calories
        items = []
        for recipe in options:
            recipe_calories = per_person_calories(recipe, False)
            servings = parse_servings_count(recipe)
            portion = "1 suất chuẩn" if servings <= 1 else f"1 suất (công thức nguồn {recipe.get('servings')})"
            items.append({
                "food_id": recipe["id"],
                "name": recipe["title"],
                "portion": portion,
                "calories": recipe_calories,
                "recipe": recipe,
            })
        meals_out.append({
            "meal_name": meal_name,
            "meal_time": slot,
            "target_calories": meal_target,
            "calories": primary_calories,
            "items": items,
        })

    # Build one calorie-balanced combo for each lunch or dinner.
    food_combos = []
    is_diabetic_or_cut = any("đái tháo đường" in c.lower() for c in clean_conds) or "giam can" in _strip_accents(goal)
    if is_diabetic_or_cut:
        staple_options = [
            ("Cơm gạo lứt (1 chén vừa)", 150, "/static/images/recipes/canonical_staple_com_gao_lut.jpg", "1 người ăn (1 chén ~130g)"),
            ("Khoai lang luộc (1 củ vừa)", 130, "/static/images/recipes/vifoodrec_2901.jpg", "1 người ăn (~150g)"),
            ("Bắp luộc (1 trái vừa)", 140, "/static/images/recipes/canonical_staple_bap_luoc.jpg", "1 người ăn (~150g)"),
            ("Bánh mì nguyên cám (2 lát)", 160, "/static/images/recipes/canonical_staple_banh_mi_nguyen_cam.jpg", "1 người ăn (~60g)"),
        ]
    else:
        staple_options = [
            ("Cơm trắng (1 chén vừa)", 180, "/static/images/recipes/canonical_staple_com_trang.jpg", "1 người ăn (1 chén ~130g)"),
            ("Cơm gạo lứt (1 chén vừa)", 150, "/static/images/recipes/canonical_staple_com_gao_lut.jpg", "1 người ăn (1 chén ~130g)"),
            ("Bún tươi (1 phần vừa)", 165, "/static/images/recipes/canonical_staple_bun_tuoi_plain.jpg", "1 người ăn (~150g)"),
            ("Khoai lang luộc (1 củ vừa)", 130, "/static/images/recipes/vifoodrec_2901.jpg", "1 người ăn (~150g)"),
            ("Bánh mì nguyên cám (2 lát)", 160, "/static/images/recipes/canonical_staple_banh_mi_nguyen_cam.jpg", "1 người ăn (~60g)"),
        ]
    filtered_staples = [
        st for st in staple_options
        if not _matches_custom_avoid({"title": st[0], "ingredients": [{"name": st[0]}]}, custom_avoid_terms)
    ]
    if filtered_staples:
        staple_options = filtered_staples
    chosen_staples = random.sample(staple_options, k=min(2, len(staple_options)))

    role_pools = {"main": mains, "soup": soups, "side": sides}
    used_combo_ids = set()

    def select_calorie_balanced_combo(meal_target: int):
        # Each combo has one staple, one main dish, and either soup or a side.
        # A looser 150% ceiling allows variety while preventing extreme totals.
        calorie_ceiling = round(meal_target * 1.5)
        role_groups = (("main", "soup"), ("main", "side"))
        best_overall = None
        for roles in role_groups:
            pools = []
            for role in roles:
                share = meal_target * (0.48 if role == "main" else 0.24)
                candidates = [
                    recipe for recipe in role_pools[role]
                    if recipe.get("id") not in used_combo_ids
                    and 0 < per_person_calories(recipe, True) <= calorie_ceiling
                ]
                candidates.sort(key=lambda recipe: abs(per_person_calories(recipe, True) - share))
                pools.append(candidates[:36])
            if any(not pool for pool in pools):
                continue

            for recipes in product(*pools):
                if len({recipe.get("id") for recipe in recipes}) != len(recipes):
                    continue
                if "soup" in roles and _is_stir_fried(recipes[0]):
                    continue
                for staple in staple_options:
                    total = staple[1] + sum(per_person_calories(recipe, True) for recipe in recipes)
                    if total > calorie_ceiling:
                        continue
                    score = (abs(meal_target - total), total > meal_target, 0 if "soup" in roles else 1, total)
                    if best_overall is None or score < best_overall[0]:
                        best_overall = (score, staple, roles, recipes)
        if not best_overall:
            return None
        score, staple, roles, recipes = best_overall
        return staple, list(zip(roles, recipes)), score[3]

    for meal_name, ratio, meal_slot in splits:
        if meal_slot in ("breakfast", "snack"):
            continue
        meal_target = round(target_calories * ratio)
        selected = select_calorie_balanced_combo(meal_target)
        if not selected:
            continue
        (st_title, st_cal, st_img, st_note), chosen_parts, combo_cal = selected
        dishes_norm = [{
            "id": f"staple_{meal_slot}",
            "title": st_title,
            "dish_role_label": "Tinh bột ăn kèm",
            "calories": st_cal,
            "servings_note": st_note,
            "image_link": st_img,
            "recipe": None,
        }]
        for role, rec in chosen_parts:
            role_label = {"main": "Món chính", "soup": "Món canh", "side": "Món rau / phụ"}[role]
            calories = per_person_calories(rec, True)
            used_combo_ids.add(rec["id"])
            dishes_norm.append({
                "id": rec["id"],
                "title": rec["title"],
                "dish_role_label": role_label,
                "calories": calories,
                "servings_note": f"1 suất chia từ {rec.get('servings') or '1 người'}",
                "image_link": rec["image_link"],
                "recipe": rec,
            })
        slot_label = {"lunch": "Bữa trưa", "dinner": "Bữa tối"}.get(meal_slot, meal_name)
        food_combos.append({
            "title": f"Combo {slot_label} (Đủ món cân bằng)",
            "meal_time": meal_slot,
            "target_calories": meal_target,
            "total_calories": combo_cal,
            "note": f"Combo 3 món, ước tính cho 1 người và cân đối linh hoạt quanh mục tiêu {meal_target} kcal.",
            "dishes": dishes_norm,
        })

    return {
        "success": True,
        "status": "success",
        "ai_used": ai_choice is not None,
        "ai_rationale": (ai_choice or {}).get("rationale") or (
            f"Thực đơn được lọc cho hồ sơ ({bmr} kcal BMR, {tdee} kcal TDEE) từ kho công thức dinh dưỡng."
        ),
        "daily_plan": {
            "target_calories": target_calories,
            "recommended_calories": energy["recommended_calories"],
            "total_calories": total_actual,
            "bmr": bmr,
            "tdee": tdee,
            "calorie_warning": calorie_warning,
            "conditions": clean_conds,
            "allergies": allergies,
            "meals": meals_out,
        },
        "food_combos": food_combos,
        "avoidance": prep_food.get("avoidance") or [],
        "sources": prep_food.get("guidance") or [],
    }
