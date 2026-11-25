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

_DRINK_BASE_CALORIES = {
    "warm_water": (0, 0),
    "warm_milk": (120, 0),
    "oat_drink": (95, 1),
    "cucumber_water": (15, 0),
    "warm_soy": (85, 2),
    "pear_water": (60, 10),
    "barley_water": (65, 1),
}
for _drink_item in DRINK:
    _cal_val, _sug_val = _DRINK_BASE_CALORIES.get(_drink_item["id"], (80, 0))
    _drink_item["recipe_type"] = "drink"
    _drink_item["calories"] = _cal_val
    _drink_item["sugar"] = _sug_val
    _drink_item["servings"] = "1 ly (250ml)"
    _drink_item["calories_basis"] = "per_serving"

GOUT_DRINKS = [
    {
        **_recipe(
            "gout_celery_juice",
            "Nước ép cần tây táo xanh",
            "🥬",
            "Ít purin, giàu vitamin C · hỗ trợ bù nước",
            "8 phút",
            "Cần tây và táo xanh hầu như không chứa nhân purin, giúp bổ sung nước và vitamin C nhẹ nhàng.",
            [_i("Cần tây", 80, "g", "🥬"), _i("Táo xanh", 80, "g", "🍏"), _i("Nước lọc", 150, "ml", "💧")],
            ["Rửa sạch cần tây và táo xanh, cắt khúc vừa máy ép.",
             "Ép lấy nước (hoặc xay cùng 150ml nước lọc rồi lọc bỏ bã).",
             "Không thêm đường tinh luyện; dùng tươi ngay sau khi pha."],
            ["Kiểm tra khẩu phần trái cây nếu bạn đồng thời cần kiểm soát đường huyết."]
        ),
        "recipe_type": "drink", "calories": 55, "sugar": 6,
        "servings": "1 ly (250ml)", "calories_basis": "per_serving",
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Celery & green apple juice",
            "subtitle": "Low-purine, vitamin-C-rich hydration",
            "benefit": "Celery and green apple are naturally low in purines and add light hydration and vitamin C.",
            "ingredients": ["Celery", "Green apple", "Water"],
            "steps": ["Wash the celery and green apple thoroughly and chop.",
                      "Juice together or blend with water and strain.",
                      "Serve fresh without added refined sugar."],
            "avoid": ["Monitor fruit portions if you also manage blood sugar."],
        }},
    },
    {
        **_recipe(
            "gout_cucumber_lemon",
            "Nước ép dưa leo chanh tươi ít đường",
            "🥒",
            "Thanh mát, lợi tiểu · không đường thêm",
            "6 phút",
            "Dưa leo giàu nước kết hợp chanh tươi bổ sung vitamin C và hỗ trợ đào thải dịch.",
            [_i("Dưa leo", 120, "g", "🥒"), _i("Chanh tươi", 10, "ml", "🍋"), _i("Nước lọc", 200, "ml", "💧")],
            ["Rửa sạch dưa leo (giữ hoặc gọt vỏ tùy ý), thái lát.",
             "Xay nhuyễn cùng 200ml nước lọc rồi lọc qua rây.",
             "Thêm nước cốt chanh tươi, khuấy đều và uống mát."],
            ["Tránh nếu bạn đang đau dạ dày cấp hoặc nhạy cảm với vị chua của chanh."]
        ),
        "recipe_type": "drink", "calories": 45, "sugar": 3,
        "servings": "1 ly (250ml)", "calories_basis": "per_serving",
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Light cucumber & fresh lemon juice",
            "subtitle": "Hydrating, refreshing · no added sugar",
            "benefit": "Cucumber provides hydration while fresh lemon adds vitamin C without extra sugar.",
            "ingredients": ["Cucumber", "Fresh lemon", "Water"],
            "steps": ["Wash and slice the cucumber.",
                      "Blend with 200ml filtered water and strain through a sieve.",
                      "Stir in fresh lemon juice and serve cool."],
            "avoid": ["Avoid if you have active gastritis or acid reflux sensitivity."],
        }},
    },
    {
        **_recipe(
            "gout_cherry_juice",
            "Nước ép anh đào (Cherry) không đường",
            "🍒",
            "Giàu vitamin C & polyphenol tự nhiên",
            "8 phút",
            "Quả anh đào (cherry) chứa ít purin và giàu vitamin C cùng chất chống oxy hóa thực vật.",
            [_i("Quả anh đào (Cherry)", 120, "g", "🍒"), _i("Nước lọc", 180, "ml", "💧")],
            ["Rửa sạch quả anh đào, bỏ cuống và tách hạt.",
             "Xay nhuyễn với 180ml nước lọc.",
             "Lọc lấy nước ép hoặc uống cả phần xác mịn; không thêm đường."],
            ["Không thêm đường hay siro ngọt để tránh tăng tải fructose không cần thiết."]
        ),
        "recipe_type": "drink", "calories": 85, "sugar": 12,
        "servings": "1 ly (250ml)", "calories_basis": "per_serving",
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Unsweetened tart cherry drink",
            "subtitle": "Low-purine fruit · natural vitamin C",
            "benefit": "Cherries are naturally low in purines and provide vitamin C and plant polyphenols.",
            "ingredients": ["Cherries", "Water"],
            "steps": ["Wash, stem, and pit the cherries.",
                      "Blend smoothly with 180ml filtered water.",
                      "Strain if desired and drink without added sugar."],
            "avoid": ["Do not add sugar or sweet syrups to keep fructose intake modest."],
        }},
    },
    {
        **_recipe(
            "gout_light_green_tea",
            "Trà xanh nhạt pha loãng",
            "🍵",
            "Thức uống thảo mộc thanh nhẹ, lợi tiểu",
            "7 phút",
            "Trà xanh pha loãng giúp bổ sung nước và chất chống oxy hóa mà gần như không nạp purin.",
            [_i("Lá trà xanh tươi", 5, "g", "🍵"), _i("Nước nóng", 250, "ml", "💧")],
            ["Rửa sạch lá trà xanh, vò nhẹ.",
             "Tráng nhanh qua nước nóng rồi hãm với 250ml nước nóng 80°C khoảng 3 phút.",
             "Chắt lấy nước trà nhạt để uống trong ngày; tránh uống quá đặc hoặc gần giờ ngủ."],
            ["Tránh dùng vào buổi tối muộn nếu bạn nhạy cảm với caffeine hoặc dễ mất ngủ."]
        ),
        "recipe_type": "drink", "calories": 15, "sugar": 0,
        "servings": "1 ly (250ml)", "calories_basis": "per_serving",
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Lightly brewed green tea",
            "subtitle": "Mild diuretic hydration · zero sugar",
            "benefit": "Dilute green tea supports daily hydration without purine load or added sugars.",
            "ingredients": ["Fresh green tea leaves", "Hot water"],
            "steps": ["Rinse fresh green tea leaves gently.",
                      "Steep briefly in 250ml hot water (about 80°C) for 3 minutes.",
                      "Pour out a light infusion and avoid drinking close to bedtime."],
            "avoid": ["Avoid late at night if you are sensitive to caffeine or insomnia."],
        }},
    },
    {
        **_recipe(
            "gout_orange_carrot",
            "Nước ép cam cà rốt không đường",
            "🍊",
            "Bổ sung vitamin C & beta-carotene tự nhiên",
            "10 phút",
            "Cam tươi giàu vitamin C kết hợp cà rốt ít purin, tạo thức uống cân bằng tự nhiên.",
            [_i("Cam tươi", 100, "g", "🍊"), _i("Cà rốt", 70, "g", "🥕"), _i("Nước lọc", 120, "ml", "💧")],
            ["Gọt vỏ cam, bỏ hạt; rửa sạch, gọt vỏ cà rốt.",
             "Ép cà rốt với cam tươi, pha thêm 120ml nước lọc để giảm độ đậm.",
             "Khuấy đều và dùng không thêm đường."],
            ["Hạn chế nếu bạn đang bị trào ngược dạ dày hoặc viêm loét dạ dày nhạy cảm với cam."]
        ),
        "recipe_type": "drink", "calories": 95, "sugar": 14,
        "servings": "1 ly (250ml)", "calories_basis": "per_serving",
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Unsweetened orange & carrot juice",
            "subtitle": "Vitamin C & low-purine vegetable blend",
            "benefit": "Fresh orange provides vitamin C alongside low-purine carrot hydration.",
            "ingredients": ["Fresh orange", "Carrot", "Water"],
            "steps": ["Peel and seed the orange; wash and peel the carrot.",
                      "Juice both together and dilute with 120ml filtered water.",
                      "Stir well and serve without added sugar."],
            "avoid": ["Limit if you have active acid reflux or gastritis triggered by citrus."],
        }},
    },
]

GOUT_FOODS = [
    {
        **_recipe(
            "gout_egg_tomato",
            "Trứng gà bác cà chua ít dầu",
            "🍳",
            "Đạm ít purin từ trứng · loại trừ thịt, hải sản, đậu",
            "12 phút",
            "Trứng gà cung cấp protein ít nhân purin thay thế thịt và hải sản cho người bệnh Gút.",
            [_i("Trứng gà", 2, "quả", "🥚"), _i("Cà chua", 100, "g", "🍅"), _i("Hành lá", 10, "g", "🌿"), _i("Dầu thực vật", 5, "ml", "🫒")],
            ["Rửa sạch cà chua, bỏ hạt và thái múi cau hoặc băm nhỏ; đánh tan trứng gà.",
             "Xào nhẹ cà chua với chút dầu thực vật và ít nước đến khi mềm.",
             "Cho trứng vào đảo nhẹ lửa vừa đến khi chín tới, thêm hành lá rồi dùng nóng."],
            ["Tránh dùng nếu bạn dị ứng trứng; giữ lượng dầu ít khi chế biến."]
        ),
        "recipe_type": "food", "dish_role": "main", "calories": 210, "sugar": 3,
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Lightly cooked eggs with tomato",
            "subtitle": "Low-purine protein · free of poultry, red meat, seafood & beans",
            "benefit": "Eggs provide a very low-purine protein alternative for gout management.",
            "ingredients": ["Chicken eggs", "Tomato", "Scallion", "Vegetable oil"],
            "steps": ["Wash and chop the tomatoes; beat the eggs lightly.",
                      "Simmer tomatoes gently with a touch of oil and water until soft.",
                      "Fold in the eggs until cooked through, top with scallions, and serve warm."],
            "avoid": ["Avoid if allergic to eggs."],
        }},
    },
    {
        **_recipe(
            "gout_steamed_egg_veggies",
            "Trứng hấp cà rốt rau củ",
            "🥚",
            "Món chính hấp nhẹ, không dầu chiên · ít purin",
            "15 phút",
            "Trứng hấp cùng cà rốt giúp bổ sung đạm và vitamin mà không làm tăng acid uric.",
            [_i("Trứng gà", 2, "quả", "🥚"), _i("Cà rốt", 50, "g", "🥕"), _i("Nước ấm", 100, "ml", "💧")],
            ["Cà rốt gọt vỏ, thái hạt lựu rất nhỏ và trụng chín sơ.",
             "Đánh tan trứng với 100ml nước ấm, rây mịn rồi trộn cà rốt.",
             "Hấp cách thủy lửa nhỏ 10 phút đến khi trứng chín mềm hoàn toàn."],
            ["Tránh dùng nếu bạn dị ứng trứng."]
        ),
        "recipe_type": "food", "dish_role": "main", "calories": 195, "sugar": 2,
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Steamed egg custard with carrot",
            "subtitle": "Steamed low-purine main · no frying",
            "benefit": "Steamed eggs and carrots deliver gentle protein without high-purine meats.",
            "ingredients": ["Chicken eggs", "Carrot", "Warm water"],
            "steps": ["Finely dice and parboil the carrot.",
                      "Whisk eggs with warm water, strain, and stir in carrots.",
                      "Steam gently for 10 minutes until set."],
            "avoid": ["Avoid if allergic to eggs."],
        }},
    },
    {
        **_recipe(
            "gout_braised_eggplant",
            "Cà tím kho tiêu xanh ít dầu",
            "🍆",
            "Món mặn thanh đạm từ rau củ & nấm · ít purin",
            "18 phút",
            "Cà tím và nấm nấu nhạt cung cấp chất xơ, không chứa đạm động vật hay đậu hạt giàu purin.",
            [_i("Cà tím", 180, "g", "🍆"), _i("Nấm hương", 40, "g", "🍄"), _i("Hành lá", 10, "g", "🌿"), _i("Nước lọc", 100, "ml", "💧")],
            ["Cà tím rửa sạch cắt khúc ngâm nước muối loãng rồi vớt ráo; nấm hương ngâm mềm.",
             "Kho cà tím và nấm với 100ml nước lọc, nêm nhạt vừa ăn.",
             "Đun nhỏ lửa đến khi cà chín mềm thấm vị, rắc hành lá."],
            ["Nêm nhạt muối và ít gia vị cay nóng nếu đang có bệnh nền kèm theo."]
        ),
        "recipe_type": "food", "dish_role": "main", "calories": 155, "sugar": 3,
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Light braised eggplant with shiitake",
            "subtitle": "Plant-based low-purine main · oil-light preparation",
            "benefit": "Eggplant adds fiber with minimal purine load and no meats, seafood, or beans.",
            "ingredients": ["Eggplant", "Shiitake mushrooms", "Scallion", "Water"],
            "steps": ["Cut eggplant, soak briefly in lightly salted water, drain; soften mushrooms.",
                      "Braise eggplant and mushrooms gently in 100ml water with light seasoning.",
                      "Simmer until tender and garnish with scallions."],
            "avoid": ["Season lightly with salt and spice."],
        }},
    },
    {
        **_recipe(
            "gout_winter_melon_soup",
            "Canh bí đao cà rốt thanh mát",
            "🥣",
            "Canh rau củ thanh nhẹ, lợi tiểu · an toàn cho Gút",
            "15 phút",
            "Bí đao giàu nước giúp thanh nhiệt, lợi tiểu nhẹ và hỗ trợ đào thải acid uric.",
            [_i("Bí đao", 150, "g", "🥒"), _i("Cà rốt", 50, "g", "🥕"), _i("Hành lá", 10, "g", "🌿"), _i("Nước lọc", 350, "ml", "💧")],
            ["Bí đao và cà rốt gọt vỏ, rửa sạch, thái lát vừa ăn.",
             "Đun sôi 350ml nước lọc, cho cà rốt vào nấu 5 phút rồi thêm bí đao.",
             "Nấu chín mềm, nêm nhạt và rắc hành lá trước khi dùng ấm."],
            ["Không nêm hạt nêm từ thịt hay xương hầm cho thực đơn Gút."]
        ),
        "recipe_type": "food", "dish_role": "soup", "calories": 75, "sugar": 3,
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Light winter melon & carrot soup",
            "subtitle": "Hydrating, low-purine vegetable soup",
            "benefit": "Winter melon and carrot add water and fiber to help support hydration in gout.",
            "ingredients": ["Winter melon", "Carrot", "Scallion", "Water"],
            "steps": ["Peel and slice winter melon and carrot.",
                      "Boil water, cook carrot 5 minutes, then add winter melon.",
                      "Simmer until tender, season lightly, and top with scallions."],
            "avoid": ["Do not use meat- or bone-based broths."],
        }},
    },
    {
        **_recipe(
            "gout_cabbage_tomato_soup",
            "Canh bắp cải cà chua thanh nhẹ",
            "🥬",
            "Rau xanh giàu vitamin C, ít purin · hỗ trợ Gút",
            "15 phút",
            "Bắp cải và cà chua bổ sung vitamin C và chất xơ thực vật giúp trung hòa kiềm nhẹ nước tiểu.",
            [_i("Bắp cải", 120, "g", "🥬"), _i("Cà chua", 80, "g", "🍅"), _i("Nước lọc", 350, "ml", "💧")],
            ["Cà chua cắt múi cau; bắp cải rửa sạch, thái sợi vừa ăn.",
             "Nấu cà chua với 350ml nước lọc đến khi mềm ra màu đẹp.",
             "Thả bắp cải vào nấu chín tới 3 phút, nêm nhạt và dùng ấm."],
            ["Giảm lượng cà chua nếu bạn đang bị trào ngược hoặc đau dạ dày cấp."]
        ),
        "recipe_type": "food", "dish_role": "soup", "calories": 85, "sugar": 4,
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Cabbage & tomato vegetable soup",
            "subtitle": "Vitamin-C-rich low-purine soup",
            "benefit": "Cabbage and tomato supply vitamin C and hydration with negligible purines.",
            "ingredients": ["Cabbage", "Tomato", "Water"],
            "steps": ["Slice tomatoes; wash and shred cabbage.",
                      "Simmer tomatoes in 350ml water until softened.",
                      "Add cabbage, cook 3 minutes, season lightly, and serve warm."],
            "avoid": ["Reduce tomato if you also have active reflux or gastritis."],
        }},
    },
    {
        **_recipe(
            "gout_boiled_greens",
            "Cải thìa & bông cải xanh luộc",
            "🥦",
            "Rau xanh ít purin, giàu vitamin C · không dầu mỡ",
            "10 phút",
            "Rau cải xanh chứa vitamin C và chất xơ giúp hỗ trợ giảm tích tụ acid uric an toàn.",
            [_i("Cải thìa", 100, "g", "🥬"), _i("Bông cải xanh", 100, "g", "🥦"), _i("Nước lọc", 250, "ml", "💧")],
            ["Rửa sạch cải thìa và tách bông cải xanh thành miếng vừa ăn.",
             "Đun sôi 250ml nước lọc, cho rau vào luộc chín vừa giữ màu xanh.",
             "Vớt ra đĩa, có thể chấm cùng nước tương nhạt (nếu không kiêng) hoặc dùng trực tiếp."],
            ["Không chấm cùng mắm mặn hoặc sốt từ hải sản."]
        ),
        "recipe_type": "food", "dish_role": "side", "calories": 65, "sugar": 2,
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Boiled bok choy & broccoli greens",
            "subtitle": "Oil-free vitamin C vegetables · safe for gout",
            "benefit": "Bok choy and broccoli provide fiber and vitamin C without purine burden.",
            "ingredients": ["Bok choy", "Broccoli", "Water"],
            "steps": ["Wash bok choy and cut broccoli into florets.",
                      "Boil in 250ml water until tender-crisp.",
                      "Drain and serve fresh without meat or seafood sauces."],
            "avoid": ["Avoid high-purine seafood dipping sauces."],
        }},
    },
    {
        **_recipe(
            "gout_oat_pumpkin_congee",
            "Cháo yến mạch bí đỏ ít purin",
            "🥣",
            "Bữa ăn trọn vị nhẹ nhàng, không thịt/đậu · tốt cho Gút",
            "18 phút",
            "Yến mạch và bí đỏ cung cấp năng lượng sạch, chất xơ hòa tan và beta-carotene mà không tạo purin.",
            [_i("Yến mạch", 45, "g", "🌾"), _i("Bí đỏ", 100, "g", "🎃"), _i("Nước lọc", 400, "ml", "💧")],
            ["Bí đỏ gọt vỏ, cắt hạt lựu nhỏ, hấp hoặc nấu mềm cùng 400ml nước.",
             "Cho yến mạch vào khuấy đều lửa nhỏ khoảng 8-10 phút.",
             "Nêm cực nhạt, múc ra bát dùng ấm."],
            ["Tránh dùng nếu bạn dị ứng hoặc cần kiêng hoàn toàn gluten."]
        ),
        "recipe_type": "food", "dish_role": "staple", "calories": 245, "sugar": 4,
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Low-purine oat & pumpkin porridge",
            "subtitle": "Complete plant-based bowl · free of meat & beans",
            "benefit": "Oats and pumpkin provide steady energy and fiber without animal or legume purines.",
            "ingredients": ["Oats", "Pumpkin", "Water"],
            "steps": ["Dice pumpkin and simmer in 400ml water until soft.",
                      "Stir in oats and cook gently for 8-10 minutes.",
                      "Season very lightly and serve warm."],
            "avoid": ["Avoid if strictly avoiding gluten."],
        }},
    },
    {
        **_recipe(
            "gout_rice_egg_veggies",
            "Cơm gạo lứt trứng ốp la rau củ",
            "🍚",
            "Món trọn vị ít purin · thay thế đạm thịt/cá/đậu",
            "25 phút",
            "Gạo lứt nguyên cám kết hợp trứng gà và dưa leo tạo bữa ăn đủ năng lượng, kiểm soát acid uric.",
            [_i("Gạo lứt", 70, "g", "🍚"), _i("Trứng gà", 1, "quả", "🥚"), _i("Dưa leo", 80, "g", "🥒"), _i("Cải thìa", 80, "g", "🥬")],
            ["Nấu chín cơm gạo lứt; cải thìa luộc chín, dưa leo rửa sạch thái lát.",
             "Ốp la 1 quả trứng gà trên chảo chống dính với lượng dầu tối thiểu.",
             "Dùng cơm gạo lứt kèm trứng và rau củ luộc."],
            ["Tránh dùng nếu dị ứng trứng; điều chỉnh lượng cơm theo nhu cầu đường huyết."]
        ),
        "recipe_type": "food", "dish_role": "staple", "calories": 360, "sugar": 2,
        "source_provider": "MediMind · công thức tham khảo",
        "translations": {"en": {
            "title": "Brown rice with pan-cooked egg & greens",
            "subtitle": "Balanced low-purine single-plate meal",
            "benefit": "Whole-grain brown rice paired with egg and fresh greens provides safe gout nutrition.",
            "ingredients": ["Brown rice", "Chicken egg", "Cucumber", "Bok choy"],
            "steps": ["Cook brown rice; steam or boil bok choy and slice cucumber.",
                      "Lightly cook one egg in a nonstick pan with minimal oil.",
                      "Plate together and serve warm."],
            "avoid": ["Avoid if allergic to eggs; adjust rice portion for blood sugar goals."],
        }},
    },
]

_CURATED_NUTRITION_MACROS = {
    "oat_porridge": {"calories": 240, "protein": 6.8, "fat": 3.1, "carbs": 48.0},
    "pumpkin_soup": {"calories": 105, "protein": 3.1, "fat": 0.3, "carbs": 24.0},
    "rice_carrot": {"calories": 200, "protein": 4.1, "fat": 0.5, "carbs": 44.0},
    "soft_egg": {"calories": 72, "protein": 6.3, "fat": 4.8, "carbs": 0.4},
    "sweet_potato": {"calories": 130, "protein": 2.4, "fat": 0.2, "carbs": 30.0},
    "chicken_congee": {"calories": 225, "protein": 19.0, "fat": 1.8, "carbs": 32.0},
    "tofu_pumpkin": {"calories": 90, "protein": 6.2, "fat": 3.2, "carbs": 9.0},
    "warm_water": {"calories": 0, "protein": 0.0, "fat": 0.0, "carbs": 0.0},
    "warm_milk": {"calories": 120, "protein": 6.4, "fat": 6.6, "carbs": 9.6},
    "oat_drink": {"calories": 95, "protein": 3.4, "fat": 1.7, "carbs": 17.0},
    "cucumber_water": {"calories": 15, "protein": 0.3, "fat": 0.1, "carbs": 1.5},
    "warm_soy": {"calories": 85, "protein": 7.0, "fat": 4.0, "carbs": 4.5},
    "pear_water": {"calories": 60, "protein": 0.4, "fat": 0.1, "carbs": 15.0},
    "barley_water": {"calories": 65, "protein": 2.0, "fat": 0.4, "carbs": 14.0},
    "fl_steamed_fish": {"calories": 110, "protein": 20.5, "fat": 2.5, "carbs": 1.5},
    "fl_chicken_vegetables": {"calories": 175, "protein": 25.5, "fat": 2.2, "carbs": 12.0},
    "fl_tofu_tomato": {"calories": 95, "protein": 7.0, "fat": 3.8, "carbs": 6.5},
    "fl_winter_melon_soup": {"calories": 45, "protein": 2.8, "fat": 0.4, "carbs": 8.0},
    "fl_steamed_greens": {"calories": 25, "protein": 2.3, "fat": 0.3, "carbs": 3.5},
    "fl_oat_vegetable_porridge": {"calories": 200, "protein": 7.5, "fat": 3.3, "carbs": 35.0},
    "fl_brown_rice_chicken": {"calories": 320, "protein": 23.0, "fat": 3.5, "carbs": 48.0},
    "gout_egg_tomato": {"calories": 210, "protein": 13.5, "fat": 14.5, "carbs": 5.5},
    "gout_steamed_egg_veggies": {"calories": 195, "protein": 13.0, "fat": 10.0, "carbs": 5.5},
    "gout_braised_eggplant": {"calories": 155, "protein": 4.2, "fat": 2.5, "carbs": 28.0},
    "gout_winter_melon_soup": {"calories": 75, "protein": 1.6, "fat": 0.5, "carbs": 16.0},
    "gout_cabbage_tomato_soup": {"calories": 85, "protein": 2.4, "fat": 0.5, "carbs": 17.0},
    "gout_boiled_greens": {"calories": 65, "protein": 4.3, "fat": 0.6, "carbs": 10.0},
    "gout_oat_pumpkin_congee": {"calories": 245, "protein": 7.2, "fat": 3.3, "carbs": 46.0},
    "gout_rice_egg_veggies": {"calories": 360, "protein": 13.5, "fat": 7.5, "carbs": 59.0},
    "gout_celery_juice": {"calories": 55, "protein": 0.8, "fat": 0.3, "carbs": 13.0},
    "gout_cucumber_lemon": {"calories": 45, "protein": 0.9, "fat": 0.2, "carbs": 9.5},
    "gout_cherry_juice": {"calories": 85, "protein": 1.3, "fat": 0.3, "carbs": 19.0},
    "gout_light_green_tea": {"calories": 15, "protein": 0.3, "fat": 0.0, "carbs": 3.0},
    "gout_orange_carrot": {"calories": 95, "protein": 1.6, "fat": 0.3, "carbs": 21.0},
}
_CURATED_EXACT_IMAGES = {
    "oat_porridge": "/static/images/nutrition/oat_porridge.svg?v=2",
    "pumpkin_soup": "/static/images/recipes/vifoodrec_3756.jpg",
    "rice_carrot": "/static/images/nutrition/rice_carrot.svg?v=2",
    "soft_egg": "/static/images/nutrition/soft_egg.svg?v=2",
    "sweet_potato": "/static/images/recipes/canonical_staple_khoai_lang_steamed.jpg",
    "chicken_congee": "/static/images/recipes/vifoodrec_2046.jpg",
    "tofu_pumpkin": "/static/images/nutrition/tofu_pumpkin.svg?v=2",
    "warm_water": "/static/images/nutrition/warm_water.svg?v=2",
    "warm_milk": "/static/images/nutrition/warm_milk.svg?v=2",
    "oat_drink": "/static/images/recipes/vifoodrec_2004.jpg",
    "cucumber_water": "/static/images/recipes/vifoodrec_3943.jpg",
    "warm_soy": "/static/images/recipes/vifoodrec_3417.jpg",
    "pear_water": "/static/images/nutrition/pear_water.svg?v=2",
    "barley_water": "/static/images/nutrition/barley_water.svg?v=2",
    "fl_steamed_fish": "/static/images/recipes/vifoodrec_762.jpg",
    "fl_chicken_vegetables": "/static/images/recipes/curated_uc_ga_luoc_rau_cu.jpg",
    "fl_tofu_tomato": "/static/images/recipes/vifoodrec_1984.jpg",
    "fl_winter_melon_soup": "/static/images/recipes/vifoodrec_304.jpg",
    "fl_steamed_greens": "/static/images/nutrition/category-food.svg?v=2",
    "fl_oat_vegetable_porridge": "/static/images/nutrition/oat_porridge.svg?v=2",
    "fl_brown_rice_chicken": "/static/images/recipes/vifoodrec_1925.png",
    "gout_egg_tomato": "/static/images/recipes/vifoodrec_3072.jpg",
    "gout_steamed_egg_veggies": "/static/images/recipes/vifoodrec_1241.jpg",
    "gout_braised_eggplant": "/static/images/recipes/vifoodrec_2090.jpg",
    "gout_winter_melon_soup": "/static/images/recipes/vifoodrec_304.jpg",
    "gout_cabbage_tomato_soup": "/static/images/recipes/vifoodrec_2697.jpg",
    "gout_boiled_greens": "/static/images/nutrition/category-food.svg?v=2",
    "gout_oat_pumpkin_congee": "/static/images/nutrition/oat_porridge.svg?v=2",
    "gout_rice_egg_veggies": "/static/images/recipes/canonical_staple_com_gao_lut.jpg",
    "gout_celery_juice": "/static/images/recipes/vifoodrec_2798.jpg",
    "gout_cucumber_lemon": "/static/images/recipes/vifoodrec_3943.jpg",
    "gout_cherry_juice": "/static/images/recipes/vifoodrec_3042.jpg",
    "gout_light_green_tea": "/static/images/nutrition/barley_water.svg?v=2",
    "gout_orange_carrot": "/static/images/nutrition/pear_water.svg?v=2",
}
for _group in (FOOD, DRINK, FATTY_LIVER_FOOD, GOUT_FOODS, GOUT_DRINKS):
    for _rec in _group:
        _macros = _CURATED_NUTRITION_MACROS.get(_rec.get("id"))
        if _macros:
            for _mk, _mv in _macros.items():
                if _rec.get(_mk) is None:
                    _rec[_mk] = _mv
        _exact_img = _CURATED_EXACT_IMAGES.get(_rec.get("id"))
        if _exact_img and not _rec.get("image_link"):
            _rec["image_link"] = _exact_img


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
    "snack": "Bữa phụ"
}

_ROLE_LABELS = {
    "main": "Món chính",
    "soup": "Món canh",
    "side": "Món rau / phụ",
    "staple": "Món tinh bột / cháo",
    "drink": "Thức uống"
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
    is_drink = recipe.get("recipe_type") == "drink"
    if "gout" in ctxs:
        if is_drink:
            return f"Thức uống từ {ing_text} ít nhân purin, giàu vitamin C và hỗ trợ bù nước lợi tiểu giúp đào thải acid uric an toàn cho người bệnh Gút."
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
    if is_drink:
        return f"Thức uống từ {ing_text} đã được sàng lọc an toàn theo tình trạng “{condition}” và hồ sơ dị ứng."
    return f"Món kết hợp {ing_text} chế biến cân bằng, đã sàng lọc an toàn theo yêu cầu “{condition}”."


_GENERIC_REASON_RE = re.compile(
    r"món có kết cấu mềm và đã qua bộ lọc|đã qua bộ lọc nguyên liệu theo mô tả|thức uống đã qua bộ lọc nguyên liệu|món canh súp/dạng nước dễ dùng|công thức đã qua bộ lọc nguyên liệu|món có kết cấu mềm trong kho|một công thức qua bộ lọc nguyên liệu",
    re.IGNORECASE,
)


def _enrich_recipe(recipe: Dict[str, Any], condition: str, contexts: Optional[List[str]] = None) -> None:
    """Add display labels and enforce clinical, non-generic explanation."""
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
    from core.nutrition_rules import prepare_nutrition_candidates
    from core.nutrition_ai import NutritionAIError, select_recipes

    result = _get_general_options(condition, recipe_type)
    profile = profile if isinstance(profile, dict) else {}
    prepared = prepare_nutrition_candidates(condition, result["recipes"], profile.get("allergies"),
                                            fatty_liver_recipes=FATTY_LIVER_FOOD if recipe_type == "food" else None,
                                            gout_drink_recipes=GOUT_DRINKS if recipe_type == "drink" else None,
                                            gout_food_recipes=GOUT_FOODS if recipe_type == "food" else None)
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
    elif recipe_type == "food" and "gout" in prepared["contexts"]:
        curated_ids = {recipe["id"] for recipe in GOUT_FOODS}
        curated = [recipe for recipe in remaining if recipe["id"] in curated_ids]
        candidates = (curated + [recipe for recipe in candidates if recipe["id"] not in curated_ids])[:32]
    elif recipe_type == "drink" and "gout" in prepared["contexts"]:
        curated_ids = {recipe["id"] for recipe in GOUT_DRINKS}
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
            item_word = "thức uống" if recipe_type == "drink" else "món ăn"
            result["notice"] = f"MediMind đã chọn lọc các {item_word} an toàn và phù hợp nhất với yêu cầu và hồ sơ sức khỏe của bạn."
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
