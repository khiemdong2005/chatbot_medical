"""Gợi ý công thức để người dùng tự chọn, không thay thế tư vấn dinh dưỡng."""
from copy import deepcopy
from typing import Any, Dict, List, Optional
import unicodedata
from core.recipe_catalog import imported_recipes, catalog_stats, retrieve_candidates, title_key


def _recipe(key, title, icon, subtitle, time, benefit, ingredients, steps, avoid):
    return {"id": key, "title": title, "icon": icon, "subtitle": subtitle,
            "cooking_time": time, "benefit": benefit, "ingredients": ingredients,
            "steps": steps, "avoid": avoid}


def _i(name, amount, unit, icon):
    return {"name": name, "amount": amount, "unit": unit, "icon": icon}


FOOD = [
    _recipe("oat_porridge", "Cháo yến mạch chuối", "🥣", "Món mềm, dễ chuẩn bị", "15 phút", "Yến mạch và chuối cung cấp carbohydrate và chất xơ.",
        [_i("Yến mạch",40,"g","🌾"),_i("Chuối chín",1,"quả","🍌"),_i("Nước lọc",250,"ml","💧")],
        ["Nấu yến mạch với nước trên lửa nhỏ, khuấy đều.","Nghiền chuối rồi cho vào nồi.","Nấu thêm 2 phút, để nguội bớt trước khi dùng."],
        ["Chọn độ ấm và độ mềm phù hợp khi ăn."]),
    _recipe("pumpkin_soup", "Súp bí đỏ", "🎃", "Bí đỏ nấu mềm, vị nhẹ", "25 phút", "Bí đỏ cung cấp chất xơ và beta-carotene.",
        [_i("Bí đỏ",150,"g","🎃"),_i("Khoai tây",80,"g","🥔"),_i("Nước lọc",300,"ml","💧")],
        ["Gọt vỏ bí và khoai, rửa sạch rồi cắt nhỏ.","Nấu với nước đến khi chín mềm.","Xay nhuyễn, nêm nhẹ và để nguội bớt."],
        ["Gia giảm gia vị theo mức chịu đựng của bạn."]),
    _recipe("rice_carrot", "Cháo gạo cà rốt", "🍚", "Cháo nấu nhừ, đơn giản", "30 phút", "Gạo cung cấp năng lượng; cà rốt bổ sung chất xơ.",
        [_i("Gạo tẻ",50,"g","🍚"),_i("Cà rốt",60,"g","🥕"),_i("Nước lọc",450,"ml","💧")],
        ["Vo gạo; rửa sạch, thái nhỏ cà rốt.","Nấu gạo với nước đến khi nở, thêm cà rốt.","Ninh mềm, nêm nhẹ và để nguội bớt."],
        ["Điều chỉnh lượng ăn theo nhu cầu và hướng dẫn cá nhân."]),
    _recipe("soft_egg", "Trứng hấp mềm", "🍳", "Bữa ăn nhẹ giàu đạm", "15 phút", "Trứng là nguồn cung cấp đạm.",
        [_i("Trứng gà",1,"quả","🥚"),_i("Nước ấm",80,"ml","💧")],
        ["Đánh tan trứng với nước ấm.","Lọc qua rây và đổ vào bát chịu nhiệt.","Hấp đến khi trứng chín hoàn toàn."],
        ["Không dùng nếu bạn dị ứng trứng."])
]

DRINK = [
    _recipe("warm_water", "Nước ấm", "💧", "Một ly nước đơn giản", "2 phút", "Nước giúp bổ sung dịch cho cơ thể.",
        [_i("Nước uống",250,"ml","💧")], ["Đun nước sạch đến sôi.","Để nguội đến nhiệt độ dễ uống.","Rót ra ly và uống từng ngụm."],
        ["Nếu bạn được hướng dẫn giới hạn dịch, làm theo hướng dẫn của bác sĩ."]),
    _recipe("warm_milk", "Sữa ấm", "🥛", "Sữa làm ấm nhẹ", "5 phút", "Sữa cung cấp đạm và canxi.",
        [_i("Sữa tươi không đường",200,"ml","🥛")], ["Rót sữa vào nồi sạch.","Làm ấm trên lửa nhỏ, không cần đun sôi.","Rót ra ly và kiểm tra nhiệt độ trước khi uống."],
        ["Chọn loại sữa phù hợp nếu dị ứng sữa hoặc không dung nạp lactose."]),
    _recipe("oat_drink", "Nước yến mạch không đường", "🌾", "Vị yến mạch nhẹ", "12 phút", "Là một lựa chọn đồ uống không thêm đường.",
        [_i("Yến mạch",25,"g","🌾"),_i("Nước lọc",250,"ml","💧")], ["Nấu yến mạch với nước khoảng 8 phút.","Để nguội bớt rồi xay nhuyễn.","Lọc nếu muốn mịn và dùng ở nhiệt độ dễ chịu."],
        ["Kiểm tra thành phần nếu bạn cần tránh gluten hoặc yến mạch."]),
    _recipe("cucumber_water", "Nước dưa leo", "🥒", "Nước lọc có hương nhẹ", "5 phút", "Nước là nguồn bổ sung dịch; dưa leo tạo vị thanh nhẹ.",
        [_i("Dưa leo",5,"lát","🥒"),_i("Nước uống",250,"ml","💧")], ["Rửa sạch dưa leo và thái lát.","Cho dưa leo vào ly nước uống.","Để vài phút rồi thưởng thức."],
        ["Nếu đang cần giới hạn dịch, tham khảo lượng uống với chuyên gia y tế."])
]


FOOD.extend([
    _recipe("sweet_potato", "Khoai lang nghiền", "🍠", "Khoai hấp mềm, vị ngọt tự nhiên", "25 phút", "Khoai lang cung cấp carbohydrate và chất xơ.",
        [_i("Khoai lang",150,"g","🍠"),_i("Nước lọc",30,"ml","💧")],
        ["Rửa khoai, gọt vỏ và cắt miếng nhỏ.","Hấp đến khi khoai chín mềm.","Nghiền với một ít nước đến độ mềm mong muốn; để nguội bớt."],
        ["Điều chỉnh khẩu phần theo nhu cầu và hướng dẫn cá nhân."]),
    _recipe("chicken_congee", "Cháo gà xé mềm", "🍲", "Cháo nấu nhừ với thịt gà", "35 phút", "Thịt gà cung cấp đạm, kết hợp với cháo gạo tạo thành bữa ăn mềm.",
        [_i("Gạo tẻ",40,"g","🍚"),_i("Thịt ức gà",70,"g","🍗"),_i("Nước lọc",450,"ml","💧")],
        ["Vo gạo và rửa sạch thịt gà.","Nấu cháo với nước; luộc gà chín hoàn toàn rồi xé nhỏ.","Cho gà vào cháo, nấu thêm vài phút và nêm nhẹ."],
        ["Đảm bảo thịt gà chín kỹ; để món ăn nguội bớt trước khi dùng."]),
    _recipe("tofu_pumpkin", "Đậu hũ non bí đỏ", "🍛", "Đậu hũ và bí đỏ hấp mềm", "20 phút", "Đậu hũ cung cấp đạm thực vật; bí đỏ bổ sung beta-carotene.",
        [_i("Đậu hũ non",100,"g","🥣"),_i("Bí đỏ",100,"g","🎃"),_i("Nước lọc",50,"ml","💧")],
        ["Gọt bí, rửa sạch rồi cắt thành miếng nhỏ.","Hấp bí đến khi mềm; nghiền cùng một ít nước.","Làm nóng đậu hũ non, ăn cùng bí đỏ đã nghiền."],
        ["Không dùng nếu bạn dị ứng đậu nành."])
])

DRINK.extend([
    _recipe("warm_soy", "Sữa đậu nành ấm", "🫘", "Sữa đậu nành không đường", "5 phút", "Sữa đậu nành là nguồn cung cấp đạm thực vật.",
        [_i("Sữa đậu nành không đường đã nấu chín",200,"ml","🥛")],
        ["Rót sữa đậu nành đã nấu chín vào nồi sạch.","Làm ấm trên lửa nhỏ và khuấy đều.","Rót ra ly, kiểm tra nhiệt độ trước khi uống."],
        ["Không dùng nếu bạn dị ứng đậu nành."]),
    _recipe("pear_water", "Nước lê ấm", "🍐", "Nước nấu cùng lê, vị dịu", "12 phút", "Lê tạo hương vị tự nhiên cho nước uống.",
        [_i("Lê",100,"g","🍐"),_i("Nước lọc",250,"ml","💧")],
        ["Rửa sạch lê, bỏ lõi và cắt miếng nhỏ.","Nấu lê với nước khoảng 8 phút.","Để nguội bớt, rót ra ly; có thể ăn phần lê mềm."],
        ["Không cần thêm đường; điều chỉnh lượng lê theo nhu cầu cá nhân."]),
    _recipe("barley_water", "Nước lúa mạch", "🌾", "Nước lúa mạch nấu nhạt", "35 phút", "Một lựa chọn đồ uống từ ngũ cốc, không thêm đường.",
        [_i("Lúa mạch khô",25,"g","🌾"),_i("Nước lọc",350,"ml","💧")],
        ["Rửa sạch lúa mạch.","Đun với nước cho đến khi hạt mềm, thêm nước nếu cần.","Lọc lấy nước, để nguội đến nhiệt độ dễ uống."],
        ["Lúa mạch chứa gluten; tránh dùng nếu bạn cần kiêng gluten."])
])


def _get_general_options(condition: str, recipe_type: str) -> Dict[str, Any]:
    """Danh mục chung theo loại món; tình trạng chỉ bổ sung ghi chú, không lọc món."""
    query = condition.strip().replace("_", " ")
    normalized = " ".join("".join(c for c in unicodedata.normalize("NFD", query.lower())
                                  if unicodedata.category(c) != "Mn").replace("đ", "d").split())
    # Only use explicit note labels. Substring matching can misread negation or
    # multi-condition input (e.g. "không mất ngủ") as a confirmed condition.
    note_context = {"nhiet mieng": "nhiet_mieng", "loet mieng": "nhiet_mieng",
                    "mat ngu": "mat_ngu", "kho ngu": "mat_ngu"}.get(normalized)
    recipes = imported_recipes(recipe_type)
    if not catalog_stats()["imported_count"]:
        recipes = deepcopy(DRINK if recipe_type == "drink" else FOOD)
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
            "selection_explanation": "Các công thức được soạn sẵn và chia theo nhóm thức ăn hoặc nước uống. "
                "Tên tình trạng chưa được dùng để lọc hay xếp hạng từng món. Với nhiệt miệng và mất ngủ, "
                "hệ thống chỉ bổ sung lưu ý chung. Bước này không dùng AI, RAG hoặc tra cứu MedlinePlus; "
                "chưa có nguồn y khoa liên kết và xác minh cho từng công thức.",
            "notice": notice, "recipe_type": recipe_type, "recipes": recipes}


_MEAL_LABELS = {
    "breakfast": "Bữa sáng",
    "lunch": "Bữa trưa",
    "dinner": "Bữa tối",
    "snack": "Bữa phụ / Trước ngủ"
}

_ROLE_LABELS = {
    "main": "Món chính",
    "soup": "Món canh",
    "side": "Món rau / phụ",
    "staple": "Món tinh bột / cháo",
    "drink": "Thức uống"
}


def _enrich_recipe(recipe: Dict[str, Any], condition: str) -> None:
    from core.recipe_catalog import classify_dish_role, classify_meal_times, is_standalone_one_dish
    dish_role = recipe.get("dish_role")
    if dish_role not in _ROLE_LABELS:
        dish_role = classify_dish_role(recipe)
        recipe["dish_role"] = dish_role

    title_lower = str(recipe.get("title", "")).lower()

    # Gán nhãn vai trò hiển thị thân thiện, phân biệt rõ món ăn trọn vị (One-dish meals)
    if is_standalone_one_dish(recipe):
        if any(k in title_lower for k in ["bún", "phở", "hủ tiếu", "mì", "miến", "bánh canh", "nui"]):
            recipe["dish_role_label"] = "Món nước / Bún · Phở · Mì"
        elif any(k in title_lower for k in ["cơm tấm", "cơm gà", "cơm chiên", "cơm rang", "cơm sườn", "cơm trộn"]):
            recipe["dish_role_label"] = "Cơm đĩa trọn vị"
        elif any(k in title_lower for k in ["cháo", "súp", "soup", "congee"]):
            recipe["dish_role_label"] = "Cháo / Súp dinh dưỡng"
        elif any(k in title_lower for k in ["bánh", "xôi"]):
            recipe["dish_role_label"] = "Món điểm tâm / Bánh"
        elif recipe.get("recipe_type") == "drink" or any(k in title_lower for k in ["chè", "sữa", "trà", "sinh tố", "nước"]):
            recipe["dish_role_label"] = "Thức uống / Chè thanh nhiệt"
        else:
            recipe["dish_role_label"] = "Món ăn trọn vị"
    else:
        recipe["dish_role_label"] = _ROLE_LABELS.get(dish_role, "Món ăn")

    possible_meals = classify_meal_times(recipe, dish_role)
    recipe["possible_meals"] = possible_meals
    meal_time = recipe.get("meal_time")
    if meal_time not in _MEAL_LABELS:
        meal_time = possible_meals[0] if possible_meals else "dinner"
        recipe["meal_time"] = meal_time
    recipe["meal_label"] = _MEAL_LABELS.get(meal_time, "Bữa ăn")

    desc_text = title_lower + " " + " ".join(str(i.get("name", "")).lower() for i in recipe.get("ingredients", []))
    cond_norm = unicodedata.normalize("NFD", condition.lower()).encode("ascii", "ignore").decode("utf-8")
    
    nutrients = []
    reasons = []

    # Giải thích dinh dưỡng lâm sàng chuyên biệt theo từng thể trạng
    if "nhiet mieng" in cond_norm or "loet" in cond_norm:
        if any(k in desc_text for k in ["đậu hũ", "tàu hũ", "đậu phụ", "đậu nành", "đậu xanh"]):
            nutrients.append("Đạm thực vật mềm & Kẽm")
            reasons.append("Đậu hũ non kết cấu mềm mịn không gây ma sát xót vết loét niêm mạc, giàu đạm lành tính và kẽm thúc đẩy lành mô miệng")
        if any(k in desc_text for k in ["mồng tơi", "rau ngót", "bầu", "bí", "mướp", "rau"]):
            nutrients.append("Chất nhầy tự nhiên & Vitamin A, C")
            reasons.append("Rau củ tính mát giàu chất nhầy tự nhiên làm dịu niêm mạc khoang miệng sưng rát, hỗ trợ thanh nhiệt")
        if any(k in desc_text for k in ["cháo", "súp", "bánh canh", "bún", "miến"]):
            nutrients.append("Tinh bột mềm mịn dễ nuốt")
            reasons.append("Món dạng lỏng mềm trơn mượt, dễ nuốt không cần nhai cọ xát, hạn chế tối đa kích ứng cơ học lên vết loét")
        if any(k in desc_text for k in ["sen", "hạt sen", "đậu xanh"]):
            nutrients.append("Flavonoid thanh nhiệt")
            reasons.append("Đậu xanh và hạt sen có tính mát thanh nhiệt giải độc, giảm cảm giác bức bối nóng rát miệng")
        if any(k in desc_text for k in ["cá", "gà", "thịt nạc"]):
            nutrients.append("Protein nạc tái tạo mô")
            reasons.append("Bổ sung đạm nạc mềm dễ hấp thu giúp tăng sinh nguyên bào sợi và đẩy nhanh tái tạo biểu mô miệng")
    elif "da day" in cond_norm or "trao nguoc" in cond_norm or "stomach" in cond_norm:
        if any(k in desc_text for k in ["cháo", "súp", "yến mạch"]):
            nutrients.append("Chất xơ hòa tan & Tinh bột mềm")
            reasons.append("Bao bọc nhẹ nhàng niêm mạc dạ dày, trung hòa dịch vị và giảm co bóp kích thích")
        if any(k in desc_text for k in ["đậu hũ", "cá", "gà"]):
            nutrients.append("Đạm nạc dễ tiêu")
            reasons.append("Cung cấp đạm dễ tiêu hóa mà không làm chậm quá trình làm rỗng dạ dày, tránh tăng tiết acid")
        if any(k in desc_text for k in ["bí đỏ", "khoai lang", "rau củ"]):
            nutrients.append("Pectin & Beta-carotene")
            reasons.append("Pectin tự nhiên làm êm dịu niêm mạc tiêu hóa và hỗ trợ làm lành thương tổn dịch vị")
    elif "gut" in cond_norm or "uric" in cond_norm:
        nutrients.append("Purin cực thấp & Khoáng kiềm")
        reasons.append("Thực phẩm thực vật lành tính, không chứa purin, giúp kiềm hóa nước tiểu và tăng đào thải acid uric qua thận")
    elif "sot" in cond_norm or "met moi" in cond_norm or "fever" in cond_norm:
        if any(k in desc_text for k in ["cháo", "súp", "bún", "miến", "phở"]):
            nutrients.append("Nước, Điện giải & Tinh bột hấp thu nhanh")
            reasons.append("Bổ sung dịch và năng lượng tức thời cho cơ thể, giảm kiệt sức và dễ tiêu hóa khi mệt mỏi")
        if any(k in desc_text for k in ["gà", "bò", "cá", "nạc"]):
            nutrients.append("Acid amin thiết yếu & Sắt")
            reasons.append("Bồi bổ thể lực, hỗ trợ tổng hợp hemoglobin và kích hoạt lại năng lượng tế bào")
    else:  # Mặc định hoặc mất ngủ / an thần
        if any(k in desc_text for k in ["hạt sen", "củ sen", "tâm sen", "sen"]):
            nutrients.append("Nelumbin & Magie")
            reasons.append("Hoạt chất Nelumbin trong sen giúp an thần định trí, thư giãn hệ thần kinh trung ương và giảm căng thẳng trằn trọc")
        if any(k in desc_text for k in ["đậu hũ", "tàu hũ", "đậu phụ", "đậu nành", "đậu xanh"]):
            nutrients.append("Tryptophan")
            nutrients.append("Đạm thực vật nhẹ bụng")
            reasons.append("Cung cấp Tryptophan - acid amin thiết yếu để cơ thể tổng hợp Serotonin và Melatonin điều hòa chu kỳ sinh học giấc ngủ")
        if any(k in desc_text for k in ["nấm", "nấm hương", "nấm đông cô", "nấm rơm", "nấm sò"]):
            nutrients.append("Vitamin nhóm B & Kẽm")
            reasons.append("Vitamin nhóm B hỗ trợ dẫn truyền thần kinh và tăng chuyển hóa êm dịu tế bào")
        if any(k in desc_text for k in ["cải bó xôi", "rau bina", "rau ngót", "mồng tơi", "bông cải", "rau"]):
            nutrients.append("Chất xơ & Magie")
            reasons.append("Bổ sung Magie tự nhiên hỗ trợ giãn cơ bắp và giúp thanh nhiệt cơ thể")
        if any(k in desc_text for k in ["rong biển", "tảo"]):
            nutrients.append("Magie & Khoáng vi lượng")
            reasons.append("Rong biển giàu magie và khoáng chất giúp làm dịu thần kinh và nhẹ bụng vào buổi tối")
        if any(k in desc_text for k in ["atisô", "a-ti-sô", "hoa atiso"]):
            nutrients.append("Cynarin & Flavonoid")
            reasons.append("Atisô giúp mát gan hạ hỏa, giảm cảm giác bức rứt nóng trong người về đêm")
        if any(k in desc_text for k in ["gà", "ức gà", "thịt nạc"]):
            nutrients.append("Protein nạc & Tryptophan")
            reasons.append("Cung cấp đạm dễ hấp thu mà không làm nặng gánh tiêu hóa của dạ dày")
        if any(k in desc_text for k in ["cá", "cá hồi", "cá lóc"]):
            nutrients.append("Omega-3 & Vitamin D")
            reasons.append("Omega-3 và Vitamin D tham gia điều hòa trung khu giấc ngủ và kháng viêm tự nhiên")
        if any(k in desc_text for k in ["yến mạch", "chuối"]):
            nutrients.append("Melatonin tự nhiên & Kali")
            reasons.append("Giàu kali và chất xơ giúp giãn cơ trơn và hỗ trợ giấc ngủ sâu")

    if not recipe.get("key_nutrients"):
        recipe["key_nutrients"] = ", ".join(dict.fromkeys(nutrients)) if nutrients else "Chất xơ, Vitamin & Khoáng chất tự nhiên"

    raw_reason = recipe.get("recommendation_reason")
    current_reason = "" if not raw_reason or str(raw_reason).strip().lower() == "none" else str(raw_reason).strip()

    if len(current_reason) < 40 or not any(w in current_reason.lower() for w in ["tryptophan", "magie", "nelumbin", "melatonin", "an thần", "chuyển hóa", "niêm mạc", "loét", "acid", "kẽm", "purin", "điện giải"]):
        if reasons:
            extra = "; ".join(reasons[:2]) + "."
            recipe["recommendation_reason"] = f"{current_reason} {extra}".strip() if current_reason else extra
        elif not current_reason:
            if "nhiet mieng" in cond_norm or "loet" in cond_norm:
                recipe["recommendation_reason"] = "Món thanh nhiệt mềm dịu, dễ nuốt và hạn chế tối đa ma sát lên niêm mạc khoang miệng."
            elif "da day" in cond_norm or "trao nguoc" in cond_norm:
                recipe["recommendation_reason"] = "Món thanh đạm êm dịu, bảo vệ niêm mạc dạ dày và không kích thích tăng tiết acid dịch vị."
            elif "gut" in cond_norm:
                recipe["recommendation_reason"] = "Món ăn từ nguyên liệu ít purin, an toàn cho khớp và hỗ trợ quá trình thanh lọc cơ thể."
            elif "sot" in cond_norm or "met moi" in cond_norm:
                recipe["recommendation_reason"] = "Món dạng lỏng mềm dễ hấp thu, giúp bù nước, bổ sung năng lượng và phục hồi thể trạng."
            else:
                recipe["recommendation_reason"] = "Món ăn thanh nhẹ giàu dưỡng chất tự nhiên, cung cấp năng lượng cân bằng cho cơ thể."


def _is_valid_main(r: Dict) -> bool:
    if not r:
        return False
    title = str(r.get("title", "")).lower()
    if any(k in title for k in ["canh ", "canh", "súp", "sup", "cháo", "chao", "lẩu", "bún", "phở", "hủ tiếu", "mì ", "miến", "bánh canh", "nui"]):
        return False
    from core.recipe_catalog import classify_dish_role
    role = r.get("dish_role") or classify_dish_role(r)
    return role == "main"


def _is_valid_soup(r: Dict) -> bool:
    if not r:
        return False
    title = str(r.get("title", "")).lower()
    from core.recipe_catalog import classify_dish_role
    role = r.get("dish_role") or classify_dish_role(r)
    return "canh" in title or "súp" in title or role == "soup"


def _is_valid_side(r: Dict, main_id: str = None, soup_id: str = None) -> bool:
    if not r:
        return False
    if r.get("id") in (main_id, soup_id):
        return False
    title = str(r.get("title", "")).lower()
    if any(k in title for k in ["canh ", "canh", "súp", "cháo", "lẩu", "bún", "phở", "mì", "miến", "bánh canh"]):
        return False
    from core.recipe_catalog import classify_dish_role
    role = r.get("dish_role") or classify_dish_role(r)
    return role in ("side", "staple")
    role = r.get("dish_role") or classify_dish_role(r)
    return role in ("side", "staple")


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

    if ai_fms and ai_fms.get("main_recipe_id") in all_pool and ai_fms.get("soup_recipe_id") in all_pool:
        candidate_main = all_pool[ai_fms["main_recipe_id"]]
        candidate_soup = all_pool[ai_fms["soup_recipe_id"]]
        if _is_valid_main(candidate_main) and _is_valid_soup(candidate_soup):
            main_r = candidate_main
            soup_r = candidate_soup
            side_id = ai_fms.get("side_recipe_id")
            candidate_side = all_pool.get(side_id) if side_id else None
            if _is_valid_side(candidate_side, main_r["id"], soup_r["id"]):
                side_r = candidate_side
            else:
                side_pool = [r for r in recipes + candidates if _is_valid_side(r, main_r["id"], soup_r["id"])]
                side_pool.sort(key=lambda r: -_side_score(r))
                side_r = side_pool[0] if side_pool else None

            dishes = [
                {"role": "main", "role_label": "Món chính · Đạm lành tính", "recipe": main_r},
                {"role": "soup", "role_label": "Món canh · Thanh nhiệt an thần", "recipe": soup_r}
            ]
            if side_r:
                dishes.append({"role": "side", "role_label": "Món rau / phụ · Bổ sung xơ & khoáng", "recipe": side_r})

            return {
                "title": ai_fms.get("title", "Mâm cơm thanh nhẹ, đủ món cho Bữa tối"),
                "meal_time": ai_fms.get("meal_time", "dinner"),
                "meal_label": _MEAL_LABELS.get(ai_fms.get("meal_time", "dinner"), "Bữa tối"),
                "rationale": ai_fms.get("rationale", "Mâm cơm kết hợp hài hòa đạm lành tính, canh thanh nhiệt an thần và rau xanh giàu chất xơ cùng khoáng chất, vừa đủ dinh dưỡng vừa không gây khó tiêu vào ban đêm."),
                "staple_text": ai_fms.get("staple_text") or "Cơm gạo lứt hạt sen hoặc cơm trắng dẻo mềm",
                "dishes": dishes
            }

    main_candidates = [r for r in recipes if _is_valid_main(r)] or [r for r in candidates if _is_valid_main(r)]
    soup_candidates = [r for r in recipes if _is_valid_soup(r)] or [r for r in candidates if _is_valid_soup(r)]

    if not main_candidates or not soup_candidates:
        return None

    main_r = main_candidates[0]
    soup_filtered = [r for r in soup_candidates if r.get("id") != main_r.get("id")]
    if not soup_filtered:
        return None
    soup_r = soup_filtered[0]

    side_candidates = [r for r in recipes if _is_valid_side(r, main_r["id"], soup_r["id"])] or [r for r in candidates if _is_valid_side(r, main_r["id"], soup_r["id"])]
    side_candidates.sort(key=lambda r: -_side_score(r))
    side_r = side_candidates[0] if side_candidates else None

    dishes = [
        {"role": "main", "role_label": "Món chính · Đạm lành tính", "recipe": main_r},
        {"role": "soup", "role_label": "Món canh · Thanh nhiệt an thần", "recipe": soup_r}
    ]
    if side_r:
        dishes.append({"role": "side", "role_label": "Món rau / phụ · Bổ sung xơ & khoáng", "recipe": side_r})

    return {
        "title": "Mâm cơm thanh nhẹ, đủ món cho Bữa tối",
        "meal_time": "dinner",
        "meal_label": "Bữa tối",
        "rationale": "Mâm cơm kết hợp cân bằng giữa món chính giàu đạm lành tính dễ tiêu, món canh thanh nhiệt an thần và rau củ giàu chất xơ cùng khoáng chất. Sự kết hợp này giúp hệ tiêu hóa không bị quá tải, hỗ trợ phục hồi và đem lại cảm giác nhẹ nhõm, dễ chịu.",
        "staple_text": "Cơm gạo lứt hạt sen hoặc cơm trắng dẻo mềm",
        "dishes": dishes
    }


def get_nutrition_options(condition: str, recipe_type: str, exclude_recipe_ids=None) -> Dict[str, Any]:
    """Filter canonical recipes first, then let Gemini select and explain IDs."""
    from core.nutrition_rules import prepare_nutrition_candidates
    from core.nutrition_ai import NutritionAIError, select_recipes

    result = _get_general_options(condition, recipe_type)
    prepared = prepare_nutrition_candidates(condition, result["recipes"])
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
    candidates = retrieve_candidates(condition, remaining)
    guidance = prepared["guidance"]
    stats = catalog_stats()
    type_count = stats["drink_count"] if recipe_type == "drink" else stats["food_count"]
    result.update(recipes=candidates, sources=guidance, excluded=prepared["excluded"][:20], excluded_count=len(prepared["excluded"]),
                  catalog=stats, catalog_type_count=type_count, eligible_count=len(eligible), considered_count=len(candidates),
                  has_more=False,
                  avoidance=prepared["avoidance"], avoidance_note=prepared["avoidance_note"],
                  limitations=prepared.get("limitations", []), gemini_used=False,
                  needs_clarification=False, clarification_question="",
                  selection_explanation="Python kiểm tra nhãn nguyên liệu và các quy tắc có nguồn trước. "
                      "Gemini chỉ được chọn và giải thích các công thức đã qua bộ lọc; không thay đổi nguyên liệu hoặc cách nấu. "
                      f'Kho hiện có {stats["total"]} công thức từ {stats["source"]}. '
                      + ("Danh mục món Việt được chọn theo tiêu chí món quen thuộc và nguyên liệu địa phương; nhãn này không chứng nhận nguồn gốc địa lý hay độ phù hợp với bệnh. " if stats["cuisine"] == "VN" else "") +
                      "Bộ tìm kiếm lấy một nhóm ứng viên liên quan từ các công thức qua bộ lọc để gửi Gemini; không gửi cả kho trong mỗi yêu cầu. "
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
    ai_fms = None
    try:
        selection = select_recipes(condition, recipe_type, candidates, guidance)
        ai_fms = selection.get("full_meal_set")
        result.update(recipes=selection["recipes"], gemini_used=True,
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
                    tags = item.get("rule_tags", [])
                    item["recommendation_reason"] = (
                        "Thức uống trong kho công thức để tham khảo khi cần bổ sung dịch; dùng lượng phù hợp với hướng dẫn cá nhân."
                        if "liquid" in tags else
                        "Món có kết cấu mềm trong kho công thức; có thể tham khảo nếu muốn ăn và dùng được các nguyên liệu."
                        if "soft" in tags else
                        "Một công thức qua bộ lọc nguyên liệu để bạn tham khảo theo sở thích.")
                    item.update(ai_caution="Đây là lựa chọn tham khảo của hệ thống, chưa được Gemini xếp hạng theo thông tin cá nhân.",
                                source_ids=[], selection_origin="guided_catalog")
                    preview.append(item)
                result.update(recipes=preview, provider_status="ai_clarification_with_options",
                              recommendation_scope="guided_catalog",
                              clarification_question="Bạn có dị ứng thực phẩm hoặc chế độ ăn riêng cần lưu ý không? Bạn có thể bổ sung để gợi ý sát hơn.",
                              notice="Bạn vẫn có thể xem các công thức tham khảo bên dưới. Gemini cần thêm thông tin để cá nhân hóa; các món này chưa được AI xếp hạng.")
            else:
                result["notice"] = "Cần thêm thông tin trước khi gợi ý món."
        else:
            result["notice"] = f'Gemini đã chọn {len(selection["recipes"])} công thức từ {len(candidates)} ứng viên liên quan trong {len(eligible)} công thức qua bộ lọc. Đây là gợi ý tham khảo, không phải chế độ ăn điều trị.'
            if not prepared["recognized"]:
                result["notice"] += " Chưa có bộ quy tắc riêng cho nội dung bạn nhập."
    except NutritionAIError as error:
        result.update(recipes=candidates[:8], provider_status="fallback_" + error.code, recommendation_scope="filtered_catalog",
                      notice="Gemini chưa trả được gợi ý hợp lệ. Bạn đang xem danh sách tham khảo qua bộ lọc Python, chưa được AI xếp hạng.")

    # Enrich every recipe with meal_time, dish_role, key_nutrients, and clinical explanation
    for r in result.get("recipes", []):
        _enrich_recipe(r, condition)

    # Build full meal set if in food mode and recipes exist
    if recipe_type == "food" and result.get("recipes"):
        full_meal = _build_full_meal_set(condition, result["recipes"], candidates, ai_fms)
        if full_meal:
            for d in full_meal["dishes"]:
                _enrich_recipe(d["recipe"], condition)
            result["full_meal_set"] = full_meal

            # Tách biệt hoàn toàn món lẻ và mâm cơm:
            # 1. Món lẻ (Các món đơn lẻ theo bữa) BẮT BUỘC là món ăn trọn vị (One-dish meals:
            #    bún, phở, mì, miến, cơm tấm, cơm chiên, cơm gà, cháo, súp, bánh cuốn, xôi...)
            #    hoặc thức uống/chè cho bữa phụ, chứ KHÔNG phải bát canh suông hay đĩa rau luộc bóc tách từ mâm cơm.
            # 2. TUYỆT ĐỐI KHÔNG chứa các món thành phần trong mâm cơm (không trùng ID hoặc tiêu đề).
            if len(result["recipes"]) >= 3 and not result.get("needs_clarification"):
                from core.recipe_catalog import is_standalone_one_dish, classify_meal_times

                fms_ids = {d["recipe"]["id"] for d in full_meal["dishes"]}
                fms_titles = {title_key(d["recipe"]) for d in full_meal["dishes"]}

                # Lấy các món ban đầu mà Gemini đã chọn thỏa mãn: không trùng mâm cơm và là món trọn vị
                initial_singles = [
                    r for r in result["recipes"]
                    if r["id"] not in fms_ids and title_key(r) not in fms_titles and is_standalone_one_dish(r)
                ]

                selected_ids = {r["id"] for r in initial_singles} | fms_ids
                selected_titles = {title_key(r) for r in initial_singles} | fms_titles

                # Bổ sung từ candidates và eligible các món lẻ trọn vị phong phú theo từng bữa (sáng, trưa, tối, phụ)
                available_pool = [
                    c for c in candidates + eligible
                    if is_standalone_one_dish(c) and c["id"] not in selected_ids and title_key(c) not in selected_titles
                ]

                target_meals = ["breakfast", "lunch", "dinner", "snack"]
                for target_meal in target_meals:
                    if len(initial_singles) >= 5:
                        break
                    for cand in available_pool:
                        cand_meals = cand.get("possible_meals") or classify_meal_times(cand)
                        if target_meal in cand_meals and cand["id"] not in selected_ids and title_key(cand) not in selected_titles:
                            cand_copy = deepcopy(cand)
                            cand_copy["meal_time"] = target_meal
                            _enrich_recipe(cand_copy, condition)
                            initial_singles.append(cand_copy)
                            selected_ids.add(cand["id"])
                            selected_titles.add(title_key(cand))
                            break

                for cand in available_pool:
                    if len(initial_singles) >= 5:
                        break
                    if cand["id"] not in selected_ids and title_key(cand) not in selected_titles:
                        cand_copy = deepcopy(cand)
                        _enrich_recipe(cand_copy, condition)
                        initial_singles.append(cand_copy)
                        selected_ids.add(cand["id"])
                        selected_titles.add(title_key(cand))

                if len(initial_singles) < 4:
                    for r in result["recipes"]:
                        if r["id"] not in selected_ids and title_key(r) not in selected_titles:
                            initial_singles.append(r)
                            selected_ids.add(r["id"])
                            selected_titles.add(title_key(r))
                            if len(initial_singles) >= 5:
                                break

                if initial_singles:
                    result["recipes"] = initial_singles

    result["has_more"] = bool(result["recipes"]) and len({title_key(r) for r in remaining}) > len(result["recipes"])
    return result
