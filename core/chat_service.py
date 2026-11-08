import uuid
import logging
from typing import Dict, Any, List, Optional
from core.triage import analyze_symptoms, assess_emergency_risk, apply_safety_guardrails
from core.rag_service import medical_rag_service
from core.gemini_service import GeminiMedicalService

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


def process_clinical_chat(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    image_bytes: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg",
    lang: str = "vi",
    gemini_service: Optional[GeminiMedicalService] = None,
    request_id: Optional[str] = None,
    clinical_hint: Optional[str] = None,
    intake_facts: Optional[dict] = None
) -> Dict[str, Any]:
    """
    Dịch vụ điều phối tư vấn lâm sàng 4 tầng dùng chung (Shared Application Service):
      Tầng 1: Tiền kiểm Cờ đỏ cấp cứu (Pre-check Emergency Guardrail) có bẫy phủ định.
      Tầng 2: Truy vấn tri thức y khoa RAG từ ChromaDB.
      Tầng 3: Bộ não suy luận AI Gemini Flash + Fallback nội bộ có đánh dấu degraded.
      Tầng 4: Hậu kiểm an toàn (Post-check Guardrail) chặn và can thiệp kê đơn kháng sinh.
    
    Đảm bảo 100% hợp đồng dữ liệu đầu ra nhất quán giữa Flask và FastAPI.
    """
    req_id = request_id or uuid.uuid4().hex[:8]
    lang = lang if lang in ALLOWED_LANGUAGES else "vi"
    history = (history or [])[-MAX_HISTORY_ITEMS:]

    user_message = (message or "").strip()
    if len(user_message) > MAX_MESSAGE_LENGTH:
        user_message = user_message[:MAX_MESSAGE_LENGTH]

    has_image = bool(image_bytes and len(image_bytes) > 0)
    if not user_message and not has_image:
        raise ValueError("Vui lòng nhập nội dung tin nhắn hoặc đính kèm ảnh triệu chứng.")

    if gemini_service is None:
        gemini_service = GeminiMedicalService()

    # -------------------------------------------------------------
    # TẦNG 1: TIỀN KIỂM AN TOÀN (Pre-check Guardrail)
    # -------------------------------------------------------------
    previous = history[-1].get("content", "") if history and history[-1].get("role") == "assistant" else ""
    emergency = assess_emergency_risk(user_message, lang=lang, previous_question=previous)
    if emergency.get("clarification"):
        return {"answer": emergency["clarification"], "needs_red_flag_confirmation": True, "risk_level": "Chưa đủ thông tin" if lang == "vi" else "Unclear",
                "risk_score": None, "symptoms": [], "specialist": "", "is_emergency": False,
                "visual_findings": [], "differential_diagnosis": [], "degraded": False, "sources": []}
    if emergency.get("is_emergency"):
        logger.warning(f"[REQ-{req_id}] Phát hiện cờ đỏ cấp cứu: {emergency.get('symptoms')}")
        return {
            "answer": emergency["message"],
            "risk_level": "Nguy cơ cao (Cần thăm khám khẩn)" if lang == "vi" else "High Risk (Immediate Care Needed)",
            "risk_score": 90,
            "symptoms": emergency["symptoms"],
            "specialist": "Cấp cứu 115 / Khoa Cấp cứu" if lang == "vi" else "Emergency 115 / ER Department",
            "is_emergency": True,
            "visual_findings": [],
            "differential_diagnosis": ["Dấu hiệu cấp cứu tim mạch / hô hấp"],
            "degraded": False,
            "sources": [
                {
                    "title": "Quy trình Cấp cứu Ban đầu - Bộ Y Tế",
                    "source": "Cục Quản lý Khám chữa bệnh",
                    "url": "https://kcb.vn"
                }
            ]
        }

    import re
    msg_clean = user_message.lower().strip()
    if not has_image and any(re.search(pattern, msg_clean) for pattern in OUT_OF_SCOPE_PATTERNS):
        reported = (intake_facts or {}).get("present_symptoms", [])
        if lang == "en":
            answer = "I focus on health questions, so I can't help solve that. We can continue with your symptoms whenever you're ready."
            risk_level = "Outside health scope"
        elif reported:
            answer = f"Mình tập trung hỗ trợ sức khỏe nên không giải bài toán được. Nếu muốn, mình có thể tiếp tục với chuyện {reported[0].lower()}."
            risk_level = "Ngoài phạm vi tư vấn sức khỏe"
        else:
            answer = "Mình tập trung hỗ trợ sức khỏe nên không giải bài toán được. Bạn muốn hỏi gì về triệu chứng, thuốc hoặc kết quả xét nghiệm?"
            risk_level = "Ngoài phạm vi tư vấn sức khỏe"
        return {
            "answer": answer,
            "risk_level": risk_level,
            "risk_score": None,
            "symptoms": reported,
            "specialist": "",
            "visual_findings": [],
            "differential_diagnosis": [],
            "is_emergency": False,
            "degraded": False,
            "sources": [],
        }

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
        return {
            "answer": triage_result["answer"],
            "risk_level": triage_result["risk_level"],
            "risk_score": 10,
            "symptoms": triage_result.get("symptoms", []),
            "specialist": triage_result.get("specialist", "Y học gia đình"),
            "visual_findings": [],
            "differential_diagnosis": [],
            "is_emergency": False,
            "degraded": False,
            "sources": triage_result.get("sources", [])
        }

    # -------------------------------------------------------------
    # TẦNG 2: TRUY VẤN TRI THỨC Y KHOA RAG TỪ CHROMADB
    # -------------------------------------------------------------
    rag_docs = []
    try:
        rag_docs = medical_rag_service.retrieve_context(user_message, top_k=2)
    except Exception as e:
        logger.warning(f"[REQ-{req_id}] RAG retrieval gặp lỗi: {e}")

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
            clinical_hint=clinical_hint
        )
    except Exception as err:
        logger.warning(f"[REQ-{req_id}] Gemini service exception: {err}")
        gemini_result = None

    if gemini_result and isinstance(gemini_result, dict) and gemini_result.get("answer"):
        triage_result = gemini_result
    else:
        # Kích hoạt Fallback Engine và đánh dấu trạng thái degraded
        degraded = True
        logger.info(f"[REQ-{req_id}] Chuyển sang Fallback Engine (degraded=True)")
        triage_result = analyze_symptoms(user_message, history, lang=lang, has_image=has_image)
        present = (intake_facts or {}).get("present_symptoms", [])
        if intake_facts and lang == "vi" and not has_image and not triage_result.get("is_emergency"):
            recap = ", ".join(present).lower()
            question = clinical_hint or ""
            if re.search(r"kê (?:toa|đơn)|(?:uống|dùng|ún) thuốc (?:gì|nào)", msg_clean):
                answer = "Mình không thể chọn thuốc an toàn chỉ từ những thông tin này."
                if "tay" in msg_clean and "sưng" in msg_clean:
                    answer += " Tay sưng đau nên được nhân viên y tế đánh giá trước khi dùng thuốc."
                question = ""
            elif "sốt" in msg_clean and present and not (intake_facts.get("vitals") or {}).get("temperature"):
                answer = "Nếu có nhiệt kế, bạn đo được khoảng bao nhiêu độ?"
                question = ""
            elif any(token in msg_clean for token in ("tay", "cổ tay", "bàn tay", "cánh tay")) and "sưng" in msg_clean and "đau" in msg_clean:
                answer = "Tay vừa đau vừa sưng thì nên làm rõ nguyên nhân trước. Bạn có bị va đập hoặc chấn thương gần đây không?"
                question = ""
            else:
                answer = ("Bạn muốn mình hỗ trợ điều gì về triệu chứng này?" if recap else
                          "Mình chưa rõ điều bạn muốn hỏi. Bạn nói thêm một chút được không?") if not question else ""
            if question and any(question in str(turn.get("content", "")) for turn in history if turn.get("role") == "assistant"):
                question = ""
            triage_result.update(answer=" ".join(filter(None, [answer, question])), symptoms=present,
                                 differential_diagnosis=[], specialist="Chưa xác định",
                                 risk_level="Chưa đủ thông tin", risk_score=None)
        elif clinical_hint and triage_result.get("answer"):
            triage_result["answer"] += f"\n\n💡 *Lưu ý y tế:* {clinical_hint}"
        if rag_docs:
            triage_result["sources"] = [
                {
                    "title": d.get("title", "MedlinePlus"),
                    "source": d.get("source", "MedlinePlus"),
                    "url": d.get("source_url", "https://medlineplus.gov")
                }
                for d in rag_docs
            ]

    # -------------------------------------------------------------
    # TẦNG 4: HẬU KIỂM AN TOÀN (Post-check Guardrail)
    # -------------------------------------------------------------
    raw_answer = triage_result.get("answer", "")
    # A brief update to an existing cough history only needs a clarification.
    facts = intake_facts or {}
    reported = facts.get("present_symptoms", [])
    if (lang == "vi" and not has_image and not triage_result.get("is_emergency")
            and any(s in reported for s in ("Ho", "Ho khan", "Ho có đờm"))
            and not (facts.get("vitals") or {}).get("temperature")
            and re.fullmatch(r"(?:lâu lâu|thỉnh thoảng|đôi lúc)\s+(?:có\s+)?sốt(?:\s+nữa)?[.! ]*", msg_clean)):
        raw_answer = "Lúc sốt, bạn có đo được nhiệt độ khoảng bao nhiêu không?"
    if any(turn.get("role") == "assistant" for turn in history):
        body = re.sub(r"^\s*(?:xin chào(?: bạn)?|chào bạn|hello(?: there)?|hi there)[!,.:;–—\s]+",
                      "", raw_answer, count=1, flags=re.IGNORECASE)
        if body and body != raw_answer:
            raw_answer = body[:1].upper() + body[1:]
    from core.intake_service import abdominal_pain, pain_ready
    if (lang == "vi" and not has_image and abdominal_pain(facts) and not pain_ready(facts)
            and not triage_result.get("is_emergency")):
        triage_result.update(risk_level="Chưa đủ thông tin", risk_score=None,
                             specialist="Chưa xác định", differential_diagnosis=[])
        if clinical_hint and "?" not in user_message and not re.search(r"thuốc|kê đơn", msg_clean):
            raw_answer = clinical_hint
    # Khi người bệnh vừa trả lời câu hỏi khai thác, tiếp tục hỏi dữ kiện kế tiếp
    # thay vì để mô hình chuyển đột ngột sang checklist chăm sóc chung.
    previous_assistant = next(
        (turn.get("content", "") for turn in reversed(history) if turn.get("role") == "assistant"),
        ""
    )
    is_answering_intake = bool(
        clinical_hint
        and "?" in previous_assistant
        and not re.search(
            r"\?|\b(?:thuốc|uống|dùng|nên|làm sao|vì sao|bao nhiêu|có cần|có phải|là gì|kê đơn|tư vấn)\b",
            msg_clean,
        )
    )
    if is_answering_intake:
        raw_answer = clinical_hint
    cleaned_answer = apply_safety_guardrails(raw_answer, lang=lang)

    # Chuẩn hóa cấu trúc đầu ra theo hợp đồng y tế
    default_risk = "Chưa xác định (Cần thêm thông tin)" if lang == "vi" else "Undetermined (Needs more information)"
    default_spec = "Nội tổng quát" if lang == "vi" else "General Internal Medicine"

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

    sources = triage_result.get("sources", [])
    if not isinstance(sources, list):
        sources = []

    return {
        "answer": cleaned_answer,
        "risk_level": triage_result.get("risk_level", default_risk),
        "risk_score": risk_score,
        "symptoms": triage_result.get("symptoms", []),
        "specialist": triage_result.get("specialist", default_spec),
        "visual_findings": visual_findings,
        "differential_diagnosis": diff_diag,
        "is_emergency": bool(triage_result.get("is_emergency", False)),
        "degraded": degraded,
        "sources": sources
    }

