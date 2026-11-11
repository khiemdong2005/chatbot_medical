"""Gợi ý công thức để người dùng tự chọn, không thay thế tư vấn dinh dưỡng."""
from copy import deepcopy
from typing import Any, Dict
import unicodedata


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


def get_nutrition_options(condition: str, recipe_type: str) -> Dict[str, Any]:
    """Filter canonical recipes first, then let Gemini select and explain IDs."""
    from core.nutrition_rules import prepare_nutrition_candidates
    from core.nutrition_ai import NutritionAIError, select_recipes

    result = _get_general_options(condition, recipe_type)
    prepared = prepare_nutrition_candidates(condition, result["recipes"])
    candidates = prepared["recipes"]
    guidance = prepared["guidance"]
    result.update(recipes=candidates, sources=guidance, excluded=prepared["excluded"],
                  avoidance=prepared["avoidance"], avoidance_note=prepared["avoidance_note"],
                  limitations=prepared.get("limitations", []), gemini_used=False,
                  needs_clarification=False, clarification_question="",
                  selection_explanation="Python kiểm tra nhãn nguyên liệu và các quy tắc có nguồn trước. "
                      "Gemini chỉ được chọn và giải thích các công thức đã qua bộ lọc; không thay đổi nguyên liệu hoặc cách nấu. "
                      "Kho hiện có 14 công thức soạn sẵn, chưa nhập RecipeNLG. Việc được gợi ý không xác nhận phù hợp y khoa.")
    if not candidates:
        result.update(provider_status="no_candidates", recommendation_scope="filtered_catalog",
                      needs_clarification=True,
                      clarification_question="Chưa có công thức đáp ứng những giới hạn bạn nhập. Bạn có thể bổ sung loại thực phẩm dùng được không?",
                      notice="Không có món trong kho hiện tại vượt qua bộ lọc nguyên liệu; hệ thống không tự thêm món khác.")
        return result
    try:
        selection = select_recipes(condition, recipe_type, candidates, guidance)
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
            result["notice"] = f'Gemini đã chọn {len(selection["recipes"])} công thức từ {len(candidates)} lựa chọn qua bộ lọc. Đây là gợi ý tham khảo, không phải chế độ ăn điều trị.'
            if not prepared["recognized"]:
                result["notice"] += " Chưa có bộ quy tắc riêng cho nội dung bạn nhập."
    except NutritionAIError as error:
        result.update(provider_status="fallback_" + error.code, recommendation_scope="filtered_catalog",
                      notice="Gemini chưa trả được gợi ý hợp lệ. Bạn đang xem danh sách tham khảo qua bộ lọc Python, chưa được AI xếp hạng.")
    return result
