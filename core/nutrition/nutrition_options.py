"""Gợi ý công thức để người dùng tự chọn, không thay thế tư vấn dinh dưỡng."""
from copy import deepcopy
from datetime import datetime, date
import math
import re
from typing import Any, Dict, List, Optional
import unicodedata
from core.nutrition.recipe_catalog import imported_recipes, catalog_stats, retrieve_candidates, title_key


def _get_general_options(condition: str, recipe_type: str = "food") -> Dict[str, Any]:
    """Danh mục món ăn từ Món Ngon Mỗi Ngày; tình trạng chỉ bổ sung ghi chú, không lọc món."""
    query = condition.strip().replace("_", " ")
    normalized = " ".join("".join(c for c in unicodedata.normalize("NFD", query.lower())
                                  if unicodedata.category(c) != "Mn").replace("đ", "d").split())
    # Only use explicit note labels. Substring matching can misread negation or
    # multi-condition input (e.g. "không mất ngủ") as a confirmed condition.
    note_context = {"nhiet mieng": "nhiet_mieng", "loet mieng": "nhiet_mieng",
                    "mat ngu": "mat_ngu", "kho ngu": "mat_ngu"}.get(normalized)
    recipes = imported_recipes("food")
    notice = f'Danh sách tham khảo chung. Chưa xác nhận mức độ phù hợp của từng món với tình trạng “{query}”.'
    if note_context == "nhiet_mieng":
        notice = "Danh sách tham khảo chung, có thêm lưu ý khi miệng khó chịu. Các món chưa được lọc riêng theo tình trạng này."
        for recipe in recipes:
            recipe["avoid"].append("Hạn chế đồ cay, chua hoặc quá nóng nếu gây rát miệng.")
    elif note_context == "mat_ngu":
        notice = "Danh sách tham khảo chung, có thêm lưu ý về caffeine và giờ ngủ. Các món chưa được lọc riêng theo tình trạng này."
        for recipe in recipes:
            recipe["avoid"].append("Hạn chế cà phê, trà đặc và đồ uống chứa caffeine gần giờ ngủ.")
    return {"condition_name": query,
            "matched": False,
            "recommendation_scope": "general_catalog",
            "has_condition_notes": note_context is not None,
            "selection_explanation": "Các công thức món ăn được soạn sẵn theo danh mục thực phẩm. "
                "Tên tình trạng chưa được dùng để lọc hay xếp hạng từng món. Với nhiệt miệng và mất ngủ, "
                "hệ thống chỉ bổ sung lưu ý chung. Bước này không dùng AI, RAG hoặc tra cứu MedlinePlus; "
                "chưa có nguồn y khoa liên kết và xác minh cho từng công thức.",
            "notice": notice, "recipe_type": "food", "recipes": recipes}


_MEAL_LABELS = {
    "breakfast": "Bữa sáng",
    "lunch": "Bữa trưa",
    "dinner": "Bữa tối",
    "snack": "Bữa phụ"
}

_ROLE_LABELS = {
    "main": "Món chính",
    "soup": "Món canh",
    "side": "Món rau / phụ",
    "staple": "Món tinh bột / cháo",
}


def _resolve_meal_slot(condition: str = "", now_hour: Optional[int] = None) -> tuple[str, str]:
    """Resolve meal tag from explicit query intent first, otherwise real system hour."""
    norm = " ".join(
        "".join(c for c in unicodedata.normalize("NFD", str(condition or "").lower())
                if unicodedata.category(c) != "Mn").replace("đ", "d").split()
    )
    if re.search(r"\b(?:bua\s+sang|an\s+sang|buoi\s+sang|sang\s+nay|breakfast)\b", norm):
        return "breakfast", "Bữa sáng"
    if re.search(r"\b(?:bua\s+trua|an\s+trua|buoi\s+trua|trua\s+nay|lunch)\b", norm):
        return "lunch", "Bữa trưa"
    if re.search(r"\b(?:bua\s+toi|an\s+toi|buoi\s+toi|toi\s+nay|dinner)\b", norm):
        return "dinner", "Bữa tối"
    if re.search(r"\b(?:bua\s+phu|bua\s+xe|an\s+nhe|truoc\s+ngu|snack)\b", norm):
        return "snack", "Bữa phụ"

    hour = datetime.now().hour if now_hour is None else int(now_hour) % 24
    if 5 <= hour < 11:
        return "breakfast", "Bữa sáng"
    if 11 <= hour < 15:
        return "lunch", "Bữa trưa"
    if 15 <= hour < 17:
        return "snack", "Bữa phụ"
    if 17 <= hour < 22:
        return "dinner", "Bữa tối"
    return "snack", "Bữa nhẹ"


def _ingredient_snippet(recipe: Dict[str, Any], max_items: int = 3) -> str:
    names = []
    for item in (recipe.get("ingredients") or []):
        if isinstance(item, dict) and item.get("name"):
            cleaned = re.sub(r"\s+\d+(?:[.,/]\d+)?\s*(?:gr?|kg|ml|lít|trái|quả|củ|muỗng.*|nhánh|bông|túi|gói|bịch|hộp|hũ|chén|ly|lát|bó|cọng|cây|cái|tép).*$", "", str(item["name"]).strip(), flags=re.IGNORECASE)
            cleaned = re.sub(r"^\d+(?:[.,/]\d+)?\s*(?:gr?|kg|ml|lít|trái|quả|hủ|củ|tép|nhánh)\s+", "", cleaned.strip(), flags=re.IGNORECASE)
            if cleaned and cleaned.lower() not in ("nước lọc", "nước ấm", "nước nóng", "nước uống", "nước", "đá viên"):
                names.append(cleaned)
        if len(names) >= max_items:
            break
    return ", ".join(names) if names else str(recipe.get("title") or "nguyên liệu thanh đạm").strip()


def _clinical_fallback_reason(recipe: Dict[str, Any], condition: str, contexts: Optional[List[str]] = None) -> str:
    """Produce a clinical disease-specific explanation using actual recipe ingredients."""
    ctxs = list(contexts or [])
    ing_text = _ingredient_snippet(recipe)
    if "gout" in ctxs:
        return f"Sử dụng {ing_text} ít purin, đã loại trừ thịt gà, thịt bò, nội tạng, hải sản và các loại đậu để hỗ trợ kiểm soát acid uric an toàn cho người bệnh Gút."
    if "diabetes" in ctxs:
        return f"Kết hợp {ing_text} hạn chế đường tinh luyện, giàu chất xơ tự nhiên giúp kiểm soát đường huyết ổn định hơn."
    if "hypertension" in ctxs:
        return f"Sử dụng {ing_text} ít natri, hạn chế muối mặn nhằm giảm áp lực thành mạch và hỗ trợ kiểm soát huyết áp."
    if "stomach" in ctxs or "reflux" in ctxs:
        return f"Chế biến dịu nhẹ từ {ing_text}, tránh vị cay chua và dầu mỡ kích thích, giúp bảo vệ niêm mạc dạ dày."
    if "fatty_liver" in ctxs:
        return f"Dùng {ing_text} ít chất béo bão hòa và hạn chế đường đơn, hỗ trợ giảm tích tụ mỡ tại gan."
    if "mouth" in ctxs:
        return f"Kết cấu dịu từ {ing_text}, ít gia vị cay nóng hoặc chua gắt để tránh làm rát vùng niêm mạc miệng."
    if "fever" in ctxs:
        return f"Cung cấp nước và dưỡng chất nhẹ từ {ing_text}, giúp bù dịch và dễ hấp thu khi đang sốt."
    if "sleep" in ctxs:
        return f"Lựa chọn thanh nhẹ từ {ing_text} không chứa caffeine, phù hợp cho bữa tối êm bụng và hỗ trợ giấc ngủ."
    if "cough" in ctxs:
        return f"Thành phần {ing_text} giúp bổ sung dịch ấm/mát dịu cổ họng mà không gây kích ứng đường thở."
    return f"Món kết hợp {ing_text} chế biến cân bằng, đã sàng lọc an toàn theo yêu cầu “{condition}”."


_GENERIC_REASON_RE = re.compile(
    r"món có kết cấu mềm và đã qua bộ lọc|đã qua bộ lọc nguyên liệu theo mô tả|món canh súp/dạng nước dễ dùng|công thức đã qua bộ lọc nguyên liệu|món có kết cấu mềm trong kho|một công thức qua bộ lọc nguyên liệu",
    re.IGNORECASE,
)


def _enrich_recipe(recipe: Dict[str, Any], condition: str, contexts: Optional[List[str]] = None) -> None:
    """Add display labels and enforce clinical, non-generic explanation."""
    from core.nutrition.recipe_catalog import classify_dish_role, classify_meal_times, is_standalone_one_dish

    role = recipe.get("dish_role")
    if role not in _ROLE_LABELS:
        role = classify_dish_role(recipe)
        recipe["dish_role"] = role
    if is_standalone_one_dish(recipe):
        recipe["dish_role_label"] = "Món ăn trọn vị"
    else:
        recipe["dish_role_label"] = _ROLE_LABELS.get(role, "Món ăn")
    possible_meals = classify_meal_times(recipe, role)
    recipe["possible_meals"] = possible_meals
    meal_time = recipe.get("meal_time")
    if meal_time not in _MEAL_LABELS:
        meal_time = possible_meals[0] if possible_meals else _resolve_meal_slot(condition)[0]
        recipe["meal_time"] = meal_time
    recipe["meal_label"] = _MEAL_LABELS.get(meal_time, "Bữa ăn")

    # Nutrient-specific claims from prose or a model are not verified by the
    # source table. The numeric source values remain available separately.
    recipe["key_nutrients"] = ""
    reason = str(recipe.get("recommendation_reason") or "").strip()
    if not reason or reason.lower() == "none" or _GENERIC_REASON_RE.search(reason):
        reason = _clinical_fallback_reason(recipe, condition, contexts)
    recipe["recommendation_reason"] = reason
    if recipe.get("purine_warning"):
        existing_caution = str(recipe.get("ai_caution") or "").strip()
        warn_text = str(recipe["purine_warning"]).strip()
        if warn_text and warn_text not in existing_caution:
            recipe["ai_caution"] = f"{existing_caution} {warn_text}".strip() if existing_caution else warn_text


def _is_valid_main(r: Dict) -> bool:
    if not r:
        return False
    title = str(r.get("title", "")).lower()
    if any(k in title for k in [
        "canh ", "canh:", "súp", "sup", "cháo", "chao", "lẩu", "bún", "phở", "hủ tiếu",
        "mì ", "miến", "bánh canh", "nui", "chè ", "trà ", "sữa ", "bánh mì baguette",
        "nước mắm", "gia vị", "nước chấm", "bánh tro", "bánh ít", "bánh ngọt", "bánh rán",
        "bánh xếp", "bánh chưng", "bánh tét", "dưa món", "ngô chiên", "khoai tây chiên",
        "ruốc", "mứt", "caramel", "pudding"
    ]):
        return False
    from core.nutrition.recipe_catalog import classify_dish_role
    role = r.get("dish_role") or classify_dish_role(r)
    if role == "main":
        return True
    tags = _extract_main_ingredient_tags(r)
    return bool(tags & {"đậu", "nấm", "trứng", "bò", "heo", "gà", "vịt", "cá", "tôm", "mực", "cua", "ốc", "ếch"})


def _is_valid_soup(r: Dict) -> bool:
    if not r:
        return False
    title = str(r.get("title", "")).lower()
    t = re.sub(r"bánh\s+canh", "", title)
    from core.nutrition.recipe_catalog import classify_dish_role
    role = r.get("dish_role") or classify_dish_role(r)
    return bool(re.search(r"\b(canh|súp)\b", t)) or role == "soup"


def _extract_main_ingredient_tags(recipe: Dict) -> set:
    if not recipe:
        return set()
    raw_text = (str(recipe.get("title", "")) + " " + " ".join(str(i.get("name", "")) for i in recipe.get("ingredients", []))).lower()
    text = re.sub(r"hạt\s+nêm[^,;.\n]*", " ", raw_text)
    kw_groups = [
        ('đậu', ['đậu hũ', 'tàu hũ', 'đậu phụ', 'đậu non']),
        ('nấm', ['nấm']),
        ('bò', ['thịt bò', 'bắp bò', 'bò']),
        ('heo', ['thịt heo', 'thịt lợn', 'ba chỉ', 'ba rọi', 'sườn', 'giò heo', 'thịt băm', 'xá xíu']),
        ('gà', ['thịt gà', 'ức gà', 'đùi gà', 'gà']),
        ('vịt', ['vịt', 'ngan']),
        ('cá', ['cá hồi', 'cá lóc', 'cá diêu hồng', 'cá thu', 'cá bớp', 'cá ngừ', 'chả cá', 'cá ']),
        ('tôm', ['tôm', 'tép']),
        ('mực', ['mực', 'bạch tuộc']),
        ('cua', ['cua', 'ghẹ', 'chả cua']),
        ('ốc', ['ốc', 'nghêu', 'sò', 'hến']),
        ('trứng', ['trứng', 'hột vịt']),
        ('ếch', ['ếch'])
    ]
    found = set()
    for grp, tokens in kw_groups:
        if any(t in text for t in tokens):
            found.add(grp)
    return found


def _is_valid_side(r: Dict, main_id: str = None, soup_id: str = None, main_r: Dict = None, soup_r: Dict = None) -> bool:
    if not r:
        return False
    if r.get("id") in (main_id, soup_id):
        return False
    title = str(r.get("title", "")).lower()
    if any(k in title for k in ["canh ", "canh", "súp", "cháo", "lẩu", "bún", "phở", "mì", "miến", "bánh canh", "khoai", "bắp luộc", "ngô luộc", "sắn"]):
        return False
    from core.nutrition.recipe_catalog import classify_dish_role
    role = r.get("dish_role") or classify_dish_role(r)
    if role != "side":
        return False

    # Món phụ tuyệt đối KHÔNG trùng nguyên liệu chính/đạm với món chính hoặc món canh trong thực đơn mâm cơm
    side_tags = _extract_main_ingredient_tags(r)
    if main_r:
        main_tags = _extract_main_ingredient_tags(main_r)
        if side_tags and main_tags and (side_tags & main_tags):
            return False
    if soup_r:
        soup_tags = _extract_main_ingredient_tags(soup_r)
        if side_tags and soup_tags and (side_tags & soup_tags):
            return False

    return True


def _main_score(r: Dict) -> int:
    title = str(r.get("title", "")).lower()
    if any(k in title for k in ["gà", "cá", "đậu hũ", "tàu hũ", "đậu phụ", "nấm", "chả", "thịt", "trứng", "bò", "heo", "ếch"]):
        return 3
    tags = _extract_main_ingredient_tags(r)
    return 2 if tags else 1


def _side_score(r: Dict) -> int:
    title = str(r.get("title", "")).lower()
    meat = any(k in title for k in ["thịt", "heo", "bò", "gà", "vịt", "cá", "tôm", "cua", "mực", "ốc", "sườn", "giò"])
    veg = any(k in title for k in ["rau", "cải", "bí", "bầu", "mướp", "bông cải", "nấm", "cà tím", "đậu", "su", "củ", "ngó sen"])
    return (2 if veg and not meat else 1 if veg else 0)


def _build_full_meal_set(condition: str, recipes: List[Dict], candidates: List[Dict], ai_fms: Dict = None) -> Any:
    all_pool = {r["id"]: r for r in recipes}
    for c in candidates:
        if c["id"] not in all_pool:
            all_pool[c["id"]] = c

    slot_time, slot_label = _resolve_meal_slot(condition)

    if ai_fms and ai_fms.get("main_recipe_id") in all_pool and ai_fms.get("soup_recipe_id") in all_pool:
        candidate_main = all_pool[ai_fms["main_recipe_id"]]
        candidate_soup = all_pool[ai_fms["soup_recipe_id"]]
        if _is_valid_main(candidate_main) and _is_valid_soup(candidate_soup):
            main_r = candidate_main
            soup_r = candidate_soup
            side_id = ai_fms.get("side_recipe_id")
            candidate_side = all_pool.get(side_id) if side_id else None
            if _is_valid_side(candidate_side, main_r["id"], soup_r["id"], main_r, soup_r):
                side_r = candidate_side
            else:
                side_pool = [r for r in recipes + candidates if _is_valid_side(r, main_r["id"], soup_r["id"], main_r, soup_r)]
                side_pool.sort(key=lambda r: -_side_score(r))
                side_r = side_pool[0] if side_pool else None

            if side_r:
                dishes = [
                    {"role": "main", "role_label": "Món chính", "recipe": main_r},
                    {"role": "soup", "role_label": "Món canh", "recipe": soup_r},
                    {"role": "side", "role_label": "Món rau / phụ", "recipe": side_r}
                ]
                return {
                    "title": ai_fms.get("title", "Mâm cơm gợi ý cho 1 bữa"),
                    "meal_time": slot_time,
                    "meal_label": slot_label,
                    "rationale": ai_fms.get("rationale", "Các món được phối hợp ít purin, an toàn theo tình trạng sức khỏe và hồ sơ dị ứng của bạn."),
                    "staple_text": ai_fms.get("staple_text") or "Cơm gạo lứt hoặc cơm trắng dẻo mềm",
                    "dishes": dishes
                }

    main_candidates = [r for r in recipes if _is_valid_main(r)] + [r for r in candidates if _is_valid_main(r)]
    seen_m, dedup_mains = set(), []
    for r in main_candidates:
        if r.get("id") not in seen_m:
            seen_m.add(r.get("id"))
            dedup_mains.append(r)
    dedup_mains.sort(key=lambda r: -_main_score(r))

    soup_candidates = [r for r in recipes if _is_valid_soup(r)] + [r for r in candidates if _is_valid_soup(r)]
    seen_s, dedup_soups = set(), []
    for r in soup_candidates:
        if r.get("id") not in seen_s:
            seen_s.add(r.get("id"))
            dedup_soups.append(r)

    # Mâm cơm 1 bữa chuẩn vị: BẮT BUỘC đủ 3 món: Món chính + Món canh + Món rau / phụ
    for main_r in dedup_mains[:8]:
        for soup_r in dedup_soups[:8]:
            if soup_r.get("id") == main_r.get("id"):
                continue
            side_candidates = [
                r for r in recipes + candidates
                if _is_valid_side(r, main_r["id"], soup_r["id"], main_r, soup_r)
            ]
            side_candidates.sort(key=lambda r: -_side_score(r))
            if side_candidates:
                side_r = side_candidates[0]
                dishes = [
                    {"role": "main", "role_label": "Món chính", "recipe": main_r},
                    {"role": "soup", "role_label": "Món canh", "recipe": soup_r},
                    {"role": "side", "role_label": "Món rau / phụ", "recipe": side_r}
                ]
                return {
                    "title": "Mâm cơm gợi ý cho 1 bữa",
                    "meal_time": slot_time,
                    "meal_label": slot_label,
                    "rationale": "Các món được ghép hài hòa và đã qua bộ lọc an toàn theo tình trạng sức khỏe của bạn.",
                    "staple_text": "Cơm gạo lứt hoặc cơm trắng dẻo mềm",
                    "dishes": dishes
                }

    return None


def _profile_context(profile, dob, prepared):
    profile = profile if isinstance(profile, dict) else {}
    def number(value):
        try:
            return float(str(value).strip().replace(",", "."))
        except (TypeError, ValueError):
            return None
    height = number(profile.get("height"))
    weight = number(profile.get("weight"))
    height = height if height is not None and 100 <= height <= 230 else None
    weight = weight if weight is not None and 20 <= weight <= 350 else None
    adult = False
    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            born = datetime.strptime(str(dob), date_format).date()
            adult = (date.today() - born).days >= 18 * 365.2425
            break
        except (TypeError, ValueError):
            continue
    bmi = round(weight / (height / 100) ** 2, 1) if adult and height and weight else None
    category = None
    if adult and bmi is not None:
        category = "Thiếu cân" if bmi < 18.5 else "Trong khoảng tham chiếu" if bmi < 25 else "Thừa cân" if bmi < 30 else "Béo phì"
    from core.nutrition.nutrition_rules import ALLERGEN_NAMES
    allergies = [ALLERGEN_NAMES[code] for code in prepared.get("profile_allergies", [])]
    needs_review = bool(prepared.get("profile_allergy_needs_review"))
    return {"used": bool(allergies or bmi is not None or needs_review), "allergies": allergies,
            "allergy_needs_review": needs_review,
            "height_cm": height, "weight_kg": weight, "bmi": bmi, "bmi_category": category,
            "bmi_note": "BMI chỉ là chỉ số tham khảo ở người trưởng thành; không dùng để tự đặt mức kcal." if bmi is not None else ""}


def _meal_calories(meal, prepared):
    meal["title"] = "Mâm cơm gợi ý cho 1 bữa"
    roles = {item.get("role") for item in meal.get("dishes", [])}
    composition = "món chính, món canh" + (" và món rau/phụ" if "side" in roles else "")
    constraints = []
    if prepared.get("recognized"):
        constraints.append(prepared.get("context_label", "tình trạng đã nhập"))
    constraints.extend(prepared.get("query_preferences", []))
    constraint_text = " theo " + ", ".join(constraints) if constraints else " theo mô tả bạn nhập"
    allergy_text = "; đã loại món có nguyên liệu khớp dị ứng khai báo" if prepared.get("allergies") else ""
    if "gout" in (prepared.get("contexts") or []):
        meal["rationale"] = (
            f"Phối hợp {composition} từ nhóm trứng, rau xanh và củ quả ít nhân purin; "
            f"đã loại trừ thịt gà/gia cầm, thịt bò/thịt đỏ, nội tạng, hải sản/cá và các loại đậu{allergy_text}."
        )
    else:
        meal["rationale"] = (f"Ghép {composition} từ các công thức an toàn{constraint_text}{allergy_text}. "
                             "Cần kiểm tra cách nêm và khẩu phần thực tế trước khi dùng.")
    # Free-text staples from a model have no catalog ingredients to screen
    # against food allergies, so never name an unscreened food here.
    meal["staple_text"] = "Chọn loại tinh bột bạn dùng được theo khẩu phần cá nhân; phần này chưa có công thức trong mâm."
    values = []
    for item in meal.get("dishes", []):
        item["role_label"] = {"main": "Món chính", "soup": "Món canh", "side": "Món rau / phụ"}.get(item.get("role"), "Món ăn")
        value = item.get("recipe", {}).get("calories")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
            values.append(value)
    meal["total_calories"] = round(sum(values), 1) if values else None
    meal["calorie_note"] = (f"Ước tính theo dữ liệu nguồn cho {len(values)}/{len(meal.get('dishes', []))} món; "
                            "chưa tính phần tinh bột ăn kèm. Không chia theo số người trong công thức.")


def get_nutrition_options(condition: str, recipe_type: str, exclude_recipe_ids=None,
                          profile=None, dob=None) -> Dict[str, Any]:
    """Filter canonical recipes first, then let AI select and explain IDs."""
    from core.nutrition.nutrition_rules import prepare_nutrition_candidates
    from core.nutrition.nutrition_ai import NutritionAIError, select_recipes

    recipe_type = "food"
    result = _get_general_options(condition, recipe_type)
    profile = profile if isinstance(profile, dict) else {}
    prepared = prepare_nutrition_candidates(condition, result["recipes"], profile.get("allergies"))
    result["profile_context"] = _profile_context(profile, dob, prepared)
    result["query_preferences"] = prepared.get("query_preferences", [])
    if prepared.get("is_unmapped_disease"):
        result.update(recipes=[], eligible_count=0, considered_count=0, has_more=False,
                      needs_clarification=True, provider_status="clinical_safeguard_refusal",
                      clarification_question=f"Tình trạng '{condition}' là bệnh lý cần chế độ dinh dưỡng lâm sàng chuyên biệt được bác sĩ chỉ định. Hệ thống không tự động gợi ý món để tránh rủi ro tương tác bệnh lý.",
                      notice="Để bảo đảm an toàn lâm sàng, hệ thống không tự động gợi ý món cho các bệnh lý chưa có bộ quy tắc dinh dưỡng được kiểm duyệt.",
                      selection_explanation="Hệ thống MediMind kích hoạt rào chắn an toàn (Clinical Safety Guardrail): không tự ý tạo thực đơn cho các bệnh lý khi chưa có dữ liệu dinh dưỡng kiểm chứng.")
        return result
    eligible = prepared["recipes"]
    seen = set(exclude_recipe_ids or [])
    seen_titles = {title_key(recipe) for recipe in eligible if recipe["id"] in seen}
    remaining = [recipe for recipe in eligible if recipe["id"] not in seen and title_key(recipe) not in seen_titles]
    candidates = retrieve_candidates(condition, remaining,
                                     sort_by_sugar="no_added_sugar" in prepared.get("preference_codes", []))
    if "no_added_sugar" in prepared.get("preference_codes", []):
        candidates.sort(key=lambda r: (not isinstance(r.get("sugar"), (int, float)),
                                       r.get("sugar") if isinstance(r.get("sugar"), (int, float)) else float("inf")))
    guidance = prepared["guidance"]
    stats = catalog_stats()
    type_count = stats["food_count"]
    result.update(recipes=candidates, sources=guidance, excluded=prepared["excluded"][:20], excluded_count=len(prepared["excluded"]),
                  catalog=stats, catalog_type_count=type_count, eligible_count=len(eligible), considered_count=len(candidates),
                  has_more=False,
                  avoidance=prepared["avoidance"], avoidance_note=prepared["avoidance_note"],
                  limitations=prepared.get("limitations", []), gemini_used=False, ai_used=False,
                  needs_clarification=False, clarification_question="",
                  selection_explanation="Python kiểm tra nhãn nguyên liệu và các quy tắc có nguồn trước. "
                      "AI chỉ được chọn và giải thích các công thức đã qua bộ lọc; không thay đổi nguyên liệu hoặc cách nấu. "
                      f'Kho hiện có {stats["total"]} công thức từ {stats["source"]}. '
                      + ("Danh mục món Việt được chọn theo tiêu chí món quen thuộc và nguyên liệu địa phương; nhãn này không chứng nhận nguồn gốc địa lý hay độ phù hợp với bệnh. " if stats["cuisine"] == "VN" else "") +
                      "Bộ tìm kiếm lấy một nhóm ứng viên liên quan từ các công thức qua bộ lọc để AI xếp hạng; không gửi cả kho trong mỗi yêu cầu. "
                      "Nhãn của công thức nhập được quét tự động từ văn bản, chưa được rà soát chuyên môn từng món. Việc được gợi ý không xác nhận phù hợp y khoa.")
    if not candidates:
        if eligible and seen:
            result.update(provider_status="catalog_exhausted", needs_clarification=False,
                          notice="Bạn đã xem hết các công thức qua bộ lọc hiện tại.")
            return result
        result.update(provider_status="no_candidates", recommendation_scope="filtered_catalog",
                          needs_clarification=True,
                          clarification_question="Chưa có công thức đáp ứng những giới hạn bạn nhập. Bạn có thể bổ sung loại thực phẩm dùng được không?",
                          notice="Không có món trong kho hiện tại vượt qua bộ lọc nguyên liệu; hệ thống không tự thêm món khác.")
        return result
    if "fatty_liver" in prepared["contexts"]:
        # Show clinical-filtered Mon Ngon Moi Ngay dishes directly with NIDDK guidance.
        shown = candidates[:10]
        for recipe in shown:
            recipe["recommendation_reason"] = (
                "Công thức qua bộ lọc nguyên liệu tham khảo cho gan nhiễm mỡ; "
                "chưa xác nhận phù hợp với khẩu phần hoặc bệnh nền của bạn."
            )
            _enrich_recipe(recipe, condition, prepared.get("contexts"))
        full_meal = _build_full_meal_set(condition, shown, candidates)
        meal_ids = set()
        if full_meal:
            for dish in full_meal["dishes"]:
                meal_ids.add(dish["recipe"]["id"])
                _enrich_recipe(dish["recipe"], condition, prepared.get("contexts"))
            _meal_calories(full_meal, prepared)
            result["full_meal_set"] = full_meal
        result.update(
            recipes=[recipe for recipe in shown if recipe["id"] not in meal_ids],
            matched=True, has_condition_notes=True,
            provider_status="guided_catalog", recommendation_scope="guided_catalog", has_more=len(remaining) > len(shown),
            notice="Đây là công thức tham khảo từ Món Ngon Mỗi Ngày đã qua bộ lọc nguyên liệu và dị ứng được nhận diện. "
                   "Hướng dẫn NIDDK dành cho gan nhiễm mỡ không do rượu; chưa xác nhận từng món phù hợp với nguyên nhân bệnh, mức độ bệnh hoặc khẩu phần cá nhân.",
            selection_explanation="MediMind đối chiếu danh sách nguyên liệu với dị ứng đã khai báo và các nguyên tắc ăn uống chung có nguồn. "
                                  "Các công thức này chưa được xác minh dinh dưỡng lâm sàng; cần kiểm tra cách nêm, khẩu phần và bệnh nền trước khi dùng.",
        )
        return result
    ai_fms = None
    try:
        selection = select_recipes(condition, recipe_type, candidates, guidance,
                                   personalization={"allergen_codes": prepared.get("allergies", []),
                                                    "bmi_category": result["profile_context"].get("bmi_category"),
                                                    "diet_preferences": prepared.get("preference_codes", [])})
        ai_fms = selection.get("full_meal_set")
        # gemini_used is a legacy response field retained for older clients.
        # provider_status and ai_used describe the provider result accurately.
        result.update(recipes=selection["recipes"], gemini_used=True, ai_used=True,
                      needs_clarification=selection["needs_clarification"],
                      clarification_question=selection["clarification_question"], model=selection["model"],
                      provider_status="ai_needs_clarification" if selection["needs_clarification"] else "ai_ranked",
                      recommendation_scope="ai_ranked_catalog")
        if selection["needs_clarification"]:
            if prepared["recognized"]:
                # A known short symptom is enough to show general eating
                # options; missing personalization must not blank the page.
                # These are canonical, pre-filtered items, NOT AI-ranked IDs.
                preview = []
                for recipe in candidates[:5]:
                    item = deepcopy(recipe)
                    item["recommendation_reason"] = _clinical_fallback_reason(item, condition, prepared.get("contexts"))
                    item.update(ai_caution="Đây là lựa chọn tham khảo của hệ thống, chưa được AI xếp hạng theo thông tin cá nhân.",
                                source_ids=[], selection_origin="guided_catalog")
                    preview.append(item)
                result.update(recipes=preview, provider_status="ai_clarification_with_options",
                              gemini_used=False, ai_used=False,
                              recommendation_scope="guided_catalog",
                              clarification_question="Bạn có dị ứng thực phẩm hoặc chế độ ăn riêng cần lưu ý không? Bạn có thể bổ sung để gợi ý sát hơn.",
                              notice="Bạn vẫn có thể xem các công thức tham khảo bên dưới. AI cần thêm thông tin để cá nhân hóa; các món này chưa được AI xếp hạng.")
            else:
                result["notice"] = "Cần thêm thông tin trước khi gợi ý món."
        else:
            result["notice"] = "MediMind đã chọn lọc các món ăn an toàn và phù hợp nhất với yêu cầu và hồ sơ sức khỏe của bạn."
            if not prepared["recognized"]:
                result["notice"] += " Chưa có bộ quy tắc riêng cho nội dung bạn nhập."
    except NutritionAIError as error:
        result.update(recipes=candidates[:8], provider_status="fallback_" + error.code,
                      gemini_used=False, ai_used=False, recommendation_scope="filtered_catalog",
                      selection_explanation="Danh sách tham khảo được lấy từ kho công thức và lọc bằng Python theo yêu cầu của bạn. AI chưa xếp hạng các món này.",
                      notice="AI tạm thời chưa thể xếp hạng món ăn. Hệ thống đang hiển thị các gợi ý tham khảo đã được lọc theo yêu cầu của bạn.")

    contexts = prepared.get("contexts", [])
    # Enrich every recipe with meal_time, dish_role, key_nutrients, and clinical explanation
    for r in result.get("recipes", []):
        if "fatty_liver" in contexts:
            r["recommendation_reason"] = ("Công thức qua bộ lọc nguyên liệu tham khảo cho gan nhiễm mỡ; "
                                          "chưa xác nhận phù hợp với khẩu phần hoặc bệnh nền của bạn.")
        _enrich_recipe(r, condition, contexts)

    # Build full meal set if in food mode and recipes exist (require at least 2 recipes or explicit AI meal set)
    if recipe_type == "food" and result.get("recipes") and (ai_fms or len(result["recipes"]) >= 2):
        full_meal = _build_full_meal_set(condition, result["recipes"], candidates, ai_fms)
        if full_meal:
            for d in full_meal["dishes"]:
                _enrich_recipe(d["recipe"], condition, contexts)
            _meal_calories(full_meal, prepared)
            result["full_meal_set"] = full_meal

            from core.nutrition.recipe_catalog import is_standalone_one_dish, classify_meal_times

            fms_ids = {d["recipe"]["id"] for d in full_meal["dishes"]}
            fms_titles = {title_key(d["recipe"]) for d in full_meal["dishes"]}

            # 1. Lọc món đơn lẻ từ kết quả AI đã chọn: loại bỏ mọi món trong mâm cơm và chỉ giữ món trọn vị
            singles = [
                r for r in result["recipes"]
                if r["id"] not in fms_ids and title_key(r) not in fms_titles and is_standalone_one_dish(r)
            ]

            selected_ids = {r["id"] for r in singles} | fms_ids
            selected_titles = {title_key(r) for r in singles} | fms_titles

            # 2. Bổ sung từ candidates và eligible: CHỈ CHỌN các món trọn vị (is_standalone_one_dish == True)
            available_pool = [
                c for c in candidates + eligible
                if c["id"] not in selected_ids and title_key(c) not in selected_titles and is_standalone_one_dish(c)
            ]

            target_meals = ["breakfast", "lunch", "dinner", "snack"]
            # Ưu tiên 2a: món trọn vị theo từng bữa ăn
            for target_meal in target_meals:
                if len(singles) >= 5:
                    break
                for cand in available_pool:
                    if cand["id"] in selected_ids or title_key(cand) in selected_titles:
                        continue
                    cand_meals = cand.get("possible_meals") or classify_meal_times(cand)
                    if target_meal in cand_meals:
                        cand_copy = deepcopy(cand)
                        cand_copy["meal_time"] = target_meal
                        cand_copy["meal_label"] = _MEAL_LABELS.get(target_meal, "Bữa ăn")
                        _enrich_recipe(cand_copy, condition, contexts)
                        singles.append(cand_copy)
                        selected_ids.add(cand["id"])
                        selected_titles.add(title_key(cand))
                        break

            # Ưu tiên 2b: món trọn vị còn lại trong pool
            for cand in available_pool:
                if len(singles) >= 5:
                    break
                if cand["id"] not in selected_ids and title_key(cand) not in selected_titles:
                    cand_copy = deepcopy(cand)
                    _enrich_recipe(cand_copy, condition, contexts)
                    singles.append(cand_copy)
                    selected_ids.add(cand["id"])
                    selected_titles.add(title_key(cand))

            # Dự phòng: Nếu không có đủ món trọn vị (ví dụ trong tập test nhỏ), lấy các món không trùng mâm cơm
            if not singles:
                singles = [
                    r for r in result["recipes"]
                    if r["id"] not in fms_ids and title_key(r) not in fms_titles
                ]
                if not singles:
                    for cand in candidates + eligible:
                        if cand["id"] not in fms_ids and title_key(cand) not in fms_titles and cand["id"] not in selected_ids:
                            cand_copy = deepcopy(cand)
                            _enrich_recipe(cand_copy, condition, contexts)
                            singles.append(cand_copy)
                            selected_ids.add(cand["id"])
                            if len(singles) >= 3:
                                break

            result["recipes"] = singles
        else:
            result["full_meal_set"] = None
    else:
        result["full_meal_set"] = None

    result["has_more"] = bool(result["recipes"]) and len({title_key(r) for r in remaining}) > len(result["recipes"])
    return result
