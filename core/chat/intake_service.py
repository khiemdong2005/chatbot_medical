"""
=========================================================================
# ==============================================================================
# PRESCRIPTION IMAGE QUALITY CHECK & PII MASKING (OCR PIPELINE)
# ==============================================================================
🩺 MEDIMIND CLINICAL INTAKE & PRE-VISIT SUMMARY SERVICE
================================================================================
Tuân thủ nghiêm ngặt Quy chuẩn Lâm sàng (Mục 8, 9, 10, 13):
  1. Trích xuất dữ kiện có cấu trúc (Clinical Facts): Tách bạch rõ triệu chứng đã khai
     và các triệu chứng người bệnh ĐÃ PHỦ NHẬN (vd: 'không khó thở', 'không tức ngực').
  2. Xác định thông tin còn thiếu (Missing Information) theo nhóm triệu chứng (Hô hấp, Tiêu hóa...).
  3. Chọn câu hỏi tiếp theo từ dữ kiện còn thiếu, không hỏi lan man, không hỏi lặp vô tận.
  4. Quản lý trạng thái phiên tư vấn (Session State): collecting -> ready_for_review -> confirmed.
  5. Xuất bản Tóm tắt trước khám chuẩn 2 Phần (Pre-visit Summary):
       - Phần A: Thông tin đã thu thập từ người bệnh (lời khai trung thực, triệu chứng phủ nhận, tiền sử, ảnh).
       - Phần B: Đánh giá định tính sơ bộ, định tuyến chuyên khoa, y văn RAG tham chiếu và giới hạn kết quả.
  6. Tuyệt đối KHÔNG hiển thị điểm 0-100 như xác suất bệnh tật giả lập.
================================================================================
"""

import os
import re
import uuid
import datetime
import logging
import threading
from contextlib import contextmanager
from typing import Dict, Any, List, Optional
from core.triage import assess_emergency_risk, remove_accents
from core.rag_service import medical_rag_service  # noqa: F401 - exported for backwards-compatible callers/tests

logger = logging.getLogger("IntakeService")

_shared_flask_app = None

def set_flask_app(app: Any) -> None:
    """Đăng ký cá thể Flask application instance dùng chung cho tầng lưu trữ Intake."""
    global _shared_flask_app
    _shared_flask_app = app

def get_flask_app() -> Optional[Any]:
    """Lấy cá thể Flask application instance hiện tại một cách an toàn."""
    global _shared_flask_app
    if _shared_flask_app is not None:
        return _shared_flask_app
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            _shared_flask_app = current_app._get_current_object()
            return _shared_flask_app
    except Exception:
        pass
    try:
        from app import app as flask_app
        _shared_flask_app = flask_app
        return _shared_flask_app
    except Exception:
        return None

@contextmanager
def intake_db_context():
    """Context manager đảm bảo luôn có Flask app_context hợp lệ để truy vấn và ghi DB."""
    from flask import has_app_context
    if has_app_context():
        yield
    else:
        app_inst = get_flask_app()
        if app_inst is not None:
            with app_inst.app_context():
                yield
        else:
            raise RuntimeError("Không tìm thấy Flask application instance để truy cập CSDL Intake.")

# ==============================================================================
# 1. BỘ TỪ KHÓA & QUY TẮC NHẬN DIỆN DỮ KIỆN (CLINICAL FACT EXTRACTOR)
# ==============================================================================

# Danh sách các từ phủ định đơn lẻ hoặc cụm từ
NEGATION_WORDS = {
    "không", "khong", "chưa", "chua", "chẳng", "chang",
    "không hề", "khong he", "không bị", "khong bi", "không có", "khong co",
    "chưa hề", "chua he", "chưa bị", "chua bi", "chưa có", "chua co",
    "hết", "het", "đỡ", "khỏi", "khoi", "không còn", "khong con",
    "hết bị", "het bi", "hết rồi", "het roi", "đã hết", "da het",
    "no", "not", "without", "denies", "deny"
}
NEGATIVE_SYMPTOM_PREFIX = re.compile(r"\b(?:" + "|".join(re.escape(word) for word in sorted(NEGATION_WORDS)) + r")\b")

GREETING_WORDS = {
    "xin", "chao", "chào", "hello", "hi", "hey", "alo", "alô",
    "bac", "bác", "si", "sĩ", "bs", "ban", "bạn", "em", "ad", "bot",
    "a", "ơi", "oi", "nhe", "nhé", "nha", "chuc", "chúc", "buoi", "buổi",
    "sang", "sáng", "chieu", "chiều", "toi", "tối", "tot", "tốt", "lanh", "lành"
}

def is_greeting_only(text: str) -> bool:
    """Kiểm tra xem câu người dùng có chỉ đơn thuần là lời chào hay không (không chứa từ khóa y tế)."""
    if not text:
        return True
    cleaned = remove_accents(text.strip().lower())
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    words = cleaned.split()
    if not words:
        return True
    greetings = {
        "xin", "chao", "hello", "hi", "hey", "alo",
        "bac", "si", "bs", "ban", "em", "ad", "bot",
        "a", "da", "oi", "nhe", "nha", "chuc", "buoi",
        "sang", "chieu", "toi", "tot", "lanh"
    }
    medical_kw = {
        "sot", "dau", "ho", "rat", "nghet", "met", "non", "bung", "ngua",
        "thuoc", "benh", "fever", "pain", "cough", "ache", "rash", "vomit",
        "kho", "tho", "tuc", "nguc", "nghen", "so", "mui", "chong", "mat"
    }
    if any(w in medical_kw for w in words):
        return False
    return len(words) <= 6 and all(w in greetings for w in words)


def is_informational_query(text: str) -> bool:
    """Identify a health information request without treating it as a symptom report."""
    folded = remove_accents(text.lower()).replace("đ", "d") if text else ""
    if not folded or requests_consultation_conclusion(text):
        return False
    if re.search(
        r"\b(?:toi|minh|em|con|chau|bac|ba|me|bo|ong|chi|anh|vo|chong|be|nguoi nha)"
        r"(?:\s+(?:toi|minh|em))?\s+(?:(?:dang|vua|moi|hien|da|van|lai)\s+)*"
        r"(?:bi|thay|cam thay|dau|sot|ho|kho tho)\b"
        r"|\b(?:cuu toi|kho chiu may hom|bi dau may|bi sot may|tu hom qua|tu sang|tu dem|"
        r"bay gio dang|luc nay|hien gio|for the last|since yesterday|right now)\b"
        r"|\b\d+(?:[.,]\d+)?\s*(?:ngay nay|gio nay|gio roi|tieng roi|do c|°c)\b"
        r"|\b(?:i|my (?:child|mother|father|partner))\s+(?:am|have|feel|has|feels|cannot breathe)\b"
        r"|\bmy (?:chest pain|breathing|symptoms?)\b",
        folded,
    ):
        return False

    return bool(re.search(
        r"\b(?:la (?:benh |cai )?gi|the nao la|nhu the nao|nguyen nhan|tai sao lai|vi sao lai|"
        r"co nguy hiem khong|co lay khong|lay qua duong nao|cach phong (?:ngua|tranh)|"
        r"cach dieu tri|dau hieu cua|trieu chung cua|tim hieu ve|cho (?:toi|em|minh) hoi ve|"
        r"dinh nghia|phan biet giua|uong (?:thuoc )?gi khi|"
        r"what (?:is|are)|how to (?:treat|prevent)|causes of|symptoms of)\b"
        r"|\b(?:thuoc|lieu dung|uong|xet nghiem|chi so|ket qua)\b[^.!?\n]{0,100}\b"
        r"(?:luc nao|khi nao|truoc hay sau|truoc an|sau an|bao nhieu|nghia gi|co tac dung gi|co.*duoc khong)\b"
        r"|\b(?:when|how|can|should)\b[^.!?\n]{0,80}\b(?:take|medication|medicine|test results?)\b",
        folded,
    ))


def is_general_health_definition(text: str) -> bool:
    """Restrict the lexical red-flag exception to clearly impersonal definitions."""
    if not is_informational_query(text):
        return False
    folded = remove_accents(text.lower()).replace("đ", "d").strip(" .?!")
    if re.search(r"\b(?:i|my|me|(?:cua|cho) (?:toi|minh|em))\b", folded):
        return False
    return bool(re.fullmatch(
        r"[^,;?!.]{1,100}\s+la (?:benh |cai )?gi|the nao la [^,;?!.]{1,100}"
        r"|what (?:is|are) (?!causing\b)[^,;?!.]{1,100}",
        folded,
    ))


def requests_consultation_conclusion(text: str) -> bool:
    """Recognize a request to finish the current consultation, not a general fact query."""
    folded = remove_accents(text.lower()).replace("đ", "d").strip(" .?!")
    next_step = (r"(?:(?:can|nen|phai)\s+(?:lam\s+(?:gi|sao)|(?:di\s+)?kham(?:\s+ngay)?)"
                 r"|xu ly\s+(?:the nao|sao)|buoc tiep theo la gi)")
    if re.fullmatch(rf"(?:(?:vay|the|gio|bay gio)\s+)?(?:co\s+)?{next_step}(?:\s+khong)?", folded):
        return True
    if re.fullmatch(r"(?:vay\s+)?co\s+sao\s+khong", folded):
        return True
    return bool(re.search(
        r"\b(?:toi|minh|em|con|chau)\s+(?:dang\s+)?bi\s+(?:gi|sao)\b"
        r"|\b(?:vay|the|gio|bay gio)\s+(?:(?:toi|minh|em)\s+)?(?:bi\s+(?:gi|sao)|phai\s+lam\s+sao|nen\s+lam\s+gi)\b"
        rf"|\b(?:toi|minh|em)\s+(?:co\s+)?{next_step}(?:\s+(?:khong|bay gio))?(?=$|[,.?!])"
        rf"|\b(?:toi|minh|em)\s+(?:dang\s+)?(?:bi|dau|sot|ho)\b[^?]*\bco\s+{next_step}\s+khong$"
        r"|\b(?:vay|the|tinh trang nay|truong hop nay|bi vay|toi)\s+co\s+(?:nguy hiem|sao)\s+khong\b"
        r"|\b(?:chot\s+tu\s+van|ket\s+luan\s+(?:cho\s+toi|giup\s+toi))\b"
        r"|\b(?:what (?:do|might) i have|what(?:'s| is) wrong with me|"
        r"what should i do(?: now| about (?:this|it))?|is (?:this|it) serious|is my condition serious|"
        r"(?:do i need to|should i) (?:see (?:a|my) doctor|go to (?:a clinic|the hospital))|what are my next steps)\b",
        folded,
    ))


def last_assistant_question(answer: str) -> str:
    """Use the last question actually shown to the patient, not an intake hint."""
    if not isinstance(answer, str) or "?" not in answer:
        return ""
    before = answer[:answer.rfind("?") + 1]
    return re.split(r"[.!?\n]", before[:-1])[-1].strip(" \t*-•") + "?"


def question_topic(question: str) -> str:
    folded = remove_accents(question.lower()).replace("đ", "d")
    topics = (
        ("medication_use", r"\b(?:thuoc|medicine|medication)\b.*\b(?:dung|uong|take|use)\b|\b(?:dung|uong|take|use)\b.*\b(?:thuoc|medicine|medication)\b"),
        ("dyspnea", r"\b(?:kho tho|hut hoi|shortness of breath|difficulty breathing)\b"),
        ("chest_pain", r"\b(?:dau|tuc|that|nang)\s+nguc\b|\bchest pain\b"),
        ("swallowing_ability", r"\b(?:ban (?:con|van) nuot duoc nuoc bot|can you (?:still )?swallow your saliva)\b"),
        ("swallowing", r"\b(?:kho nuot|can tro.*nuot|nuot nuoc bot|swallow)\b"),
        ("swelling", r"\b(?:sung|phu ne|swelling)\b"),
        ("redness", r"\b(?:do da|do nong|redness)\b"),
        ("rash", r"\b(?:noi man|phat ban|rash|hives)\b"),
        ("movement", r"\b(?:han che van dong|cu dong|di lai|movement|move)\b"),
        ("activity_impact", r"\b(?:anh huong.*sinh hoat|anh huong.*cong viec|sinh hoat|daily activities)\b"),
        ("pain_frequency", r"\b(?:dau|con dau|pain)\b.*\b(?:thuong xuyen|lien tuc|bao nhieu lan|frequent|often)\b"),
        ("pain_severity", r"\b(?:thang.*10|may diem|scale.*10|pain score)\b"),
        ("pain_location", r"\b(?:dau o vi tri|dau cho nao|pain location|where (?:is|do you feel).*pain)\b"),
        ("pain_quality", r"\b(?:cam giac.*dau|con dau.*cam giac|dau am i|dau quan|pain feel)\b"),
        ("pain_radiation", r"\b(?:lan sang|lan ra|nguyen mot cho|radiat)\b"),
        ("pain_modifiers", r"\b(?:lam con dau tang|lam con dau giam|dieu gi lam con dau|better or worse)\b"),
        ("temperature", r"\b(?:nhiet do|cap nhiet do|temperature)\b"),
        ("duration", r"\b(?:tu khi nao|bao lau|may ngay|when.*start|how long)\b"),
    )
    if "đỏ" in question.lower():
        return "redness"
    return next((name for name, pattern in topics if re.search(pattern, folded)), "")


SALIVA_SWALLOWING_LOSS = "Không nuốt được nước bọt"
ITCHING = "Ngứa"
RASH = "Phát ban da / Nổi mề đay"


def bind_short_reply(text: str, previous_answer: str, facts: Dict[str, Any]) -> bool:
    """Persist a terse answer against the question that was actually displayed."""
    question = last_assistant_question(previous_answer)
    if not question or len(text.split()) > 8:
        return False
    folded = remove_accents(text.strip().lower()).replace("đ", "d").strip(" .!?")
    if not folded:
        return False
    bare_reply = bool(re.fullmatch(
        r"(?:co|khong|chua|chang|vang|dung|uh|yes|no)"
        r"(?:\s+(?:co|bi|thuong xuyen|lam|luon|he|a|nhe|roi|dau|ca|that))*",
        folded,
    ))
    frequent_reply = bool(re.fullmatch(r"thuong xuyen(?:\s+(?:lam|luon))?", folded))
    affirmative = (bare_reply and bool(re.match(r"^(?:co|vang|dung|uh|yes)\b", folded))) or frequent_reply
    negative = bare_reply and bool(re.match(r"^(?:khong|chua|chang|no)\b", folded))
    topic = question_topic(question)
    numeric_pain = topic == "pain_severity" and re.fullmatch(r"(?:10|\d)(?:/10)?", folded)
    temperature = None
    if topic == "temperature" and re.search(r"°C|độ C\b|Celsius\b", question, re.IGNORECASE):
        temperature = re.fullmatch(r"(\d{2}(?:[.,]\d)?)(?:\s*(?:°c|c|do(?:\s+c)?))?", folded)
    duration = None
    if topic == "duration":
        duration = re.sub(r"^(?:từ|tu|mới|moi|since|for)\s+", "", text.strip(" .!?"), flags=re.IGNORECASE)
        if not any(re.fullmatch(pattern, duration, re.IGNORECASE) for pattern in DURATION_PATTERNS):
            duration = None
    swallowing_able = swallowing_unable = False
    if topic == "swallowing_ability":
        swallowing_able = affirmative or bool(re.fullmatch(
            r"(?:van )?nuot (?:duoc(?: nuoc bot)?|nuoc bot duoc)|(?:yes[, ]+)?i (?:still )?can(?: swallow(?: my saliva)?)?", folded
        ))
        swallowing_unable = negative or bool(re.fullmatch(
            r"khong (?:the nuot|nuot duoc)(?: nuoc bot)?|(?:no[, ]+)?i (?:can't|cannot)(?: swallow(?: my saliva)?)?", folded
        ))
    unknown = topic and re.fullmatch(r"(?:khong ro|khong nho|khong biet|chua do|not sure|i don't know)", folded)
    if not (affirmative or negative or numeric_pain or temperature or duration
            or swallowing_able or swallowing_unable or unknown):
        return False
    answers = facts.setdefault("contextual_answers", [])
    answers.append({"question": question[:300], "answer": text[:150]})
    del answers[:-20]
    if topic:
        facts.setdefault("answered_topics", {})[topic] = text[:150]

    symptom_labels = {
        "dyspnea": "Khó thở / Hụt hơi",
        "chest_pain": "Đau tức ngực",
        "swallowing": "Khó nuốt / Nghẹn khi nuốt",
        "swelling": "Sưng / Phù nề",
        "redness": "Đỏ da",
        "rash": RASH,
        "movement": "Hạn chế vận động",
    }
    if ((topic in symptom_labels and (affirmative or negative)) or swallowing_able or swallowing_unable):
        label = SALIVA_SWALLOWING_LOSS if topic == "swallowing_ability" else symptom_labels[topic]
        present = swallowing_unable if topic == "swallowing_ability" else affirmative
        destination = "present_symptoms" if present else "denied_symptoms"
        opposite = "denied_symptoms" if present else "present_symptoms"
        if label not in facts[destination]:
            facts[destination].append(label)
        if label in facts[opposite]:
            facts[opposite].remove(label)
    elif topic == "medication_use" and (affirmative or negative):
        facts["medication_use"] = {"status": "yes" if affirmative else "no",
                                   "frequency": "thường xuyên" if "thuong xuyen" in folded else "chưa rõ",
                                   "question": question[:300]}
    elif topic == "activity_impact" and (affirmative or negative):
        facts["activity_impact"] = "có" if affirmative else "không"
    elif topic == "pain_frequency" and (affirmative or negative):
        facts["pain_frequency"] = "thường xuyên" if affirmative else "không thường xuyên"
    elif numeric_pain:
        facts.setdefault("pain", {})["severity"] = f"{folded.split('/')[0]}/10"
    elif temperature:
        reported = temperature.group(1).replace(",", ".")
        facts.setdefault("vitals", {})["temperature"] = f"{reported}°C"
    elif duration:
        facts["duration"] = duration
    return True

# Các triệu chứng cờ đỏ hoặc triệu chứng quan trọng thường được rà soát
CANONICAL_SYMPTOMS = {
    "kho_tho": {
        "label": "Khó thở / Hụt hơi",
        "patterns": ["khó thở", "kho tho", "hụt hơi", "hut hoi", "thở gấp", "shortness of breath", "dyspnea"]
    },
    "tuc_nguc": {
        "label": "Đau tức ngực",
        "patterns": ["đau nhói ngực", "nhói ngực", "đau ở ngực", "đau vùng ngực", "tức ngực", "tuc nguc", "đau ngực", "dau nguc", "đau thắt ngực", "chest pain"]
    },
    "dau_dau": {
        "label": "Đau đầu / Nặng đầu",
        "patterns": ["đau đầu", "dau dau", "nhức đầu", "nhuc dau", "nặng đầu", "nang dau", "đau nửa đầu", "dau nua dau", "headache", "migraine"]
    },
    "sot": {
        "label": "Sốt / Thân nhiệt tăng",
        "patterns": ["sốt", "sot", "nhiệt độ", "nong dau", "fever", "pyrexia", "nóng sốt"]
    },
    "dau_hong": {
        "label": "Đau rát họng / Nuốt đau",
        "patterns": ["đau họng", "dau hong", "đau cổ họng", "dau co hong", "cổ họng đau", "co hong dau",
                     "rát họng", "rat hong", "nuốt đau", "nuot dau", "sore throat", "throat hurts", "pharyngitis"]
    },
    "ho": {
        "label": "Ho khan / Ho có đờm",
        "patterns": ["ho khan", "ho đờm", "ho dom", "ho nhiều", "ho dai dẳng", "ho", "cough"]
    },
    "nghet_mui": {
        "label": "Nghẹt mũi / Chảy nước mũi",
        "patterns": ["nghẹt mũi", "nghet mui", "sổ mũi", "so mui", "chảy nước mũi", "runny nose", "congestion"]
    },
    "non": {
        "label": "Buồn nôn / Nôn ói",
        "patterns": ["buồn nôn", "buon non", "nôn ói", "non oi", "nôn", "non", "nausea", "vomiting"]
    },
    "dau_bung": {
        "label": "Đau bụng / Cồn cào dạ dày",
        "patterns": ["đau bụng", "dau bung", "đau dạ dày", "dau da day", "trào ngược", "trao nguoc", "stomach ache", "acid reflux"]
    },
    "phat_ban": {
        "label": RASH,
        "patterns": ["phát ban", "nổi mẩn", "mề đay", "me day", "mẩn ngứa", "rash", "hives"]
    },
    "ngua": {
        "label": ITCHING,
        "patterns": ["ngứa người", "ngứa khắp người", "ngứa toàn thân", "ngứa khắp cơ thể", "cả người ngứa",
                     "ngứa da", "da ngứa", "da bị ngứa", "ngứa mình", "bị ngứa", "thấy ngứa", "hơi ngứa",
                     "ngứa từ", "itchy", "itching"]
    },
    "kho_nuot": {
        "label": "Khó nuốt / Nghẹn khi nuốt",
        "patterns": ["khó nuốt", "kho nuot", "nghẹn", "nghen khi nuot", "không nuốt được", "khong nuot duoc",
                     "không thể nuốt", "khong the nuot", "difficulty swallowing", "unable to swallow", "cannot swallow", "can't swallow"]
    },
    "sung": {
        "label": "Sưng / Phù nề",
        "patterns": ["sưng", "sung", "phù nề", "phu ne", "swelling"]
    },
    "han_che_van_dong": {
        "label": "Hạn chế vận động",
        "patterns": ["hạn chế vận động", "han che van dong", "khó cử động", "kho cu dong", "limited movement"]
    },
    "dau_khop": {
        "label": "Đau khớp / Đau chi",
        "patterns": ["đau khớp", "dau khop", "đau gối", "dau goi", "đau cổ chân", "dau co chan", "đau ngón chân", "dau ngon chan", "joint pain"]
    }
}

# Các mẫu thời gian diễn tiến (Onset & Duration)
DURATION_PATTERNS = [
    r"((?:mấy|may|vài|vai|một|mot|hai|ba|bốn|bon|năm|nam|\d+)\s*(?:ngày|ngay|hôm|hom|tuần|tuan|tháng|thang|giờ|gio|tiếng|tieng))\s*(?:nay|trước|truoc|rồi|roi)?",
    r"\b(?:hôm qua|hom qua|hôm nay|hom nay|sáng nay|sang nay|tối qua|toi qua|yesterday|today|this morning|last night)\b",
    r"\b(?:one|two|three|four|five|several|\d+)\s+(?:hours?|days?|weeks?|months?)(?:\s+(?:ago|now))?\b",
]

# Các mẫu chỉ số tự đo (Vitals)
TEMPERATURE_PATTERN = r"(?:nhiệt độ|nhiet do|sốt|sot)?\s*(\d{2}(?:[\.,]\d)?)\s*(?:°c|c|độ|do)\b"
SYMPTOM_CLAUSE_BREAK = re.compile(r"[,.](?!\d)|[;!?\n]|\b(?:nhung|tuy nhien|song|chi con|ma|but|however)\b")


# ==============================================================================
# 2. HÀM TRÍCH XUẤT DỮ KIỆN TỪ VĂN BẢN (FACT EXTRACTION)
# ==============================================================================

def extract_clinical_facts_from_text(text: str) -> Dict[str, Any]:
    """
    Trích xuất dữ kiện có cấu trúc từ văn bản người bệnh nhập.
    Tách rõ:
      - present_symptoms: Các triệu chứng người bệnh xác nhận có.
      - denied_symptoms: Các triệu chứng người bệnh ĐÃ PHỦ NHẬN (vd: 'không khó thở').
      - duration: Thời gian bắt đầu / diễn tiến.
      - vitals: Thân nhiệt hoặc huyết áp tự đo.
    """
    raw_text = text.strip()
    lower_text = raw_text.lower()
    no_accent_text = remove_accents(lower_text)

    # Nếu câu hỏi là tra cứu định nghĩa / kiến thức thuần túy, không bóc tách triệu chứng thành lời khai bản thân
    if is_informational_query(raw_text):
        return {
            "present_symptoms": [],
            "denied_symptoms": [],
            "duration": None,
            "vitals": {},
            "allergies": [],
            "medications": [],
            "activity_impact": None
        }

    present_symptoms = []
    denied_symptoms = []

    # 1. Quét từng triệu chứng chuẩn và kiểm tra xem có phủ định hay không
    for sym_key, sym_info in CANONICAL_SYMPTOMS.items():
        label = sym_info["label"]
        patterns = sym_info["patterns"]

        matched = False
        is_denied = False

        for pat in patterns:
            pat_no_accent = remove_accents(pat)
            match = re.search(r"\b" + re.escape(pat_no_accent) + r"\b", no_accent_text)
            idx = match.start() if match else -1

            if idx != -1:
                matched = True
                # Kiểm tra 30 ký tự trước đó xem có từ phủ định không
                start_window = max(0, idx - 30)
                preceding_text = lower_text[start_window:idx]
                preceding_no_accent = no_accent_text[start_window:idx]

                # Tách ranh giới mệnh đề (dấu phẩy, chấm phẩy, liên từ nhưng/mà/chỉ còn) để không phủ định chéo sang triệu chứng khẳng định
                b_matches = list(SYMPTOM_CLAUSE_BREAK.finditer(preceding_no_accent))
                if b_matches:
                    last_b = b_matches[-1].end()
                    preceding_text = preceding_text[last_b:]
                    preceding_no_accent = preceding_no_accent[last_b:]

                # 1. Kiểm tra tiền tố phủ định (30 ký tự trước triệu chứng)
                is_denied = bool(NEGATIVE_SYMPTOM_PREFIX.search(preceding_text)
                                 or NEGATIVE_SYMPTOM_PREFIX.search(preceding_no_accent))

                # 2. Kiểm tra hậu tố phủ định (25 ký tự ngay sau triệu chứng, vd: 'sốt đã hết', 'đau họng đỡ rồi')
                if not is_denied:
                    end_idx = idx + len(pat)
                    succeeding_text = lower_text[end_idx:min(len(lower_text), end_idx + 25)]
                    succeeding_no_accent = no_accent_text[end_idx:min(len(no_accent_text), end_idx + 25)]
                    boundary = SYMPTOM_CLAUSE_BREAK.search(succeeding_no_accent)
                    if boundary:
                        succeeding_text = succeeding_text[:boundary.start()]
                        succeeding_no_accent = succeeding_no_accent[:boundary.start()]
                    words_after = set(re.findall(r"\w+", succeeding_text))
                    words_after_no_accent = set(re.findall(r"\w+", succeeding_no_accent))
                    if any(w in words_after or w in words_after_no_accent for w in ["hết", "het", "đỡ", "khỏi", "khoi", "giảm", "giam"]):
                        is_denied = True
                    else:
                        for neg_phrase in ["đã hết", "da het", "hết rồi", "het roi", "không còn", "khong con", "đã khỏi", "da khoi"]:
                            if neg_phrase in succeeding_text or neg_phrase in succeeding_no_accent:
                                is_denied = True
                                break
                break

        if matched:
            if sym_key == "tuc_nguc" and "nhoi" in no_accent_text:
                label = "Đau nhói ngực"
            elif sym_key == "tuc_nguc" and "tuc" not in no_accent_text and "that" not in no_accent_text:
                label = "Đau vùng ngực"
            if sym_key == "ho":
                label = "Ho"
                if re.search(r"\bho khang?\b", no_accent_text):
                    label = "Ho khan"
                elif re.search(r"\bho (co )?dom\b", no_accent_text):
                    label = "Ho có đờm"
            if is_denied:
                if label not in denied_symptoms:
                    denied_symptoms.append(label)
            else:
                if label not in present_symptoms:
                    present_symptoms.append(label)

    # Nếu có triệu chứng vừa nằm ở denied vừa present (do lặp lại), ưu tiên present nếu có khẳng định
    for s in present_symptoms:
        if s in denied_symptoms:
            denied_symptoms.remove(s)

    # A lone "đỏ" is too ambiguous in unaccented Vietnamese ("do"), so only
    # accept the accented word or an unambiguous English/longer phrase.
    if re.search(r"\bđỏ\b|\bredness\b|\bdo da\b", lower_text):
        if re.search(r"\b(?:không|chưa|chẳng)\s+(?:(?:bị|có)\s+)?đỏ\b", lower_text):
            denied_symptoms.append("Đỏ da")
        else:
            present_symptoms.append("Đỏ da")

    clauses = SYMPTOM_CLAUSE_BREAK.split(no_accent_text.replace("đ", "d"))
    if any(re.fullmatch(
        r"(?:(?:toi|minh|em) )?(?:van|con) nuot duoc nuoc bot(?: binh thuong)?"
        r"|i can (?:still )?swallow (?:my )?saliva",
        clause.strip(),
    ) for clause in clauses):
        denied_symptoms.append(SALIVA_SWALLOWING_LOSS)

    # 2. Trích xuất thời gian diễn tiến
    duration = None
    for pat in DURATION_PATTERNS:
        match = re.search(pat, lower_text)
        if match:
            duration = match.group(0).strip()
            break

    # 3. Trích xuất thân nhiệt tự đo
    vitals = {}
    temp_match = re.search(TEMPERATURE_PATTERN, lower_text)
    if temp_match:
        val = temp_match.group(1).replace(",", ".")
        vitals["temperature"] = f"{val}°C"

    # 4. Retain only positive self-reports, not a keyword appearing in a denial.
    # Keep the patient's wording rather than inventing an allergen/drug name.
    allergies = []
    medications = []
    def positive_report(pattern, exclude_drink=False):
        context_text = no_accent_text.replace("đ", "d")
        for found in re.finditer(pattern, context_text):
            preceding = context_text[max(0, found.start() - 55):found.start()]
            preceding = re.split(r"[,;.!?\n]|\b(?:nhung|tuy nhien|con|hien tai|va)\b", preceding)[-1]
            if re.search(r"\b(?:khong|chua|chang|khong he|chua tung|no|not)\b", preceding):
                continue
            following = context_text[found.end():].lstrip(" :")
            if exclude_drink and re.match(r"(?:nuoc|sua|tra|ca phe|bia|ruou)\b", following):
                continue
            start = max(raw_text.rfind(mark, 0, found.start()) for mark in ",;.!?\n") + 1
            tail = re.search(r"[,;.!?\n]", raw_text[found.end():])
            end = found.end() + tail.start() if tail else len(raw_text)
            return raw_text[start:end].strip()[:500]
        return None
    allergy_report = positive_report(r"\b(?:di ung|allergic)\b")
    medication_report = positive_report(r"\b(?:dang\s+(?:uong|dung|su dung)|thuoc\s+(?:dang|thuong)\s+(?:uong|dung))\b", exclude_drink=True)
    if allergy_report:
        allergies.append("Người dùng khai: " + allergy_report)
    if medication_report:
        medications.append("Người dùng khai: " + medication_report)

    activity_impact = None
    if re.search(r"\b(?:không ảnh hưởng|không cản trở|sinh hoạt bình thường|đi lại bình thường)\b", lower_text):
        activity_impact = "không"
    elif re.search(r"\b(?:ảnh hưởng sinh hoạt|cản trở sinh hoạt|khó đi lại|không đi lại được)\b", lower_text):
        activity_impact = "có"

    return {
        "present_symptoms": present_symptoms,
        "denied_symptoms": denied_symptoms,
        "duration": duration,
        "vitals": vitals,
        "allergies": allergies,
        "medications": medications,
        "activity_impact": activity_impact
    }


# ==============================================================================
# 3. QUẢN LÝ THÔNG TIN CÒN THIẾU & CHỌN CÂU HỎI TIẾP THEO
# ==============================================================================

PAIN_QUESTIONS = {
    "location": "Bạn đau ở vị trí nào rõ nhất?",
    "quality": "Cơn đau có cảm giác như thế nào, chẳng hạn đau âm ỉ hay đau quặn?",
    "severity": "Trên thang 0 đến 10, bạn thấy đau khoảng mấy điểm?",
}
PAIN_QUESTIONS_EN = {
    "location": "Where is the pain strongest?",
    "quality": "What does the pain feel like?",
    "severity": "On a scale of 0 to 10, how strong is the pain?",
}
PAIN_PATTERNS = {
    "location": r"(?:thượng vị|chấn thủy|quanh rốn|hạ sườn (?:trái|phải)|hố chậu (?:trái|phải)|(?:bụng|rốn) (?:trên|dưới|bên trái|bên phải|trái|phải))",
    "quality": r"(?:âm ỉ|quặn(?: thắt)?|đau nhói|đau rát|như dao đâm)",
    "radiation": r"(?:không lan|ở nguyên một chỗ|lan (?:ra |sang |xuống |lên )?(?:sau )?(?:lưng|vai|ngực|tay|chân))",
    "modifiers": r"(?:tăng|giảm|đỡ|nặng hơn) (?:khi |sau |lúc )?(?:ăn|đói|vận động|nghỉ ngơi|nằm|đi lại)",
    "severity": r"\b(?:10|[0-9])\s*/\s*10\b",
}


def abdominal_pain(facts):
    return any("Đau bụng" in label for label in facts.get("present_symptoms", []))


def pain_ready(facts):
    pain = facts.get("pain", {})
    return bool(pain.get("location") and facts.get("duration")
                and (pain.get("quality") or pain.get("severity")))


def respiratory_symptoms(facts):
    return any(symptom in {
        "Đau rát họng / Nuốt đau", "Ho", "Ho khan", "Ho có đờm", "Ho khan / Ho có đờm", "Sốt / Thân nhiệt tăng"
    } for symptom in facts.get("present_symptoms", []))


def identify_missing_information(facts: Dict[str, Any]) -> List[str]:
    """
    Xác định những dữ kiện quan trọng còn thiếu theo phác đồ sàng lọc ban đầu:
      - Thời gian diễn tiến (mấy ngày?).
      - Nhiệt độ sốt tự đo (nếu có triệu chứng sốt).
      - Rà soát cờ đỏ phủ định: khó thở, đau tức ngực.
      - Mức độ ảnh hưởng sinh hoạt (ăn uống, nuốt).
    """
    missing = []
    present = facts.get("present_symptoms", [])
    denied = facts.get("denied_symptoms", [])
    duration = facts.get("duration")
    vitals = facts.get("vitals", {})
    if not present:
        return missing

    if abdominal_pain(facts):
        pain = facts.get("pain", {})
        if not pain.get("location"):
            missing.append(PAIN_QUESTIONS["location"])

    # 1. Nếu chưa có thời gian diễn tiến
    if not duration:
        missing.append("Thời gian bắt đầu ngứa" if present == [ITCHING]
                       else "Thời gian bắt đầu xuất hiện triệu chứng (bạn bị từ khi nào, kéo dài mấy ngày?)")

    # 2. Nếu có sốt mà chưa có thân nhiệt cụ thể
    has_fever = any("Sốt" in s for s in present)
    if has_fever and "temperature" not in vitals:
        missing.append("Nhiệt độ cơ thể cao nhất bạn tự đo được (khoảng bao nhiêu độ C?)")

    # 3. Rà soát cờ đỏ cấp cứu tim mạch / hô hấp nếu chưa được phủ nhận
    is_respiratory = respiratory_symptoms(facts)
    has_denied_dyspnea = any("Khó thở" in s for s in denied)
    has_denied_chest_pain = any("Đau tức ngực" in s for s in denied)

    chest_pain = any("ngực" in symptom.lower() for symptom in present)
    if (is_respiratory or chest_pain) and not has_denied_dyspnea and not any("Khó thở" in s for s in present):
        missing.append("Bạn có cảm thấy khó thở, thở dốc hay hụt hơi khi nghỉ ngơi không?")
    # Pain when swallowing alone does not establish whether saliva can be swallowed.
    has_sore_throat = any("Đau rát họng" in s for s in present)
    has_difficulty_swallowing = any("Khó nuốt" in s for s in present)
    has_checked_swallow = (SALIVA_SWALLOWING_LOSS in present + denied
                           or any("Khó nuốt" in s for s in denied))
    if (has_sore_throat or has_difficulty_swallowing) and not has_checked_swallow:
        missing.append("Khả năng nuốt nước bọt")

    if is_respiratory and not chest_pain and not has_denied_chest_pain:
        missing.append("Bạn có bị đau thắt ngực hoặc tức nặng vùng ngực không?")

    if ITCHING in present and RASH not in present + denied:
        missing.append("Biểu hiện nổi mẩn ở vùng ngứa")

    if abdominal_pain(facts):
        pain = facts.get("pain", {})
        if not (pain.get("quality") or pain.get("severity")):
            missing.extend((PAIN_QUESTIONS["quality"], PAIN_QUESTIONS["severity"]))
    return missing


def select_next_question(missing_list: List[str], turn_count: int = 1, lang: str = "vi") -> Optional[str]:
    """
    Chọn câu hỏi tiếp theo ngắn gọn, ân cần từ danh sách thông tin còn thiếu.
    """
    if not missing_list:
        return None

    # Lấy câu hỏi ưu tiên cao nhất
    top_missing = missing_list[0]
    english = lang == "en"

    # Định dạng câu hỏi tự nhiên, thấu cảm
    for key, question in PAIN_QUESTIONS.items():
        if top_missing == question:
            return PAIN_QUESTIONS_EN[key] if english else question
    if top_missing == "Thời gian bắt đầu ngứa":
        return "When did the itching start?" if english else "Bạn bị ngứa từ khi nào?"
    elif "Thời gian" in top_missing:
        return "When did your symptoms start?" if english else "Bạn bị như vậy từ khi nào?"
    elif "Nhiệt độ" in top_missing:
        return ("What was the highest temperature you measured, in °C?" if english
                else "Nhiệt độ cao nhất bạn đo được là bao nhiêu độ C?")
    elif "khó thở" in top_missing:
        return ("Do you have difficulty breathing while resting?" if english
                else "Bạn có bị khó thở khi nghỉ ngơi không?")
    elif "đau thắt ngực" in top_missing:
        return "Do you have chest pain or pressure now?" if english else "Bạn có bị đau hoặc tức ngực không?"
    elif "nuốt" in top_missing:
        return "Can you still swallow your saliva?" if english else "Bạn còn nuốt được nước bọt không?"
    elif "nổi mẩn" in top_missing:
        return "Have you noticed a rash where it itches?" if english else "Bạn có thấy nổi mẩn ở vùng ngứa không?"
    else:
        return f"Bạn có thể chia sẻ thêm: {top_missing}?"


# ==============================================================================
# 4. TẠO BẢN TÓM TẮT TRƯỚC KHÁM CHUẨN 2 PHẦN (PRE-VISIT SUMMARY)
# ==============================================================================

def _verified_summary_assessment(assessment: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(assessment, dict) or assessment.get("degraded") is not False:
        return None
    grounding = assessment.get("grounding_status")
    if assessment.get("is_emergency") is True and grounding == "emergency":
        return {"is_emergency": True}
    if grounding != "verified" or assessment.get("consultation_mode") != "final":
        return None

    summary = {"is_emergency": False, "sources": []}
    for name in ("risk_level", "specialist", "care_approach"):
        value = assessment.get(name)
        if isinstance(value, str) and value.strip():
            summary[name] = value.strip()
    sources = assessment.get("sources")
    if isinstance(sources, list):
        summary["sources"] = [source for source in sources if isinstance(source, dict)
                              and isinstance(source.get("url"), str) and source["url"].startswith("https://")]
    return summary


def _invalidate_summary_assessment(session_data: Dict[str, Any]) -> None:
    for message in session_data.get("messages", []):
        message.pop("verified_assessment", None)


def has_patient_facts(facts: Dict[str, Any]) -> bool:
    return any(facts.get(field) for field in (
        "chief_complaint", "present_symptoms", "denied_symptoms", "duration", "vitals",
        "allergies", "medications", "activity_impact", "pain", "medication_use",
    ))


def generate_pre_visit_summary(
    session_data: Dict[str, Any],
    lang: str = "vi"
) -> Dict[str, Any]:
    """
    Tạo Bản Tóm Tắt Trước Khám (Pre-visit Clinical Summary) tuân thủ Mục 8:
      - Phần A: Thông tin đã thu thập từ người bệnh (lời khai, triệu chứng, phủ nhận, tiền sử, ảnh).
      - Phần B: Đánh giá sơ bộ hệ thống, định tuyến chuyên khoa, y văn RAG và giới hạn kết quả.
    Tuyệt đối KHÔNG hiển thị điểm số 0-100 như xác suất bệnh tật.
    """
    facts = session_data.get("facts", {})
    created_at = session_data.get("created_at", datetime.datetime.now().strftime("%H:%M %d/%m/%Y"))
    version = session_data.get("version", 1)
    is_confirmed = session_data.get("is_confirmed", False)
    confirmation_label = "Đã được người bệnh xác nhận lời khai" if is_confirmed else "Chờ người bệnh xác nhận"

    # Trích xuất dữ kiện cho Phần A
    chief_complaint = facts.get("chief_complaint") or ", ".join(facts.get("present_symptoms", [])) or "Chưa ghi nhận lý do khám"
    present_syms = facts.get("present_symptoms", [])
    denied_syms = facts.get("denied_symptoms", [])
    duration = facts.get("duration") or "Chưa ghi nhận cụ thể"
    vitals = facts.get("vitals", {})
    vitals_str = ", ".join(f"{k}: {v}" for k, v in vitals.items()) if vitals else "Chưa rõ các chỉ số tự đo"
    allergies = facts.get("allergies", [])
    allergies_str = "; ".join(allergies) if allergies else "Chưa rõ tiền sử dị ứng"
    medications = facts.get("medications", [])
    meds_str = "; ".join(medications) if medications else "Chưa rõ thuốc đang dùng"
    medication_use = facts.get("medication_use", {})
    if not medications and medication_use.get("status") == "yes":
        meds_str = "Người bệnh xác nhận đang dùng thuốc; chưa rõ tên thuốc"
        if medication_use.get("frequency") == "thường xuyên":
            meds_str += " (thường xuyên)"
    elif not medications and medication_use.get("status") == "no":
        meds_str = "Người bệnh phủ nhận đang dùng thuốc trong câu hỏi trước"
    missing_info = identify_missing_information(facts)

    # Ảnh đính kèm & quan sát sơ bộ
    attachments = session_data.get("attachments", [])
    attachments_str = f"Có đính kèm {len(attachments)} hình ảnh lâm sàng" if attachments else "Không có tệp hình ảnh đính kèm"

    part_a = {
        "title": "Phần A — Thông tin đã thu thập từ người bệnh",
        "chief_complaint": chief_complaint,
        "pain": facts.get("pain", {}),
        "pain_frequency": facts.get("pain_frequency") or "Chưa rõ",
        "symptoms_present": present_syms,
        "symptoms_denied": denied_syms,  # Dữ kiện phủ định cực kỳ quan trọng
        "duration": duration,
        "vitals": vitals_str,
        "allergies": allergies_str,
        "current_medications": meds_str,
        "activity_impact": facts.get("activity_impact") or "Chưa rõ",
        "contextual_answers": facts.get("contextual_answers", []),
        "attachments_and_observations": attachments_str,
        "missing_or_unclear_info": missing_info or (["Chưa ghi nhận triệu chứng tự khai"] if not present_syms else [])
    }

    # Đánh giá Phần B: Kết quả hệ thống
    assessment = next((message["verified_assessment"] for message in reversed(session_data.get("messages", []))
                       if message.get("verified_assessment")), {})
    is_emergency = session_data.get("is_emergency", False) or assessment.get("is_emergency", False)
    if is_emergency:
        triage_status = "Cảnh báo nguy cơ cao (Cần đánh giá cấp cứu)"
        triage_badge = "emergency"
        specialist = "Khoa Cấp cứu"
        care_approach = "Cần được nhân viên y tế đánh giá trực tiếp khẩn nếu triệu chứng đang xảy ra, kéo dài hoặc nặng lên."
    elif assessment:
        triage_status = assessment.get("risk_level", "Chưa đủ thông tin để phân tầng")
        triage_badge = "assessed"
        specialist = assessment.get("specialist", "Chưa xác định")
        care_approach = assessment.get("care_approach", "Xem đánh giá sơ bộ trong cuộc hội thoại.")
    else:
        triage_status = "Chưa đủ thông tin để phân tầng"
        triage_badge = "collecting"
        specialist = "Chưa xác định"
        care_approach = "Chưa có đánh giá sơ bộ đủ căn cứ trong cuộc hội thoại."

    part_b = {
        "title": "Phần B — Đánh giá sơ bộ & Hướng tiếp cận chăm sóc",
        "triage_status": triage_status,
        "triage_badge": triage_badge,
        "recommended_specialist": specialist,
        "care_approach": care_approach,
        "sources": [] if is_emergency else assessment.get("sources", []),
        "limitations": "Kết quả do trợ lý AI tổng hợp phục vụ tham khảo và tóm tắt trước khám. Đây KHÔNG phải là chẩn đoán y khoa chính thức thay thế bác sĩ điều trị.",
        "version": version,
        "created_at": created_at,
        "confirmation_status": confirmation_label
    }

    summary_available = is_emergency or has_patient_facts(facts) or bool(attachments)
    return {
        "part_a_patient_facts": part_a,
        "part_b_system_assessment": part_b,
        "is_confirmed": is_confirmed,
        "summary_available": summary_available,
        "ready_to_finalize": is_emergency or (summary_available and (not abdominal_pain(facts) or pain_ready(facts))),
        "version": version
    }


# ==============================================================================
# 5. LỚP ĐIỀU PHỐI PHIÊN HỘI THOẠI LÂM SÀNG (INTAKE SESSION MANAGER)
# ==============================================================================

class IntakeSessionManager:
    """
    Quản lý bộ nhớ các phiên tư vấn trong ứng dụng:
    Bộ đệm In-Memory song song CSDL SQLite bền vững (IntakeSessionRecord).
    Đảm bảo an toàn đa luồng (Thread-safe) thông qua threading.RLock().
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def clear(self):
        """Dọn dẹp an toàn toàn bộ phiên trong RAM."""
        with self._lock:
            self._sessions.clear()

    def _save_to_db(self, session_data: Dict[str, Any], raise_on_error: bool = False) -> bool:
        """Đồng bộ phiên vào CSDL bền vững (hỗ trợ cả Flask và FastAPI)."""
        try:
            with intake_db_context():
                from core.models import db, IntakeSessionRecord
                from core.db_utils import commit_or_rollback
                import json
                cid = session_data["conversation_id"]
                rec = IntakeSessionRecord.query.filter_by(conversation_id=cid).first()
                if not rec:
                    rec = IntakeSessionRecord(conversation_id=cid)
                    db.session.add(rec)
                rec.user_id = session_data.get("user_id")
                rec.guest_token = session_data.get("guest_token")
                rec.status = session_data.get("status", "collecting")
                rec.turn_count = session_data.get("turn_count", 0)
                rec.facts_json = json.dumps(session_data.get("facts", {}), ensure_ascii=False)
                rec.messages_json = json.dumps(session_data.get("messages", []), ensure_ascii=False)
                rec.attachments_json = json.dumps(session_data.get("attachments", []), ensure_ascii=False)
                rec.is_emergency = bool(session_data.get("is_emergency", False))
                rec.is_confirmed = bool(session_data.get("is_confirmed", False))
                rec.version = session_data.get("version", 1)
                rec.created_at = session_data.get("created_at")
                commit_or_rollback()
                return True
        except Exception as e:
            try:
                with intake_db_context():
                    from core.models import db
                    db.session.rollback()
            except Exception:
                pass
            logger.error("Không thể ghi phiên tư vấn (%s).", type(e).__name__)
            if raise_on_error:
                raise RuntimeError("Không thể ghi phiên tư vấn vào cơ sở dữ liệu.") from None
            return False

    def _load_from_db(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Nạp phiên từ CSDL nếu chưa có trong RAM cache."""
        try:
            with intake_db_context():
                from core.models import IntakeSessionRecord
                rec = IntakeSessionRecord.query.populate_existing().filter_by(conversation_id=conversation_id).first()
                if not rec:
                    return None
                return rec.to_dict()
        except Exception as e:
            logger.error("Không thể nạp phiên tư vấn (%s).", type(e).__name__)
            return None

    def check_access(self, session_data: Dict[str, Any], user_id: Optional[int] = None, guest_token: Optional[str] = None, *, claim_guest: bool = True) -> bool:
        """
        Đối soát bảo mật quyền truy cập phiên (Authorization & Tenant Isolation):
        - Nếu phiên thuộc tài khoản đã đăng nhập (owner_id is not None): Chỉ tài khoản đó được phép truy cập.
        - Nếu phiên tạo lúc chưa đăng nhập (owner_id is None):
            + Nếu có guest_token trùng khớp: Cho phép truy cập.
            + Nếu người dùng vừa đăng nhập (user_id có giá trị) và có guest_token trùng khớp: Liên kết tài khoản.
        - Mọi trường hợp truy cập chéo tài khoản hoặc không có quyền: Từ chối (False).
        """
        owner_id = session_data.get("user_id")
        owner_guest = session_data.get("guest_token")

        if owner_id is not None:
            return user_id is not None and user_id == owner_id

        if owner_guest:
            if guest_token and guest_token == owner_guest:
                if user_id is not None and claim_guest:
                    session_data["user_id"] = user_id
                    self._save_to_db(session_data)
                return True
            return False

        # A legacy row without either owner cannot prove ownership. Do not
        # disclose or let an arbitrary signed-in account claim that row.
        return False

    def _existing_session(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            session_data = self._sessions.get(conversation_id)
            if session_data is None:
                session_data = self._load_from_db(conversation_id)
                if session_data is not None:
                    self._sessions[conversation_id] = session_data
            return session_data

    def delete_session(self, conversation_id: str, user_id: Optional[int] = None,
                       guest_token: Optional[str] = None, *, commit: bool = True) -> bool:
        """Delete an existing owned draft from persistent storage and RAM.

        ``commit=False`` lets an API combine this deletion with another row in
        one transaction. An unknown ID never creates a replacement session.
        """
        with self._lock:
            session_data = self._existing_session(conversation_id)
            if session_data is None:
                return False
            if not self.check_access(session_data, user_id, guest_token, claim_guest=False):
                raise PermissionError("Bạn không có quyền xóa phiên tư vấn này.")
            with intake_db_context():
                from core.models import db, IntakeSessionRecord
                from core.db_utils import commit_or_rollback
                row = IntakeSessionRecord.query.populate_existing().filter_by(conversation_id=conversation_id).first()
                if row is not None:
                    if not self.check_access({"user_id": row.user_id, "guest_token": row.guest_token},
                                             user_id, guest_token, claim_guest=False):
                        raise PermissionError("Bạn không có quyền xóa phiên tư vấn này.")
                    db.session.delete(row)
                if commit:
                    commit_or_rollback()
            self._sessions.pop(conversation_id, None)
            return True

    def record_assistant_reply(self, conversation_id: str, answer: str,
                               user_id: Optional[int] = None,
                               guest_token: Optional[str] = None,
                               assessment: Optional[Dict[str, Any]] = None,
                               expected_turn_count: Optional[int] = None) -> Dict[str, Any]:
        """Store the actual displayed reply instead of the intake placeholder."""
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 60000:
            raise ValueError("Nội dung phản hồi không hợp lệ.")
        with self._lock:
            session_data = self._existing_session(conversation_id)
            if session_data is None:
                raise KeyError(conversation_id)
            if not self.check_access(session_data, user_id, guest_token, claim_guest=False):
                raise PermissionError("Bạn không có quyền sửa phiên tư vấn này.")
            with intake_db_context():
                from core.models import IntakeSessionRecord
                row = IntakeSessionRecord.query.populate_existing().filter_by(conversation_id=conversation_id).first()
                if row is None:
                    self._sessions.pop(conversation_id, None)
                    raise KeyError(conversation_id)
                if not self.check_access({"user_id": row.user_id, "guest_token": row.guest_token},
                                         user_id, guest_token, claim_guest=False):
                    raise PermissionError("Bạn không có quyền sửa phiên tư vấn này.")
                if expected_turn_count is not None and (
                    session_data.get("turn_count") != expected_turn_count or row.turn_count != expected_turn_count
                ):
                    raise ValueError("Phiên tư vấn đã có lượt tiếp theo.")
            reply = {"sender": "assistant", "content": answer,
                     "timestamp": datetime.datetime.now().strftime("%H:%M:%S")}
            verified_assessment = _verified_summary_assessment(assessment)
            if verified_assessment:
                reply["verified_assessment"] = verified_assessment
            previous_messages = session_data.setdefault("messages", [])
            messages = previous_messages.copy()
            if messages and messages[-1].get("sender") == "assistant":
                messages[-1] = reply
            else:
                messages.append(reply)
            session_data["messages"] = messages
            try:
                self._save_to_db(session_data, raise_on_error=True)
            except RuntimeError:
                session_data["messages"] = previous_messages
                raise
            return session_data

    def get_or_create_session(
        self,
        conversation_id: Optional[str] = None,
        user_id: Optional[int] = None,
        guest_token: Optional[str] = None,
        enforce_access: bool = True
    ) -> Dict[str, Any]:
        """Tạo mới hoặc lấy lại phiên tư vấn hiện có (Kiểm tra RAM trước, rồi DB, kèm đối soát quyền truy cập)."""
        with self._lock:
            cid = conversation_id or f"conv_{uuid.uuid4().hex[:10]}"
            if cid not in self._sessions:
                loaded = self._load_from_db(cid)
                if loaded:
                    self._sessions[cid] = loaded
                else:
                    self._sessions[cid] = {
                        "conversation_id": cid,
                        "user_id": user_id,
                        "guest_token": guest_token,
                        "status": "collecting",  # collecting | partially_collected | ready_for_review | confirmed
                        "turn_count": 0,
                        "facts": {
                            "chief_complaint": "",
                            "present_symptoms": [],
                            "denied_symptoms": [],
                            "duration": None,
                            "vitals": {},
                            "allergies": [],
                            "medications": [],
                            "activity_impact": None,
                            "contextual_answers": [],
                            "answered_topics": {}
                        },
                        "messages": [],
                        "attachments": [],
                        "is_emergency": False,
                        "is_confirmed": False,
                        "version": 1,
                        "created_at": datetime.datetime.now().strftime("%H:%M %d/%m/%Y")
                    }
                    self._save_to_db(self._sessions[cid])

            session = self._sessions[cid]
            if enforce_access and conversation_id:
                if not self.check_access(session, user_id=user_id, guest_token=guest_token):
                    raise PermissionError("Bạn không có quyền truy cập hoặc thao tác trên phiên tư vấn y tế này.")

            return session

    def process_message(
        self,
        conversation_id: str,
        message: str,
        image_bytes: Optional[bytes] = None,
        image_name: Optional[str] = None,
        user_id: Optional[int] = None,
        guest_token: Optional[str] = None,
        include_summary: bool = True,
        lang: str = "vi",
    ) -> Dict[str, Any]:
        """
        Xử lý 1 lượt tin nhắn trong quy trình hỏi bệnh:
          1. Tiền kiểm cờ đỏ cấp cứu.
          2. Trích xuất và cập nhật dữ kiện (loại bỏ khỏi present khi phủ nhận, tự hủy xác nhận cũ).
          3. Kiểm tra thông tin còn thiếu.
          4. Đánh giá trạng thái thu thập chính xác (không nhảy sớm sang ready_for_review nếu còn thiếu).
        """
        with self._lock:
            session = self.get_or_create_session(conversation_id, user_id=user_id, guest_token=guest_token)
            session["turn_count"] += 1
            user_text = message.strip()

            # Lưu tin nhắn người dùng
            session["messages"].append({
                "sender": "patient",
                "content": user_text,
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
            })

            if image_bytes:
                session["attachments"].append(image_name or "clinical_image.jpg")

            # 1. Tiền kiểm cờ đỏ cấp cứu
            previous = session["messages"][-2] if len(session["messages"]) > 1 else {}
            previous_question = previous.get("content", "") if previous.get("sender") == "assistant" else ""
            emergency_res = {} if is_general_health_definition(user_text) else assess_emergency_risk(
                user_text, lang=lang, previous_question=previous_question
            )
            if emergency_res.get("clarification"):
                question = emergency_res["clarification"]
                session["messages"].append({"sender": "assistant", "content": question})
                session["status"] = "collecting"
                _invalidate_summary_assessment(session)
                self._save_to_db(session)
                return {"conversation_id": conversation_id, "status": "collecting", "facts": session["facts"],
                        "answer": question, "next_question": question, "needs_red_flag_confirmation": True,
                        "summary_available": has_patient_facts(session["facts"]) or bool(session["attachments"]),
                        "turn_count": session["turn_count"],
                        "summary": generate_pre_visit_summary(session) if include_summary else None}
            if emergency_res.get("is_emergency"):
                bind_short_reply(user_text, previous_question, session["facts"])
                session["is_emergency"] = True
                session["status"] = "emergency"
                answer = emergency_res.get("message")
                symptoms = emergency_res.get("symptoms", [])
                facts = session["facts"]
                for symptom in symptoms:
                    if symptom not in facts["present_symptoms"]:
                        facts["present_symptoms"].append(symptom)
                    if symptom in facts["denied_symptoms"]:
                        facts["denied_symptoms"].remove(symptom)
                if not facts["chief_complaint"]:
                    facts["chief_complaint"] = ", ".join(symptoms)
                _invalidate_summary_assessment(session)
                if session.get("is_confirmed"):
                    session["is_confirmed"] = False
                    session["version"] = session.get("version", 1) + 1
                summary = generate_pre_visit_summary(session) if include_summary else None
                self._save_to_db(session)
                return {
                    "conversation_id": conversation_id,
                    "status": "emergency",
                    "answer": answer,
                    "facts": session["facts"],
                    "missing_information": [],
                    "next_question": None,
                    "emergency_symptoms": symptoms,
                    "summary_available": True,
                    "turn_count": session["turn_count"],
                    "summary": summary,
                    "sources": emergency_res.get("sources", [])
                }

            # 2. Trích xuất dữ kiện mới
            informational = not image_bytes and is_informational_query(user_text)
            extracted = extract_clinical_facts_from_text(user_text)
            current_facts = session["facts"]
            facts_changed = bool(image_bytes)

            # Nếu chưa có lý do khám chính thì chỉ gán khi:
            # - Không phải là lời chào đơn thuần
            # - Không phải là câu hỏi tra cứu thông tin / định nghĩa kiến thức y khoa thuần túy
            # - Có triệu chứng xác nhận hoặc có phát ngôn ý định khám bệnh
            if not current_facts["chief_complaint"] and user_text:
                if not is_greeting_only(user_text) and not informational:
                    if extracted["present_symptoms"]:
                        current_facts["chief_complaint"] = ", ".join(extracted["present_symptoms"])
                        facts_changed = True
            # Hợp nhất triệu chứng khẳng định
            for s in extracted["present_symptoms"]:
                if s not in current_facts["present_symptoms"]:
                    current_facts["present_symptoms"].append(s)
                    facts_changed = True
                # Nếu trước đó từng nằm trong denied_symptoms mà giờ khẳng định có thì bỏ khỏi denied
                if s in current_facts["denied_symptoms"]:
                    current_facts["denied_symptoms"].remove(s)
                    facts_changed = True

            # Hợp nhất triệu chứng phủ nhận (QUAN TRỌNG: Nếu trước đó nằm trong present_symptoms thì PHẢI xóa khỏi present_symptoms!)
            for s in extracted["denied_symptoms"]:
                if s not in current_facts["denied_symptoms"]:
                    current_facts["denied_symptoms"].append(s)
                    facts_changed = True
                if s in current_facts["present_symptoms"]:
                    current_facts["present_symptoms"].remove(s)
                    facts_changed = True

            if extracted["duration"] and current_facts.get("duration") != extracted["duration"]:
                current_facts["duration"] = extracted["duration"]
                facts_changed = True

            if extracted.get("activity_impact") is not None and current_facts.get("activity_impact") != extracted["activity_impact"]:
                current_facts["activity_impact"] = extracted["activity_impact"]
                facts_changed = True

            if abdominal_pain(current_facts) and not informational:
                slots = current_facts.setdefault("pain", {})
                for field, pattern in PAIN_PATTERNS.items():
                    match = re.search(pattern, user_text, re.IGNORECASE)
                    if match and slots.get(field) != match.group():
                        slots[field] = match.group()
                        facts_changed = True

            if extracted["vitals"]:
                for vk, vv in extracted["vitals"].items():
                    if current_facts["vitals"].get(vk) != vv:
                        current_facts["vitals"][vk] = vv
                        facts_changed = True

            for a in extracted["allergies"]:
                if a not in current_facts["allergies"]:
                    current_facts["allergies"].append(a)
                    facts_changed = True

            for m in extracted["medications"]:
                if m not in current_facts["medications"]:
                    current_facts["medications"].append(m)
                    facts_changed = True

            # The patient's short reply belongs to the last question actually
            # displayed, which may differ from the internal intake suggestion.
            if bind_short_reply(user_text, previous_question, current_facts):
                facts_changed = True

            if facts_changed:
                _invalidate_summary_assessment(session)

            # TỰ ĐỘNG HỦY XÁC NHẬN CŨ NẾU PHIÊN ĐÃ TỪNG ĐƯỢC XÁC NHẬN MÀ NAY CÓ DỮ KIỆN MỚI
            if facts_changed and session.get("is_confirmed"):
                session["is_confirmed"] = False
                session["version"] = session.get("version", 1) + 1

            # 3. Rà soát thông tin còn thiếu
            missing_info = identify_missing_information(current_facts)
            readiness = not missing_info and (respiratory_symptoms(current_facts) or pain_ready(current_facts))
            asked_topics = set(current_facts.get("answered_topics", {}))
            asked_topics.update(question_topic(last_assistant_question(m.get("content", "")))
                                for m in session["messages"] if m.get("sender") == "assistant")
            asked_topics.discard("")
            unanswered = [item for item in missing_info
                          if question_topic(select_next_question([item], lang=lang) or item) not in asked_topics]
            final_mode = requests_consultation_conclusion(user_text) or (facts_changed and readiness)
            consultation_mode = "informational" if informational else "final" if final_mode else "collecting"
            next_q = select_next_question(unanswered, lang=lang) if consultation_mode == "collecting" and facts_changed else None

            # 4. Xác định trạng thái và phản hồi
            if informational or is_greeting_only(user_text):
                answer = "Bạn có thể tiếp tục đặt câu hỏi về sức khỏe."
            elif next_q:
                session["status"] = "collecting"
                answer = next_q
            else:
                if missing_info:
                    session["status"] = "partially_collected"
                    answer = (
                        "Cảm ơn bạn. Mình đã ghi nhận các thông tin cơ bản hiện có. "
                        "Tuy nhiên một số chi tiết (như thời gian hoặc chỉ số đo) chưa được thu thập đầy đủ. "
                        "Bạn vui lòng kiểm tra bảng **Thông tin đã ghi nhận**, có thể bổ sung trực tiếp hoặc xác nhận nhé!"
                    )
                else:
                    session["status"] = "ready_for_review"
                    answer = (
                        "Cảm ơn bạn đã cung cấp chi tiết các triệu chứng. Mình đã hoàn tất việc tổng hợp bệnh sử sơ bộ. "
                        "Bạn vui lòng kiểm tra bảng **Thông tin đã ghi nhận** và xác nhận nếu các dữ kiện đã hoàn toàn chính xác nhé!"
                    )

            summary = generate_pre_visit_summary(session) if include_summary else None

            # Lưu tin nhắn trợ lý
            session["messages"].append({
                "sender": "assistant",
                "content": answer,
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
            })

            # Lưu bền vững vào CSDL
            self._save_to_db(session)

            return {
                "conversation_id": conversation_id,
                "status": session["status"],
                "answer": answer,
                "facts": current_facts,
                "missing_information": missing_info,
                "next_question": next_q,
                "consultation_mode": consultation_mode,
                "summary_available": has_patient_facts(current_facts) or bool(session["attachments"]),
                "turn_count": session["turn_count"],
                "summary": summary,
                "sources": summary["part_b_system_assessment"].get("sources", []) if summary else []
            }

    def update_fact(
        self,
        conversation_id: str,
        field: str,
        value: Any,
        user_id: Optional[int] = None,
        guest_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cho phép người bệnh sửa một dữ kiện (vd: sửa duration, sửa thân nhiệt).
        Khi sửa, đánh dấu phiên bản mới (version += 1) và đặt lại trạng thái cần xác nhận.
        """
        with self._lock:
            session = self.get_or_create_session(conversation_id, user_id=user_id, guest_token=guest_token)
            facts = session["facts"]

            if field in facts:
                facts[field] = value
                _invalidate_summary_assessment(session)
                session["version"] = session.get("version", 1) + 1
                session["is_confirmed"] = False  # Bắt buộc xác nhận lại khi sửa dữ kiện quan trọng
                session["status"] = "ready_for_review"
                self._save_to_db(session)

            summary = generate_pre_visit_summary(session)
            return {
                "conversation_id": conversation_id,
                "status": session["status"],
                "facts": facts,
                "summary": summary,
                "message": "Đã cập nhật dữ kiện thành công. Vui lòng xác nhận lại bản tóm tắt mới."
            }

    def confirm_summary(
        self,
        conversation_id: str,
        user_id: Optional[int] = None,
        guest_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Bệnh nhân xác nhận: Lời khai đã phản ánh đúng thực tế tình trạng sức khỏe."""
        with self._lock:
            session = self.get_or_create_session(conversation_id, user_id=user_id, guest_token=guest_token)
            prev_confirmed = session.get("is_confirmed", False)
            prev_status = session.get("status", "ready_for_review")

            session["is_confirmed"] = True
            session["status"] = "confirmed"

            # Bắt buộc lưu thành công vào CSDL bền vững thì mới trả về thành công
            saved = self._save_to_db(session)
            if not saved:
                # Rollback in-memory status nếu ghi CSDL thất bại
                session["is_confirmed"] = prev_confirmed
                session["status"] = prev_status
                return {
                    "success": False,
                    "error": "Không thể ghi nhận trạng thái xác nhận vào cơ sở dữ liệu bền vững. Vui lòng thử lại sau.",
                    "conversation_id": conversation_id,
                    "status": prev_status,
                    "is_confirmed": prev_confirmed
                }

            summary = generate_pre_visit_summary(session)
            return {
                "success": True,
                "conversation_id": conversation_id,
                "status": "confirmed",
                "is_confirmed": True,
                "summary": summary,
                "message": "Đã xác nhận lời khai thành công. Bản tóm tắt sẵn sàng gửi tới Bác sĩ."
            }

    def get_summary(
        self,
        conversation_id: str,
        user_id: Optional[int] = None,
        guest_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Lấy bản tóm tắt trước khám của phiên."""
        with self._lock:
            session = self._existing_session(conversation_id)
            if session is None:
                raise KeyError(conversation_id)
            if not self.check_access(session, user_id, guest_token, claim_guest=False):
                raise PermissionError("Bạn không có quyền truy cập hoặc thao tác trên phiên tư vấn y tế này.")
            return generate_pre_visit_summary(session)


# Thể hiện Singleton dùng chung toàn bộ Backend
intake_service = IntakeSessionManager()

try:
    import cv2
except ImportError:
    cv2 = None
import numpy as np
from typing import Dict, Any, Tuple, Optional

def check_image_quality(image_path: str) -> Dict[str, Any]:
    """
    [0] Intake: Kiểm tra chất lượng ảnh (mờ, tối, lóa sáng).
    - Độ sắc nét (Blur): Variance of Laplacian.
    - Độ sáng trung bình (Brightness): Mean pixel intensity.
    - Tỉ lệ lóa sáng (Glare): Tỉ lệ pixel > 250.
    """
    if cv2 is None:
        return {"passed": True, "reason": "OpenCV optional dependency not loaded."}
    if not os.path.exists(image_path):
        return {"passed": False, "reason": "Tệp ảnh không tồn tại."}

    # Đọc ảnh an toàn với đường dẫn tiếng Việt / Unicode
    try:
        with open(image_path, "rb") as f:
            chunk = f.read()
        img_arr = np.frombuffer(chunk, dtype=np.uint8)
        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
    except Exception:
        img = cv2.imread(image_path)

    if img is None:
        return {"passed": False, "reason": "Không thể giải mã dữ liệu ảnh."}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. Đo độ sắc nét (Laplacian Variance + cường độ biên ký tự p99.9 tránh phạt tờ A4 nền trắng nhiều khoảng trống)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    laplacian_var = float(lap.var())
    edge_p999 = float(np.percentile(np.abs(lap), 99.9))
    is_blur = (laplacian_var < 18.0 and edge_p999 < 110.0) or (laplacian_var < 45.0 and edge_p999 < 90.0)

    # 2. Đo độ sáng trung bình & dải tương phản thực tế đến nét mực (p98 - p0.05)
    mean_brightness = float(np.mean(gray))
    p_ink, p98 = np.percentile(gray, [0.05, 98])
    dynamic_range = float(p98 - p_ink)
    is_too_dark = mean_brightness < 35.0 and float(p98) < 110.0
    is_dark = mean_brightness < 90.0  # Cần CLAHE

    # 3. Đo tỉ lệ lóa sáng (Glare): phân biệt nền giấy trắng A4 có nét mực đen rõ với ảnh cháy sáng/trắng xóa
    glare_ratio = float(np.mean(gray > 250))
    dark_pixel_count = int(np.sum(gray < 160))
    has_readable_ink = dark_pixel_count >= 120 and dynamic_range >= 55.0 and edge_p999 >= 110.0
    is_glare = glare_ratio > 0.35 and not has_readable_ink

    passed = True
    issues = []
    recommendation = "Ảnh đạt chuẩn phân tích."

    if is_blur:
        passed = False
        issues.append("Ảnh bị rung lắc hoặc mờ nét chữ.")
        recommendation = "Vui lòng giữ chắc tay, lấy nét lại và chụp lại ảnh rõ hơn."
    elif is_too_dark:
        passed = False
        issues.append("Ảnh quá tối, thiếu sáng nghiêm trọng.")
        recommendation = "Vui lòng bật đèn hoặc chụp ở nơi có ánh sáng tốt hơn."
    elif is_glare:
        passed = False
        issues.append("Ảnh bị lóa đèn flash hoặc phản quang trắng.")
        recommendation = "Vui lòng tắt đèn flash hoặc nghiêng góc chụp để tránh chói sáng."

    return {
        "passed": passed,
        "sharpness_score": round(float(laplacian_var), 1),
        "brightness": round(mean_brightness, 1),
        "glare_ratio": round(glare_ratio, 3),
        "need_clahe": is_dark,
        "issues": issues,
        "recommendation": recommendation
    }

def mask_pii_on_image(image_path: str, bboxes_to_mask: list) -> str:
    """
    (Tùy chọn) Che thông tin định danh (PII: tên, ngày sinh, địa chỉ)
    trước khi gửi ảnh ra API bên ngoài.
    """
    try:
        with open(image_path, "rb") as f:
            chunk = f.read()
        img_arr = np.frombuffer(chunk, dtype=np.uint8)
        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        if img is None:
            return image_path
            
        for box in bboxes_to_mask:
            if len(box) == 4 and isinstance(box[0], (int, float)):
                # box dạng [x1, y1, x2, y2]
                x1, y1, x2, y2 = map(int, box)
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 0), -1)
            elif len(box) >= 4 and isinstance(box[0], (list, tuple)):
                # polygon box [[x1, y1], [x2, y2], ...]
                pts = np.array(box, dtype=np.int32)
                cv2.fillPoly(img, [pts], (0, 0, 0))

        out_path = os.path.splitext(image_path)[0] + "_masked.jpg"
        is_success, buffer = cv2.imencode(".jpg", img)
        if is_success:
            with open(out_path, "wb") as f:
                f.write(buffer)
            return out_path
    except Exception as e:
        print(f"[PII MASK ERROR] {e}")
    return image_path

