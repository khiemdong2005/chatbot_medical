"""
core/nutrition_service.py
Dịch vụ Phân tích Dinh dưỡng Lâm sàng & Pha chế Bữa ăn Trị liệu theo Thể trạng.
Hỗ trợ cả cơ sở dữ liệu mẫu chuẩn y khoa và AI Sinh động lực (Gemini).
"""

import os
import json
import logging
import re
from typing import Dict, Any, Optional
from google import genai
from google.genai import types

logger = logging.getLogger("medimind.nutrition")

# Bộ dữ liệu mẫu chuẩn Y học cổ truyền & Dinh dưỡng lâm sàng (Phản hồi tức thì 0ms)
PRESET_CONDITIONS: Dict[str, Dict[str, Any]] = {
    "dau_bung_kinh": {
        "id": "dau_bung_kinh",
        "condition_name": "Đau bụng kinh",
        "short_desc": "Mệt mỏi, uể oải",
        "icon": "droplet",
        "accent_color": "rose",
        "foods_to_eat": [
            {"name": "Nước ấm gừng", "icon": "🍵", "desc": "Làm ấm tử cung, tán hàn thông kinh", "glow": "amber"},
            {"name": "Nước đường đỏ", "icon": "🫖", "desc": "Bổ huyết hoạt huyết, giảm co thắt", "glow": "rose"},
            {"name": "Canh khoai lang", "icon": "🍠", "desc": "Giàu magie, thư giãn cơ trơn bụng", "glow": "orange"},
            {"name": "Hạt dẻ hầm", "icon": "🌰", "desc": "Bổ tỳ thận, bổ sung năng lượng", "glow": "amber"}
        ],
        "foods_to_avoid": [
            {"name": "Đồ sống lạnh", "icon": "🧊", "desc": "Khiến huyết ứ trệ, tăng cơn co bóp", "glow": "red"},
            {"name": "Đồ mặn cay", "icon": "🌶️", "desc": "Gây tích nước, trướng bụng và bức rứt", "glow": "red"},
            {"name": "Thức uống có cồn", "icon": "🍷", "desc": "Rối loạn lưu lượng máu vùng chậu", "glow": "red"}
        ],
        "recipe": {
            "title": "Canh khoai lang hạt dẻ hầm",
            "subtitle": "Ấm bụng, bớt mệt mỏi",
            "badge": "CÔNG THỨC 3 BƯỚC",
            "cooking_time": "~25 phút",
            "tip": "Ăn nóng, cả nước lẫn cái",
            "servings_default": 1,
            "ingredients": [
                {"name": "Khoai lang", "amount": 1, "unit": "củ", "icon": "🍠"},
                {"name": "Hạt dẻ", "amount": 50, "unit": "g", "icon": "🌰"},
                {"name": "Gừng", "amount": 2, "unit": "lát", "icon": "🫚"},
                {"name": "Nước", "amount": 400, "unit": "ml", "icon": "💧"}
            ],
            "steps": [
                "Khoai lang gọt vỏ thái khúc, hạt dẻ ngâm mềm.",
                "Hầm khoai + hạt dẻ + gừng trong 400ml nước 25 phút.",
                "Nêm nhạt, ăn nóng cả nước lẫn cái."
            ]
        }
    },
    "nhiet_mieng": {
        "id": "nhiet_mieng",
        "condition_name": "Nhiệt miệng",
        "short_desc": "Nóng trong người",
        "icon": "flame",
        "accent_color": "amber",
        "foods_to_eat": [
            {"name": "Bột sắn dây", "icon": "🥣", "desc": "Thanh nhiệt giáng hỏa, dịu vết loét", "glow": "emerald"},
            {"name": "Nước râu ngô", "icon": "🌽", "desc": "Lợi tiểu, thải độc gan", "glow": "emerald"},
            {"name": "Trà hoa cúc", "icon": "🌼", "desc": "Kháng viêm tự nhiên, mát họng", "glow": "amber"},
            {"name": "Đậu xanh nấu nhừ", "icon": "🫘", "desc": "Giải độc tiêu viêm lành niêm mạc", "glow": "emerald"}
        ],
        "foods_to_avoid": [
            {"name": "Đồ chiên rán", "icon": "🍟", "desc": "Tích tụ nhiệt độc, vết loét lâu lành", "glow": "red"},
            {"name": "Ớt & tiêu cay", "icon": "🌶️", "desc": "Kích ứng trực tiếp gây rát bỏng", "glow": "red"},
            {"name": "Nước ngọt có gas", "icon": "🥤", "desc": "Tăng tính axit làm loét sâu hơn", "glow": "red"}
        ],
        "recipe": {
            "title": "Chè đậu xanh bột sắn dây hoa cúc",
            "subtitle": "Thanh nhiệt, làm dịu vết nhiệt miệng",
            "badge": "CÔNG THỨC 3 BƯỚC",
            "cooking_time": "~20 phút",
            "tip": "Dùng nguội hoặc hơi mát, không ăn nóng",
            "servings_default": 1,
            "ingredients": [
                {"name": "Đậu xanh cà vỏ", "amount": 40, "unit": "g", "icon": "🫘"},
                {"name": "Bột sắn dây", "amount": 20, "unit": "g", "icon": "🥣"},
                {"name": "Hoa cúc khô", "amount": 3, "unit": "bông", "icon": "🌼"},
                {"name": "Nước lọc", "amount": 450, "unit": "ml", "icon": "💧"}
            ],
            "steps": [
                "Đậu xanh đãi sạch, nấu nhừ cùng 400ml nước trong 15 phút.",
                "Hòa tan bột sắn dây với 50ml nước lạnh và thả hoa cúc vào nồi chè đang sôi lăn tăn.",
                "Khuấy đều tay đến khi trong suốt, tắt bếp và để nguội bớt trước khi dùng."
            ]
        }
    },
    "day_hoi": {
        "id": "day_hoi",
        "condition_name": "Đầy hơi",
        "short_desc": "Khó tiêu sau tiệc",
        "icon": "activity",
        "accent_color": "yellow",
        "foods_to_eat": [
            {"name": "Trà gừng ấm", "icon": "🫚", "desc": "Kích thích enzym tiêu hóa, tống hơi thừa", "glow": "amber"},
            {"name": "Sữa chua men sống", "icon": "🥛", "desc": "Bổ sung lợi khuẩn cân bằng ruột", "glow": "cyan"},
            {"name": "Nước ép dứa / thơm", "icon": "🍍", "desc": "Bromelain phân cắt protein ứ đọng", "glow": "amber"},
            {"name": "Hạt thì là / Bạc hà", "icon": "🍃", "desc": "Chống co thắt dạ dày ruột", "glow": "emerald"}
        ],
        "foods_to_avoid": [
            {"name": "Thức uống có ga", "icon": "🥤", "desc": "Tăng lượng khí CO2 ứ đọng dạ dày", "glow": "red"},
            {"name": "Đồ béo ngập dầu", "icon": "🍔", "desc": "Làm chậm quá trình làm rỗng dạ dày", "glow": "red"},
            {"name": "Sữa đặc nhiều đường", "icon": "🧋", "desc": "Gây lên men sinh hơi chướng bụng", "glow": "red"}
        ],
        "recipe": {
            "title": "Trà gừng bạc hà chanh ấm",
            "subtitle": "Xẹp bụng tức thì, nhẹ nhõm tiêu hóa",
            "badge": "CÔNG THỨC 3 BƯỚC",
            "cooking_time": "~5 phút",
            "tip": "Uống từng ngụm nhỏ sau bữa tiệc no",
            "servings_default": 1,
            "ingredients": [
                {"name": "Gừng tươi đập dập", "amount": 3, "unit": "lát", "icon": "🫚"},
                {"name": "Lá bạc hà tươi", "amount": 5, "unit": "lá", "icon": "🍃"},
                {"name": "Mật ong", "amount": 1, "unit": "thìa cà phê", "icon": "🍯"},
                {"name": "Nước sôi", "amount": 300, "unit": "ml", "icon": "💧"}
            ],
            "steps": [
                "Cho gừng đập dập và lá bạc hà vào ly thủy tinh chịu nhiệt.",
                "Rót 300ml nước sôi vào hãm đậy nắp trong 5-7 phút.",
                "Thêm một chút mật ong, khuấy đều và uống khi còn ấm nóng."
            ]
        }
    },
    "cam_cum": {
        "id": "cam_cum",
        "condition_name": "Cảm cúm",
        "short_desc": "Đau rát họng",
        "icon": "heart",
        "accent_color": "sky",
        "foods_to_eat": [
            {"name": "Cháo tía tô hành", "icon": "🥣", "desc": "Phát hãn giải biểu, giải cảm phong hàn", "glow": "emerald"},
            {"name": "Nước cam ấm mật ong", "icon": "🍊", "desc": "Bổ sung vitamin C tăng đề kháng", "glow": "amber"},
            {"name": "Canh gà hầm gừng", "icon": "🍲", "desc": "Chứa carnosine làm thông thoáng mũi họng", "glow": "amber"},
            {"name": "Tỏi đen / Tỏi nướng", "icon": "🧄", "desc": "Allicin kháng khuẩn tự nhiên", "glow": "emerald"}
        ],
        "foods_to_avoid": [
            {"name": "Đá lạnh & kem", "icon": "🍦", "desc": "Kích ứng co thắt niêm mạc họng", "glow": "red"},
            {"name": "Món chiên xào béo", "icon": "🍗", "desc": "Sinh đờm nhớt, gây nặng ngực", "glow": "red"},
            {"name": "Cà phê đậm đặc", "icon": "☕", "desc": "Gây mất nước và suy giảm miễn dịch", "glow": "red"}
        ],
        "recipe": {
            "title": "Cháo tía tô hành hoa trứng gà",
            "subtitle": "Vã mồ hôi giải cảm, thông họng nhanh chóng",
            "badge": "CÔNG THỨC 3 BƯỚC",
            "cooking_time": "~15 phút",
            "tip": "Ăn xong nằm đắp chăn mỏng cho ra mồ hôi nhẹ",
            "servings_default": 1,
            "ingredients": [
                {"name": "Gạo tẻ nấu cháo", "amount": 1, "unit": "bát cháo hoa", "icon": "🍚"},
                {"name": "Lá tía tô thái sợi", "amount": 10, "unit": "lá", "icon": "🌿"},
                {"name": "Hành hoa thái nhỏ", "amount": 2, "unit": "nhánh", "icon": "🌱"},
                {"name": "Lòng đỏ trứng gà", "amount": 1, "unit": "quả", "icon": "🥚"}
            ],
            "steps": [
                "Nấu cháo hoa sôi lục bục trên bếp lửa vừa.",
                "Cho lòng đỏ trứng gà vào đáy bát, múc cháo sôi đổ lên trên khuấy tan đều.",
                "Rắc lá tía tô, hành hoa và chút tiêu ấm, trộn đều ăn ngay khi còn bốc khói."
            ]
        }
    },
    "mat_ngu": {
        "id": "mat_ngu",
        "condition_name": "Mất ngủ",
        "short_desc": "Căng thẳng, cần thư giãn",
        "icon": "moon",
        "accent_color": "indigo",
        "foods_to_eat": [
            {"name": "Trà tâm sen", "icon": "🫖", "desc": "Hạ hỏa an thần, dễ đi vào giấc ngủ", "glow": "indigo"},
            {"name": "Sữa hạnh nhân ấm", "icon": "🥛", "desc": "Chứa tryptophan kích thích melatonin", "glow": "cyan"},
            {"name": "Hạt sen tươi hầm", "icon": "🪷", "desc": "Dưỡng tâm an thần, ngủ sâu giấc", "glow": "amber"},
            {"name": "Chuối chín", "icon": "🍌", "desc": "Magie và kali giúp thả lỏng cơ bắp", "glow": "amber"}
        ],
        "foods_to_avoid": [
            {"name": "Cà phê & Trà đặc", "icon": "☕", "desc": "Chặn thụ thể adenosine gây tỉnh táo giả", "glow": "red"},
            {"name": "Socola đen", "icon": "🍫", "desc": "Chứa theobromine kích thích tim đập nhanh", "glow": "red"},
            {"name": "Đồ ăn cay nóng đêm", "icon": "🌶️", "desc": "Tăng thân nhiệt làm gián đoạn giấc ngủ", "glow": "red"}
        ],
        "recipe": {
            "title": "Sữa hạt sen hạnh nhân mật ong",
            "subtitle": "Xoa dịu thần kinh, đưa vào giấc ngủ êm đềm",
            "badge": "CÔNG THỨC 3 BƯỚC",
            "cooking_time": "~15 phút",
            "tip": "Uống ấm trước giờ ngủ 45 phút",
            "servings_default": 1,
            "ingredients": [
                {"name": "Hạt sen tươi", "amount": 40, "unit": "g", "icon": "🪷"},
                {"name": "Sữa tươi ấm (hoặc sữa hạt)", "amount": 250, "unit": "ml", "icon": "🥛"},
                {"name": "Mật ong tự nhiên", "amount": 1, "unit": "thìa cà phê", "icon": "🍯"},
                {"name": "Bột hạnh nhân", "amount": 10, "unit": "g", "icon": "🥜"}
            ],
            "steps": [
                "Hạt sen bỏ tâm xanh, luộc chín mềm cùng ít nước.",
                "Xay nhuyễn hạt sen chín cùng sữa tươi ấm và bột hạnh nhân.",
                "Rót ra ly, hòa mật ong ấm và thưởng thức trong không gian yên tĩnh."
            ]
        }
    },
    "dau_da_day": {
        "id": "dau_da_day",
        "condition_name": "Đau dạ dày",
        "short_desc": "Rát thượng vị, ợ chua",
        "icon": "shield",
        "accent_color": "emerald",
        "foods_to_eat": [
            {"name": "Tinh bột nghệ", "icon": "🌾", "desc": "Curcumin chống loét, hồi phục niêm mạc", "glow": "amber"},
            {"name": "Nước bắp cải ép", "icon": "🥬", "desc": "Giàu vitamin U hỗ trợ lành vết trợt", "glow": "emerald"},
            {"name": "Khoai tây hấp", "icon": "🥔", "desc": "Kiềm hóa dịch vị dư thừa", "glow": "amber"},
            {"name": "Bí đỏ nấu nhừ", "icon": "🎃", "desc": "Bọc dịu axit dạ dày, dễ tiêu", "glow": "orange"}
        ],
        "foods_to_avoid": [
            {"name": "Chanh, xoài chua", "icon": "🍋", "desc": "Axit citric ăn mòn trực tiếp ổ loét", "glow": "red"},
            {"name": "Rượu bia", "icon": "🍺", "desc": "Phá hủy hàng rào chất nhầy dạ dày", "glow": "red"},
            {"name": "Món chiên xào nhiều dầu", "icon": "🥓", "desc": "Gây đầy tức và trào ngược axit", "glow": "red"}
        ],
        "recipe": {
            "title": "Cháo bí đỏ nghệ mật ong",
            "subtitle": "Bọc êm niêm mạc, xua tan cơn đau rát",
            "badge": "CÔNG THỨC 3 BƯỚC",
            "cooking_time": "~20 phút",
            "tip": "Ăn khi cháo còn hơi ấm, chia nhỏ bữa",
            "servings_default": 1,
            "ingredients": [
                {"name": "Bí đỏ gọt vỏ", "amount": 80, "unit": "g", "icon": "🎃"},
                {"name": "Gạo tẻ dẻo", "amount": 40, "unit": "g", "icon": "🍚"},
                {"name": "Tinh bột nghệ", "amount": 1, "unit": "thìa cà phê", "icon": "🌾"},
                {"name": "Mật ong", "amount": 1, "unit": "thìa", "icon": "🍯"}
            ],
            "steps": [
                "Bí đỏ thái hạt lựu, nấu nhừ cùng gạo tẻ trong 20 phút thành cháo mịn.",
                "Tắt bếp, để cháo hạ nhiệt xuống khoảng 50°C.",
                "Khuấy đều tinh bột nghệ và mật ong, dùng trước bữa ăn chính 30 phút."
            ]
        }
    },
    "gout": {
        "id": "gout",
        "condition_name": "Gút / Khớp",
        "short_desc": "Axit uric cao, nhức mỏi",
        "icon": "zap",
        "accent_color": "sky",
        "foods_to_eat": [
            {"name": "Nước ép cần tây", "icon": "🥬", "desc": "Kiềm hóa cơ thể, đào thải axit uric", "glow": "emerald"},
            {"name": "Quả anh đào (Cherry)", "icon": "🍒", "desc": "Anthocyanin ức chế viêm khớp gút", "glow": "rose"},
            {"name": "Dưa chuột tươi", "icon": "🥒", "desc": "Thanh nhiệt lợi tiểu, giảm tích tinh thể", "glow": "emerald"},
            {"name": "Dầu ô liu nguyên chất", "icon": "🫒", "desc": "Chất béo kháng viêm an toàn", "glow": "amber"}
        ],
        "foods_to_avoid": [
            {"name": "Hải sản & tôm cua", "icon": "🦀", "desc": "Cực giàu nhân purin sinh axit uric", "glow": "red"},
            {"name": "Thịt bò & lòng tạng", "icon": "🥩", "desc": "Kích hoạt bùng phát cơn đau cấp", "glow": "red"},
            {"name": "Bia rượu các loại", "icon": "🍺", "desc": "Ức chế thận đào thải axit uric", "glow": "red"}
        ],
        "recipe": {
            "title": "Nước ép cần tây dưa leo táo xanh",
            "subtitle": "Thanh lọc axit uric, nhẹ nhõm khớp ngón",
            "badge": "CÔNG THỨC 3 BƯỚC",
            "cooking_time": "~5 phút",
            "tip": "Uống vào buổi sáng trước khi ăn 20 phút",
            "servings_default": 1,
            "ingredients": [
                {"name": "Cần tây cuống to", "amount": 2, "unit": "nhánh", "icon": "🥬"},
                {"name": "Dưa leo tươi", "amount": 1, "unit": "trái", "icon": "🥒"},
                {"name": "Táo xanh", "amount": 0.5, "unit": "trái", "icon": "🍏"},
                {"name": "Nước cốt chanh", "amount": 1, "unit": "thìa cà phê", "icon": "🍋"}
            ],
            "steps": [
                "Rửa sạch cần tây, dưa leo và táo xanh bằng nước muối loãng.",
                "Cắt khúc vừa miệng rồi cho vào máy ép lấy nước cốt trong.",
                "Thêm một chút cốt chanh tươi, khuấy đều và uống tươi ngay."
            ]
        }
    },
    "tieu_duong": {
        "id": "tieu_duong",
        "condition_name": "Tiểu đường",
        "short_desc": "Kiểm soát đường huyết",
        "icon": "check-circle",
        "accent_color": "emerald",
        "foods_to_eat": [
            {"name": "Mướp đắng (Khổ qua)", "icon": "🥒", "desc": "Charantin hỗ trợ tế bào hấp thụ glucose", "glow": "emerald"},
            {"name": "Yến mạch nguyên cám", "icon": "🌾", "desc": "Chỉ số GI thấp, giải phóng năng lượng từ từ", "glow": "amber"},
            {"name": "Bông cải xanh", "icon": "🥦", "desc": "Sulforaphane bảo vệ thành mạch máu", "glow": "emerald"},
            {"name": "Quế chi hãm nước", "icon": "🪵", "desc": "Tăng độ nhạy cảm của insulin", "glow": "amber"}
        ],
        "foods_to_avoid": [
            {"name": "Bánh kẹo & trà sữa", "icon": "🧋", "desc": "Đường hấp thu nhanh gây vọt đường huyết", "glow": "red"},
            {"name": "Gạo trắng quá nhừ", "icon": "🍚", "desc": "GI cao làm tụy quá tải", "glow": "red"},
            {"name": "Trái cây sấy khô", "icon": "🍇", "desc": "Mật độ đường cô đặc nguy hại", "glow": "red"}
        ],
        "recipe": {
            "title": "Canh khổ qua nhồi đậu hũ yến mạch",
            "subtitle": "Ổn định đường huyết, mát gan hạ hỏa",
            "badge": "CÔNG THỨC 3 BƯỚC",
            "cooking_time": "~20 phút",
            "tip": "Dùng trong bữa cơm trưa hoặc tối",
            "servings_default": 1,
            "ingredients": [
                {"name": "Khổ qua bỏ ruột", "amount": 1, "unit": "trái", "icon": "🥒"},
                {"name": "Đậu hũ trắng tán nhuyễn", "amount": 60, "unit": "g", "icon": "🧈"},
                {"name": "Yến mạch cán", "amount": 15, "unit": "g", "icon": "🌾"},
                {"name": "Nấm mèo thái sợi", "amount": 1, "unit": "tai", "icon": "🍄"}
            ],
            "steps": [
                "Trộn đậu hũ tán nhuyễn với yến mạch, nấm mèo và chút tiêu làm nhân.",
                "Khổ qua cắt khúc, nhồi chặt phần nhân vào giữa.",
                "Đun sôi nước dùng thanh đạm, thả khổ qua vào hầm 15 phút cho chín mềm."
            ]
        }
    }
}


def remove_accents(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để tìm kiếm chuẩn xác."""
    s1 = "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"
    s0 = "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd"
    result = text.lower()
    for i, c in enumerate(s1):
        result = result.replace(c, s0[i])
    return result


def find_preset_condition(query: str) -> Optional[Dict[str, Any]]:
    """Tra cứu kho dữ liệu mẫu chuẩn dựa trên từ khóa người dùng nhập."""
    q_norm = remove_accents(query.strip().lower())
    if not q_norm:
        return None

    # Khớp chính xác hoặc khớp từ khóa đặc trưng
    mappings = {
        "dau_bung_kinh": ["kinh nguyet", "dau bung kinh", "toi thang", "chu ky", "hanh kinh", "ngay den do"],
        "nhiet_mieng": ["nhiet mieng", "nong trong", "loet mieng", "nong gan", "loet luoi", "dau mieng"],
        "day_hoi": ["day hoi", "kho tieu", "chuong bung", "an khong tieu", "day bung", "kho chiu bung"],
        "cam_cum": ["cam cum", "cam lanh", "ho sot", "rat hong", "so mui", "viem hong", "cum"],
        "mat_ngu": ["mat ngu", "kho ngu", "cang thang", "stress", "tran troc", "thao thuc", "ngu khong sau"],
        "dau_da_day": ["dau da day", "bao tu", "rat thuong vi", "o chua", "viem da day", "trao nguoc"],
        "gout": ["gout", "gut", "axit uric", "nhuc khop", "dau khop chan", "sung ngon chan"],
        "tieu_duong": ["tieu duong", "duong huyet", "dai thao duong", "duong cao", "ha duong"]
    }

    for cond_id, keywords in mappings.items():
        if any(kw in q_norm for kw in keywords):
            return PRESET_CONDITIONS.get(cond_id)

    # Thử khớp tên hiển thị
    for cond_id, data in PRESET_CONDITIONS.items():
        if remove_accents(data["condition_name"].lower()) in q_norm:
            return data

    return None


def generate_ai_nutrition(condition_query: str, recipe_type: str = "food") -> Dict[str, Any]:
    """
    Sinh phác đồ đĩa ăn, thực phẩm nên nạp/nên né và công thức món ăn 3 bước
    bằng mô hình Gemini chính xác cao với Structured Output.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.warning("[Nutrition] Không tìm thấy GEMINI_API_KEY, chuyển sang Fallback động.")
        return generate_dynamic_fallback(condition_query, recipe_type)

    prompt = f"""Bạn là một Bác sĩ Dinh dưỡng Lâm sàng kiêm Đầu bếp Trị liệu Y học cổ truyền.
Người dùng có vấn đề sức khỏe / bệnh lý sau: '{condition_query}'.
Loại công thức người dùng chọn: {'thức uống' if recipe_type == 'drink' else 'món ăn'}. Công thức bắt buộc phải đúng loại đã chọn.

Hãy phân tích và xuất ra định dạng JSON chuẩn y khoa:
- Tên bệnh / thể trạng ngắn gọn chuẩn xác
- 4 món/thực phẩm NÊN NẠP (bổ trợ cơ thể, có lý do tác dụng cụ thể)
- 3 món/thực phẩm NÊN NÉ (kiêng kỵ, giải thích vì sao gây hại)
- 1 Công thức pha chế / Nấu ăn trị liệu 3 BƯỚC rõ ràng, thơm ngon, dễ làm tại nhà (có nguyên liệu cho 1 người định lượng số, 3 bước làm đánh số, lưu ý cách dùng, thời gian làm).

Cấu trúc JSON bắt buộc:
{{
  "condition_name": "Tên thể trạng / bệnh lý",
  "short_desc": "Mô tả biểu hiện (dưới 5 từ)",
  "accent_color": "emerald" (hoặc "amber", "rose", "sky", "indigo"),
  "foods_to_eat": [
     {{"name": "Tên món/nguyên liệu", "icon": "Emoji thực phẩm", "desc": "Tác dụng sinh học", "glow": "amber/emerald/rose"}},
     {{"name": "...", "icon": "...", "desc": "...", "glow": "..."}},
     {{"name": "...", "icon": "...", "desc": "...", "glow": "..."}},
     {{"name": "...", "icon": "...", "desc": "...", "glow": "..."}}
  ],
  "foods_to_avoid": [
     {{"name": "Tên món kiêng", "icon": "Emoji", "desc": "Tại sao phải kiêng", "glow": "red"}},
     {{"name": "...", "icon": "...", "desc": "...", "glow": "red"}},
     {{"name": "...", "icon": "...", "desc": "...", "glow": "red"}}
  ],
  "recipe": {{
     "title": "Tên món ăn / ly nước dinh dưỡng",
     "subtitle": "Tác dụng phục hồi thể trạng",
     "badge": "CÔNG THỨC 3 BƯỚC",
     "cooking_time": "~15-20 phút",
     "tip": "Lưu ý khi dùng (VD: Ăn nóng, dùng trước khi ngủ...)",
     "servings_default": 1,
     "ingredients": [
        {{"name": "Nguyên liệu 1", "amount": 1, "unit": "củ/g/ml/thìa", "icon": "Emoji"}},
        {{"name": "Nguyên liệu 2", "amount": 50, "unit": "g", "icon": "Emoji"}},
        {{"name": "Nguyên liệu 3", "amount": 2, "unit": "lát/nhánh", "icon": "Emoji"}},
        {{"name": "Nguyên liệu 4", "amount": 300, "unit": "ml", "icon": "Emoji"}}
     ],
     "steps": [
        "Bước 1 sơ chế cụ thể.",
        "Bước 2 nấu/hầm/pha chế với thời gian.",
        "Bước 3 thưởng thức và nêm nếm."
     ]
  }}
}}
Chỉ trả về JSON thuần túy, tuyệt đối không kèm markdown ```json.
"""

    try:
        http_opts = types.HttpOptions(timeout=12000)
        client = genai.Client(api_key=api_key, http_options=http_opts)
        resp = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3
            )
        )
        if resp and resp.text:
            cleaned = resp.text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned)
            data = json.loads(cleaned)
            data["id"] = "ai_" + re.sub(r"[^a-z0-9]", "_", remove_accents(condition_query))[:20]
            return data
    except Exception as e:
        logger.error(f"[Nutrition] Lỗi gọi Gemini AI ({e}), chuyển sang Fallback.")

    return generate_dynamic_fallback(condition_query, recipe_type)


def generate_dynamic_fallback(query: str, recipe_type: str = "food") -> Dict[str, Any]:
    """Tạo phác đồ dinh dưỡng dự phòng an toàn khi không có mạng/AI."""
    clean_q = query.strip()
    if recipe_type == "drink":
        return {
            "id": "fallback_drink_" + re.sub(r"[^a-z0-9]", "_", remove_accents(clean_q))[:20],
            "condition_name": clean_q.title(),
            "short_desc": "Thức uống dịu nhẹ",
            "accent_color": "sky",
            "foods_to_eat": [
                {"name": "Trà hoa cúc", "icon": "🌼", "desc": "Thức uống nhẹ, thơm dịu", "glow": "amber"},
                {"name": "Nước ấm", "icon": "💧", "desc": "Bổ sung nước cho cơ thể", "glow": "cyan"},
                {"name": "Lá bạc hà", "icon": "🌿", "desc": "Tạo hương vị thanh mát", "glow": "emerald"}
            ],
            "foods_to_avoid": [
                {"name": "Nước tăng lực", "icon": "🥤", "desc": "Có thể chứa caffeine và nhiều đường", "glow": "red"},
                {"name": "Đồ uống có cồn", "icon": "🍷", "desc": "Không phù hợp khi cần nghỉ ngơi", "glow": "red"}
            ],
            "recipe": {
                "title": "Trà hoa cúc bạc hà",
                "subtitle": "Thức uống ấm, hương vị dịu nhẹ",
                "badge": "THỨC UỐNG · 3 BƯỚC",
                "cooking_time": "~8 phút",
                "tip": "Để trà nguội bớt trước khi uống",
                "servings_default": 1,
                "ingredients": [
                    {"name": "Hoa cúc khô", "amount": 3, "unit": "bông", "icon": "🌼"},
                    {"name": "Lá bạc hà", "amount": 4, "unit": "lá", "icon": "🌿"},
                    {"name": "Mật ong", "amount": 1, "unit": "thìa cà phê", "icon": "🍯"},
                    {"name": "Nước nóng", "amount": 250, "unit": "ml", "icon": "💧"}
                ],
                "steps": [
                    "Tráng hoa cúc và lá bạc hà bằng nước sạch.",
                    "Hãm hoa cúc trong 250ml nước nóng khoảng 5 phút.",
                    "Thêm bạc hà và mật ong, khuấy nhẹ rồi thưởng thức."
                ]
            }
        }

    return {
        "id": "fallback_" + re.sub(r"[^a-z0-9]", "_", remove_accents(clean_q))[:20],
        "condition_name": clean_q.title(),
        "short_desc": "Điều hòa thể trạng, bồi bổ",
        "accent_color": "emerald",
        "foods_to_eat": [
            {"name": "Cháo hạt sen yến mạch", "icon": "🥣", "desc": "Thanh đạm, dễ tiêu, phục hồi khí huyết", "glow": "emerald"},
            {"name": "Nước ấm gừng mật ong", "icon": "🍵", "desc": "Kích thích tuần hoàn máu và đề kháng", "glow": "amber"},
            {"name": "Rau củ hấp thanh nhẹ", "icon": "🥦", "desc": "Bổ sung chất xơ hòa tan và vitamin", "glow": "emerald"},
            {"name": "Trà thảo mộc ấm", "icon": "🫖", "desc": "Xoa dịu thần kinh, đào thải độc tố", "glow": "cyan"}
        ],
        "foods_to_avoid": [
            {"name": "Đồ cay nóng & chiên dầu", "icon": "🌶️", "desc": "Gây nhiệt độc tích tụ, tăng gánh nặng tạng phủ", "glow": "red"},
            {"name": "Đồ sống lạnh", "icon": "🧊", "desc": "Làm ngưng trệ khí huyết và yếu tỳ vị", "glow": "red"},
            {"name": "Chất kích thích & Rượu", "icon": "🍺", "desc": "Làm suy giảm khả năng phục hồi tự nhiên", "glow": "red"}
        ],
        "recipe": {
            "title": f"Cháo dưỡng sinh hạt sen gừng ấm",
            "subtitle": f"Bồi bổ cơ thể khi gặp tình trạng {clean_q}",
            "badge": "CÔNG THỨC 3 BƯỚC",
            "cooking_time": "~20 phút",
            "tip": "Dùng nóng ấm vào bữa sáng hoặc tối",
            "servings_default": 1,
            "ingredients": [
                {"name": "Gạo tẻ & Yến mạch", "amount": 50, "unit": "g", "icon": "🌾"},
                {"name": "Hạt sen tươi", "amount": 30, "unit": "g", "icon": "🪷"},
                {"name": "Gừng tươi thái mỏng", "amount": 2, "unit": "lát", "icon": "🫚"},
                {"name": "Nước lọc tinh khiết", "amount": 400, "unit": "ml", "icon": "💧"}
            ],
            "steps": [
                "Gạo và hạt sen rửa sạch, ngâm nước ấm 15 phút cho mềm.",
                "Đun sôi 400ml nước, cho gạo, hạt sen và gừng vào nấu nhừ lửa nhỏ 20 phút.",
                "Nêm nhạt vừa miệng, múc ra bát và dùng nóng ấm."
            ]
        }
    }


def get_nutrition_recommendation(condition_query: str, recipe_type: str = "food") -> Dict[str, Any]:
    """Hàm điều phối: Ưu tiên dữ liệu mẫu nhanh -> AI linh hoạt."""
    def recipe_matches_type(result: Dict[str, Any]) -> bool:
        title = str(result.get("recipe", {}).get("title", "")).lower()
        drink_words = ("trà", "nước", "sữa", "sinh tố", "nước ép", "đồ uống")
        is_drink = any(word in title for word in drink_words)
        return is_drink == (recipe_type == "drink")

    preset = find_preset_condition(condition_query)
    if preset:
        if recipe_matches_type(preset):
            return preset
        fallback = generate_dynamic_fallback(condition_query, recipe_type)
        fallback["condition_name"] = preset.get("condition_name", condition_query.title())
        fallback["foods_to_eat"] = preset.get("foods_to_eat", fallback["foods_to_eat"])
        fallback["foods_to_avoid"] = preset.get("foods_to_avoid", fallback["foods_to_avoid"])
        return fallback
    result = generate_ai_nutrition(condition_query, recipe_type)
    if recipe_matches_type(result):
        return result

    # Mô hình đôi khi trả sai loại món dù prompt đã yêu cầu cụ thể. Giữ logic
    # danh sách dinh dưỡng nhưng thay công thức bằng fallback đúng loại.
    fallback = generate_dynamic_fallback(condition_query, recipe_type)
    fallback["condition_name"] = result.get("condition_name", condition_query.title())
    fallback["foods_to_eat"] = result.get("foods_to_eat", fallback["foods_to_eat"])
    fallback["foods_to_avoid"] = result.get("foods_to_avoid", fallback["foods_to_avoid"])
    fallback["short_desc"] = result.get("short_desc", fallback["short_desc"])
    fallback["accent_color"] = result.get("accent_color", fallback["accent_color"])
    return fallback

