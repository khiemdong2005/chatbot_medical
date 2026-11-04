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
    "no", "not", "without", "denies", "deny"
}

# Các triệu chứng cờ đỏ hoặc triệu chứng quan trọng thường được rà soát
CANONICAL_SYMPTOMS = {
    "kho_tho": {
        "label": "Khó thở / Hụt hơi",
        "patterns": ["khó thở", "kho tho", "hụt hơi", "hut hoi", "thở gấp", "shortness of breath", "dyspnea"]
    },
    "tuc_nguc": {
        "label": "Đau tức ngực",
        "patterns": ["tức ngực", "tuc nguc", "đau ngực", "dau nguc", "đau thắt ngực", "chest pain"]
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
            idx = lower_text.find(pat)
            if idx == -1:
                idx = no_accent_text.find(pat_no_accent)

            if idx != -1:
                matched = True
                # Kiểm tra 30 ký tự trước đó xem có từ phủ định không
                start_window = max(0, idx - 30)
                preceding_text = lower_text[start_window:idx]
                preceding_no_accent = no_accent_text[start_window:idx]

                # Tách các từ trong cửa sổ trước triệu chứng
                words_before = set(re.findall(r"\w+", preceding_text))
                words_before_no_accent = set(re.findall(r"\w+", preceding_no_accent))

                # Kiểm tra từ đơn
                if any(w in words_before or w in words_before_no_accent for w in ["không", "khong", "chưa", "chua", "chẳng", "chang", "no", "not"]):
                    is_denied = True
                else:
                    # Kiểm tra cụm từ
                    for neg_phrase in NEGATION_WORDS:
                        if neg_phrase in preceding_text or neg_phrase in preceding_no_accent:
                            is_denied = True
                            break
                break

        if matched:
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

    # 1. Nếu chưa có thời gian diễn tiến
    if not duration:
        missing.append("Thời gian bắt đầu xuất hiện triệu chứng (bạn bị từ khi nào, kéo dài mấy ngày?)")

    # 2. Nếu có sốt mà chưa có thân nhiệt cụ thể
    has_fever = any("Sốt" in s for s in present)
    if has_fever and "temperature" not in vitals:
        missing.append("Nhiệt độ cơ thể cao nhất bạn tự đo được (khoảng bao nhiêu độ C?)")

    # 3. Rà soát cờ đỏ cấp cứu tim mạch / hô hấp nếu chưa được phủ nhận
    is_respiratory = any(s in ["Đau rát họng / Nuốt đau", "Ho khan / Ho có đờm", "Sốt / Thân nhiệt tăng"] for s in present)
    has_denied_dyspnea = any("Khó thở" in s for s in denied)
    has_denied_chest_pain = any("Đau tức ngực" in s for s in denied)

    if is_respiratory and not has_denied_dyspnea:
        missing.append("Bạn có cảm thấy khó thở, thở dốc hay hụt hơi khi nghỉ ngơi không?")
    if is_respiratory and not has_denied_chest_pain:
        missing.append("Bạn có bị đau thắt ngực hoặc tức nặng vùng ngực không?")

    # 4. Nếu có đau họng, kiểm tra khả năng nuốt
    has_sore_throat = any("Đau rát họng" in s for s in present)
    has_checked_swallow = any("Khó nuốt" in s for s in present + denied)
    if has_sore_throat and not has_checked_swallow:
        missing.append("Cảm giác đau họng có cản trở việc nuốt thức ăn hoặc uống nước nhiều không?")

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
    if "Thời gian" in top_missing:
        return "Để mình ghi nhận bệnh sử rõ ràng cho bác sĩ, bạn đã cảm thấy các triệu chứng này xuất hiện từ khi nào (khoảng mấy ngày rồi)?"
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
        "version": version
    }


# ==============================================================================
# 5. LỚP ĐIỀU PHỐI PHIÊN HỘI THOẠI LÂM SÀNG (INTAKE SESSION MANAGER)
# ==============================================================================

class IntakeSessionManager:
    """
    Quản lý bộ nhớ các phiên tư vấn trong ứng dụng (In-Memory với khả năng đồng bộ DB).
    """

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def get_or_create_session(self, conversation_id: Optional[str] = None, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Tạo mới hoặc lấy lại phiên tư vấn hiện có."""
        cid = conversation_id or f"conv_{uuid.uuid4().hex[:10]}"
        if cid not in self._sessions:
            self._sessions[cid] = {
                "conversation_id": cid,
                "user_id": user_id,
                "status": "collecting",  # collecting | ready_for_review | confirmed
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
        return self._sessions[cid]

    def process_message(
        self,
        conversation_id: str,
        message: str,
        image_bytes: Optional[bytes] = None,
        image_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Xử lý 1 lượt tin nhắn trong quy trình hỏi bệnh:
          1. Tiền kiểm cờ đỏ cấp cứu.
          2. Trích xuất và cập nhật dữ kiện (gộp các triệu chứng mới, cập nhật phủ định).
          3. Kiểm tra thông tin còn thiếu.
          4. Tạo câu trả lời tiếp theo hoặc chuẩn bị bản tóm tắt nếu đã đủ dữ kiện.
        """
        session = self.get_or_create_session(conversation_id)
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
        emergency_res = assess_emergency_risk(user_text)
        if emergency_res.get("is_emergency"):
            session["is_emergency"] = True
            session["status"] = "emergency"
            answer = emergency_res.get("message")
            summary = generate_pre_visit_summary(session)
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

        # Hợp nhất dữ kiện vào session (không bị ghi đè mất thông tin cũ)
        current_facts = session["facts"]

        # Nếu chưa có lý do khám chính thì lấy tin nhắn đầu tiên làm chief_complaint
        if not current_facts["chief_complaint"] and user_text:
            current_facts["chief_complaint"] = user_text[:120]

        for s in extracted["present_symptoms"]:
            if s not in current_facts["present_symptoms"]:
                current_facts["present_symptoms"].append(s)
            # Nếu trước đó từng nghĩ là phủ nhận mà giờ khẳng định có thì bỏ khỏi denied
            if s in current_facts["denied_symptoms"]:
                current_facts["denied_symptoms"].remove(s)

        for s in extracted["denied_symptoms"]:
            if s not in current_facts["denied_symptoms"] and s not in current_facts["present_symptoms"]:
                current_facts["denied_symptoms"].append(s)

        if extracted["duration"]:
            current_facts["duration"] = extracted["duration"]

        if extracted["vitals"]:
            current_facts["vitals"].update(extracted["vitals"])

        for a in extracted["allergies"]:
            if a not in current_facts["allergies"]:
                current_facts["allergies"].append(a)

        for m in extracted["medications"]:
            if m not in current_facts["medications"]:
                current_facts["medications"].append(m)

        # 3. Rà soát thông tin còn thiếu
        missing_info = identify_missing_information(current_facts)
        next_q = select_next_question(missing_info, turn_count=session["turn_count"])

        # 4. Xác định trạng thái và phản hồi
        if next_q:
            session["status"] = "collecting"
            answer = f"Mình đã ghi nhận thông tin từ bạn. {next_q}"
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

    def update_fact(self, conversation_id: str, field: str, value: Any) -> Dict[str, Any]:
        """
        Cho phép người bệnh sửa một dữ kiện (vd: sửa duration, sửa thân nhiệt).
        Khi sửa, đánh dấu phiên bản mới (version += 1) và đặt lại trạng thái cần xác nhận.
        """
        session = self.get_or_create_session(conversation_id)
        facts = session["facts"]

        if field in facts:
            facts[field] = value
            session["version"] += 1
            session["is_confirmed"] = False  # Bắt buộc xác nhận lại khi sửa dữ kiện quan trọng
            session["status"] = "ready_for_review"

        summary = generate_pre_visit_summary(session)
        return {
            "conversation_id": conversation_id,
            "status": session["status"],
            "facts": facts,
            "summary": summary,
            "message": "Đã cập nhật dữ kiện thành công. Vui lòng xác nhận lại bản tóm tắt mới."
        }

    def confirm_summary(self, conversation_id: str) -> Dict[str, Any]:
        """Bệnh nhân xác nhận: Lời khai đã phản ánh đúng thực tế tình trạng sức khỏe."""
        session = self.get_or_create_session(conversation_id)
        session["is_confirmed"] = True
        session["status"] = "confirmed"
        summary = generate_pre_visit_summary(session)
        return {
            "conversation_id": conversation_id,
            "status": "confirmed",
            "is_confirmed": True,
            "summary": summary,
            "message": "Đã xác nhận lời khai thành công. Bản tóm tắt sẵn sàng gửi tới Bác sĩ."
        }

    def get_summary(self, conversation_id: str) -> Dict[str, Any]:
        """Lấy bản tóm tắt trước khám của phiên."""
        session = self.get_or_create_session(conversation_id)
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

