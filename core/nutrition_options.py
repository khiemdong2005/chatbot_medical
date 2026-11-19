"""Gợi ý công thức để người dùng tự chọn, không thay thế tư vấn dinh dưỡng."""
from copy import deepcopy
from datetime import datetime, date
import math
import re
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

FATTY_LIVER_FOOD = [
    _recipe("fl_steamed_fish", "Cá hấp gừng", "🐟", "Cá hấp không chiên", "25 phút",
        "Cá cung cấp đạm.",
        [_i("Cá diêu hồng", 100, "g", "🐟"), _i("Gừng", 10, "g", "🫚"),
         _i("Nước lọc", 100, "ml", "💧")],
        ["Rửa sạch cá và gừng; thái gừng thành lát mỏng.",
         "Hấp cá với gừng đến khi cá chín hoàn toàn.",
         "Dùng cá khi còn ấm; nêm nhẹ theo hướng dẫn cá nhân."],
        ["Không dùng nếu dị ứng cá; kiểm tra khẩu phần và cách nêm trước khi ăn."]),
    _recipe("fl_chicken_vegetables", "Ức gà luộc rau củ", "🍗", "Ức gà và rau củ luộc", "25 phút",
        "Ức gà cung cấp đạm; rau củ bổ sung chất xơ.",
        [_i("Thịt ức gà", 100, "g", "🍗"), _i("Bông cải xanh", 100, "g", "🥦"),
         _i("Cà rốt", 60, "g", "🥕"), _i("Nước lọc", 300, "ml", "💧")],
        ["Rửa sạch ức gà và rau củ; cắt rau thành miếng vừa ăn.",
         "Luộc ức gà đến khi chín hoàn toàn, để nguội bớt rồi thái miếng.",
         "Luộc rau củ vừa chín, dùng cùng gà và nêm nhẹ theo hướng dẫn cá nhân."],
        ["Điều chỉnh khẩu phần theo nhu cầu và hướng dẫn cá nhân."]),
    _recipe("fl_tofu_tomato", "Đậu hũ sốt cà chua", "🍅", "Đậu hũ nấu cà chua không chiên", "20 phút",
        "Đậu hũ cung cấp đạm thực vật; cà chua là một loại rau quả.",
        [_i("Đậu hũ non", 120, "g", "🫘"), _i("Cà chua", 100, "g", "🍅"),
         _i("Nước lọc", 80, "ml", "💧")],
        ["Rửa cà chua, cắt nhỏ; cắt đậu hũ thành miếng vừa ăn.",
         "Nấu cà chua với nước đến khi mềm, cho đậu hũ vào.",
         "Nấu sôi nhẹ đến khi đậu hũ nóng đều; nêm nhẹ theo hướng dẫn cá nhân."],
        ["Không dùng nếu dị ứng đậu nành; kiểm tra thành phần đậu hũ đóng gói."]),
    _recipe("fl_winter_melon_soup", "Canh bí xanh nấm", "🍲", "Canh rau nấm nấu nhẹ", "20 phút",
        "Bí xanh và nấm góp phần bổ sung rau trong bữa ăn.",
        [_i("Bí xanh", 150, "g", "🥒"), _i("Nấm rơm", 60, "g", "🍄"),
         _i("Nước lọc", 300, "ml", "💧")],
        ["Gọt vỏ, rửa và cắt bí xanh; rửa sạch nấm.",
         "Nấu bí xanh với nước đến khi gần mềm, thêm nấm.",
         "Nấu chín nấm, nêm nhẹ rồi dùng khi còn ấm."],
        ["Điều chỉnh lượng muối và khẩu phần theo hướng dẫn cá nhân."]),
    _recipe("fl_steamed_greens", "Rau cải hấp", "🥬", "Rau hấp đơn giản", "12 phút",
        "Rau cải bổ sung chất xơ trong bữa ăn.",
        [_i("Cải thìa", 150, "g", "🥬"), _i("Nước lọc", 150, "ml", "💧")],
        ["Rửa sạch và cắt cải thìa thành miếng vừa ăn.",
         "Hấp rau đến khi chín vừa.",
         "Dùng cùng món chính và nêm nhẹ theo hướng dẫn cá nhân."],
        ["Điều chỉnh lượng muối theo hướng dẫn cá nhân."]),
    _recipe("fl_oat_vegetable_porridge", "Cháo yến mạch rau củ", "🥣", "Cháo yến mạch không thêm đường", "20 phút",
        "Yến mạch và rau củ cung cấp chất xơ.",
        [_i("Yến mạch", 45, "g", "🌾"), _i("Cà rốt", 50, "g", "🥕"),
         _i("Cải bó xôi", 40, "g", "🥬"), _i("Nước lọc", 350, "ml", "💧")],
        ["Rửa, cắt nhỏ cà rốt và cải bó xôi.",
         "Nấu yến mạch với nước và cà rốt đến khi mềm.",
         "Thêm cải bó xôi, nấu chín rồi để nguội bớt trước khi dùng."],
        ["Nếu cần tránh gluten, chỉ dùng yến mạch đã được xác minh phù hợp."]),
    _recipe("fl_brown_rice_chicken", "Cơm gạo lứt ức gà rau xanh", "🍚", "Bữa cơm với gạo lứt và rau", "35 phút",
        "Gạo lứt cung cấp ngũ cốc nguyên hạt; ức gà và rau bổ sung đạm và chất xơ.",
        [_i("Gạo lứt", 60, "g", "🍚"), _i("Thịt ức gà", 80, "g", "🍗"),
         _i("Cải thìa", 100, "g", "🥬"), _i("Nước lọc", 250, "ml", "💧")],
        ["Vo gạo lứt và nấu chín với nước theo loại gạo đang dùng.",
         "Luộc ức gà đến khi chín hoàn toàn rồi thái miếng.",
         "Luộc cải thìa vừa chín; dùng cùng cơm và gà, nêm nhẹ theo hướng dẫn cá nhân."],
        ["Khẩu phần gạo và đạm cần điều chỉnh theo hướng dẫn cá nhân."]),
]
_FATTY_LIVER_EN = {
    "fl_steamed_fish": {
        "title": "Ginger-steamed fish", "subtitle": "Steamed fish; no frying",
        "benefit": "Fish provides protein.",
        "ingredients": ["Red tilapia", "Ginger", "Water"],
        "steps": ["Wash the fish and ginger; slice the ginger.",
                  "Steam the fish with ginger until fully cooked.",
                  "Serve the fish warm and season lightly as personally advised."],
        "avoid": ["Avoid if you have a fish allergy; review portion size and seasoning before eating."],
    },
    "fl_chicken_vegetables": {
        "title": "Boiled chicken breast with vegetables", "subtitle": "Boiled chicken breast and vegetables",
        "benefit": "Chicken breast provides protein; vegetables add fiber.",
        "ingredients": ["Chicken breast", "Broccoli", "Carrot", "Water"],
        "steps": ["Wash the chicken and vegetables; cut the vegetables into bite-sized pieces.",
                  "Boil the chicken until fully cooked, let it cool slightly, then slice it.",
                  "Boil the vegetables until tender; serve with chicken and season lightly as personally advised."],
        "avoid": ["Adjust the portion to your needs and personal dietary advice."],
    },
    "fl_tofu_tomato": {
        "title": "Silken tofu in tomato sauce", "subtitle": "Tofu simmered with tomato, without frying",
        "benefit": "Tofu provides plant protein; tomato is a vegetable ingredient.",
        "ingredients": ["Silken tofu", "Tomato", "Water"],
        "steps": ["Wash and chop the tomato; cut tofu into bite-sized pieces.",
                  "Simmer the tomato in water until soft, then add the tofu.",
                  "Simmer gently until the tofu is heated through; season lightly as personally advised."],
        "avoid": ["Avoid if you have a soy allergy; check the ingredients of packaged tofu."],
    },
    "fl_winter_melon_soup": {
        "title": "Winter melon and mushroom soup", "subtitle": "Light vegetable and mushroom soup",
        "benefit": "Winter melon and mushrooms add vegetables to the meal.",
        "ingredients": ["Winter melon", "Straw mushrooms", "Water"],
        "steps": ["Peel, wash, and cut the winter melon; wash the mushrooms.",
                  "Simmer the winter melon in water until almost tender, then add the mushrooms.",
                  "Cook the mushrooms fully; season lightly and serve warm."],
        "avoid": ["Adjust salt and portion size according to personal dietary advice."],
    },
    "fl_steamed_greens": {
        "title": "Steamed bok choy", "subtitle": "Simple steamed greens",
        "benefit": "Greens add fiber to a meal.", "ingredients": ["Bok choy", "Water"],
        "steps": ["Wash and cut the bok choy into bite-sized pieces.",
                  "Steam the greens until tender.",
                  "Serve alongside a main dish and season lightly as personally advised."],
        "avoid": ["Adjust salt according to personal dietary advice."],
    },
    "fl_oat_vegetable_porridge": {
        "title": "Savory oat and vegetable porridge", "subtitle": "Oat porridge without added sugar",
        "benefit": "Oats and vegetables provide fiber.",
        "ingredients": ["Oats", "Carrot", "Spinach", "Water"],
        "steps": ["Wash and chop the carrot and spinach.",
                  "Cook the oats with water and carrot until soft.",
                  "Add the spinach, cook thoroughly, then let cool slightly before serving."],
        "avoid": ["If you must avoid gluten, use only oats verified as suitable for you."],
    },
    "fl_brown_rice_chicken": {
        "title": "Brown rice with chicken breast and greens", "subtitle": "Brown rice meal with vegetables",
        "benefit": "Brown rice is a whole grain; chicken breast and greens provide protein and fiber.",
        "ingredients": ["Brown rice", "Chicken breast", "Bok choy", "Water"],
        "steps": ["Rinse and cook the brown rice with water according to the rice package.",
                  "Boil the chicken breast until fully cooked, then slice it.",
                  "Boil the bok choy until tender; serve with the rice and chicken, seasoning lightly as personally advised."],
        "avoid": ["Adjust rice and protein portions according to personal dietary advice."],
    },
}
for _item in FATTY_LIVER_FOOD:
    _item["recipe_type"] = "food"
    _item["source_provider"] = "MediMind · công thức tham khảo"
    _item["translations"] = {"en": _FATTY_LIVER_EN[_item["id"]]}
    _item["dish_role"] = {
        "fl_steamed_fish": "main", "fl_chicken_vegetables": "main", "fl_tofu_tomato": "main",
        "fl_winter_melon_soup": "soup", "fl_steamed_greens": "side",
        "fl_oat_vegetable_porridge": "staple", "fl_brown_rice_chicken": "staple",
    }[_item["id"]]

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
    """Add display labels and a modest explanation without inventing benefits."""
    from core.recipe_catalog import classify_dish_role, classify_meal_times, is_standalone_one_dish

    role = recipe.get("dish_role")
    if role not in _ROLE_LABELS:
        role = classify_dish_role(recipe)
        recipe["dish_role"] = role
    if is_standalone_one_dish(recipe):
        recipe["dish_role_label"] = "Món ăn trọn vị" if recipe.get("recipe_type") != "drink" else "Thức uống"
    else:
        recipe["dish_role_label"] = _ROLE_LABELS.get(role, "Món ăn")
    possible_meals = classify_meal_times(recipe, role)
    recipe["possible_meals"] = possible_meals
    meal_time = recipe.get("meal_time")
    if meal_time not in _MEAL_LABELS:
        meal_time = possible_meals[0] if possible_meals else "dinner"
        recipe["meal_time"] = meal_time
    recipe["meal_label"] = _MEAL_LABELS.get(meal_time, "Bữa ăn")

    # Nutrient-specific claims from prose or a model are not verified by the
    # source table. The numeric source values remain available separately.
    recipe["key_nutrients"] = ""
    reason = str(recipe.get("recommendation_reason") or "").strip()
    if not reason or reason.lower() == "none":
        tags = recipe.get("rule_tags") or []
        if "soft" in tags:
            reason = "Món có kết cấu mềm và đã qua bộ lọc nguyên liệu theo mô tả bạn nhập."
        elif "liquid" in tags:
            if recipe.get("recipe_type") == "drink":
                reason = "Thức uống đã qua bộ lọc nguyên liệu theo mô tả bạn nhập."
            else:
                reason = "Món canh súp/dạng nước dễ dùng, đã qua bộ lọc nguyên liệu theo mô tả bạn nhập."
        else:
            reason = "Công thức đã qua bộ lọc nguyên liệu theo mô tả bạn nhập; kiểm tra khẩu phần và cách nêm trước khi dùng."
    recipe["recommendation_reason"] = reason


def _is_valid_main(r: Dict) -> bool:
    if not r:
        return False
    title = str(r.get("title", "")).lower()
    if any(k in title for k in ["canh ", "canh:", "súp", "sup", "cháo", "chao", "lẩu", "bún", "phở", "hủ tiếu", "mì ", "miến", "bánh canh", "nui", "chè ", "trà ", "sữa ", "bánh mì baguette", "nước mắm", "gia vị", "nước chấm", "bánh tro", "bánh ít", "bánh ngọt", "caramel", "pudding"]):
        return False
    from core.recipe_catalog import classify_dish_role
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
    from core.recipe_catalog import classify_dish_role
    role = r.get("dish_role") or classify_dish_role(r)
    return bool(re.search(r"\b(canh|súp)\b", t)) or role == "soup"


def _extract_main_ingredient_tags(recipe: Dict) -> set:
    if not recipe:
        return set()
    text = (str(recipe.get("title", "")) + " " + " ".join(str(i.get("name", "")) for i in recipe.get("ingredients", []))).lower()
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
    from core.recipe_catalog import classify_dish_role
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
                    "meal_time": ai_fms.get("meal_time", "dinner"),
                    "meal_label": _MEAL_LABELS.get(ai_fms.get("meal_time", "dinner"), "Bữa tối"),
                    "rationale": ai_fms.get("rationale", "Các món được ghép từ những công thức qua bộ lọc nguyên liệu; cần kiểm tra khẩu phần và cách nêm trước khi dùng."),
                    "staple_text": ai_fms.get("staple_text") or "Cơm gạo lứt hạt sen hoặc cơm trắng dẻo mềm",
                    "dishes": dishes
                }

    main_candidates = [r for r in recipes if _is_valid_main(r)] or [r for r in candidates if _is_valid_main(r)]
    main_candidates.sort(key=lambda r: -_main_score(r))
    soup_candidates = [r for r in recipes if _is_valid_soup(r)] or [r for r in candidates if _is_valid_soup(r)]

    # Mâm cơm 1 bữa chuẩn vị: BẮT BUỘC đủ 3 món: Món chính + Món canh + Món rau / phụ
    if main_candidates and soup_candidates:
        main_r = main_candidates[0]
        soup_filtered = [r for r in soup_candidates if r.get("id") != main_r.get("id")]
        if soup_filtered:
            soup_r = soup_filtered[0]
            side_candidates = [r for r in recipes if _is_valid_side(r, main_r["id"], soup_r["id"], main_r, soup_r)] or [r for r in candidates if _is_valid_side(r, main_r["id"], soup_r["id"], main_r, soup_r)]
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
                    "meal_time": "dinner",
                    "meal_label": "Bữa tối",
                    "rationale": "Các món được ghép từ những công thức qua bộ lọc nguyên liệu; cần kiểm tra khẩu phần và cách nêm trước khi dùng.",
                    "staple_text": "Cơm gạo lứt hạt sen hoặc cơm trắng dẻo mềm",
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
    from core.nutrition_rules import ALLERGEN_NAMES
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
    meal["rationale"] = (f"Ghép {composition} từ các công thức qua bộ lọc nguyên liệu{constraint_text}{allergy_text}. "
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
    from core.nutrition_rules import prepare_nutrition_candidates
    from core.nutrition_ai import NutritionAIError, select_recipes

    result = _get_general_options(condition, recipe_type)
    profile = profile if isinstance(profile, dict) else {}
    prepared = prepare_nutrition_candidates(condition, result["recipes"], profile.get("allergies"),
                                            fatty_liver_recipes=FATTY_LIVER_FOOD if recipe_type == "food" else None)
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
    if recipe_type == "food" and "fatty_liver" in prepared["contexts"]:
        curated_ids = {recipe["id"] for recipe in FATTY_LIVER_FOOD}
        curated = [recipe for recipe in remaining if recipe["id"] in curated_ids]
        candidates = (curated + [recipe for recipe in candidates if recipe["id"] not in curated_ids])[:32]
    if "no_added_sugar" in prepared.get("preference_codes", []):
        candidates.sort(key=lambda r: (not isinstance(r.get("sugar"), (int, float)),
                                       r.get("sugar") if isinstance(r.get("sugar"), (int, float)) else float("inf")))
    guidance = prepared["guidance"]
    stats = catalog_stats()
    if recipe_type == "food" and "fatty_liver" in prepared["contexts"]:
        stats = {"imported_count": 0, "food_count": len(FATTY_LIVER_FOOD), "drink_count": 0,
                 "total": len(FATTY_LIVER_FOOD), "source": "MediMind",
                 "cuisine": "VN", "license": "project_samples"}
    type_count = stats["drink_count"] if recipe_type == "drink" else stats["food_count"]
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
    if recipe_type == "food" and "fatty_liver" in prepared["contexts"]:
        # These locally authored dishes have complete, fixed ingredient lists.
        # Show them directly; model ranking is unnecessary for this small set.
        for recipe in candidates:
            recipe["recommendation_reason"] = (
                "Công thức qua bộ lọc nguyên liệu tham khảo cho gan nhiễm mỡ; "
                "chưa xác nhận phù hợp với khẩu phần hoặc bệnh nền của bạn."
            )
            _enrich_recipe(recipe, condition)
        full_meal = _build_full_meal_set(condition, candidates, candidates)
        meal_ids = set()
        if full_meal:
            for dish in full_meal["dishes"]:
                meal_ids.add(dish["recipe"]["id"])
            _meal_calories(full_meal, prepared)
            result["full_meal_set"] = full_meal
        result.update(
            recipes=[recipe for recipe in candidates if recipe["id"] not in meal_ids],
            matched=True, has_condition_notes=True,
            provider_status="guided_catalog", recommendation_scope="guided_catalog", has_more=False,
            notice="Đây là công thức tham khảo được biên soạn với nguyên liệu rõ ràng và đã lọc dị ứng được nhận diện. "
                   "Hướng dẫn NIDDK dành cho gan nhiễm mỡ không do rượu; chưa xác nhận từng món phù hợp với nguyên nhân bệnh, mức độ bệnh hoặc khẩu phần cá nhân.",
            selection_explanation="MediMind đối chiếu danh sách nguyên liệu cố định với dị ứng đã khai báo và các nguyên tắc ăn uống chung có nguồn. "
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
                    tags = item.get("rule_tags", [])
                    item["recommendation_reason"] = (
                        "Thức uống trong kho công thức để tham khảo khi cần bổ sung dịch; dùng lượng phù hợp với hướng dẫn cá nhân."
                        if "liquid" in tags else
                        "Món có kết cấu mềm trong kho công thức; có thể tham khảo nếu muốn ăn và dùng được các nguyên liệu."
                        if "soft" in tags else
                        "Một công thức qua bộ lọc nguyên liệu để bạn tham khảo theo sở thích.")
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
            result["notice"] = f'AI đã chọn {len(selection["recipes"])} công thức từ {len(candidates)} ứng viên liên quan trong {len(eligible)} công thức qua bộ lọc. Đây là gợi ý tham khảo, không phải chế độ ăn điều trị.'
            if not prepared["recognized"]:
                result["notice"] += " Chưa có bộ quy tắc riêng cho nội dung bạn nhập."
    except NutritionAIError as error:
        result.update(recipes=candidates[:8], provider_status="fallback_" + error.code,
                      gemini_used=False, ai_used=False, recommendation_scope="filtered_catalog",
                      selection_explanation="Danh sách tham khảo được lấy từ kho công thức và lọc bằng Python theo yêu cầu của bạn. AI chưa xếp hạng các món này.",
                      notice="AI tạm thời chưa thể xếp hạng món ăn. Hệ thống đang hiển thị các gợi ý tham khảo đã được lọc theo yêu cầu của bạn.")

    # Enrich every recipe with meal_time, dish_role, key_nutrients, and clinical explanation
    for r in result.get("recipes", []):
        if "fatty_liver" in prepared["contexts"]:
            r["recommendation_reason"] = ("Công thức qua bộ lọc nguyên liệu tham khảo cho gan nhiễm mỡ; "
                                          "chưa xác nhận phù hợp với khẩu phần hoặc bệnh nền của bạn.")
        _enrich_recipe(r, condition)

    # Build full meal set if in food mode and recipes exist (require at least 2 recipes or explicit AI meal set)
    if recipe_type == "food" and result.get("recipes") and (ai_fms or len(result["recipes"]) >= 2):
        full_meal = _build_full_meal_set(condition, result["recipes"], candidates, ai_fms)
        if full_meal:
            for d in full_meal["dishes"]:
                _enrich_recipe(d["recipe"], condition)
            _meal_calories(full_meal, prepared)
            result["full_meal_set"] = full_meal

            from core.recipe_catalog import is_standalone_one_dish, classify_meal_times

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
                        _enrich_recipe(cand_copy, condition)
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
                    _enrich_recipe(cand_copy, condition)
                    singles.append(cand_copy)
                    selected_ids.add(cand["id"])
                    selected_titles.add(title_key(cand))

            result["recipes"] = singles
        else:
            result["full_meal_set"] = None
    else:
        result["full_meal_set"] = None

    result["has_more"] = bool(result["recipes"]) and len({title_key(r) for r in remaining}) > len(result["recipes"])
    return result
