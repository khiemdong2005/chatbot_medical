"""
core/appointment_service.py
Dịch vụ quản lý lịch hẹn khám chữa bệnh (Medical Appointments).
Tuân thủ đầy đủ bất biến giao dịch Phase 5.2 (commit_or_rollback).
"""
import json
import logging
import re
from typing import Any, Dict, List, Tuple
from core.models import ClinicalConsultation, MedicalAppointment
from core.db_utils import app_db_context, commit_or_rollback

logger = logging.getLogger("AppointmentService")

_APPT_DATE_RE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})$")
_APPT_TIME_RE = re.compile(
    r"^\d{1,2}:\d{2}(?:\s*(?:AM|PM))?(?:\s*[-–]\s*\d{1,2}:\d{2}(?:\s*(?:AM|PM))?)?$",
    re.IGNORECASE,
)


def _clean_text(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return default
    return default


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
        return False, {"success": False, "error": "Dữ liệu đặt lịch hẹn không hợp lệ."}, 400

    raw_fac_id = payload.get("facility_id")
    facility_id = (str(raw_fac_id).strip() if isinstance(raw_fac_id, (str, int)) and not isinstance(raw_fac_id, bool) else "fac_unknown") or "fac_unknown"
    facility_name = _clean_text(payload.get("facility_name"))
    facility_address = _clean_text(payload.get("facility_address"))

    # Chuẩn hóa theo dữ liệu CSKCB thật khi có facility_id hợp lệ từ danh mục bệnh viện
    if facility_id and facility_id != "fac_unknown":
        try:
            from core.facilities_service import load_facilities_data
            matched = next(
                (item for item in load_facilities_data() if str(item.get("id")) == facility_id),
                None,
            )
            if matched:
                facility_name = (matched.get("ten") or matched.get("ten_ngan") or facility_name).strip()
                facility_address = (
                    matched.get("dia_chi_hien_thi_tren_web") or matched.get("dia_chi") or facility_address
                ).strip()
        except Exception:
            pass

    if not facility_name:
        facility_name = "Cơ sở Y tế"

    specialty = _clean_text(payload.get("specialty")) or "Đa khoa"
    appointment_date = _clean_text(payload.get("appointment_date"))
    appointment_time = _clean_text(payload.get("appointment_time"))
    patient_name = _clean_text(payload.get("patient_name"))
    patient_phone = _clean_text(payload.get("patient_phone"))
    note = _clean_text(payload.get("note"))

    if not appointment_date or not appointment_time or not patient_name or not patient_phone:
        return (
            False,
            {
                "success": False,
                "error": "Vui lòng điền đầy đủ ngày khám, giờ khám, họ tên và số điện thoại."
            },
            400
        )

    # SECURITY (L-02): Kiểm tra độ dài và định dạng đầu vào đặt lịch khám
    if len(facility_id) > 64 or len(facility_name) > 200 or len(facility_address) > 300:
        return False, {"success": False, "error": "Thông tin cơ sở y tế vượt quá độ dài cho phép."}, 400
    if len(specialty) > 120:
        return False, {"success": False, "error": "Tên chuyên khoa tối đa 120 ký tự."}, 400
    if len(patient_name) < 2 or len(patient_name) > 120:
        return False, {"success": False, "error": "Họ tên người khám phải từ 2 đến 120 ký tự."}, 400
    phone_digits = "".join(ch for ch in patient_phone if ch.isdigit())
    if len(patient_phone) > 25 or len(phone_digits) < 9 or len(phone_digits) > 15:
        return False, {"success": False, "error": "Số điện thoại liên hệ không hợp lệ (9-15 chữ số)."}, 400
    if len(appointment_date) > 32 or not _APPT_DATE_RE.match(appointment_date):
        return False, {"success": False, "error": "Ngày khám phải đúng định dạng YYYY-MM-DD hoặc DD/MM/YYYY."}, 400
    if len(appointment_time) > 25 or not _APPT_TIME_RE.match(appointment_time):
        return False, {"success": False, "error": "Giờ khám không hợp lệ (VD: 09:30 hoặc 08:00 - 09:30)."}, 400
    if len(note) > 1000:
        return False, {"success": False, "error": "Ghi chú khám tối đa 1000 ký tự."}, 400

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
            logger.error("Không thể commit lịch hẹn mới vào CSDL (%s).", type(e).__name__)
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
