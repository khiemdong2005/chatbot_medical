"""
================================================================================
🩺 MEDIMIND CLINICAL TRIAGE & DOUBLE GUARDRAILS ENGINE
================================================================================
Mục đích:
  - Tầng An toàn kép (Double Guardrails) cho hệ thống Chatbot Y tế phục vụ Người Dân.
  - TIỀN KIỂM (Pre-check): Phát hiện sớm dấu hiệu nguy kịch (Cờ đỏ), có xử lý bẫy phủ định ("không khó thở") và chữ không dấu.
  - HẬU KIỂM (Post-check): Chặn đứng việc AI tự ý kê đơn thuốc kháng sinh hay thuốc đặc trị.
  - BỘ MÁY DỰ PHÒNG (Fallback Engine): Tự động tư vấn triệu chứng theo phác đồ MedlinePlus/Bộ Y Tế khi mất mạng hoặc không có API Key.
================================================================================
"""

import re
import unicodedata
from typing import Dict, Any, List


# ------------------------------------------------------------------------------
# 1. HÀM CHUẨN HÓA VĂN BẢN (HỖ TRỢ ĐỌC KHÔNG DẤU & XỬ LÝ PHỦ ĐỊNH)
# ------------------------------------------------------------------------------

def remove_accents(input_str: str) -> str:
    """Loại bỏ dấu tiếng Việt để phát hiện người dân gõ không dấu (ví dụ: 'tuc nguc')."""
    if not input_str:
        return ""
    nfkd = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower()


# Danh sách từ khóa cờ đỏ nguy kịch đe dọa tính mạng
EMERGENCY_SIGNS = [
    # Tim mạch & Hô hấp
    {"vi": "đau ngực dữ dội", "no_accent": "dau nguc du doi"},
    {"vi": "tức ngực", "no_accent": "tuc nguc"},
    {"vi": "đau thắt ngực", "no_accent": "dau that nguc"},
    {"vi": "khó thở dữ dội", "no_accent": "kho tho du doi"},
    {"vi": "ngạt thở", "no_accent": "ngat tho"},
    {"vi": "ngừng thở", "no_accent": "ngung tho"},
    
    # Đột quỵ thần kinh (Quy tắc FAST)
    {"vi": "méo miệng", "no_accent": "meo mieng"},
    {"vi": "liệt nửa người", "no_accent": "liet nua nguoi"},
    {"vi": "yếu nửa người", "no_accent": "yeu nua nguoi"},
    {"vi": "nói đớ", "no_accent": "noi do"},
    {"vi": "nói ngọng đột ngột", "no_accent": "noi ngong"},
    {"vi": "mất thị lực đột ngột", "no_accent": "mat thi luc"},
    
    # Cấp cứu ngoại khoa & Phản vệ
    {"vi": "co giật", "no_accent": "co giat"},
    {"vi": "hôn mê", "no_accent": "hon me"},
    {"vi": "bất tỉnh", "no_accent": "bat tinh"},
    {"vi": "nôn ra máu", "no_accent": "non ra mau"},
    {"vi": "ho ra máu", "no_accent": "ho ra mau"},
    {"vi": "sốc phản vệ", "no_accent": "soc phan ve"}
]

# Danh mục các từ phủ định trong tiếng Việt để tránh báo nhầm ("tôi không khó thở")
NEGATION_WORDS = ["không", "khong", "chưa", "chua", "chẳng", "chang", "không hề", "khong he", "không bị", "khong bi"]


# ------------------------------------------------------------------------------
# 2. BƯỚC TIỀN KIỂM: PHÁT HIỆN CỜ ĐỎ CẤP CỨU & XỬ LÝ PHỦ ĐỊNH
# ------------------------------------------------------------------------------

def assess_emergency_risk(message: str) -> Dict[str, Any]:
    """
    Tiền kiểm an toàn: Quét xem tin nhắn người dân có dấu hiệu nguy kịch hay không.
    Có cơ chế phân tích cụm phủ định để không báo nhầm (ví dụ: 'sốt nhưng không khó thở').
    """
    text_lower = message.lower()
    text_no_accent = remove_accents(message)
    matched_flags = []

    for sign in EMERGENCY_SIGNS:
        vi_kw = sign["vi"]
        no_kw = sign["no_accent"]

        # Kiểm tra xem từ khóa có xuất hiện trong tin nhắn (có dấu hoặc không dấu)
        is_matched = (vi_kw in text_lower) or (no_kw in text_no_accent)

        if is_matched:
            # KIỂM TRA BẪY PHỦ ĐỊNH: Quét xem ngay phía trước từ khóa có từ "không" không
            # Ví dụ: "không bị khó thở", "không tức ngực"
            is_negated = False
            for neg in NEGATION_WORDS:
                pattern_vi = rf"\b{neg}\s+(bị\s+)?{re.escape(vi_kw)}"
                pattern_no = rf"\b{neg}\s+(bi\s+)?{re.escape(no_kw)}"
                if re.search(pattern_vi, text_lower) or re.search(pattern_no, text_no_accent):
                    is_negated = True
                    break

            # Nếu KHÔNG bị phủ định thì mới tính là cờ đỏ thực sự!
            if not is_negated:
                matched_flags.append(vi_kw.capitalize())

    if matched_flags:
        return {
            "is_emergency": True,
            "symptoms": matched_flags,
            "message": (
                "⚠️ **CẢNH BÁO LÂM SÀNG CẦN CHÚ Ý ĐẶC BIỆT:**\n\n"
                f"Hệ thống nhận thấy bạn có đề cập đến dấu hiệu: **{', '.join(matched_flags)}**.\n\n"
                "Đây là nhóm triệu chứng có thể liên quan đến các vấn đề tim mạch, hô hấp hoặc tuần hoàn cấp tính. "
                "Để đảm bảo an toàn tính mạng cao nhất, bạn nên:\n"
                "1. **Tạm dừng các hoạt động gắng sức**, ngồi hoặc nằm nghỉ ở nơi thoáng khí.\n"
                "2. **Cần người thân bên cạnh hỗ trợ** và liên hệ ngay cơ sở y tế gần nhất hoặc gọi tổng đài cấp cứu **115** để được bác sĩ kiểm tra kịp thời.\n"
                "3. Tuyệt đối không tự ý dùng các loại thuốc giảm đau hay an thần liều cao khi chưa rõ nguyên nhân."
            )
        }

    return {"is_emergency": False, "symptoms": []}


# ------------------------------------------------------------------------------
# 3. BƯỚC HẬU KIỂM: MÀNG LỌC CHẶN KÊ ĐƠN THUỐC KHÁNG SINH BỪA BÃI
# ------------------------------------------------------------------------------

ANTIBIOTIC_BLACKLIST = [
    "amoxicillin", "augmentin", "ciprofloxacin", "azithromycin",
    "cephalexin", "cefixime", "ampicillin", "clarithromycin",
    "metronidazole", "levofloxacin", "doxycycline", "tetracycline",
    "erythromycin", "penicillin", "gentamicin", "ceftriaxone"
]

def apply_safety_guardrails(answer: str) -> str:
    """
    Hậu kiểm an toàn (Post-generation Guardrail):
    Rà soát câu trả lời của AI trước khi gửi cho người dân.
    Nếu phát hiện nhắc tên thuốc kháng sinh kê đơn -> Tự động thêm khuyến cáo an toàn bắt buộc.
    """
    answer_lower = answer.lower()
    found_antibiotics = [ab for ab in ANTIBIOTIC_BLACKLIST if ab in answer_lower]

    if found_antibiotics:
        warning_note = (
            "\n\n> [!CAUTION]\n"
            f"> ⚠️ **CẢNH BÁO AN TOÀN DƯỢC PHẨM:**\n"
            f"> Thuốc được đề cập ({', '.join(found_antibiotics).capitalize()}) thuộc nhóm **KHÁNG SINH KÊ ĐƠN BẮT BUỘC**.\n"
            "> Theo quy định của Bộ Y Tế, AI tuyệt đối không chỉ định liều dùng. Bạn **không được tự ý mua uống** để tránh nguy cơ sốc phản vệ và vi khuẩn kháng thuốc. Hãy thăm khám bác sĩ chuyên khoa để có đơn thuốc chính xác."
        )
        return answer + warning_note

    return answer


# ------------------------------------------------------------------------------
# 4. BỘ MÁY TƯ VẤN DỰ PHÒNG NỘI BỘ (FALLBACK ENGINE - CHẠY 100% OFFLINE)
# ------------------------------------------------------------------------------

def analyze_symptoms(message: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Bộ máy phân loại lâm sàng nội bộ: Hoạt động khi chưa có API Key hoặc mất mạng.
    Đưa ra lời khuyên chăm sóc ban đầu tại nhà chuẩn MedlinePlus và Bộ Y Tế.
    """
    text = message.lower().strip()
    risk_score = 30
    risk_level = "Thấp (Tự chăm sóc & Theo dõi)"
    specialist = "Nội tổng quát / Y học gia đình"

    # Phát hiện chào hỏi
    GREETING_PATTERNS = [
        r"^hello\b", r"^hi\b", r"^hey\b", r"^alo\b",
        r"^xin ch[àa]o\b", r"^ch[àa]o\b", r"^ch[àa]o b[ạa]n\b"
    ]
    is_greeting = any(re.search(pat, text) for pat in GREETING_PATTERNS) or text in ["hello", "hi", "chào", "xin chào"]

    # Nhận diện triệu chứng
    is_fever = any(w in text for w in ["sốt", "sot", "nhiệt độ", "nong"])
    is_cough_throat = any(w in text for w in ["ho", "rát họng", "đau họng", "dau hong", "rat hong"])
    is_headache = any(w in text for w in ["đau đầu", "dau dau", "nhức đầu", "nhuc dau"])
    is_stomach = any(w in text for w in ["đau bụng", "dau bung", "tiêu chảy", "tieu chay", "buồn nôn", "da day", "dạ dày"])
    is_respiratory = any(w in text for w in ["nghẹt mũi", "nghet mui", "sổ mũi", "so mui", "chảy nước mũi"])

    has_symptoms = any([is_fever, is_cough_throat, is_headache, is_stomach, is_respiratory])

    # Nếu chỉ chào hỏi
    if not has_symptoms and is_greeting:
        return {
            "answer": (
                "Chào bạn! Tôi là **Trợ lý Sức khỏe MediMind AI**.\n\n"
                "Hôm nay bạn cảm thấy trong người thế nào? Hãy chia sẻ với mình các biểu hiện cơ thể bạn đang gặp "
                "(ví dụ: đau họng, sốt, ho, đau đầu, mệt mỏi hay câu hỏi về thuốc/chỉ số xét nghiệm) để mình hỗ trợ tư vấn ban đầu nhé!"
            ),
            "risk_level": "Chào hỏi ban đầu",
            "risk_score": 10,
            "symptoms": ["Khởi tạo hội thoại"],
            "specialist": "Y học gia đình",
            "sources": [{"title": "Hệ thống Tư vấn Sức khỏe Ban đầu MediMind", "url": "https://medlineplus.gov"}]
        }

    # Nếu người dùng hỏi mà chưa thấy triệu chứng rõ
    if not has_symptoms:
        return {
            "answer": (
                "Mình đã ghi nhận tin nhắn từ bạn. Để mình hỗ trợ tư vấn chăm sóc sức khỏe chính xác hơn, "
                "bạn có thể mô tả cụ thể hơn không?\n\n"
                "• Bạn cảm thấy khó chịu ở vị trí nào trên cơ thể?\n"
                "• Dấu hiệu này xuất hiện được bao nhiêu ngày rồi?\n"
                "• Có kèm theo sốt, mệt mỏi hay biểu hiện gì khác không?"
            ),
            "risk_level": "Cần thêm thông tin",
            "risk_score": 15,
            "symptoms": ["Mô tả chưa rõ"],
            "specialist": "Nội tổng quát",
            "sources": [{"title": "MedlinePlus Medical Encyclopedia", "url": "https://medlineplus.gov"}]
        }

    # Xây dựng phản hồi lâm sàng tự nhiên & thấu cảm
    symptoms_detected = []
    advice_bullets = []

    if is_fever and is_cough_throat:
        symptoms_detected = ["Sốt", "Đau rát họng / Ho"]
        risk_score = 45
        risk_level = "Trung bình (Theo dõi & Chăm sóc)"
        specialist = "Tai Mũi Họng / Hô hấp"
        advice_bullets = [
            "**Súc họng nước muối ấm (0.9%):** Súc miệng từ 3 - 4 lần mỗi ngày sau ăn và trước khi đi ngủ giúp sát khuẩn, giảm phù nề niêm mạc họng.",
            "**Uống nhiều nước ấm:** Bổ sung từ 1.5 - 2 lít nước ấm, nước cam hoặc nước chanh ấm để làm dịu cổ họng và hỗ trợ hạ nhiệt.",
            "**Theo dõi thân nhiệt:** Nếu sốt trên 38.5°C hoặc đau rát nhiều, có thể dùng Paracetamol 500mg (cách nhau 4 - 6 giờ/lần, không quá 3000mg/ngày) nếu không có tiền sử dị ứng hay bệnh gan.",
            "**Dấu hiệu cần đi khám:** Nếu sốt cao liên tục không hạ sau 48 giờ hoặc có đờm đặc màu vàng/xanh, hãy tới cơ sở y tế gần nhất."
        ]
    elif is_cough_throat:
        symptoms_detected = ["Viêm đau họng / Ho"]
        specialist = "Tai Mũi Họng"
        advice_bullets = [
            "**Giữ ấm vùng cổ và ngực:** Tránh uống nước đá lạnh hoặc ngồi phòng điều hòa nhiệt độ quá thấp (< 25°C).",
            "**Súc họng nước muối sinh lý:** Thực hiện đều đặn mỗi ngày giúp giảm cảm giác ngứa rát và tan đờm.",
            "**Dùng siro ho thảo dược:** Có thể ngậm mật ong chanh đào hoặc siro ho thảo dược an toàn để làm dịu cơn ho khan."
        ]
    elif is_stomach:
        symptoms_detected = ["Đau bụng / Rối loạn tiêu hóa"]
        risk_score = 40
        specialist = "Tiêu hóa"
        advice_bullets = [
            "**Chế độ ăn nhẹ thanh đạm:** Ưu tiên cháo loãng, súp nóng, chia nhỏ bữa ăn và tạm tránh đồ cay nóng, dầu mỡ, cà phê.",
            "**Bù nước và điện giải:** Nếu có kèm tiêu chảy, hãy pha Oresol đúng tỷ lệ ghi trên gói để uống từng ngụm nhỏ.",
            "**Dấu hiệu cần cấp cứu:** Nếu đau quặn dữ dội lệch hố chậu phải (nghi viêm ruột thừa) hoặc nôn nhiều, hãy tới bệnh viện ngay."
        ]
    else:
        symptoms_detected = ["Mệt mỏi / Cảm cúm nhẹ"]
        specialist = "Nội tổng quát"
        advice_bullets = [
            "**Nghỉ ngơi đầy đủ:** Giữ phòng ngủ thoáng khí, ngủ đủ giấc để cơ thể tự phục hồi hệ miễn dịch.",
            "**Bổ sung dinh dưỡng:** Ăn thức ăn lỏng ấm, bổ sung vitamin C từ hoa quả tươi."
        ]

    bullets_text = "\n".join([f"• {b}" for b in advice_bullets])
    answer_text = (
        f"Dựa trên các dấu hiệu bạn chia sẻ ({', '.join(symptoms_detected)}), "
        "tình trạng này thường gặp ở phản ứng viêm đường hô hấp hoặc rối loạn nhẹ. "
        "Dưới đây là một số hướng dẫn chăm sóc ban đầu tại nhà an toàn:\n\n"
        f"{bullets_text}\n\n"
        "*Lưu ý: Các hướng dẫn trên mang tính chất hỗ trợ chăm sóc ban đầu. Nếu các triệu chứng kéo dài trên 3 ngày hoặc có chiều hướng nặng lên, bạn hãy tới cơ sở y tế để được bác sĩ thăm khám trực tiếp nhé.*"
    )

    return {
        "answer": answer_text,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "symptoms": symptoms_detected,
        "specialist": specialist,
        "sources": [
            {
                "title": "MedlinePlus Medical Encyclopedia - NIH",
                "source": "Thư viện Y khoa Quốc gia Hoa Kỳ",
                "url": "https://medlineplus.gov"
            }
        ]
    }
