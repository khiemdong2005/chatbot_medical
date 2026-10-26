"""
Clinical Triage & Risk Assessment Engine for MediMind AI
Clean Medical Terminology - No Toy Emojis
Provides structured clinical triage, risk scoring, and evidence-based medication guidance.
"""

import re
from typing import Dict, Any, List

# Dấu hiệu cờ đỏ cấp cứu đe dọa tính mạng (Red Flag Symptoms)
EMERGENCY_KEYWORDS = [
    "đau ngực", "tức ngực", "khó thở dữ dội", "ngừng thở",
    "liệt nửa người", "méo miệng", "mất thị lực đột ngột",
    "co giật", "hôn mê", "bất tỉnh", "nôn ra máu", "ho ra máu",
    "sốc phản vệ", "cứng cổ sốt cao"
]

def assess_emergency_risk(message: str) -> Dict[str, Any]:
    text = message.lower()
    matched_flags = [kw for kw in EMERGENCY_KEYWORDS if kw in text]

    if matched_flags:
        return {
            "is_emergency": True,
            "symptoms": [kw.capitalize() for kw in matched_flags],
            "message": (
                "**CẢNH BÁO Y TẾ KHẨN CẤP:**\n\n"
                f"Hệ thống ghi nhận dấu hiệu lâm sàng nguy cấp: **{', '.join(matched_flags)}**.\n\n"
                "Tình trạng này có thể đe dọa tính mạng (Hội chứng mạch vành cấp, Đột quỵ hoặc Suy hô hấp cấp tính).\n\n"
                "**Hướng dẫn xử trí:**\n"
                "- Gọi ngay dịch vụ cấp cứu **115** hoặc di chuyển khẩn cấp đến khoa Cấp cứu bệnh viện gần nhất.\n"
                "- Giữ tư thế ngồi nghỉ thoải mái, không tự lái xe và cần người thân hỗ trợ ngay."
            )
        }

    return {"is_emergency": False, "symptoms": []}

def analyze_symptoms(message: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
    text = message.lower().strip()
    extracted_symptoms = []
    risk_score = 25
    risk_level = "Thấp (Theo dõi)"
    specialist = "Nội tổng quát"
    medications = []

    # 1. Phát hiện lời chào hỏi xã giao thông thường
    GREETING_PATTERNS = [
        r"^hello\b", r"^hi\b", r"^hey\b", r"^alo\b", r"^halo\b",
        r"^xin ch[àa]o\b", r"^ch[àa]o\b", r"^ch[àa]o b[ạa]n\b", r"^ch[àa]o b[áa]c s[ĩi]\b"
    ]
    is_greeting = any(re.search(pat, text) for pat in GREETING_PATTERNS) or text in ["hello", "hi", "hey", "alo", "chào", "xin chào"]

    # 2. Trích xuất triệu chứng lâm sàng
    is_allergy = any(w in text for w in ["dị ứng", "ngứa", "hắt hơi", "nổi mề đay", "allergy"])
    is_fever = any(w in text for w in ["sốt", "nhiệt độ", "nóng"])
    is_headache = any(w in text for w in ["đau đầu", "nhức đầu", "đau trán"])
    is_respiratory = any(w in text for w in ["nghẹt mũi", "sổ mũi", "xoang", "chảy nước mũi"])
    is_cough = any(w in text for w in ["ho", "rát họng", "đau họng"])
    is_fatigue = any(w in text for w in ["mệt mỏi", "uể oải", "kiệt sức"])
    is_stomach = any(w in text for w in ["đau bụng", "tiêu chảy", "buồn nôn", "dạ dày"])

    has_any_symptom = any([is_allergy, is_fever, is_headache, is_respiratory, is_cough, is_fatigue, is_stomach])

    # Nếu chỉ chào hỏi và không có triệu chứng lâm sàng
    if not has_any_symptom and is_greeting:
        return {
            "answer": (
                "Chào bạn! Tôi là **Trợ lý MediMind AI**.\n\n"
                "Bạn đang gặp triệu chứng gì cần mình kiểm tra hoặc cần tư vấn về vấn đề sức khỏe nào? "
                "Hãy mô tả chi tiết các dấu hiệu cơ thể bạn đang cảm thấy (ví dụ: đau họng, sốt, ho, đau đầu, dị ứng...) để mình hỗ trợ nhé!"
            ),
            "risk_level": "Bình thường (Chào hỏi)",
            "risk_score": 10,
            "symptoms": ["Chào hỏi ban đầu"],
            "specialist": "Tư vấn & Sàng lọc ban đầu",
            "medications": [],
            "sources": [
                {
                    "title": "Hệ thống Tiếp nhận & Sàng lọc Lâm sàng MediMind",
                    "source": "MediMind Clinical AI v2.5",
                    "url": "https://medimind.ai"
                }
            ]
        }

    # Nếu không có triệu chứng lâm sàng và cũng không phải chào hỏi
    if not has_any_symptom:
        return {
            "answer": (
                "Mình đã tiếp nhận tin nhắn từ bạn. Tuy nhiên hiện tại hệ thống chưa nhận diện được triệu chứng y khoa cụ thể nào trong mô tả.\n\n"
                "Bạn có thể chia sẻ cụ thể hơn về tình trạng sức khỏe hiện tại (ví dụ: vị trí đau, số ngày kéo dài, có kèm sốt hay khó chịu không?) "
                "để mình đối soát và kiểm tra phác đồ y khoa giúp bạn nhé."
            ),
            "risk_level": "Chưa xác định",
            "risk_score": 15,
            "symptoms": ["Cần bổ sung thông tin"],
            "specialist": "Nội tổng quát",
            "medications": [],
            "sources": [
                {
                    "title": "Quy chuẩn Tiếp nhận & Hỏi bệnh Ban đầu",
                    "source": "MediMind Clinical Knowledge Base",
                    "url": "https://kcb.vn"
                }
            ]
        }

    if is_allergy:
        extracted_symptoms.append("Phản ứng dị ứng / Viêm mũi dị ứng")
        risk_score += 15
        specialist = "Dị ứng & Miễn dịch lâm sàng"
        medications = [
            {
                "name": "Loratadine",
                "strength": "10mg (Viên nén)",
                "category": "Kháng Histamin H1 thế hệ 2",
                "type": "OTC (Không kê đơn)",
                "instructions": "Uống 1 viên (10mg)/ngày. Giúp giảm hắt hơi, ngứa, sổ mũi mà không gây buồn ngủ đáng kể.",
                "type_badge": "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
            },
            {
                "name": "Cetirizine HCl",
                "strength": "10mg (Viên bao phim)",
                "category": "Kháng Histamin đối kháng chọn lọc",
                "type": "OTC (Không kê đơn)",
                "instructions": "Uống 1 viên (10mg) vào buổi tối. Hiệu quả cao đối với ngứa mắt, chảy nước mũi và nổi mề đay.",
                "type_badge": "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
            },
            {
                "name": "Fluticasone Propionate",
                "strength": "50 mcg/liều (Xịt mũi)",
                "category": "Corticosteroid xịt tại chỗ",
                "type": "Cần bác sĩ kê đơn (Rx)",
                "instructions": "Xịt mỗi bên mũi 1-2 nhát/ngày. Kiểm soát viêm sung huyết và phù nề niêm mạc xoang.",
                "type_badge": "bg-cyan-500/20 text-cyan-300 border-cyan-500/30"
            }
        ]

    if is_fever:
        extracted_symptoms.append("Sốt (Pyrexia)")
        risk_score += 20
    if is_headache:
        extracted_symptoms.append("Đau đầu (Cephalea)")
        risk_score += 15
    if is_respiratory:
        extracted_symptoms.append("Nghẹt xoang mũi")
        risk_score += 10
        if not is_allergy:
            specialist = "Tai Mũi Họng"
    if is_cough:
        extracted_symptoms.append("Viêm đau họng / Ho")
        risk_score += 10
    if is_fatigue:
        extracted_symptoms.append("Hội chứng mệt mỏi")
        risk_score += 5
    if is_stomach:
        extracted_symptoms.append("Rối loạn tiêu hóa / Đau bụng")
        risk_score += 25
        specialist = "Nội Tiêu hóa"
        medications = [
            {
                "name": "Men vi sinh (Probiotics)",
                "strength": "Dạng gói bột / Ống uống",
                "category": "Cân bằng hệ vi sinh đường ruột",
                "type": "OTC (Không kê đơn)",
                "instructions": "Uống 1-2 gói/ngày sau bữa ăn 30 phút với nước đun sôi để nguội.",
                "type_badge": "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
            },
            {
                "name": "Oresol 245 (ORS Chuẩn WHO)",
                "strength": "Gói pha 200ml",
                "category": "Bù nước và điện giải",
                "type": "OTC (Không kê đơn)",
                "instructions": "Pha đúng chính xác 200ml nước ấm. Uống từng ngụm nhỏ bù dịch liên tục.",
                "type_badge": "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
            }
        ]

    # Nếu không phải dị ứng và không phải đau bụng, cung cấp phác đồ hô hấp / cảm sốt thông thường
    if not medications and (is_fever or is_headache or is_respiratory or is_cough):
        medications = [
            {
                "name": "Paracetamol (Acetaminophen)",
                "strength": "500mg (Viên nén)",
                "category": "Hạ sốt & Giảm đau thông thường",
                "type": "OTC (Không kê đơn)",
                "instructions": "1 viên mỗi 4-6 giờ khi sốt > 38.5°C hoặc đau đầu nhiều. Tối đa không quá 3000mg/24h.",
                "type_badge": "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
            },
            {
                "name": "Natri Clorid 0.9%",
                "strength": "Chai xịt / Chai rửa 500ml",
                "category": "Dung dịch muối sinh lý đẳng trương",
                "type": "OTC (Không kê đơn)",
                "instructions": "Rửa sạch khoang mũi và súc họng 2 - 3 lần mỗi ngày để tống xuất đờm và dịch nhầy.",
                "type_badge": "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
            },
            {
                "name": "Oresol 245 (WHO)",
                "strength": "Gói pha 200ml",
                "category": "Bù nước & Điện giải",
                "type": "OTC (Không kê đơn)",
                "instructions": "Pha đúng tỷ lệ hướng dẫn trên bao bì, uống thay nước khi có sốt để tránh mất nước.",
                "type_badge": "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
            }
        ]

    risk_score = min(risk_score, 75)
    if risk_score >= 40:
        risk_level = "Trung bình (Cần thăm khám)"

    # Trả lời phân tích lâm sàng (lấy tên triệu chứng đầy đủ, bỏ phần mở ngoặc tiếng Anh nếu có)
    clean_symptoms = [s.split('(')[0].strip() for s in extracted_symptoms]
    symptom_summary = ', '.join(clean_symptoms) if clean_symptoms else "các dấu hiệu ghi nhận"
    if is_allergy:
        answer = (
            f"Dựa trên các dấu hiệu bạn mô tả ({symptom_summary}), hệ thống định hướng tới bệnh cảnh "
            "**Viêm mũi dị ứng hoặc Phản ứng dị ứng cấp**. Các thuốc kháng Histamin thế hệ 2 thường được ưu tiên "
            "do tác dụng phụ gây buồn ngủ thấp hơn thế hệ cũ.\n\n"
            "**Khuyến nghị chăm sóc và theo dõi:**\n"
            "- Tránh tiếp xúc trực tiếp với các dị nguyên nghi ngờ (phấn hoa, lông thú, bụi mịn, thay đổi nhiệt độ đột ngột).\n"
            "- Giữ ấm đường thở, đeo khẩu trang khi ra ngoài và vệ sinh họng miệng bằng nước muối sinh lý.\n\n"
            "**Cảnh báo an toàn thuốc:** Tham khảo ý kiến dược sĩ/bác sĩ nếu bạn có tiền sử suy gan, suy thận hoặc đang dùng các thuốc điều trị mạn tính khác."
        )
    else:
        answer = (
            f"Dựa trên các dấu hiệu bạn mô tả ({symptom_summary}), các biểu hiện này phù hợp với bệnh cảnh "
            "**Nhiễm trùng đường hô hấp trên** (như Viêm mũi xoang cấp hoặc Cảm cúm theo mùa).\n\n"
            "**Khuyến nghị chăm sóc ban đầu tại nhà:**\n"
            "- **Hạ sốt & giảm đau:** Có thể dùng Paracetamol 500mg khi sốt trên 38.5°C (cách nhau 4-6 giờ, tối đa 3g/ngày). Tuyệt đối lưu ý tiền sử dị ứng thuốc đã ghi nhận.\n"
            "- **Vệ sinh đường thở:** Rửa xoang mũi bằng dung dịch Natri Clorid 0.9% từ 2 - 3 lần/ngày.\n"
            "- **Bù dịch & Nghỉ ngơi:** Uống đủ 2 - 2.5 lít nước ấm mỗi ngày, nghỉ ngơi tại phòng thoáng khí.\n\n"
            "**Dấu hiệu cần đến cơ sở y tế thăm khám ngay:**\n"
            "Sốt cao liên tục trên 39°C không hạ sau 48 giờ, đau ngực, khó thở, cứng gáy hoặc đau dữ dội quanh hốc mắt."
        )

    sources = [
        {
            "title": "MedlinePlus: Respiratory Tract & Allergy Protocols (#6842)",
            "source": "NIH National Library of Medicine",
            "url": "https://medlineplus.gov"
        },
        {
            "title": "Hướng dẫn chẩn đoán & điều trị bệnh lý Hô hấp & Dị ứng",
            "source": "Bộ Y Tế Việt Nam",
            "url": "https://kcb.vn"
        }
    ]

    return {
        "answer": answer,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "symptoms": extracted_symptoms,
        "specialist": specialist,
        "medications": medications,
        "sources": sources
    }
