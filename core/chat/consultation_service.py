"""
core/consultation_service.py
Dịch vụ quản lý các phiên tư vấn lâm sàng (Clinical Consultations) và Phiếu tóm tắt trước khám (Pre-visit Clinical Summary).
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from core.shared.models import db, ClinicalConsultation, IntakeSessionRecord, User
from core.shared.db_utils import app_db_context, commit_or_rollback

logger = logging.getLogger("ConsultationService")

_PREVISIT_PLACEHOLDER_PREFIX = "Chưa có đánh giá sơ bộ đủ căn cứ"


def _normalize_chat_turns(raw_messages: Any) -> List[Dict[str, Any]]:
    """Chuyển đổi danh sách tin nhắn từ IntakeSessionRecord sang cặp lượt user/assistant cho Chatbot."""
    if not isinstance(raw_messages, list):
        return []
    turns: List[Dict[str, Any]] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue
        if item.get("previsit_question"):
            continue
        sender = str(item.get("sender") or item.get("role") or "").strip().lower()
        content = str(item.get("content") or item.get("text") or "").strip()
        if not content:
            continue
        if sender in ("patient", "user"):
            turns.append({"role": "user", "content": content})
        elif sender in ("assistant", "bot"):
            turns.append({"role": "assistant", "content": content})
    return turns


def _is_previsit_consultation(
    consultation: ClinicalConsultation,
    intake_rec: Optional[IntakeSessionRecord] = None,
) -> bool:
    """Phân biệt bản ghi Khảo sát trước khám (đặt lịch) với hội thoại Chatbot thực tế."""
    raw_messages: List[Dict[str, Any]] = []
    facts: Dict[str, Any] = {}
    if intake_rec is not None:
        try:
            facts = json.loads(intake_rec.facts_json or "{}")
            if not isinstance(facts, dict):
                facts = {}
        except Exception:
            facts = {}
        try:
            parsed_msgs = json.loads(intake_rec.messages_json or "[]")
            if isinstance(parsed_msgs, list):
                raw_messages = parsed_msgs
        except Exception:
            raw_messages = []

    has_chatbot_assistant = any(
        isinstance(m, dict)
        and str(m.get("sender") or m.get("role") or "").strip().lower() in ("assistant", "bot")
        and not m.get("previsit_question")
        for m in raw_messages
    )
    if has_chatbot_assistant:
        return False

    if "previsit_topics" in facts or any(isinstance(m, dict) and m.get("previsit_question") for m in raw_messages):
        return True

    # Fallback khi IntakeSessionRecord đã bị xóa: kiểm tra cấu trúc confirmed_summary & câu placeholder
    has_saved_turns = False
    if consultation.turns_json:
        try:
            saved_turns = json.loads(consultation.turns_json)
            has_saved_turns = isinstance(saved_turns, list) and any(
                isinstance(t, dict) and t.get("role") == "assistant" for t in saved_turns
            )
        except Exception:
            has_saved_turns = False

    if not has_saved_turns:
        answer_text = (consultation.answer or "").strip()
        if answer_text.startswith(_PREVISIT_PLACEHOLDER_PREFIX):
            return True
        if consultation.confirmed_summary:
            try:
                summary = json.loads(consultation.confirmed_summary)
                part_a = summary.get("part_a_patient_facts") if isinstance(summary, dict) else None
                if isinstance(part_a, dict) and "patient_reported_history" in part_a:
                    return True
            except Exception:
                pass
    return False


def get_user_consultations(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    """Lấy danh sách các phiên tư vấn đã lưu của tài khoản (VULN-05 RBAC)."""
    with app_db_context():
        consultations = (
            ClinicalConsultation.query.filter_by(user_id=user_id)
            .filter(ClinicalConsultation.confirmed_summary.isnot(None))
            .order_by(ClinicalConsultation.created_at.desc())
            .limit(limit)
            .all()
        )
        cids = [c.conversation_id for c in consultations if c.conversation_id]
        intake_map: Dict[str, IntakeSessionRecord] = {}
        if cids:
            intake_rows = IntakeSessionRecord.query.filter(
                IntakeSessionRecord.user_id == user_id,
                IntakeSessionRecord.conversation_id.in_(cids),
            ).all()
            intake_map = {r.conversation_id: r for r in intake_rows}

        result: List[Dict[str, Any]] = []
        for consultation in consultations:
            item = consultation.to_dict()
            intake_rec = intake_map.get(consultation.conversation_id) if consultation.conversation_id else None
            is_previsit = _is_previsit_consultation(consultation, intake_rec)
            item["summary_available"] = bool(consultation.conversation_id)
            item["is_previsit"] = is_previsit
            item["source"] = "previsit" if is_previsit else "chatbot"
            item["created_at_ts"] = (
                int(consultation.created_at.timestamp() * 1000) if consultation.created_at else None
            )
            if not is_previsit and not item.get("messages") and intake_rec is not None:
                try:
                    raw_msgs = json.loads(intake_rec.messages_json or "[]")
                    hydrated = _normalize_chat_turns(raw_msgs)
                    if hydrated:
                        item["messages"] = hydrated
                except Exception:
                    pass
            result.append(item)
        return result


def get_user_chatbot_sessions(user_id: int, limit: int = 30) -> List[Dict[str, Any]]:
    """
    Lấy riêng danh sách hội thoại Chatbot thực tế của người dùng (loại trừ hoàn toàn khảo sát trước khám đặt lịch).
    """
    with app_db_context():
        rows = (
            IntakeSessionRecord.query.filter_by(user_id=user_id)
            .order_by(IntakeSessionRecord.updated_at.desc())
            .limit(limit * 2)
            .all()
        )
        sessions: List[Dict[str, Any]] = []
        for rec in rows:
            try:
                facts = json.loads(rec.facts_json or "{}")
                if not isinstance(facts, dict):
                    facts = {}
            except Exception:
                facts = {}
            try:
                raw_msgs = json.loads(rec.messages_json or "[]")
                if not isinstance(raw_msgs, list):
                    raw_msgs = []
            except Exception:
                raw_msgs = []

            # Loại trừ hoàn toàn các phiên Khảo sát trước khám (previsit flow)
            if "previsit_topics" in facts or any(isinstance(m, dict) and m.get("previsit_question") for m in raw_msgs):
                continue

            turns = _normalize_chat_turns(raw_msgs)
            user_turns = [t for t in turns if t["role"] == "user"]
            assistant_turns = [t for t in turns if t["role"] == "assistant"]
            if not user_turns or not assistant_turns:
                continue

            first_user = user_turns[0]["content"]
            last_assistant = assistant_turns[-1]["content"]
            present_symptoms = facts.get("present_symptoms") if isinstance(facts.get("present_symptoms"), list) else []
            title = ", ".join(str(s) for s in present_symptoms if s) if present_symptoms else (
                first_user[:30] + "..." if len(first_user) > 30 else first_user
            )

            # Lấy risk_level từ verified_assessment gần nhất nếu có
            risk_level = "Theo dõi"
            for m in reversed(raw_msgs):
                va = m.get("verified_assessment") if isinstance(m, dict) else None
                if isinstance(va, dict) and va.get("risk_level"):
                    risk_level = str(va["risk_level"])
                    break

            ts_ms = int(rec.updated_at.timestamp() * 1000) if rec.updated_at else None
            sessions.append({
                "conversation_id": rec.conversation_id,
                "title": title,
                "last_message": last_assistant[:75].replace("\n", " "),
                "messages": turns,
                "message_count": len(user_turns),
                "risk_level": risk_level,
                "is_emergency": bool(rec.is_emergency),
                "timestamp": ts_ms,
                "summary_available": bool(rec.is_confirmed or facts.get("chief_complaint") or present_symptoms),
                "is_previsit": False,
                "source": "chatbot",
            })
            if len(sessions) >= limit:
                break
        return sessions


def delete_user_consultation(
    user_id: int,
    cid: int,
    guest_token: Optional[str] = None
) -> Tuple[bool, Dict[str, Any], int]:
    """
    Xóa một phiên tư vấn theo ID của người dùng.
    Đồng thời xóa intake session liên quan nếu có, bảo toàn tính nhất quán dữ liệu.
    """
    with app_db_context() as sess:
        c = ClinicalConsultation.query.filter_by(id=cid, user_id=user_id).first()
        if not c:
            return False, {"error": "Không tìm thấy phiên tư vấn."}, 404

        if c.conversation_id:
            try:
                from core.chat.intake_service import intake_service
                intake_service.delete_session(
                    c.conversation_id,
                    user_id=user_id,
                    guest_token=guest_token,
                    commit=False
                )
            except PermissionError:
                sess.rollback()
                return False, {"error": "Không thể xóa phiên tư vấn không thuộc tài khoản này."}, 403
            except Exception as e:
                logger.warning("Không thể dọn dẹp intake session cho cuộc trò chuyện %s: %s", c.conversation_id, e)

        sess.delete(c)
        try:
            commit_or_rollback(sess)
        except Exception as e:
            logger.error("Không thể commit xóa phiên tư vấn trong CSDL: %s", e)
            return False, {"error": "Không thể xóa phiên tư vấn khỏi cơ sở dữ liệu."}, 500

        return True, {"message": "Đã xóa phiên tư vấn thành công."}, 200


def get_clinical_summary(
    user_id: int,
    conversation_id: Optional[str] = None
) -> Tuple[bool, Dict[str, Any], int]:
    """
    Bản tóm tắt trước khám chuẩn 2 phần:
    - Trích xuất từ phiên tư vấn thực tế của tài khoản hiện tại.
    """
    with app_db_context() as sess:
        records = ClinicalConsultation.query.filter_by(user_id=user_id).filter(
            ClinicalConsultation.confirmed_summary.isnot(None)
        )
        if conversation_id:
            records = records.filter_by(conversation_id=conversation_id)

        record = records.order_by(ClinicalConsultation.id.desc()).first()
        if record is None:
            return (
                True,
                {
                    "status": "no_data",
                    "message": "Chưa có dữ liệu tư vấn đã xác nhận để hiển thị trong hồ sơ."
                },
                200
            )

        user = sess.get(User, user_id)
        patient_name = user.full_name if user else "Bệnh nhân"
        patient_id = f"BN-2026-{user_id:04d}"

        try:
            summary_data = json.loads(record.confirmed_summary)
        except Exception:
            summary_data = record.confirmed_summary

        return (
            True,
            {
                "status": "success",
                "conversation_id": record.conversation_id,
                "summary": summary_data,
                "patient_name": patient_name,
                "patient_id": patient_id
            },
            200
        )
