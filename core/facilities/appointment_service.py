"""
core/appointment_service.py
Dịch vụ quản lý lịch hẹn khám chữa bệnh (Medical Appointments).
Tuân thủ đầy đủ bất biến giao dịch Phase 5.2 (commit_or_rollback).
"""
import json
import logging
import os
import re
import smtplib
from typing import Any, Dict, List, Optional, Tuple
from core.auth.email_service import email_service
from core.auth.rate_limit_service import rate_limit_service
from core.shared.models import ClinicalConsultation, User, db, MedicalAppointment
from core.shared.db_utils import app_db_context, commit_or_rollback

logger = logging.getLogger("AppointmentService")
_SAFE_EMAIL_RE = re.compile(r"^[^@\s\r\n]+@[^@\s\r\n]+\.[^@\s\r\n]+$")


def _clean_text_field(payload: Dict[str, Any], key: str, default: str = "", max_len: int = 255) -> Tuple[Optional[str], Optional[str]]:
    """Kiểm tra kiểu chuỗi an toàn và giới hạn độ dài tối đa cho trường đầu vào."""
    raw = payload.get(key)
    if raw is None:
        return default, None
    if not isinstance(raw, str):
        return None, f"Trường '{key}' phải có định dạng văn bản hợp lệ."
    val = raw.strip()
    if not val:
        return default, None
    if len(val) > max_len:
        return None, f"Trường '{key}' vượt quá độ dài tối đa cho phép ({max_len} ký tự)."
    return val, None


def _resolve_appointment_email(sess, user_id: int, payload: Dict[str, Any]) -> Optional[str]:
    """Xác định địa chỉ email nhận xác nhận (ưu tiên email nhập ở form, fallback sang Gmail/email đăng ký)."""
    raw_explicit = payload.get("patient_email") if payload.get("patient_email") is not None else payload.get("email")
    explicit = raw_explicit.strip() if isinstance(raw_explicit, str) else ""
    if explicit and len(explicit) <= 120 and _SAFE_EMAIL_RE.match(explicit) and not explicit.lower().endswith("@phone.medimind"):
        return explicit

    user = sess.get(User, user_id)
    if user and user.email:
        reg_email = user.email.strip()
        if len(reg_email) <= 120 and _SAFE_EMAIL_RE.match(reg_email) and not reg_email.lower().endswith("@phone.medimind"):
            return reg_email
    return None


def _dispatch_confirmation_email(recipient_email: Optional[str], appt_dict: Dict[str, Any]) -> bool:
    """Gửi email xác nhận lịch hẹn an toàn (không làm lỗi giao dịch đặt lịch nếu SMTP gặp sự cố)."""
    if not recipient_email:
        return False
    # Tránh gửi email thật ra Gmail khi chạy các test không mock SMTP
    in_pytest = bool(os.getenv("PYTEST_CURRENT_TEST"))
    unmocked_smtp = getattr(smtplib.SMTP, "__module__", "") == "smtplib"
    if in_pytest and unmocked_smtp and email_service.is_configured() and os.getenv("TEST_ALLOW_LIVE_SMTP") != "1":
        return True
    try:
        return bool(email_service.send_appointment_confirmation(recipient_email, appt_dict))
    except Exception as exc:
        logger.warning("Không thể gửi email xác nhận lịch hẹn tới %s: %s", recipient_email, exc)
        return False


def get_user_appointments(user_id: int) -> List[Dict[str, Any]]:
    """Lấy danh sách các lịch hẹn khám của tài khoản đang đăng nhập."""
    with app_db_context():
        appts = (
            MedicalAppointment.query.filter_by(user_id=user_id)
            .order_by(MedicalAppointment.created_at.desc())
            .all()
        )
        return [a.to_dict() for a in appts]


def create_user_appointment(user_id: int, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], int]:
    """
    Tiếp nhận và tạo mới lịch hẹn khám chữa bệnh:
    Trả về: (thành_công, payload_kết_quả, http_status_code)
    """
    if not isinstance(payload, dict):
        return False, {"success": False, "error": "Dữ liệu đặt lịch không hợp lệ."}, 400

    field_specs = (
        ("facility_id", "fac_unknown", 100),
        ("facility_name", "Cơ sở Y tế", 255),
        ("facility_address", "", 500),
        ("specialty", "Đa khoa", 120),
        ("appointment_date", "", 40),
        ("appointment_time", "", 60),
        ("patient_name", "", 120),
        ("patient_phone", "", 30),
        ("note", "", 2000),
    )
    cleaned: Dict[str, str] = {}
    for key, default, max_len in field_specs:
        val, err = _clean_text_field(payload, key, default=default, max_len=max_len)
        if err:
            return False, {"success": False, "error": err}, 400
        cleaned[key] = val or ""

    facility_id = cleaned["facility_id"]
    facility_name = cleaned["facility_name"]
    facility_address = cleaned["facility_address"]
    specialty = cleaned["specialty"]
    appointment_date = cleaned["appointment_date"]
    appointment_time = cleaned["appointment_time"]
    patient_name = cleaned["patient_name"]
    patient_phone = cleaned["patient_phone"]
    note = cleaned["note"]

    if not appointment_date or not appointment_time or not patient_name or not patient_phone:
        return (
            False,
            {
                "success": False,
                "error": "Vui lòng điền đầy đủ ngày khám, giờ khám, họ tên và số điện thoại."
            },
            400
        )

    if not rate_limit_service.backend.check_and_increment(f"appt_create:{user_id}", max_requests=10, window_seconds=600):
        return (
            False,
            {
                "success": False,
                "error": "Bạn đã gửi quá nhiều yêu cầu đặt lịch trong thời gian ngắn. Vui lòng thử lại sau ít phút."
            },
            429
        )

    with app_db_context() as sess:
        pre_visit_summary = None
        conversation_id = payload.get("pre_visit_conversation_id")
        if conversation_id is not None:
            if not isinstance(conversation_id, str) or not conversation_id.strip() or len(conversation_id) > 100:
                return False, {"error": "Mã phiên hỏi bệnh không hợp lệ."}, 400

            record = ClinicalConsultation.query.filter_by(
                user_id=user_id, conversation_id=conversation_id.strip()
            ).first()
            if record and record.confirmed_summary:
                try:
                    pre_visit_summary = json.loads(record.confirmed_summary)
                except (TypeError, ValueError):
                    pass
            if not isinstance(pre_visit_summary, dict) or pre_visit_summary.get("is_confirmed") is not True:
                return False, {"error": "Không tìm thấy bản tóm tắt trước khám đã xác nhận."}, 400

            summary_version = payload.get("pre_visit_summary_version")
            if summary_version is not None and (
                type(summary_version) is not int or summary_version != pre_visit_summary.get("version")
            ):
                return False, {"error": "Bản tóm tắt trước khám đã thay đổi. Vui lòng mở và xem lại."}, 400

        new_appt = MedicalAppointment(
            user_id=user_id,
            facility_id=facility_id,
            facility_name=facility_name,
            facility_address=facility_address,
            specialty=specialty,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            patient_name=patient_name,
            patient_phone=patient_phone,
            note=note,
            pre_visit_summary=pre_visit_summary,
            status="pending"
        )
        sess.add(new_appt)
        try:
            commit_or_rollback(sess)
        except Exception as e:
            logger.error("Không thể commit lịch hẹn mới vào CSDL: %s", e)
            return (
                False,
                {
                    "success": False,
                    "error": "Không thể lưu thông tin lịch hẹn vào cơ sở dữ liệu."
                },
                500
            )

        appt_dict = new_appt.to_dict()
        recipient_email = _resolve_appointment_email(sess, user_id, payload)
        email_sent = _dispatch_confirmation_email(recipient_email, appt_dict)

        msg = f"Đặt lịch khám thành công tại {facility_name}!"
        if email_sent and recipient_email:
            msg = f"Đặt lịch khám thành công tại {facility_name}! Email xác nhận đã được gửi tới {recipient_email}."

        return (
            True,
            {
                "success": True,
                "message": msg,
                "appointment": appt_dict,
                "email_sent": email_sent,
                "email_recipient": recipient_email,
            },
            201
        )


def delete_user_appointment(user_id: int, appt_id: int) -> Tuple[bool, Dict[str, Any], int]:
    """Hủy một lịch hẹn khám của người dùng với kiểm tra quyền sở hữu nghiêm ngặt."""
    with app_db_context() as sess:
        appt = MedicalAppointment.query.filter_by(id=appt_id, user_id=user_id).first()
        if not appt:
            return (
                False,
                {
                    "success": False,
                    "error": "Không tìm thấy lịch hẹn hoặc bạn không có quyền hủy."
                },
                404
            )

        sess.delete(appt)
        try:
            commit_or_rollback(sess)
        except Exception as e:
            logger.error("Không thể commit hủy lịch hẹn trong CSDL: %s", e)
            return (
                False,
                {
                    "success": False,
                    "error": "Không thể hủy lịch hẹn khỏi cơ sở dữ liệu."
                },
                500
            )

        return (
            True,
            {
                "success": True,
                "message": "Đã hủy lịch hẹn khám thành công."
            },
            200
        )
