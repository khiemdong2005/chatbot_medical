"""
core/appointment_service.py
Dịch vụ quản lý lịch hẹn khám chữa bệnh (Medical Appointments).
Tuân thủ đầy đủ bất biến giao dịch Phase 5.2 (commit_or_rollback).
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from core.models import db, MedicalAppointment
from core.db_utils import app_db_context, commit_or_rollback

logger = logging.getLogger("AppointmentService")


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
    facility_id = (payload.get("facility_id") or "fac_unknown").strip()
    facility_name = (payload.get("facility_name") or "Cơ sở Y tế").strip()
    facility_address = (payload.get("facility_address") or "").strip()
    specialty = (payload.get("specialty") or "Đa khoa").strip()
    appointment_date = (payload.get("appointment_date") or "").strip()
    appointment_time = (payload.get("appointment_time") or "").strip()
    patient_name = (payload.get("patient_name") or "").strip()
    patient_phone = (payload.get("patient_phone") or "").strip()
    note = (payload.get("note") or "").strip()

    if not appointment_date or not appointment_time or not patient_name or not patient_phone:
        return (
            False,
            {
                "success": False,
                "error": "Vui lòng điền đầy đủ ngày khám, giờ khám, họ tên và số điện thoại."
            },
            400
        )

    with app_db_context() as sess:
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

        return (
            True,
            {
                "success": True,
                "message": f"Đặt lịch khám thành công tại {facility_name}!",
                "appointment": new_appt.to_dict()
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
