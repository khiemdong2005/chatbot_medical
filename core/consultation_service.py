"""
core/consultation_service.py
Dịch vụ quản lý các phiên tư vấn lâm sàng (Clinical Consultations) và Phiếu tóm tắt trước khám (Pre-visit Clinical Summary).
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from core.models import db, ClinicalConsultation, User
from core.db_utils import app_db_context, commit_or_rollback

logger = logging.getLogger("ConsultationService")


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
        return [{**consultation.to_dict(), "summary_available": bool(consultation.conversation_id)}
                for consultation in consultations]


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
                from core.intake_service import intake_service
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
                "summary": summary_data,
                "patient_name": patient_name,
                "patient_id": patient_id
            },
            200
        )
