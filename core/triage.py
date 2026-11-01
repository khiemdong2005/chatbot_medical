"""
================================================================================
🩺 MEDIMIND CLINICAL TRIAGE & DOUBLE GUARDRAILS ENGINE
================================================================================
Mục đích:
  - Tầng An toàn kép (Double Guardrails) cho hệ thống Chatbot Y tế phục vụ Người Dân.
  - TIỀN KIỂM (Pre-check): Phát hiện sớm dấu hiệu nguy kịch (Cờ đỏ), có xử lý bẫy phủ định ("không khó thở") và chữ không dấu.
  - HẬU KIỂM (Post-check): Chặn đứng và thay thế việc AI tự ý kê đơn thuốc kháng sinh hay thuốc đặc trị.
  - BỘ MÁY DỰ PHÒNG (Fallback Engine): Tự động tư vấn triệu chứng theo phác đồ MedlinePlus/Bộ Y Tế khi mất mạng hoặc không có API Key.
================================================================================
"""

import re
import unicodedata
from typing import Dict, Any, List, Optional


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
NEGATION_WORDS = [
    "không", "khong", "chưa", "chua", "chẳng", "chang",
    "không hề", "khong he", "chẳng hề", "chang he", "chưa hề", "chua he",
    "không bị", "khong bi", "chẳng bị", "chang bi", "chưa bị", "chua bi",
    "không có", "khong co", "chẳng có", "chang co", "chưa có", "chua co"
]

# English emergency keywords
EMERGENCY_SIGNS_EN = [
    "chest pain", "severe chest pain", "shortness of breath", "difficulty breathing",
    "cannot breathe", "choking", "facial drooping", "slurred speech", "paralysis",
    "seizure", "unconscious", "passed out", "coughing blood", "vomiting blood", "anaphylaxis"
]


# ------------------------------------------------------------------------------
# 2. BƯỚC TIỀN KIỂM: PHÁT HIỆN CỜ ĐỎ CẤP CỨU & XỬ LÝ PHỦ ĐỊNH
# ------------------------------------------------------------------------------

def assess_emergency_risk(message: str, lang: str = "vi") -> Dict[str, Any]:
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

        is_matched = (vi_kw in text_lower) or (no_kw in text_no_accent)

        if is_matched:
            # KIỂM TRA BẪY PHỦ ĐỊNH: Quét xem ngay phía trước từ khóa có từ phủ định không
            is_negated = False
            for neg in NEGATION_WORDS:
                pattern_vi = rf"\b{neg}\s+(?:(?:hề|có|thấy|bị|cảm thấy)\s+)?{re.escape(vi_kw)}"
                pattern_no = rf"\b{neg}\s+(?:(?:he|co|thay|bi|cam thay)\s+)?{re.escape(no_kw)}"
                if re.search(pattern_vi, text_lower) or re.search(pattern_no, text_no_accent):
                    is_negated = True
                    break

            if not is_negated:
                matched_flags.append(vi_kw.capitalize())

    if lang == "en":
        for en_sign in EMERGENCY_SIGNS_EN:
            if en_sign in text_lower:
                # English negation check
                pattern_en = rf"\b(no|not|without|neither)\s+({re.escape(en_sign)})"
                if not re.search(pattern_en, text_lower):
                    matched_flags.append(en_sign.title())

    if matched_flags:
        if lang == "en":
            emergency_text = (
                "⚠️ **CLINICAL EMERGENCY RED FLAG ALERT:**\n\n"
                f"The system detected emergency symptom(s): **{', '.join(matched_flags)}**.\n\n"
                "These signs may indicate acute cardiovascular, respiratory, or neurological emergencies. "
                "To ensure immediate safety:\n"
                "1. **Cease all physical exertion** and sit or rest in a well-ventilated space.\n"
                "2. **Seek assistance from family or bystanders** and immediately call Emergency Services (**911 / 115**) or proceed to the nearest emergency room.\n"
                "3. Do not take self-prescribed sedatives or strong analgesics before medical evaluation."
            )
        else:
            emergency_text = (
                "⚠️ **CẢNH BÁO LÂM SÀNG CẦN CHÚ Ý ĐẶC BIỆT:**\n\n"
                f"Hệ thống nhận thấy bạn có đề cập đến dấu hiệu: **{', '.join(matched_flags)}**.\n\n"
                "Đây là nhóm triệu chứng có thể liên quan đến các vấn đề tim mạch, hô hấp hoặc tuần hoàn cấp tính. "
                "Để đảm bảo an toàn tính mạng cao nhất, bạn nên:\n"
                "1. **Tạm dừng các hoạt động gắng sức**, ngồi hoặc nằm nghỉ ở nơi thoáng khí.\n"
                "2. **Cần người thân bên cạnh hỗ trợ** và liên hệ ngay cơ sở y tế gần nhất hoặc gọi tổng đài cấp cứu **115** để được bác sĩ kiểm tra kịp thời.\n"
                "3. Tuyệt đối không tự ý dùng các loại thuốc giảm đau hay an thần liều cao khi chưa rõ nguyên nhân."
            )
        return {
            "is_emergency": True,
            "symptoms": matched_flags,
            "message": emergency_text
        }

    return {"is_emergency": False, "symptoms": []}


# ------------------------------------------------------------------------------
# 3. BƯỚC HẬU KIỂM: MÀNG LỌC CHẶN VÀ THAY THẾ KÊ ĐƠN THUỐC KHÁNG SINH
# ------------------------------------------------------------------------------

ANTIBIOTIC_BLACKLIST = [
    "amoxicillin", "augmentin", "ciprofloxacin", "azithromycin",
    "cephalexin", "cefixime", "ampicillin", "clarithromycin",
    "metronidazole", "levofloxacin", "doxycycline", "tetracycline",
    "erythromycin", "penicillin", "gentamicin", "ceftriaxone"
]


def apply_safety_guardrails(answer: str, lang: str = "vi") -> str:
    """
    Hậu kiểm an toàn (Post-generation Guardrail):
    Rà soát câu trả lời của AI và Fallback.
    Nếu phát hiện nhắc tên thuốc kháng sinh kê đơn hoặc hướng dẫn liều dùng:
      - Loại bỏ/thay thế nội dung vi phạm bằng cảnh báo từ chối kê đơn chuẩn y tế.
      - Tuyệt đối không giữ nguyên hướng dẫn dùng thuốc kháng sinh bị cấm.
    """
    if not answer:
        return ""

    answer_lower = answer.lower()
    found_antibiotics = [ab for ab in ANTIBIOTIC_BLACKLIST if ab in answer_lower]

    if not found_antibiotics:
        return answer

    ab_names_str = ", ".join([ab.capitalize() for ab in found_antibiotics])

    if lang == "en":
        replacement_block = (
            f"> [!CAUTION]\n"
            f"> 🛑 **SAFETY INTERVENTION - PRESCRIPTION MEDICATION DETECTED ({ab_names_str}):**\n"
            "> Under strict healthcare safety protocols and MOH regulations, AI assistants are strictly prohibited "
            "from prescribing, dosing, or instructing the use of prescription antibiotics.\n"
            "> Any self-medication with antibiotics carries severe risks of acute anaphylaxis, organ toxicity, "
            "and dangerous antimicrobial resistance. Please consult a licensed medical practitioner for a proper examination and prescription."
        )
    else:
        replacement_block = (
            f"> [!CAUTION]\n"
            f"> 🛑 **CAN THIỆP AN TOÀN Y TẾ - PHÁT HIỆN THUỐC KHÁNG SINH ({ab_names_str}):**\n"
            "> Theo quy chuẩn an toàn lâm sàng của Bộ Y Tế, Trợ lý AI tuyệt đối không kê đơn, chỉ định liều dùng hoặc khuyến nghị tự ý sử dụng các loại thuốc kháng sinh.\n"
            "> Việc tự ý mua và dùng kháng sinh tiềm ẩn nguy cơ sốc phản vệ nguy kịch, tổn thương gan thận và gia tăng tình trạng kháng kháng sinh trong cộng đồng. "
            "Bạn hãy thăm khám trực tiếp tại cơ sở y tế để được bác sĩ chẩn đoán nguyên nhân và kê đơn chính xác."
        )

    # Tách đoạn văn bản và thay thế các đoạn có chứa tên kháng sinh
    paragraphs = answer.split("\n\n")
    cleaned_paragraphs = []
    replaced_any = False

    for p in paragraphs:
        p_lower = p.lower()
        if any(ab in p_lower for ab in found_antibiotics):
            # Thay thế đoạn vi phạm bằng khối can thiệp an toàn
            cleaned_paragraphs.append(replacement_block)
            replaced_any = True
        else:
            cleaned_paragraphs.append(p)

    if not replaced_any:
        cleaned_paragraphs.append(replacement_block)

    return "\n\n".join(cleaned_paragraphs)


# ------------------------------------------------------------------------------
# 4. BỘ MÁY TƯ VẤN DỰ PHÒNG NỘI BỘ (FALLBACK ENGINE - CHẠY 100% OFFLINE)
# ------------------------------------------------------------------------------

def analyze_symptoms(message: str, history: Optional[List[Dict[str, Any]]] = None, lang: str = 'vi', has_image: bool = False) -> Dict[str, Any]:
    """
    Bộ máy phân loại lâm sàng nội bộ: Hoạt động khi chưa có API Key hoặc mất mạng.
    Đưa ra lời khuyên chăm sóc ban đầu tại nhà chuẩn MedlinePlus và Bộ Y Tế.
    - Không tự suy diễn phát hiện hình ảnh khi không có xử lý ảnh thành công.
    - Đảm bảo đánh giá khẩn cấp nhất quán.
    """
    history = history or []
    text = message.lower().strip()
    
    # Kiểm tra khẩn cấp trước tiên để đảm bảo tính nhất quán
    emergency_check = assess_emergency_risk(message, lang=lang)
    if emergency_check["is_emergency"]:
        return {
            "answer": emergency_check["message"],
            "risk_level": "Nguy cơ cao (Cần thăm khám khẩn)" if lang == "vi" else "High Risk (Immediate Care Needed)",
            "risk_score": 90,
            "symptoms": emergency_check["symptoms"],
            "specialist": "Cấp cứu 115 / Khoa Cấp cứu" if lang == "vi" else "Emergency 115 / ER Department",
            "is_emergency": True,
            "visual_findings": [],
            "differential_diagnosis": ["Tình trạng cấp cứu tim mạch/hô hấp/tuần hoàn"],
            "sources": [
                {
                    "title": "Quy trình Cấp cứu Ban đầu - Bộ Y Tế",
                    "source": "Cục Quản lý Khám chữa bệnh",
                    "url": "https://kcb.vn"
                }
            ]
        }

    risk_score = 30
    risk_level = "Thấp (Tự chăm sóc & Theo dõi)" if lang == "vi" else "Low (Self-care & Monitor)"
    specialist = "Nội tổng quát / Y học gia đình" if lang == "vi" else "General Internal Medicine"

    # Phát hiện chào hỏi
    GREETING_PATTERNS = [
        r"^hello\b", r"^hi\b", r"^hey\b", r"^alo\b",
        r"^xin ch[àa]o\b", r"^ch[àa]o\b", r"^ch[àa]o b[ạa]n\b"
    ]
    is_greeting = any(re.search(pat, text) for pat in GREETING_PATTERNS) or text in ["hello", "hi", "chào", "xin chào"]

    # Nhận diện triệu chứng
    is_fever = any(w in text for w in ["sốt", "sot", "nhiệt độ", "nong", "fever", "temperature"])
    is_cough_throat = any(w in text for w in ["ho", "rát họng", "đau họng", "dau hong", "rat hong", "cough", "sore throat"])
    is_headache = any(w in text for w in ["đau đầu", "dau dau", "nhức đầu", "nhuc dau", "headache"])
    is_stomach = any(w in text for w in ["đau bụng", "dau bung", "tiêu chảy", "tieu chay", "buồn nôn", "da day", "dạ dày", "stomach", "diarrhea"])
    is_respiratory = any(w in text for w in ["nghẹt mũi", "nghet mui", "sổ mũi", "so mui", "chảy nước mũi", "runny nose", "congestion"])
    is_skin = any(w in text for w in [
        "tổn thương", "ton thuong", "bệnh da", "benh da", "da liễu", "da lieu",
        "mẩn ngứa", "man ngua", "ngứa", "ngua", "mụn nước", "mun nuoc", "phát ban", "phat ban",
        "mề đay", "me day", "nổi mề đay", "dị ứng", "di ung", "zona", "chàm", "cham", "eczema",
        "nấm da", "nam da", "mụn trứng cá", "mun trung ca", "rash", "itchy", "hives"
    ])

    has_symptoms = any([is_fever, is_cough_throat, is_headache, is_stomach, is_respiratory, is_skin])

    # Nếu chỉ chào hỏi
    if not has_symptoms and is_greeting:
        return {
            "answer": (
                "Chào bạn! Tôi là **Trợ lý Sức khỏe MediMind AI**.\n\n"
                "Hôm nay bạn cảm thấy trong người thế nào? Hãy chia sẻ với mình các biểu hiện cơ thể bạn đang gặp "
                "(ví dụ: đau họng, sốt, ho, đau đầu, mệt mỏi hay câu hỏi về thuốc/chỉ số xét nghiệm) để mình hỗ trợ tư vấn ban đầu nhé!"
            ) if lang == "vi" else (
                "Hello! I am your **MediMind AI Health Assistant**.\n\n"
                "How are you feeling today? Please describe any symptoms or health questions you have so I can provide initial evidence-based guidance."
            ),
            "risk_level": "Chào hỏi ban đầu" if lang == "vi" else "Initial Greeting",
            "risk_score": 10,
            "symptoms": ["Khởi tạo hội thoại"],
            "specialist": "Y học gia đình" if lang == "vi" else "Family Medicine",
            "visual_findings": [],
            "differential_diagnosis": [],
            "is_emergency": False,
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
            ) if lang == "vi" else (
                "Thank you for reaching out. To assist you with more accurate initial guidance, could you provide more details?\n\n"
                "• Where is the discomfort located?\n"
                "• How long have you experienced these symptoms?\n"
                "• Do you have any fever, fatigue, or other related signs?"
            ),
            "risk_level": "Cần thêm thông tin" if lang == "vi" else "Information Needed",
            "risk_score": 15,
            "symptoms": ["Mô tả chưa rõ"],
            "specialist": "Nội tổng quát" if lang == "vi" else "General Internal Medicine",
            "visual_findings": [],
            "differential_diagnosis": [],
            "is_emergency": False,
            "sources": [{"title": "MedlinePlus Medical Encyclopedia", "url": "https://medlineplus.gov"}]
        }

    # Xây dựng phản hồi lâm sàng tự nhiên & thấu cảm
    symptoms_detected = []
    advice_bullets = []
    diff_diag = []

    if is_fever and is_cough_throat:
        symptoms_detected = ["Sốt", "Đau rát họng / Ho"]
        risk_score = 45
        risk_level = "Trung bình (Theo dõi & Chăm sóc)"
        specialist = "Tai Mũi Họng / Hô hấp"
        diff_diag = ["Viêm họng cấp thể xuất tiết", "Nhiễm virus đường hô hấp trên"]
        advice_bullets = [
            "**Súc họng nước muối ấm (0.9%):** Súc miệng từ 3 - 4 lần mỗi ngày sau ăn và trước khi đi ngủ giúp sát khuẩn, giảm phù nề niêm mạc họng.",
            "**Uống nhiều nước ấm:** Bổ sung từ 1.5 - 2 lít nước ấm, nước cam hoặc nước chanh ấm để làm dịu cổ họng và hỗ trợ hạ nhiệt.",
            "**Theo dõi thân nhiệt:** Nếu sốt trên 38.5°C hoặc đau rát nhiều, có thể dùng Paracetamol 500mg (cách nhau 4 - 6 giờ/lần, không quá 3000mg/ngày) nếu không có tiền sử dị ứng hay bệnh gan.",
            "**Dấu hiệu cần đi khám:** Nếu sốt cao liên tục không hạ sau 48 giờ hoặc có đờm đặc màu vàng/xanh, hãy tới cơ sở y tế gần nhất."
        ]
    elif is_cough_throat:
        symptoms_detected = ["Viêm đau họng / Ho"]
        specialist = "Tai Mũi Họng"
        diff_diag = ["Viêm họng do kích ứng hoặc virus"]
        advice_bullets = [
            "**Giữ ấm vùng cổ và ngực:** Tránh uống nước đá lạnh hoặc ngồi phòng điều hòa nhiệt độ quá thấp (< 25°C).",
            "**Súc họng nước muối sinh lý:** Thực hiện đều đặn mỗi ngày giúp giảm cảm giác ngứa rát và tan đờm.",
            "**Dùng siro ho thảo dược:** Có thể ngậm mật ong chanh đào hoặc siro ho thảo dược an toàn để làm dịu cơn ho khan."
        ]
    elif is_skin:
        symptoms_detected = ["Tổn thương da / Mẩn ngứa / Dị ứng da"]
        specialist = "Da liễu (Dermatology)"
        risk_score = 35
        diff_diag = ["Mề đay cấp tính (Urticaria)", "Viêm da tiếp xúc dị ứng"]
        advice_bullets = [
            "**Vệ sinh vùng da sạch sẽ:** Rửa nhẹ nhàng bằng nước sạch hoặc nước muối sinh lý 0.9%, lau khô bằng khăn bông mềm, tuyệt đối không chà xát hoặc cào gãi làm trầy xước.",
            "**Chườm mát làm dịu:** Dùng khăn sạch thấm nước mát đắp lên vùng da ngứa rát trong 10 - 15 phút để giảm cảm giác châm chích và làm dịu phản ứng sung huyết.",
            "**Tránh tác nhân kích ứng:** Tạm ngưng sử dụng các loại xà phòng, sữa tắm có chất tẩy rửa mạnh hoặc hóa chất; mặc trang phục rộng rãi, thoáng mát bằng chất liệu cotton tự nhiên.",
            "**Dấu hiệu cần đi khám ngay:** Nếu tổn thương lan rộng nhanh, có bọng nước vỡ loét, kèm theo sốt cao hoặc sưng nề vùng mắt/môi, bạn cần đến chuyên khoa Da liễu để bác sĩ thăm khám trực tiếp."
        ]
    elif is_stomach:
        symptoms_detected = ["Đau bụng / Rối loạn tiêu hóa"]
        risk_score = 40
        specialist = "Tiêu hóa"
        diff_diag = ["Rối loạn tiêu hóa chức năng", "Viêm dạ dày ruột nhẹ"]
        advice_bullets = [
            "**Chế độ ăn nhẹ thanh đạm:** Ưu tiên cháo loãng, súp nóng, chia nhỏ bữa ăn và tạm tránh đồ cay nóng, dầu mỡ, cà phê.",
            "**Bù nước và điện giải:** Nếu có kèm tiêu chảy, hãy pha Oresol đúng tỷ lệ ghi trên gói để uống từng ngụm nhỏ.",
            "**Dấu hiệu cần cấp cứu:** Nếu đau quặn dữ dội lệch hố chậu phải (nghi viêm ruột thừa) hoặc nôn nhiều, hãy tới bệnh viện ngay."
        ]
    else:
        symptoms_detected = ["Mệt mỏi / Cảm cúm nhẹ"]
        specialist = "Nội tổng quát"
        diff_diag = ["Hội chứng cảm cúm thông thường"]
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

    # KHÔNG tự suy diễn phát hiện hình ảnh khi không có xử lý ảnh thực tế
    visual_findings_result = ["Quan sát hình thái tổn thương da (chờ bác sĩ trực tiếp đối chiếu)"] if (has_image and is_skin) else []

    return {
        "answer": answer_text,
        "risk_level": risk_level,
        "risk_score": max(0, min(100, risk_score)),
        "symptoms": symptoms_detected,
        "specialist": specialist,
        "differential_diagnosis": diff_diag,
        "visual_findings": visual_findings_result,
        "is_emergency": False,
        "sources": [
            {
                "title": "MedlinePlus Medical Encyclopedia - NIH",
                "source": "Thư viện Y khoa Quốc gia Hoa Kỳ",
                "url": "https://medlineplus.gov"
            }
        ]
    }
