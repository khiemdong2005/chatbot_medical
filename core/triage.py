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

# English contractions map for robust normalization
ENGLISH_CONTRACTIONS = {
    r"\bdon't\b": "do not",
    r"\bdont\b": "do not",
    r"\bdidn't\b": "did not",
    r"\bdidnt\b": "did not",
    r"\bdoesn't\b": "does not",
    r"\bdoesnt\b": "does not",
    r"\bhaven't\b": "have not",
    r"\bhavent\b": "have not",
    r"\bhasn't\b": "has not",
    r"\bhasnt\b": "has not",
    r"\bhadn't\b": "had not",
    r"\bhadnt\b": "had not",
    r"\bwon't\b": "will not",
    r"\bwont\b": "will not",
    r"\bwouldn't\b": "would not",
    r"\bwouldnt\b": "would not",
    r"\bcan't\b": "cannot",
    r"\bcant\b": "cannot",
    r"\bcouldn't\b": "could not",
    r"\bcouldnt\b": "could not",
    r"\bshouldn't\b": "should not",
    r"\bshouldnt\b": "should not",
    r"\bisn't\b": "is not",
    r"\bisnt\b": "is not",
    r"\baren't\b": "are not",
    r"\barent\b": "are not",
    r"\bwasn't\b": "was not",
    r"\bwasnt\b": "was not",
    r"\bweren't\b": "were not",
    r"\bwerent\b": "were not",
}

# English emergency keywords (generalized clinical red flags)
EMERGENCY_SIGNS_EN = [
    # Cardiovascular & Respiratory
    "severe chest pain", "chest pain", "shortness of breath", "difficulty breathing",
    "cannot breathe", "choking", "severe respiratory distress", "stridor",
    # Neurological (FAST)
    "facial drooping", "slurred speech", "paralysis", "seizure", "unconscious", "passed out",
    # Hemorrhage & Anaphylaxis
    "coughing blood", "vomiting blood", "blood spurting", "spurting blood", "anaphylaxis",
    # Ophthalmic emergencies (acute vision loss / retinal detachment patterns)
    "sudden vision loss", "sudden loss of vision", "loss of sight", "sudden blindness",
    "acute vision loss", "abrupt vision loss", "abrupt loss of vision",
    "curtain over vision", "curtain-like shadow", "gray shadow over vision", "dark shadow over vision",
    "shadow covering vision", "shadow over vision", "suddenly cannot see"
]

ENGLISH_NEGATION_MARKERS = {
    "no", "not", "never", "without", "neither", "no longer",
    "cannot", "denies", "denied", "free of"
}

ENGLISH_NEGATION_FILLERS = {
    # auxiliary / verbs
    "have", "had", "having", "feel", "feeling", "felt", "experience", "experienced", "experiencing",
    "see", "seeing", "noticed", "noticing", "get", "getting", "got", "suffer", "suffered", "suffering",
    "be", "is", "are", "was", "were", "been", "become", "became", "say", "think", "believe",
    "reporting", "reported",
    # pronouns / articles / prepositions
    "i", "you", "he", "she", "we", "they", "my", "any", "a", "an", "the", "kind", "of", "type", "types",
    "sign", "signs", "symptom", "symptoms", "with", "in", "to", "such",
    # modifiers / qualifiers
    "severe", "significant", "real", "actual", "noticeable", "current", "major", "acute",
    "serious", "further", "other", "such", "new", "more", "particular", "true", "obvious"
}


def is_negated_english(before: str, after: str) -> bool:
    """Determine if an English emergency sign mention is negated or resolved."""
    # 1. Post-symptom resolution (e.g. 'chest pain has resolved', 'last year', 'months ago')
    if re.match(r"\s+(?:has resolved|resolved|is gone|went away|last year|years ago|months ago)\b", after):
        return True

    # 2. Scope boundary before symptom: split by punctuation or contrastive conjunctions
    scope = re.split(r"[,;]|\b(?:but|however|although|yet|though|instead of|rather than|while)\b", before)[-1]

    # 3. Check coordinated negative list: e.g. "without slurred speech or [facial drooping]"
    coord_match = re.search(r"\b(?:no|not|never|without|neither|denies|nor|cannot)\b[^,;]{0,60}\b(?:or|nor)\b", scope)
    if coord_match:
        after_coord = scope[coord_match.end():]
        coord_tokens = re.findall(r"\b[\w']+\b", after_coord)
        if all(w in ENGLISH_NEGATION_FILLERS for w in coord_tokens):
            return True

    # 4. Token-based lookback from symptom
    tokens = re.findall(r"\b[\w']+\b", scope)
    if not tokens:
        return False

    # Check from nearest word backwards up to 7 words
    window = tokens[-7:]
    for i in range(len(window) - 1, -1, -1):
        word = window[i]
        if word in ENGLISH_NEGATION_MARKERS:
            intervening = window[i + 1:]
            if all(w in ENGLISH_NEGATION_FILLERS for w in intervening):
                return True
        elif word not in ENGLISH_NEGATION_FILLERS:
            break

    return False


# ------------------------------------------------------------------------------
# 2. BƯỚC TIỀN KIỂM: PHÁT HIỆN CỜ ĐỎ CẤP CỨU & XỬ LÝ PHỦ ĐỊNH
# ------------------------------------------------------------------------------

def assess_emergency_risk(message: str, lang: str = "vi", previous_question: str = "") -> Dict[str, Any]:
    """
    Tiền kiểm an toàn: Quét xem tin nhắn người dân có dấu hiệu nguy kịch hay không.
    Có cơ chế phân tích cụm phủ định để không báo nhầm (ví dụ: 'sốt nhưng không khó thở').
    """
    text = remove_accents(message).replace("đ", "d")
    if lang == "en":
        for pat, repl in ENGLISH_CONTRACTIONS.items():
            text = re.sub(pat, repl, text, flags=re.IGNORECASE)

    if text.strip(" .!") in {"co", "dung", "yes"}:
        for prefix in ("Hiện bạn hoặc người bạn đang hỏi giúp có đang bị ", "Are you or the person you are asking about experiencing "):
            if previous_question.startswith(prefix):
                text = remove_accents(previous_question[len(prefix):]).replace("đ", "d")
                if lang == "en":
                    for pat, repl in ENGLISH_CONTRACTIONS.items():
                        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
                break
    signs = {sign["no_accent"]: sign["vi"] for sign in EMERGENCY_SIGNS}
    if lang == "en":
        signs.update({name: name for name in sorted(EMERGENCY_SIGNS_EN, key=len, reverse=True)})
    matched_flags = []
    uncertain = []
    # Evaluate each mention in its own clause so a past denial cannot cancel a new symptom.
    clauses = re.split(r"[.;!?\n]|\b(?:nhung|tuy nhien|but|however|although|yet|though|nevertheless)\b|(?=\b(?:bay gio|hien tai|luc nay|now)\b)", text)
    for clause in clauses:
        for phrase, label in signs.items():
            for match in re.finditer(r"\b" + re.escape(phrase) + r"\b", clause):
                before = clause[:match.start()]
                after = clause[match.end():]
                history_scope = re.split(r",|\b(?:con toi|toi dang|bo toi dang|me toi dang)\b", before)[-1]
                if re.search(r"\b(?:nam ngoai|nhieu nam truoc|tien su gia dinh|last year|years ago|family history of|history of)\b", history_scope):
                    continue
                
                if lang == "en":
                    if is_negated_english(before, after):
                        continue
                else:
                    # A new subject/affirmation starts a new scope; coordinated negative lists share one.
                    scope = re.split(r"[,;]|\b(?:con toi|gio toi|i now)\b", before)[-1]
                    negative = re.search(r"\b(?:khong|chua|chang)\s+(?:(?:he|bi|co|thay|con|cam thay)\s+)*$", scope)
                    coordinated = re.search(r"\b(?:khong|chua|chang)\b[^,;]{0,45}\b(?:hay|hoac)\s*$", scope)
                    if negative or coordinated or re.match(r"\s+(?:da het|het roi|nam ngoai)\b", after):
                        continue
                    if re.search(r"\b(?:khong nho ro|khong chac co|not sure (?:if|whether))\s+(?:(?:toi|minh|bi|i|have)\s+)*$", scope):
                        uncertain.append(label)
                        continue

                cap_label = label.capitalize()
                if cap_label not in matched_flags:
                    matched_flags.append(cap_label)

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

    if uncertain:
        symptom = uncertain[0]
        question = (f"Are you or the person you are asking about experiencing {symptom} right now?"
                    if lang == "en" else f"Hiện bạn hoặc người bạn đang hỏi giúp có đang bị {symptom} không?")
        return {"is_emergency": False, "symptoms": [], "clarification": question}
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
    """Block antibiotic prescribing while preserving explanations and refusals."""
    if not answer:
        return ""
    drugs = "|".join(re.escape(name) for name in ANTIBIOTIC_BLACKLIST)
    if not re.search(r"\b(?:" + drugs + r")\b", answer, re.IGNORECASE):
        return answer
    warning = ("Do not choose an antibiotic or dose from this reply. Consult a doctor or pharmacist and tell them about your allergies and current medicines."
               if lang == "en" else "Bạn không được tự ý chọn kháng sinh hoặc liều dùng từ câu trả lời này. Hãy hỏi bác sĩ hoặc dược sĩ và cho biết dị ứng, thuốc đang dùng trước khi sử dụng.")
    kept, blocked = [], False
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", answer):
        folded = remove_accents(re.sub(r"\bđừng\b", "không", sentence, flags=re.IGNORECASE)).replace("đ", "d")
        if not re.search(r"\b(?:" + drugs + r")\b", folded):
            # A regimen may be on the following line after an antibiotic name.
            if re.search(r"\b\d+(?:\.\d+)?\s*(?:mg|ml|vien|tablets?|capsules?)\b.*\b(?:moi|ngay|lan|every|daily|times)\b", folded):
                blocked = True
                continue
            kept.append(sentence)
            continue
        unsafe = bool(re.search(r"\b(?:don thuoc cho ban|prescription for you)\b", folded))
        for action in re.finditer(r"\b(?:uong|dung|su dung|ke|take|use|start|prescribe|recommend)\b", folded):
            tail = folded[action.end():action.end() + 100]
            if not re.search(r"\b(?:" + drugs + r")\b", tail):
                continue
            prefix = folded[max(0, action.start() - 65):action.start()]
            prefix = re.split(r"[,;:!?]|\b(?:nhung|but|however)\b", prefix)[-1]
            if not re.search(r"\b(?:khong|chua|tranh|not|never|avoid|don't|shouldn't|mustn't)\b", prefix):
                unsafe = True
        regimen = re.search(r"\b\d+(?:\.\d+)?\s*(?:mg|ml|vien|tablets?|capsules?)\b.*\b(?:moi|ngay|lan|every|daily|times)\b", folded)
        regimen_prefix = re.split(r"[,;:!?]|\b(?:nhung|but|however)\b", folded[:regimen.start()])[-1] if regimen else ""
        if regimen and not re.search(r"\b(?:khong|tranh|not|never|avoid|don't|shouldn't|mustn't)\b", regimen_prefix):
            unsafe = True
        if unsafe:
            blocked = True
            if re.search(r"\b(?:115|cap cuu|emergency)\b", folded):
                kept.append("Seek emergency care now." if lang == "en" else "Hãy gọi 115 hoặc đến khoa cấp cứu ngay.")
        else:
            kept.append(sentence)
    if not blocked:
        return answer
    return "\n\n".join(part for part in [*kept, warning] if part.strip())


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
            "sources": []
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
            "sources": []
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
            "**Súc họng nước muối ấm (0.9%):** Súc 3 lần/ngày giúp sạch họng, giảm đau rát.",
            "**Uống nhiều nước ấm:** Bổ sung 1.5 - 2 lít nước ấm và nghỉ ngơi nơi thoáng khí.",
            "**Hạ sốt an toàn:** Dùng Paracetamol 500mg nếu sốt >38.5°C (cách nhau 4-6 giờ, nếu không dị ứng).",
            "⚠️ **Đi khám ngay:** Nếu sốt cao liên tục >48 giờ, khó thở hoặc khạc đờm đặc vàng/xanh."
        ]
    elif is_cough_throat:
        symptoms_detected = ["Viêm đau họng / Ho"]
        specialist = "Tai Mũi Họng"
        diff_diag = ["Viêm họng do kích ứng hoặc virus"]
        advice_bullets = [
            "**Giữ ấm cổ:** Tránh uống nước đá lạnh và tránh phòng điều hòa quá lạnh (<25°C).",
            "**Súc họng nước muối:** Thực hiện 3 lần/ngày sau khi ăn giúp làm dịu cổ họng.",
            "**Làm dịu cơn ho:** Có thể ngậm mật ong chanh hoặc siro ho thảo dược.",
            "⚠️ **Đi khám:** Nếu ho kéo dài trên 7 ngày hoặc ho kèm sốt cao, khó thở."
        ]
    elif is_skin:
        symptoms_detected = ["Tổn thương da / Mẩn ngứa / Dị ứng da"]
        specialist = "Da liễu (Dermatology)"
        risk_score = 35
        diff_diag = ["Mề đay cấp tính (Urticaria)", "Viêm da tiếp xúc dị ứng"]
        advice_bullets = [
            "**Vệ sinh nhẹ nhàng:** Rửa bằng nước muối sinh lý, lau khô khăn mềm, tuyệt đối không cào gãi.",
            "**Chườm mát:** Đắp khăn mát sạch 10-15 phút để giảm ngứa rát châm chích.",
            "**Tránh kích ứng:** Tạm ngưng xà phòng hay mỹ phẩm lạ; mặc đồ cotton thoáng rộng.",
            "⚠️ **Đi khám ngay:** Nếu nốt ban lan nhanh, có mụn nước mủ hoặc sưng phù môi/mắt."
        ]
    elif is_stomach:
        symptoms_detected = ["Đau bụng / Rối loạn tiêu hóa"]
        risk_score = 40
        specialist = "Tiêu hóa"
        diff_diag = ["Rối loạn tiêu hóa chức năng", "Viêm dạ dày ruột nhẹ"]
        advice_bullets = [
            "**Ăn nhẹ thanh đạm:** Ăn cháo loãng, súp ấm; tránh đồ cay nóng, dầu mỡ và cà phê.",
            "**Bù nước:** Uống từng ngụm nhỏ nước ấm hoặc Oresol nếu có đi ngoài.",
            "⚠️ **Cấp cứu ngay:** Nếu đau quặn dữ dội hố chậu phải hoặc nôn liên tục."
        ]
    else:
        symptoms_detected = ["Mệt mỏi / Cảm cúm nhẹ"]
        specialist = "Nội tổng quát"
        diff_diag = ["Hội chứng cảm cúm thông thường"]
        advice_bullets = [
            "**Nghỉ ngơi:** Giữ phòng ngủ thoáng khí, ngủ đủ giấc để hồi phục thể trạng.",
            "**Bổ sung dinh dưỡng:** Ăn cháo súp ấm, uống nước cam hoặc nước ấm.",
            "⚠️ **Đi khám:** Nếu mệt mỏi kéo dài hoặc xuất hiện sốt cao."
        ]

    bullets_text = "\n".join([f"• {b}" for b in advice_bullets])
    answer_text = (
        f"Mình đã ghi nhận bạn đang gặp triệu chứng: {', '.join(symptoms_detected)}.\n\n"
        "Các việc bạn nên làm ngay:\n"
        f"{bullets_text}\n\n"
        "*(Lưu ý: Hướng dẫn chăm sóc ban đầu, hãy khám bác sĩ nếu triệu chứng không đỡ)*"
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
