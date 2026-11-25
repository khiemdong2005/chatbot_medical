import time
import uuid
import logging
import re
from typing import Dict, Any, List, Optional
from core.chat.triage import analyze_symptoms, assess_emergency_risk, apply_safety_guardrails, remove_accents
from core.chat.rag_service import medical_rag_service
from core.ai.gemini_service import (GeminiMedicalService, sanitize_history, sanitize_health_context,
                                sanitize_intake_facts, numbered_references, reference_sources,
                                normalize_follow_up_question)
from core.observability import metrics_collector

logger = logging.getLogger("ChatService")

MAX_MESSAGE_LENGTH = 2000
MAX_HISTORY_ITEMS = 20
ALLOWED_LANGUAGES = {"vi", "en"}
OUT_OF_SCOPE_PATTERNS = (
    r"\b(?:giải|làm)\s+(?:(?:giúp\s+)?(?:mình|tôi)\s+)?(?:bài\s+toán|phương trình|bài tập toán)\b",
    r"\b(?:bài\s+toán|phương trình toán|thời tiết|dự báo thời tiết)\b",
    r"\b(?:lập trình|viết code|debug code|chính trị|tôn giáo)\b",
    r"\b(?:solve|math problem|weather forecast|write code|debug code|politics)\b",
)


def enforce_question_limit(answer: str, max_questions: int,
                           history: Optional[List[Dict[str, Any]]] = None,
                           facts: Optional[dict] = None) -> str:
    """Remove surplus questions and questions already answered in this intake."""
    from core.chat.intake_service import last_assistant_question, question_topic

    seen = 0
    facts = facts or {}
    answered = set(facts.get("answered_topics", {}))
    if facts.get("duration"):
        answered.add("duration")
    if facts.get("vitals", {}).get("temperature"):
        answered.add("temperature")
    answered.update(f"pain_{field}" for field, value in facts.get("pain", {}).items() if value)
    prior_questions = {last_assistant_question(turn.get("content", "")).casefold()
                       for turn in (history or []) if turn.get("role") == "assistant"}
    prior_questions.update(item.get("question", "").casefold()
                           for item in facts.get("contextual_answers", []) if isinstance(item, dict)
                           and isinstance(item.get("question"), str))

    def keep_allowed(match):
        nonlocal seen
        question = match.group().strip()
        topic = question_topic(question)
        if (topic and topic in answered) or question.casefold() in prior_questions:
            return ""
        seen += 1
        return match.group() if seen <= max_questions else ""

    limited = re.sub(r"[^.!?\n]*\?", keep_allowed, answer)
    return re.sub(r"\n{3,}", "\n\n", limited).strip()


def conversation_search_context(message, history, max_user_turns=3):
    """Earlier patient statements, used when the latest message is only a short screening reply.

    A bare "có" / "hông" carries no searchable symptom. Recent user turns from the
    same consultation supply the topic; long messages already stand on their own.
    """
    if not history or len(str(message).split()) > 7:
        return ""
    prior = [turn.get("content", "").strip() for turn in history
             if isinstance(turn, dict) and turn.get("role") == "user"
             and isinstance(turn.get("content"), str)]
    prior = [text[:300] for text in prior if len(text.split()) >= 2]
    if prior and prior[-1].strip().casefold() == str(message).strip().casefold():
        prior = prior[:-1]
    return " ".join(prior[-max_user_turns:])


def retrieval_query(message, facts, history=None):
    """Keep the current question, while removing explicitly denied symptoms.

    Negation is used only to improve document relevance; this is not a diagnosis.
    The model still receives the complete original statement and denied facts.
    For short replies the recent patient turns of the same consultation are
    added, so retrieval searches the whole reported problem instead of "có".
    """
    context = conversation_search_context(message, history)
    query = f"{context}. {message}" if context else message
    for symptom in facts.get("denied_symptoms", []):
        for phrase in symptom.split("/"):
            phrase = phrase.strip()
            if phrase:
                query = re.sub(r"\b(?:không|chưa)(?:\s+(?:có|bị|thấy))?\s+" + re.escape(phrase) + r"\b",
                               " ", query, flags=re.IGNORECASE)
    present = ", ".join(facts.get("present_symptoms", []))
    return ((present + ". " if present else "") + query).strip()[:2400]


_FACILITY_QUERY_PATTERN = re.compile(
    r"\b(?:benh vien|phong kham|co so y te|trung tam y te|"
    r"kham tong quat|kham suc khoe tong quat|kham suc khoe dinh ky|"
    r"di kham o dau|kham o dau|cho nao kham|nen kham o dau|"
    r"hospital|clinic|medical center|health checkup|check-up)\b",
    re.IGNORECASE,
)

_FACILITY_SPECIALTY_RULES = (
    (r"\b(?:da lieu|mun|viem da|nam da|dermatol)\b", "Da liễu"),
    (r"\b(?:tim mach|huyet ap|cardiol)\b", "Tim mạch"),
    (r"\b(?:nhi khoa|nhi dong|tre em|pediatr)\b", "Nhi"),
    (r"\b(?:tai mui hong|viem hong|viem xoang|\bent\b)\b", "Tai Mũi Họng"),
    (r"\b(?:san phu khoa|phu san|thai san|mang thai|obgyn)\b", "Sản"),
    (r"\b(?:tieu hoa|da day|gan mat|gastro)\b", "Tiêu hóa"),
    (r"\b(?:co xuong khop|xuong khop|chan thuong|orthop)\b", "Xương khớp"),
    (r"\b(?:nhan khoa|kham mat|eye|ophthal)\b", "Mắt"),
    (r"\b(?:rang ham mat|nha khoa|dental)\b", "Răng"),
    (r"\b(?:than kinh|neuro)\b", "Thần kinh"),
    (r"\b(?:ho hap|phoi|pulmon)\b", "Hô hấp"),
    (r"\b(?:ung buou|ung thu|oncol)\b", "Ung bướu"),
    (r"\b(?:noi tong hop|tong quat|suc khoe dinh ky|checkup|check-up)\b", "Nội"),
)

_FACILITY_DISTRICT_RULES = (
    (r"\b(?:quan|q\.?)\s*10\b", "Quận 10"),
    (r"\b(?:quan|q\.?)\s*11\b", "Quận 11"),
    (r"\b(?:quan|q\.?)\s*12\b", "Quận 12"),
    (r"\b(?:quan|q\.?)\s*1\b", "Quận 1"),
    (r"\b(?:quan|q\.?)\s*3\b", "Quận 3"),
    (r"\b(?:quan|q\.?)\s*4\b", "Quận 4"),
    (r"\b(?:quan|q\.?)\s*5\b", "Quận 5"),
    (r"\b(?:quan|q\.?)\s*6\b", "Quận 6"),
    (r"\b(?:quan|q\.?)\s*7\b", "Quận 7"),
    (r"\b(?:quan|q\.?)\s*8\b", "Quận 8"),
    (r"\bbinh thanh\b", "Bình Thạnh"),
    (r"\btan binh\b", "Tân Bình"),
    (r"\btan phu\b", "Tân Phú"),
    (r"\bphu nhuan\b", "Phú Nhuận"),
    (r"\bgo vap\b", "Gò Vấp"),
    (r"\bthu duc\b", "Thủ Đức"),
    (r"\bbinh tan\b", "Bình Tân"),
    (r"\bba dinh\b", "Ba Đình"),
    (r"\bdong da\b", "Đống Đa"),
    (r"\bcau giay\b", "Cầu Giấy"),
    (r"\bhoan kiem\b", "Hoàn Kiếm"),
    (r"\bhai ba trung\b", "Hai Bà Trưng"),
    (r"\bthanh xuan\b", "Thanh Xuân"),
)


def _is_facility_query(text: str) -> bool:
    """Detect whether the user is asking for hospital, clinic, or checkup facility recommendations."""
    if not text:
        return False
    from core.chat.triage import remove_accents
    folded = remove_accents(text.lower()).replace("đ", "d")
    return bool(_FACILITY_QUERY_PATTERN.search(folded))


def _retrieve_facility_references(user_message: str, lang: str = "vi") -> List[Dict[str, Any]]:
    """Retrieve matching verified healthcare facilities from MediMind's local CSKCB directory."""
    if not _is_facility_query(user_message):
        return []
    try:
        from core.chat.triage import remove_accents
        from core.facilities.facilities_service import get_facilities
    except Exception:
        return []

    folded = remove_accents(user_message.lower()).replace("đ", "d")
    region = "hcm"
    if re.search(r"\b(?:ha noi|hanoi|\bhn\b|ba dinh|hoan kiem|dong da|cau giay|hai ba trung|thanh xuan)\b", folded):
        region = "hanoi"

    district = ""
    for pat, label in _FACILITY_DISTRICT_RULES:
        if re.search(pat, folded):
            district = label
            break

    specialty = ""
    for pat, label in _FACILITY_SPECIALTY_RULES:
        if re.search(pat, folded):
            specialty = label
            break

    loai_hinh = ""
    if re.search(r"\b(?:benh vien|hospital)\b", folded) and not re.search(r"\b(?:phong kham|clinic)\b", folded):
        loai_hinh = "Bệnh viện"
    elif re.search(r"\b(?:phong kham|clinic)\b", folded) and not re.search(r"\b(?:benh vien|hospital)\b", folded):
        loai_hinh = "Phòng khám"

    attempts = [
        {"tinh_tp": region, "loai_hinh": loai_hinh, "chuyen_khoa": specialty, "quan_huyen": district},
        {"tinh_tp": region, "loai_hinh": loai_hinh, "chuyen_khoa": "", "quan_huyen": district},
        {"tinh_tp": region, "loai_hinh": loai_hinh, "chuyen_khoa": specialty, "quan_huyen": ""},
        {"tinh_tp": region, "loai_hinh": loai_hinh, "chuyen_khoa": "", "quan_huyen": ""},
        {"tinh_tp": region, "loai_hinh": "", "chuyen_khoa": specialty, "quan_huyen": district},
        {"tinh_tp": region, "loai_hinh": "", "chuyen_khoa": "", "quan_huyen": ""},
    ]
    items: List[Dict[str, Any]] = []
    for params in attempts:
        res = get_facilities(page=1, limit=6, **params)
        items = res.get("data") or []
        if items:
            break
    if not items:
        return []

    region_label = "TP. Hà Nội" if region == "hanoi" else "TP. Hồ Chí Minh"
    lines = [
        f"Danh sách cơ sở y tế thực tế trong hệ thống MediMind tại {region_label}:"
        if lang == "vi" else
        f"Verified healthcare facilities in the MediMind Directory ({region_label}):"
    ]
    for idx, fac in enumerate(items[:5], start=1):
        name = str(fac.get("ten") or "").strip()
        if not name:
            continue
        ftype = str(fac.get("loai_hinh") or "Cơ sở y tế").strip()
        addr = str(fac.get("dia_chi_hien_thi_tren_web") or fac.get("dia_chi") or "").strip()
        spec = str(fac.get("chuyen_khoa") or "Đa khoa").strip()
        hours = str(fac.get("gio_mo_cua") or "").strip()
        phone = str(fac.get("so_dien_thoai") or "").strip()
        parts = [f"{idx}. {name} ({ftype})"]
        if addr:
            parts.append(f"Địa chỉ: {addr}")
        if spec:
            parts.append(f"Chuyên khoa: {spec}")
        if hours:
            parts.append(f"Giờ mở cửa: {hours}")
        if phone:
            parts.append(f"Điện thoại: {phone}")
        lines.append(" — ".join(parts) + ".")

    return [{
        "title": (
            f"Danh mục cơ sở y tế MediMind ({region_label})"
            if lang == "vi" else
            f"MediMind Healthcare Facilities Directory ({region_label})"
        ),
        "source": "MediMind Facilities Directory",
        "source_url": "https://medimind.vn/facilities",
        "content": "\n".join(lines),
    }]


def process_clinical_chat(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    image_bytes: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg",
    lang: str = "vi",
    gemini_service: Optional[GeminiMedicalService] = None,
    request_id: Optional[str] = None,
    clinical_hint: Optional[str] = None,
    intake_facts: Optional[dict] = None,
    health_context: Optional[dict] = None,
    consultation_mode: str = "collecting"
) -> Dict[str, Any]:
    """
    Dịch vụ điều phối tư vấn lâm sàng 4 tầng dùng chung (Shared Application Service):
      Tầng 1: Tiền kiểm Cờ đỏ cấp cứu (Pre-check Emergency Guardrail) có bẫy phủ định.
      Tầng 2: Truy vấn tri thức y khoa RAG từ ChromaDB.
      Tầng 3: Bộ não suy luận AI Gemini Flash + Fallback nội bộ có đánh dấu degraded.
      Tầng 4: Hậu kiểm an toàn (Post-check Guardrail) chặn và can thiệp kê đơn kháng sinh.
    
    Đảm bảo 100% hợp đồng dữ liệu đầu ra nhất quán giữa Flask và FastAPI.
    """
    req_id = request_id or str(uuid.uuid4())
    total_start = time.perf_counter()
    metrics_collector.increment("requests_total")
    lang = lang if lang in ALLOWED_LANGUAGES else "vi"
    history = sanitize_history(history)
    has_session_facts = intake_facts is not None
    intake_facts = sanitize_intake_facts(intake_facts)
    health_context = sanitize_health_context(health_context)

    if not isinstance(message, str):
        raise ValueError("Tin nhắn phải là văn bản.")
    user_message = message.strip()
    if len(user_message) > MAX_MESSAGE_LENGTH:
        user_message = user_message[:MAX_MESSAGE_LENGTH]

    has_image = bool(image_bytes and len(image_bytes) > 0)
    if not user_message and not has_image:
        raise ValueError("Vui lòng nhập nội dung tin nhắn hoặc đính kèm ảnh triệu chứng.")

    from core.chat.intake_service import (
        PAIN_PATTERNS, abdominal_pain, extract_clinical_facts_from_text,
        identify_missing_information, is_general_health_definition, is_informational_query,
        question_topic, requests_consultation_conclusion, select_next_question,
    )
    facility_query = not has_image and _is_facility_query(user_message)
    if consultation_mode == "informational" or (
        consultation_mode != "final" and (is_informational_query(user_message) or facility_query)
    ):
        consultation_mode = "informational"
    elif consultation_mode == "final" or requests_consultation_conclusion(user_message):
        consultation_mode = "final"
    if consultation_mode != "collecting":
        clinical_hint = None
    if not has_session_facts and consultation_mode != "informational":
        facts = extract_clinical_facts_from_text(user_message)
        if abdominal_pain(facts):
            facts["pain"] = {key: match.group() for key, pattern in PAIN_PATTERNS.items()
                             if (match := re.search(pattern, user_message, re.IGNORECASE))}
        intake_facts = sanitize_intake_facts(facts)
        if not clinical_hint and consultation_mode == "collecting":
            clinical_hint = select_next_question(identify_missing_information(facts), lang=lang)

    follow_up = (enforce_question_limit(clinical_hint, 1, history=history, facts=intake_facts)
                 if isinstance(clinical_hint, str) else "")

    if gemini_service is None:
        gemini_service = GeminiMedicalService()

    # -------------------------------------------------------------
    # TẦNG 1: TIỀN KIỂM AN TOÀN (Pre-check Guardrail)
    # -------------------------------------------------------------
    triage_start = time.perf_counter()
    previous = history[-1].get("content", "") if history and history[-1].get("role") == "assistant" else ""
    general_definition = not has_image and is_general_health_definition(user_message)
    emergency = {} if general_definition else assess_emergency_risk(
        user_message, lang=lang, previous_question=previous
    )
    triage_ms = (time.perf_counter() - triage_start) * 1000.0
    metrics_collector.record_latency("triage_latency_ms", triage_ms)

    if emergency.get("clarification"):
        metrics_collector.increment("requests_success")
        return {"answer": emergency["clarification"], "needs_red_flag_confirmation": True, "risk_level": "Chưa đủ thông tin" if lang == "vi" else "Unclear",
                "risk_score": None, "symptoms": [], "specialist": "", "is_emergency": False,
                "visual_findings": [], "differential_diagnosis": [], "degraded": False, "sources": []}
    if emergency.get("is_emergency"):
        total_ms = (time.perf_counter() - total_start) * 1000.0
        metrics_collector.increment("emergency_short_circuit_total")
        metrics_collector.increment("requests_success")
        metrics_collector.record_latency("total_request_latency_ms", total_ms)
        metrics_collector.log_event("chat_service", req_id, total_ms, "EMERGENCY_SHORT_CIRCUIT")
        logger.warning("[REQ-%s] Emergency rule matched.", req_id)
        return {
            "answer": emergency["message"],
            "risk_level": "Nguy cơ cao (Cần thăm khám khẩn)" if lang == "vi" else "High Risk (Immediate Care Needed)",
            "risk_score": None,
            "symptoms": emergency["symptoms"],
            "specialist": "Cấp cứu 115 / Khoa Cấp cứu" if lang == "vi" else "Emergency 115 / ER Department",
            "is_emergency": True,
            "visual_findings": [],
            "differential_diagnosis": ["Dấu hiệu cấp cứu tim mạch / hô hấp"],
            "degraded": False,
            "sources": []
        }

    msg_clean = user_message.lower().strip()

    # -------------------------------------------------------------
    # FAST-PATH CHÀO HỎI & KHỞI TẠO (Phản hồi tức thì < 0.01 giây)
    # -------------------------------------------------------------
    greeting_patterns = [
        r"^hello\b", r"^hi\b", r"^hey\b", r"^alo\b",
        r"^xin ch[àa]o\b", r"^ch[àa]o\b", r"^ch[àa]o b[ạa]n\b", r"^b[áa]c s[ĩi]\s*ơi\b"
    ]
    is_greeting = any(re.search(pat, msg_clean) for pat in greeting_patterns) or msg_clean in ["hello", "hi", "chào", "xin chào"]
    has_medical_keywords = any(w in msg_clean for w in [
        "sốt", "sot", "đau", "dau", "ho", "rát", "rat", "nghẹt", "nghet", "mệt", "met",
        "nôn", "non", "bụng", "bung", "ngứa", "ngua", "thuốc", "thuoc", "bệnh", "benh",
        "fever", "pain", "cough", "ache", "rash", "vomit"
    ])
    if is_greeting and not has_medical_keywords and not has_image:
        logger.info(f"[REQ-{req_id}] Kích hoạt Fast-path chào hỏi ban đầu (<0.01s)")
        triage_result = analyze_symptoms(user_message, history, lang=lang, has_image=False)
        metrics_collector.increment("requests_success")
        return {
            "answer": triage_result["answer"],
            "risk_level": triage_result["risk_level"],
            "risk_score": None,
            "symptoms": triage_result.get("symptoms", []),
            "specialist": triage_result.get("specialist", ""),
            "visual_findings": [],
            "differential_diagnosis": [],
            "is_emergency": False,
            "degraded": False,
            "sources": triage_result.get("sources", [])
        }

    # -------------------------------------------------------------
    # TẦNG 2: TRUY VẤN TRI THỨC Y KHOA RAG TỪ CHROMADB + DANH MỤC CƠ SỞ Y TẾ
    # -------------------------------------------------------------
    rag_docs = []
    # A pending intake question depends on what the patient has reported, not on a reference article.
    if not follow_up:
        facility_docs = _retrieve_facility_references(user_message, lang=lang) if facility_query else []
        try:
            retrieval_start = time.perf_counter()
            retrieval_facts = {} if consultation_mode == "informational" else intake_facts
            medline_docs = medical_rag_service.retrieve_context(
                retrieval_query(user_message, retrieval_facts,
                                history=None if consultation_mode == "informational" else history),
                top_k=2,
                lang=lang
            )
            rag_docs = (facility_docs + (medline_docs or []))[:4]
            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000.0
            metrics_collector.record_latency("retrieval_latency_ms", retrieval_ms)
            if rag_docs:
                metrics_collector.increment("retrieval_success_total")
            else:
                metrics_collector.increment("retrieval_miss_total")
            metrics_collector.log_event("retrieval", req_id, retrieval_ms, "SUCCESS" if rag_docs else "EMPTY")
        except Exception as e:
            rag_docs = facility_docs
            metrics_collector.increment("retrieval_miss_total")
            logger.warning("[REQ-%s] Retrieval unavailable (%s).", req_id, type(e).__name__)

    # -------------------------------------------------------------
    # TẦNG 3: BỘ NÃO SUY LUẬN AI (Gemini) + FALLBACK DỰ PHÒNG NỘI BỘ
    # -------------------------------------------------------------
    degraded = False
    gemini_result = None

    try:
        gemini_result = gemini_service.generate_clinical_response(
            user_message,
            history,
            rag_docs=rag_docs,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
            lang=lang,
            request_id=req_id,
            clinical_hint=follow_up or None,
            intake_facts=intake_facts,
            health_context=health_context,
            consultation_mode=consultation_mode
        )
    except Exception as err:
        logger.warning("[REQ-%s] Gemini service unavailable (%s).", req_id, type(err).__name__)
        gemini_result = None

    if gemini_result and isinstance(gemini_result, dict) and gemini_result.get("answer"):
        triage_result = gemini_result
        degraded = triage_result.get("degraded") is True
    else:
        # Kích hoạt Fallback Engine và đánh dấu trạng thái degraded
        degraded = True
        logger.info(f"[REQ-{req_id}] Chuyển sang Fallback Engine (degraded=True)")

        # Kiểm tra an toàn khẩn cấp: Đánh giá lại dấu hiệu cấp cứu deterministically trước khi tạo fallback
        fallback_emergency = {} if general_definition else assess_emergency_risk(user_message, lang=lang)
        if fallback_emergency.get("is_emergency"):
            emg_symptoms = fallback_emergency.get("symptoms", [])
            symptom_str = ", ".join(emg_symptoms) if emg_symptoms else ("Dấu hiệu cấp cứu" if lang == "vi" else "Emergency symptoms")
            if lang == "vi":
                emg_answer = (
                    f"⚠️ **CẢNH BÁO NGUY CƠ CAO:** Hệ thống đang tạm thời gián đoạn dịch vụ AI, nhưng có dấu hiệu cần được đánh giá khẩn cấp: **{symptom_str}**.\n\n"
                    "Không chờ AI trả lời lại. Bạn cần đến Khoa Cấp cứu gần nhất để được nhân viên y tế kiểm tra, đặc biệt nếu triệu chứng vẫn còn hoặc nặng lên."
                )
                risk_lvl = "Nguy cơ cao (Cần thăm khám khẩn)"
                spec = "Khoa Cấp cứu"
            else:
                emg_answer = (
                    f"⚠️ **HIGH-RISK WARNING:** The AI service is temporarily unavailable, but these signs need urgent assessment: **{symptom_str}**.\n\n"
                    "Do not wait for the AI service to recover. Seek urgent in-person assessment at the nearest emergency department, especially if symptoms persist or worsen."
                )
                risk_lvl = "High Risk (Immediate Care Needed)"
                spec = "Emergency Department"
            triage_result = {
                "answer": emg_answer,
                "symptoms": emg_symptoms,
                "risk_level": risk_lvl,
                "risk_score": None,
                "specialist": spec,
                "visual_findings": [],
                "differential_diagnosis": ["Dấu hiệu cấp cứu tim mạch / hô hấp / thần kinh / nhãn khoa"],
                "is_emergency": True,
                "degraded": True,
                "sources": []
            }
        else:
            answer = ("Mình tạm chưa kết nối được dịch vụ AI."
                      if lang == "vi" else "The AI service is temporarily unavailable.")
            answer += " " + (follow_up or ("Bạn có thể thử gửi lại sau ít phút." if lang == "vi" else "Please try again in a few minutes."))
            triage_result = {"answer": answer, "symptoms": intake_facts.get("present_symptoms", []),
                             "risk_level": "Chưa đủ thông tin" if lang == "vi" else "Insufficient information",
                             "risk_score": None, "specialist": "Chưa xác định" if lang == "vi" else "Undetermined",
                             "visual_findings": [], "differential_diagnosis": [], "is_emergency": False,
                             "sources": []}

    # -------------------------------------------------------------
    # TẦNG 4: HẬU KIỂM AN TOÀN (Post-check Guardrail)
    # -------------------------------------------------------------
    raw_answer = triage_result.get("answer", "")
    facts = intake_facts or {}
    grounding_status = triage_result.get("grounding_status")
    if not triage_result.get("is_emergency"):
        proposed_question = normalize_follow_up_question(triage_result.get("follow_up_question"), lang)
        model_question = (enforce_question_limit(proposed_question, 1, history=history, facts=facts)
                          if consultation_mode == "collecting" else "")
        safety_question = follow_up and question_topic(follow_up) in {"dyspnea", "chest_pain", "swallowing_ability"}
        next_question = follow_up if safety_question else model_question or follow_up

        if not degraded and grounding_status == "verified" and model_question and not follow_up:
            raw_answer = f"{raw_answer}\n\n{model_question}"
        elif next_question and not degraded and grounding_status not in ("unrecognized_input", "general_reference", "general_chat"):
            raw_answer = next_question
            grounding_status = "clarification"
            triage_result.update(
                risk_level="Chưa đủ thông tin" if lang == "vi" else "Insufficient information",
                risk_score=None, specialist="", differential_diagnosis=[],
            )
        raw_answer = enforce_question_limit(raw_answer, 1 if consultation_mode == "collecting" else 0,
                                            history=history, facts=facts)
        if not raw_answer:
            raw_answer = ("Mình chưa đủ dữ kiện để trả lời chắc chắn."
                          if lang == "vi" else "I don't have enough information for a reliable answer.")
    if any(turn.get("role") == "assistant" for turn in history):
        body = re.sub(r"^\s*(?:xin chào(?: bạn)?|chào bạn|hello(?: there)?|hi there)[!,.:;–—\s]+",
                      "", raw_answer, count=1, flags=re.IGNORECASE)
        if body and body != raw_answer:
            raw_answer = body[:1].upper() + body[1:]
    from core.chat.intake_service import pain_ready
    if (lang == "vi" and not has_image and abdominal_pain(facts) and not pain_ready(facts)
            and not triage_result.get("is_emergency")):
        triage_result.update(risk_level="Chưa đủ thông tin", risk_score=None,
                             specialist="Chưa xác định", differential_diagnosis=[])
    guardrail_start = time.perf_counter()
    cleaned_answer = apply_safety_guardrails(raw_answer, lang=lang)
    guardrail_ms = (time.perf_counter() - guardrail_start) * 1000.0
    metrics_collector.record_latency("guardrail_latency_ms", guardrail_ms)
    if cleaned_answer != raw_answer:
        metrics_collector.increment("unsafe_guardrail_block_total")
        if grounding_status == "verified":
            grounding_status = "insufficient"
            cleaned_answer = re.sub(r" +\[[0-9]+\]", "", cleaned_answer)

    # Chuẩn hóa cấu trúc đầu ra theo hợp đồng y tế
    default_risk = "Chưa xác định (Cần thêm thông tin)" if lang == "vi" else "Undetermined (Needs more information)"
    default_spec = ""

    # Clamp risk_score 0..100 nếu có; không tự gán mặc định để tránh tạo cảm giác an toàn giả
    raw_score = triage_result.get("risk_score")
    if raw_score is not None:
        try:
            risk_score = max(0, min(100, int(raw_score)))
        except (ValueError, TypeError):
            risk_score = None
    else:
        risk_score = None

    # Đảm bảo visual_findings không bị bịa nếu không có ảnh
    visual_findings = triage_result.get("visual_findings", [])
    if not has_image:
        visual_findings = []

    diff_diag = triage_result.get("differential_diagnosis", [])
    if not isinstance(diff_diag, list):
        diff_diag = []

    sources = []
    source_ids = triage_result.get("verified_source_ids")
    if grounding_status == "verified" and cleaned_answer == raw_answer and isinstance(source_ids, list):
        references = numbered_references(rag_docs)
        sources = reference_sources([references[source_id] for source_id in source_ids
                                     if isinstance(source_id, str) and source_id in references])

    total_ms = (time.perf_counter() - total_start) * 1000.0
    metrics_collector.record_latency("total_request_latency_ms", total_ms)
    if degraded:
        metrics_collector.increment("requests_fallback")
    else:
        metrics_collector.increment("requests_success")
    metrics_collector.log_event("chat_service", req_id, total_ms, "DEGRADED" if degraded else "SUCCESS")

    return {
        "answer": cleaned_answer,
        "risk_level": triage_result.get("risk_level", default_risk),
        "risk_score": risk_score,
        "symptoms": triage_result.get("symptoms") or facts.get("present_symptoms", []),
        "specialist": triage_result.get("specialist", default_spec),
        "visual_findings": visual_findings,
        "differential_diagnosis": diff_diag,
        "is_emergency": bool(triage_result.get("is_emergency", False)),
        "degraded": degraded,
        "sources": sources,
        "grounding_status": grounding_status or ("unavailable" if degraded else "not_applicable"),
    }


def execute_chat_workflow(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    image_bytes: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg",
    lang: str = "vi",
    conversation_id: Optional[str] = None,
    health_context: Optional[Dict[str, Any]] = None,
    gemini_service: Optional[GeminiMedicalService] = None,
    user_id: Optional[int] = None,
    guest_token: Optional[str] = None,
    request_id: Optional[str] = None,
    chat_processor=None
) -> Dict[str, Any]:
    """
    Điều phối luồng chat lâm sàng hợp nhất giữa Chat Service và Intake Service:
    1. ĐỒNG BỘ INTAKE SERVICE: Cập nhật dữ kiện lâm sàng và tìm câu hỏi tiếp theo
    2. GỌI PROCESS_CLINICAL_CHAT: RAG + Gemini/Fallback + Guardrails
    3. HỢP NHẤT DỮ LIỆU ĐÁNH GIÁ: Cập nhật câu trả lời vào intake session và trả về contract đầy đủ
    """
    from core.chat.intake_service import intake_service

    if chat_processor is None:
        chat_processor = process_clinical_chat

    intake_res = None
    clinical_hint = None
    if conversation_id:
        intake_res = intake_service.process_message(
            conversation_id=conversation_id,
            message=message,
            image_bytes=image_bytes,
            user_id=user_id,
            guest_token=guest_token,
            include_summary=False,
            lang=lang,
        )
        if intake_res.get("next_question"):
            clinical_hint = intake_res["next_question"]

    if intake_res and intake_res.get("needs_red_flag_confirmation"):
        res = {
            "answer": intake_res["answer"],
            "risk_level": "Chưa đủ thông tin" if lang == "vi" else "Insufficient information",
            "risk_score": None, "symptoms": [], "specialist": "", "visual_findings": [],
            "differential_diagnosis": [], "is_emergency": False, "degraded": False, "sources": [],
            "needs_red_flag_confirmation": True, "grounding_status": "clarification",
        }
    elif intake_res and intake_res.get("status") == "emergency":
        # The intake layer sees the persisted last question even if the client
        # omits history; never let a later model call dilute its urgent finding.
        res = {
            "answer": intake_res["answer"],
            "risk_level": "Nguy cơ cao (Cần thăm khám khẩn)" if lang == "vi" else "High Risk (Immediate Care Needed)",
            "risk_score": None,
            "symptoms": intake_res.get("emergency_symptoms", []),
            "specialist": "Cấp cứu 115 / Khoa Cấp cứu" if lang == "vi" else "Emergency 115 / ER Department",
            "visual_findings": [], "differential_diagnosis": [],
            "is_emergency": True, "degraded": False, "sources": [], "grounding_status": "emergency",
        }
    else:
        res = chat_processor(
            message=message,
            history=history,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
            lang=lang,
            gemini_service=gemini_service,
            clinical_hint=clinical_hint,
            intake_facts=(intake_res or {}).get("facts"),
            health_context=health_context,
            request_id=request_id,
            consultation_mode=(intake_res or {}).get("consultation_mode", "collecting"),
        )

    persistence_saved = False
    if conversation_id:
        res["conversation_id"] = conversation_id
        if intake_res:
            try:
                intake_service.record_assistant_reply(
                    conversation_id, res["answer"],
                    user_id=user_id, guest_token=guest_token,
                    expected_turn_count=intake_res.get("turn_count"),
                    assessment={
                        "consultation_mode": intake_res.get("consultation_mode", "collecting"),
                        **{key: res.get(key) for key in
                           ("is_emergency", "specialist", "risk_level", "grounding_status", "sources", "degraded")},
                    },
                )
                persistence_saved = True
            except Exception as e:
                import logging
                logging.getLogger("ChatService").warning(
                    "Không thể lưu tiến trình hội thoại vào CSDL bền vững: %s", type(e).__name__
                )
                persistence_saved = False

            intake_res["answer"] = res["answer"]
            res["intake"] = intake_res
            res["intake_facts"] = intake_res.get("facts")
            res["intake_summary"] = intake_res.get("summary")
            res["intake_status"] = intake_res.get("status")

    res["history_saved"] = persistence_saved
    return res


