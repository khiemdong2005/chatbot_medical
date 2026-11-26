"""
In-app notification service ("chuông Thông báo").

- Lưu thông báo theo tài khoản trong CSDL dùng chung (RDS) để đồng bộ giữa nhiều EC2 / thiết bị.
- Chống trùng bằng (user_id, dedupe_key) duy nhất.
- Client chỉ được tự tạo thông báo loại nhắc uống thuốc; thông báo lịch hẹn do server sinh ra.
"""
import json
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError

from core.shared.db_utils import app_db_context
from core.shared.models import UserNotification, db

logger = logging.getLogger("NotificationService")

TYPE_APPOINTMENT_CREATED = "appointment_created"
TYPE_APPOINTMENT_CANCELLED = "appointment_cancelled"
TYPE_MEDICATION_REMINDER = "medication_reminder"
ALLOWED_TYPES = {TYPE_APPOINTMENT_CREATED, TYPE_APPOINTMENT_CANCELLED, TYPE_MEDICATION_REMINDER}

MAX_LIST_LIMIT = 50
MAX_KEEP_PER_USER = 100
MED_DEDUPE_RE = re.compile(r"^med:\d{4}-\d{2}-\d{2}:[a-z_]{2,16}:\d{2}:\d{2}$")
MED_SLOT_LABELS_VI = {
    "morning": "Buổi sáng",
    "noon": "Buổi trưa",
    "evening": "Chiều / Tối",
    "bedtime": "Trước khi ngủ",
}


def _clip(value: Any, max_len: int) -> str:
    return str(value or "").strip()[:max_len]


def _prune_old(user_id: int) -> None:
    """Giới hạn số thông báo lưu cho mỗi tài khoản để bảng không phình vô hạn."""
    keep_ids = [
        row.id for row in UserNotification.query.with_entities(UserNotification.id)
        .filter_by(user_id=user_id)
        .order_by(UserNotification.created_at.desc(), UserNotification.id.desc())
        .limit(MAX_KEEP_PER_USER)
    ]
    if len(keep_ids) >= MAX_KEEP_PER_USER:
        UserNotification.query.filter(
            UserNotification.user_id == user_id,
            ~UserNotification.id.in_(keep_ids),
        ).delete(synchronize_session=False)


def create_notification(
    user_id: int,
    ntype: str,
    title: str,
    message: str = "",
    *,
    link: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    dedupe_key: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Tạo thông báo; trả về (notification_dict, created). Nếu dedupe_key đã tồn tại thì trả bản cũ."""
    if ntype not in ALLOWED_TYPES or not user_id:
        raise ValueError("Loại thông báo không hợp lệ.")
    with app_db_context() as sess:
        if dedupe_key:
            existing = UserNotification.query.filter_by(user_id=user_id, dedupe_key=dedupe_key).first()
            if existing:
                return existing.to_dict(), False
        row = UserNotification(
            user_id=user_id,
            type=ntype,
            title=_clip(title, 255),
            message=_clip(message, 2000),
            link=_clip(link, 100) or None,
            data_json=json.dumps(data or {}, ensure_ascii=False),
            dedupe_key=_clip(dedupe_key, 160) or None,
            is_read=False,
        )
        sess.add(row)
        try:
            sess.flush()
            _prune_old(user_id)
            sess.commit()
        except IntegrityError:
            # Hai tab/máy gửi cùng lúc: bản ghi còn lại là bản đã được lưu trước
            sess.rollback()
            existing = UserNotification.query.filter_by(user_id=user_id, dedupe_key=dedupe_key).first()
            return (existing.to_dict() if existing else None), False
        except Exception:
            sess.rollback()
            raise
        return row.to_dict(), True


def safe_create_notification(*args, **kwargs) -> Optional[Dict[str, Any]]:
    """Phiên bản không ném lỗi, dùng cho luồng nghiệp vụ chính (đặt lịch không được hỏng vì thông báo)."""
    try:
        notification, _ = create_notification(*args, **kwargs)
        return notification
    except Exception as exc:
        logger.warning("Không thể tạo thông báo trong ứng dụng (%s).", type(exc).__name__)
        try:
            with app_db_context() as sess:
                sess.rollback()
        except Exception:
            pass
        return None


def list_notifications(user_id: int, limit: int = 30) -> Dict[str, Any]:
    limit = max(1, min(int(limit or 30), MAX_LIST_LIMIT))
    with app_db_context():
        rows = (
            UserNotification.query.filter_by(user_id=user_id)
            .order_by(UserNotification.created_at.desc(), UserNotification.id.desc())
            .limit(limit)
            .all()
        )
        unread = UserNotification.query.filter_by(user_id=user_id, is_read=False).count()
        return {"notifications": [r.to_dict() for r in rows], "unread_count": unread}


def mark_read(user_id: int, ids: Optional[Iterable[int]] = None, mark_all: bool = False) -> int:
    with app_db_context() as sess:
        query = UserNotification.query.filter_by(user_id=user_id, is_read=False)
        if not mark_all:
            clean_ids = [i for i in (ids or []) if type(i) is int and i > 0][:MAX_LIST_LIMIT]
            if not clean_ids:
                return 0
            query = query.filter(UserNotification.id.in_(clean_ids))
        updated = query.update({UserNotification.is_read: True}, synchronize_session=False)
        sess.commit()
        return int(updated or 0)


def unread_count(user_id: int) -> int:
    with app_db_context():
        return UserNotification.query.filter_by(user_id=user_id, is_read=False).count()


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def notify_appointment_created(user_id: int, appt: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    facility = _clip(appt.get("facility_name"), 255)
    date = _clip(appt.get("appointment_date"), 40)
    time = _clip(appt.get("appointment_time"), 60)
    return safe_create_notification(
        user_id,
        TYPE_APPOINTMENT_CREATED,
        f"Đặt lịch thành công: {facility}",
        f"Lịch khám lúc {time} ngày {date}" + (f" · {appt.get('specialty')}" if appt.get("specialty") else ""),
        link="appointments",
        data={
            "appointment_id": appt.get("id"),
            "facility_name": facility,
            "appointment_date": date,
            "appointment_time": time,
            "specialty": _clip(appt.get("specialty"), 120),
        },
        dedupe_key=f"appt_created:{appt.get('id')}",
    )


def notify_appointment_cancelled(user_id: int, appt: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    facility = _clip(appt.get("facility_name"), 255)
    date = _clip(appt.get("appointment_date"), 40)
    time = _clip(appt.get("appointment_time"), 60)
    return safe_create_notification(
        user_id,
        TYPE_APPOINTMENT_CANCELLED,
        f"Đã hủy lịch hẹn: {facility}",
        f"Lịch khám lúc {time} ngày {date} đã được hủy.",
        link="appointments",
        data={
            "appointment_id": appt.get("id"),
            "facility_name": facility,
            "appointment_date": date,
            "appointment_time": time,
        },
        dedupe_key=f"appt_cancelled:{appt.get('id')}",
    )


def create_medication_reminder(user_id: int, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Validate a client-fired medication reminder and persist it (deduplicated per day/slot/time)."""
    if not isinstance(payload, dict):
        raise ValueError("Dữ liệu thông báo không hợp lệ.")
    if payload.get("type") != TYPE_MEDICATION_REMINDER:
        raise ValueError("Chỉ hỗ trợ tạo thông báo nhắc uống thuốc.")
    dedupe_key = payload.get("dedupe_key")
    if not isinstance(dedupe_key, str) or not MED_DEDUPE_RE.match(dedupe_key):
        raise ValueError("Khóa chống trùng không hợp lệ.")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    slot = _clip(data.get("slot"), 16)
    time = _clip(data.get("time"), 5)
    if not re.fullmatch(r"[a-z_]{2,16}", slot or "") or not re.fullmatch(r"\d{2}:\d{2}", time or ""):
        raise ValueError("Thông tin cữ thuốc không hợp lệ.")
    meds: List[Dict[str, str]] = []
    for item in (data.get("meds") or [])[:20]:
        if isinstance(item, dict) and _clip(item.get("name"), 120):
            meds.append({"name": _clip(item.get("name"), 120), "dose": _clip(item.get("dose"), 60)})
    slot_label = MED_SLOT_LABELS_VI.get(slot, slot)
    med_text = ", ".join(m["name"] + (f" ({m['dose']})" if m["dose"] else "") for m in meds) or "Kiểm tra đơn thuốc của bạn"
    return create_notification(
        user_id,
        TYPE_MEDICATION_REMINDER,
        f"Đến giờ uống thuốc — {slot_label} ({time})",
        f"Thuốc cần dùng: {med_text}",
        link="medication",
        data={"slot": slot, "time": time, "meds": meds},
        dedupe_key=dedupe_key,
    )
