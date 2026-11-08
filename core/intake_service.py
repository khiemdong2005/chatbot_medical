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

import re
import uuid
import datetime
import logging
from typing import Dict, Any, List, Optional
from core.triage import assess_emergency_risk, remove_accents
from core.rag_service import medical_rag_service

logger = logging.getLogger("IntakeService")

# ==============================================================================
# 1. BỘ TỪ KHÓA & QUY TẮC NHẬN DIỆN DỮ KIỆN (CLINICAL FACT EXTRACTOR)
# ==============================================================================

# Danh sách các từ phủ định đơn lẻ hoặc cụm từ
NEGATION_WORDS = {
    "không", "khong", "chưa", "chua", "chẳng", "chang",
    "không hề", "khong he", "không bị", "khong bi", "không có", "khong co",
    "chưa hề", "chua he", "chưa bị", "chua bi", "chưa có", "chua co",
    "hết", "het", "đỡ", "do", "khỏi", "khoi", "không còn", "khong con",
    "hết bị", "het bi", "hết rồi", "het roi", "đã hết", "da het",
    "no", "not", "without", "denies", "deny"
}

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
    """
    Kiểm tra xem câu người dùng là câu hỏi tra cứu thông tin / định nghĩa y khoa thuần túy,
    chứ không phải lời khai báo triệu chứng bản thân.
    Ví dụ: 'Đau đầu là gì?', 'Sốt xuất huyết có lây không?', 'Nguyên nhân gây ho?'
    """
    if not text:
        return False
    lower = text.strip().lower()
    cleaned = remove_accents(lower)

    # Nếu có lời khẳng định ngôi thứ nhất rõ ràng của bệnh nhân -> không phải tra cứu thuần túy
    first_person_patterns = [
        "tôi bị", "toi bi", "em bị", "em bi", "mình bị", "minh bi",
        "con bị", "con bi", "cháu bị", "chau bi", "bác bị", "bac bi",
        "tôi thấy", "toi thay", "em thấy", "em thay", "mình thấy", "minh thay",
        "tôi đau", "toi dau", "em đau", "em dau", "mình đau", "minh dau",
        "tôi sốt", "toi sot", "em sốt", "em sot", "mình sốt", "minh sot",
        "tôi ho", "toi ho", "em ho", "em ho", "mình ho", "minh ho",
        "tôi muốn khám", "toi muon kham", "em muốn khám", "em muon kham",
        "mình muốn khám", "minh muon kham", "cho tôi khám", "cho em khám",
        "cứu tôi", "cuu toi", "khó chịu mấy hôm", "kho chiu may hom",
        "bị đau mấy", "bi dau may", "bị sốt mấy", "bi sot may"
    ]
    if any(p in lower or p in cleaned for p in first_person_patterns):
        return False

    info_patterns = [
        "là gì", "la gi", "là bệnh gì", "la benh gi", "là cái gì", "la cai gi",
        "thế nào là", "the nao la", "như thế nào", "nhu the nao",
        "nguyên nhân", "nguyen nhan", "tại sao lại", "tai sao lai", "vì sao lại", "vi sao lai",
        "có nguy hiểm không", "co nguy hiem khong", "có lây không", "co lay khong", "lây qua đường nào",
        "cách phòng ngừa", "cach phong ngua", "cách phòng tránh", "cach phong tranh",
        "cách điều trị", "cach dieu tri", "chữa như thế nào", "chua nhu the nao",
        "dấu hiệu của", "dau hieu cua", "triệu chứng của", "trieu chung cua",
        "tìm hiểu về", "tim hieu ve", "cho tôi hỏi về", "cho em hỏi về", "cho mình hỏi về",
        "định nghĩa", "dinh nghia", "phân biệt giữa", "phan biet giua",
        "uống thuốc gì khi", "uong thuoc gi khi", "uống gì khi", "uong gi khi",
        "what is", "what are", "how to treat", "how to prevent", "causes of", "symptoms of"
    ]
    return any(p in lower or p in cleaned for p in info_patterns)

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
        "patterns": ["đau họng", "dau hong", "rát họng", "rat hong", "nuốt đau", "nuot dau", "sore throat", "pharyngitis"]
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
        "label": "Phát ban da / Nổi mề đay",
        "patterns": ["phát ban", "phat ban", "mề đay", "me day", "mẩn ngứa", "man ngua", "rash", "hives"]
    },
    "kho_nuot": {
        "label": "Khó nuốt / Nghẹn khi nuốt",
        "patterns": ["khó nuốt", "kho nuot", "nghẹn", "nghen khi nuot", "difficulty swallowing"]
    }
}

# Các mẫu thời gian diễn tiến (Onset & Duration)
DURATION_PATTERNS = [
    r"((?:mấy|may|vài|vai|một|mot|hai|ba|bốn|bon|năm|nam|\d+)\s*(?:ngày|ngay|hôm|hom|tuần|tuan|tháng|thang|giờ|gio|tiếng|tieng))\s*(?:nay|trước|truoc|rồi|roi)?",
    r"(hôm qua|hom qua|sáng nay|sang nay|tối qua|toi qua|vài ngày nay|vai ngay nay|mấy ngày nay|may ngay nay)"
]

# Các mẫu chỉ số tự đo (Vitals)
TEMPERATURE_PATTERN = r"(?:nhiệt độ|nhiet do|sốt|sot)?\s*(\d{2}(?:[\.,]\d)?)\s*(?:°c|c|độ|do)\b"


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
            "medications": []
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
                boundary_pat = r"[,;\.\?!]|(?:(?:nhưng|nhung|tuy nhiên|tuy|song|chỉ còn|chi con|ma|mà))"
                b_matches = list(re.finditer(boundary_pat, preceding_text, re.IGNORECASE))
                if b_matches:
                    last_b = b_matches[-1].end()
                    preceding_text = preceding_text[last_b:]
                    preceding_no_accent = preceding_no_accent[last_b:]

                # Tách các từ trong cửa sổ trước triệu chứng
                words_before = set(re.findall(r"\w+", preceding_text))
                words_before_no_accent = set(re.findall(r"\w+", preceding_no_accent))

                # 1. Kiểm tra tiền tố phủ định (30 ký tự trước triệu chứng)
                if any(w in words_before or w in words_before_no_accent for w in ["không", "khong", "chưa", "chua", "chẳng", "chang", "hết", "het", "đỡ", "do", "khỏi", "khoi", "no", "not"]):
                    is_denied = True
                else:
                    for neg_phrase in NEGATION_WORDS:
                        if neg_phrase in preceding_text or neg_phrase in preceding_no_accent:
                            is_denied = True
                            break

                # 2. Kiểm tra hậu tố phủ định (25 ký tự ngay sau triệu chứng, vd: 'sốt đã hết', 'đau họng đỡ rồi')
                if not is_denied:
                    end_idx = idx + len(pat)
                    succeeding_text = lower_text[end_idx:min(len(lower_text), end_idx + 25)]
                    succeeding_no_accent = no_accent_text[end_idx:min(len(no_accent_text), end_idx + 25)]
                    words_after = set(re.findall(r"\w+", succeeding_text))
                    words_after_no_accent = set(re.findall(r"\w+", succeeding_no_accent))
                    if any(w in words_after or w in words_after_no_accent for w in ["hết", "het", "đỡ", "do", "khỏi", "khoi", "giảm", "giam"]):
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

    # 4. Trích xuất tiền sử / thuốc / dị ứng nếu có từ khóa
    allergies = []
    medications = []
    if "dị ứng" in lower_text or "di ung" in no_accent_text or "allergic" in lower_text:
        allergies.append("Có ghi nhận tiền sử dị ứng cần lưu ý (chi tiết trong hội thoại)")
    if any(k in lower_text for k in ["đang uống", "dang uong", "thuốc đang dùng", "thuoc"]):
        medications.append("Có khai báo đang sử dụng thuốc điều trị")

    return {
        "present_symptoms": present_symptoms,
        "denied_symptoms": denied_symptoms,
        "duration": duration,
        "vitals": vitals,
        "allergies": allergies,
        "medications": medications
    }


# ==============================================================================
# 3. QUẢN LÝ THÔNG TIN CÒN THIẾU & CHỌN CÂU HỎI TIẾP THEO
# ==============================================================================

PAIN_QUESTIONS = {
    "location": "Bạn đau ở vị trí nào rõ nhất?",
    "quality": "Cơn đau có cảm giác như thế nào, chẳng hạn đau âm ỉ hay đau quặn?",
    "radiation": "Đau ở nguyên một chỗ hay lan sang vùng nào khác?",
    "modifiers": "Điều gì làm cơn đau tăng hoặc giảm?",
    "severity": "Trên thang 0 đến 10, bạn thấy đau khoảng mấy điểm?",
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

    if abdominal_pain(facts):
        pain = facts.get("pain", {})
        if not pain.get("location"):
            missing.append(PAIN_QUESTIONS["location"])

    # 1. Nếu chưa có thời gian diễn tiến
    if not duration:
        missing.append("Thời gian bắt đầu xuất hiện triệu chứng (bạn bị từ khi nào, kéo dài mấy ngày?)")

    # 2. Nếu có sốt mà chưa có thân nhiệt cụ thể
    has_fever = any("Sốt" in s for s in present)
    if has_fever and "temperature" not in vitals:
        missing.append("Nhiệt độ cơ thể cao nhất bạn tự đo được (khoảng bao nhiêu độ C?)")

    # 3. Rà soát cờ đỏ cấp cứu tim mạch / hô hấp nếu chưa được phủ nhận
    is_respiratory = any(s in ["Đau rát họng / Nuốt đau", "Ho", "Ho khan", "Ho có đờm", "Ho khan / Ho có đờm", "Sốt / Thân nhiệt tăng"] for s in present)
    has_denied_dyspnea = any("Khó thở" in s for s in denied)
    has_denied_chest_pain = any("Đau tức ngực" in s for s in denied)

    chest_pain = any("ngực" in symptom.lower() for symptom in present)
    if (is_respiratory or chest_pain) and not has_denied_dyspnea and not any("Khó thở" in s for s in present):
        missing.append("Bạn có cảm thấy khó thở, thở dốc hay hụt hơi khi nghỉ ngơi không?")
    if is_respiratory and not chest_pain and not has_denied_chest_pain:
        missing.append("Bạn có bị đau thắt ngực hoặc tức nặng vùng ngực không?")

    # 4. Nếu có đau họng, kiểm tra khả năng nuốt
    has_sore_throat = any("Đau rát họng" in s for s in present)
    has_checked_swallow = any("Khó nuốt" in s for s in present + denied)
    if has_sore_throat and not has_checked_swallow:
        missing.append("Cảm giác đau họng có cản trở việc nuốt thức ăn hoặc uống nước nhiều không?")

    if abdominal_pain(facts):
        missing.extend(question for key, question in PAIN_QUESTIONS.items()
                       if key != "location" and not facts.get("pain", {}).get(key))
    return missing


def select_next_question(missing_list: List[str], turn_count: int = 1) -> Optional[str]:
    """
    Chọn câu hỏi tiếp theo ngắn gọn, ân cần từ danh sách thông tin còn thiếu.
    Giới hạn tối đa 3-4 lượt hỏi để tránh làm phiền hoặc hỏi lặp vô tận.
    """
    if not missing_list or turn_count > 4:
        return None

    # Lấy câu hỏi ưu tiên cao nhất
    top_missing = missing_list[0]

    # Định dạng câu hỏi tự nhiên, thấu cảm
    if top_missing in PAIN_QUESTIONS.values():
        return top_missing
    if "Thời gian" in top_missing:
        return "Bạn bị như vậy từ khi nào—mới hôm nay hay đã vài ngày rồi?"
    elif "Nhiệt độ" in top_missing:
        return "Bạn có cặp nhiệt độ tại nhà không? Nếu có thì nhiệt độ cao nhất ghi nhận được là khoảng bao nhiêu độ C?"
    elif "khó thở" in top_missing:
        return "Ngoài các biểu hiện trên, bạn có cảm thấy bị khó thở, thở gấp hay hụt hơi khi nằm không?"
    elif "đau thắt ngực" in top_missing:
        return "Bạn có cảm thấy đau tức ngực hoặc nặng ngực lan ra vai/cánh tay không?"
    elif "nuốt" in top_missing:
        return "Cổ họng đau có khiến bạn gặp khó khăn khi nuốt nước bọt hay ăn uống không?"
    else:
        return f"Bạn có thể chia sẻ thêm: {top_missing}?"


# ==============================================================================
# 4. TẠO BẢN TÓM TẮT TRƯỚC KHÁM CHUẨN 2 PHẦN (PRE-VISIT SUMMARY)
# ==============================================================================

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
    chief_complaint = facts.get("chief_complaint") or (
        ", ".join(facts.get("present_symptoms", [])) if facts.get("present_symptoms") else "Sàng lọc triệu chứng tổng quát"
    )
    present_syms = facts.get("present_symptoms", [])
    denied_syms = facts.get("denied_symptoms", [])
    duration = facts.get("duration") or "Chưa ghi nhận cụ thể"
    vitals = facts.get("vitals", {})
    vitals_str = ", ".join([f"{k}: {v}" for k, v in vitals.items()]) if vitals else "Chưa có chỉ số tự đo tại nhà"
    allergies = facts.get("allergies", [])
    allergies_str = "; ".join(allergies) if allergies else "Chưa ghi nhận tiền sử dị ứng đặc biệt"
    medications = facts.get("medications", [])
    meds_str = "; ".join(medications) if medications else "Chưa ghi nhận thuốc đang dùng thường xuyên"
    missing_info = identify_missing_information(facts)

    # Ảnh đính kèm & quan sát sơ bộ
    attachments = session_data.get("attachments", [])
    visual_observations = session_data.get("visual_observations", [])
    attachments_str = f"Có đính kèm {len(attachments)} hình ảnh lâm sàng ({', '.join(visual_observations)})" if attachments else "Không có tệp hình ảnh đính kèm"

    part_a = {
        "title": "Phần A — Thông tin đã thu thập từ người bệnh",
        "chief_complaint": chief_complaint,
        "pain": facts.get("pain", {}),
        "symptoms_present": present_syms,
        "symptoms_denied": denied_syms,  # Dữ kiện phủ định cực kỳ quan trọng
        "duration": duration,
        "vitals": vitals_str,
        "allergies": allergies_str,
        "current_medications": meds_str,
        "attachments_and_observations": attachments_str,
        "missing_or_unclear_info": missing_info if missing_info else ["Thông tin cơ bản ban đầu đã đầy đủ"]
    }

    # Đánh giá Phần B: Kết quả hệ thống
    is_emergency = session_data.get("is_emergency", False)
    if is_emergency:
        triage_status = "Cảnh báo cấp cứu khẩn cấp (Cần can thiệp y tế ngay lập tức)"
        triage_badge = "emergency"
        specialist = "Khoa Cấp cứu / Gọi 115"
        care_approach = "Người bệnh có dấu hiệu nguy kịch. Cần ngừng tự điều trị tại nhà và liên hệ cấp cứu 115 hoặc đến ngay bệnh viện gần nhất."
    elif (abdominal_pain(facts) and not pain_ready(facts)) or (not facts.get("duration") and not vitals and session_data.get("status") == "collecting"):
        triage_status = "Chưa đủ thông tin để phân tầng"
        triage_badge = "collecting"
        specialist = "Chưa xác định"
        care_approach = "Bổ sung các thông tin còn thiếu trong phần lời kể của người bệnh."
    elif len(present_syms) >= 2 or duration in ["vài ngày nay", "mấy ngày nay", "3 ngày", "4 ngày", "1 tuần"]:
        triage_status = "Khuyến nghị thăm khám bác sĩ chuyên khoa"
        triage_badge = "recommended_visit"
        # Gợi ý chuyên khoa dựa trên triệu chứng
        if any("họng" in s or "Ho" in s or "mũi" in s for s in present_syms):
            specialist = "Tai Mũi Họng / Y học Gia đình"
        elif any("bụng" in s for s in present_syms):
            specialist = "Nội tiêu hóa"
        elif any("ban" in s for s in present_syms):
            specialist = "Da liễu"
        else:
            specialist = "Nội tổng quát"
        care_approach = "Triệu chứng kéo dài hoặc ảnh hưởng sinh hoạt. Khuyên người bệnh đặt lịch khám chuyên khoa để được nội soi, xét nghiệm và chẩn đoán chính xác."
    else:
        triage_status = "Theo dõi & Chăm sóc ban đầu tại nhà"
        triage_badge = "self_care"
        specialist = "Y học gia đình / Chăm sóc ban đầu"
        care_approach = "Triệu chứng ở mức độ nhẹ ban đầu. Người bệnh có thể nghỉ ngơi, uống đủ nước ấm, giữ ấm cơ thể và theo dõi diễn biến trong 24-48 giờ tới."

    # Truy vấn nguồn y văn RAG tham chiếu
    rag_sources = session_data.get("sources", [])
    if not rag_sources:
        try:
            rag_docs = medical_rag_service.retrieve_context(chief_complaint, top_k=2)
            rag_sources = [
                {
                    "title": d.get("title", "Hướng dẫn Y tế MedlinePlus"),
                    "source": d.get("source", "MedlinePlus (NIH)"),
                    "url": d.get("source_url", "https://medlineplus.gov")
                }
                for d in rag_docs
            ]
        except Exception:
            rag_sources = [
                {"title": "MedlinePlus Medical Encyclopedia", "source": "NIH Hoa Kỳ", "url": "https://medlineplus.gov"}
            ]

    part_b = {
        "title": "Phần B — Đánh giá sơ bộ & Hướng tiếp cận chăm sóc",
        "triage_status": triage_status,
        "triage_badge": triage_badge,
        "recommended_specialist": specialist,
        "care_approach": care_approach,
        "sources": rag_sources,
        "limitations": "Kết quả do trợ lý AI tổng hợp phục vụ tham khảo và tóm tắt trước khám. Đây KHÔNG phải là chẩn đoán y khoa chính thức thay thế bác sĩ điều trị.",
        "version": version,
        "created_at": created_at,
        "confirmation_status": confirmation_label
    }

    return {
        "part_a_patient_facts": part_a,
        "part_b_system_assessment": part_b,
        "is_confirmed": is_confirmed,
        "ready_to_finalize": is_emergency or not abdominal_pain(facts) or pain_ready(facts),
        "version": version
    }


# ==============================================================================
# 5. LỚP ĐIỀU PHỐI PHIÊN HỘI THOẠI LÂM SÀNG (INTAKE SESSION MANAGER)
# ==============================================================================

class IntakeSessionManager:
    """
    Quản lý bộ nhớ các phiên tư vấn trong ứng dụng:
    Bộ đệm In-Memory song song CSDL SQLite bền vững (IntakeSessionRecord).
    """

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def _save_to_db(self, session_data: Dict[str, Any], raise_on_error: bool = False) -> bool:
        """Đồng bộ phiên vào CSDL bền vững khi có Flask App Context."""
        try:
            from flask import has_app_context
            if not has_app_context():
                return True
            from core.models import db, IntakeSessionRecord
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
            db.session.commit()
            return True
        except Exception as e:
            try:
                from core.models import db
                db.session.rollback()
            except Exception:
                pass
            import logging
            logging.getLogger("IntakeService").error(f"Lỗi ghi hồ sơ phiên {session_data.get('conversation_id')} vào CSDL: {e}")
            if raise_on_error:
                raise RuntimeError(f"Lỗi ghi hồ sơ vào CSDL bền vững: {e}") from e
            return False

    def _load_from_db(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Nạp phiên từ CSDL nếu chưa có trong RAM cache."""
        try:
            from flask import has_app_context
            if not has_app_context():
                return None
            from core.models import IntakeSessionRecord
            rec = IntakeSessionRecord.query.filter_by(conversation_id=conversation_id).first()
            if not rec:
                return None
            d = rec.to_dict()
            d["visual_observations"] = []
            d["sources"] = []
            return d
        except Exception as e:
            import logging
            logging.getLogger("IntakeService").error(f"Lỗi nạp phiên {conversation_id} từ CSDL: {e}")
            return None

    def check_access(self, session_data: Dict[str, Any], user_id: Optional[int] = None, guest_token: Optional[str] = None) -> bool:
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
                if user_id is not None:
                    session_data["user_id"] = user_id
                    self._save_to_db(session_data)
                return True
            return False

        # Phiên legacy không có token hoặc tạo trước đó
        if user_id is not None and not owner_id:
            session_data["user_id"] = user_id
            self._save_to_db(session_data)
            return True
        return True

    def get_or_create_session(
        self,
        conversation_id: Optional[str] = None,
        user_id: Optional[int] = None,
        guest_token: Optional[str] = None,
        enforce_access: bool = True
    ) -> Dict[str, Any]:
        """Tạo mới hoặc lấy lại phiên tư vấn hiện có (Kiểm tra RAM trước, rồi DB, kèm đối soát quyền truy cập)."""
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
                        "medications": []
                    },
                    "messages": [],
                    "attachments": [],
                    "visual_observations": [],
                    "sources": [],
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
        guest_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Xử lý 1 lượt tin nhắn trong quy trình hỏi bệnh:
          1. Tiền kiểm cờ đỏ cấp cứu.
          2. Trích xuất và cập nhật dữ kiện (loại bỏ khỏi present khi phủ nhận, tự hủy xác nhận cũ).
          3. Kiểm tra thông tin còn thiếu.
          4. Đánh giá trạng thái thu thập chính xác (không nhảy sớm sang ready_for_review nếu còn thiếu).
        """
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
            session["visual_observations"].append("Đã đính kèm ảnh lâm sàng phục vụ đối chiếu")

        # 1. Tiền kiểm cờ đỏ cấp cứu
        previous = session["messages"][-2] if len(session["messages"]) > 1 else {}
        previous_question = previous.get("content", "") if previous.get("sender") == "assistant" else ""
        emergency_res = assess_emergency_risk(user_text, previous_question=previous_question)
        if emergency_res.get("clarification"):
            question = emergency_res["clarification"]
            session["messages"].append({"sender": "assistant", "content": question})
            session["status"] = "collecting"
            self._save_to_db(session)
            return {"conversation_id": conversation_id, "status": "collecting", "facts": session["facts"],
                    "answer": question, "next_question": question, "summary": generate_pre_visit_summary(session)}
        if emergency_res.get("is_emergency"):
            session["is_emergency"] = True
            session["status"] = "emergency"
            answer = emergency_res.get("message")
            summary = generate_pre_visit_summary(session)
            self._save_to_db(session)
            return {
                "conversation_id": conversation_id,
                "status": "emergency",
                "answer": answer,
                "facts": session["facts"],
                "missing_information": [],
                "next_question": None,
                "summary": summary,
                "sources": emergency_res.get("sources", [])
            }

        # 2. Trích xuất dữ kiện mới
        extracted = extract_clinical_facts_from_text(user_text)
        current_facts = session["facts"]
        facts_changed = False

        # Nếu chưa có lý do khám chính thì chỉ gán khi:
        # - Không phải là lời chào đơn thuần
        # - Không phải là câu hỏi tra cứu thông tin / định nghĩa kiến thức y khoa thuần túy
        # - Có triệu chứng xác nhận hoặc có phát ngôn ý định khám bệnh
        if not current_facts["chief_complaint"] and user_text:
            if not is_greeting_only(user_text) and not is_informational_query(user_text):
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

        if abdominal_pain(current_facts) and not is_informational_query(user_text):
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

        # TỰ ĐỘNG HỦY XÁC NHẬN CŨ NẾU PHIÊN ĐÃ TỪNG ĐƯỢC XÁC NHẬN MÀ NAY CÓ DỮ KIỆN MỚI
        if facts_changed and session.get("is_confirmed"):
            session["is_confirmed"] = False
            session["version"] = session.get("version", 1) + 1

        # 3. Rà soát thông tin còn thiếu
        missing_info = identify_missing_information(current_facts)
        if abdominal_pain(current_facts):
            asked = [m.get("content", "") for m in session["messages"] if m.get("sender") == "assistant"]
            missing_info.sort(key=lambda item: sum((select_next_question([item]) or item) in reply for reply in asked))
        next_q = select_next_question(missing_info, turn_count=session["turn_count"])

        # 4. Xác định trạng thái và phản hồi
        if next_q:
            session["status"] = "collecting"
            answer = next_q
        else:
            if missing_info:
                # Dừng hỏi do quá số lượt nhưng vẫn còn thông tin thiếu trọng yếu
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

        summary = generate_pre_visit_summary(session)

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
            "summary": summary,
            "sources": summary["part_b_system_assessment"].get("sources", [])
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
        session = self.get_or_create_session(conversation_id, user_id=user_id, guest_token=guest_token)
        facts = session["facts"]

        if field in facts:
            facts[field] = value
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
        session = self.get_or_create_session(conversation_id, user_id=user_id, guest_token=guest_token)
        return generate_pre_visit_summary(session)


# Thể hiện Singleton dùng chung toàn bộ Backend
intake_service = IntakeSessionManager()
import os
import re
import cv2
import numpy as np
from typing import Dict, Any, Tuple, Optional

def check_image_quality(image_path: str) -> Dict[str, Any]:
    """
    [0] Intake: Kiểm tra chất lượng ảnh (mờ, tối, lóa sáng).
    - Độ sắc nét (Blur): Variance of Laplacian.
    - Độ sáng trung bình (Brightness): Mean pixel intensity.
    - Tỉ lệ lóa sáng (Glare): Tỉ lệ pixel > 250.
    """
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
    
    # 1. Đo độ sắc nét (Laplacian Variance)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    is_blur = laplacian_var < 45.0  # Ngưỡng mờ

    # 2. Đo độ sáng trung bình (0-255)
    mean_brightness = float(np.mean(gray))
    is_too_dark = mean_brightness < 40.0
    is_dark = mean_brightness < 90.0  # Cần CLAHE

    # 3. Đo tỉ lệ lóa sáng (Glare)
    glare_ratio = float(np.sum(gray > 250)) / float(gray.size)
    is_glare = glare_ratio > 0.15

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

