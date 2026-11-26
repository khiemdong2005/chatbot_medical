"""
core/routers/notifications.py
FastAPI native router cho chuông Thông báo trong ứng dụng (đặt lịch, hủy lịch, nhắc uống thuốc).
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.auth.rate_limit_service import rate_limit_service
from core.routers.deps import require_authenticated_user
from core.shared.api_errors import ErrorCode, fastapi_api_error
from core.shared.notification_service import (
    create_medication_reminder,
    list_notifications,
    mark_read,
    unread_count,
)

router = APIRouter(prefix="/api/notifications", tags=["6. Thông báo (Notifications)"])


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


@router.get("", summary="Lấy danh sách thông báo và số chưa đọc")
@router.get("/", include_in_schema=False)
async def list_notifications_endpoint(request: Request, limit: int = 30):
    user_id = require_authenticated_user(request)
    return JSONResponse(content={"success": True, **list_notifications(user_id, limit=limit)})


@router.post("", summary="Lưu thông báo nhắc uống thuốc (chống trùng theo ngày + cữ + giờ)")
@router.post("/", include_in_schema=False)
async def create_notification_endpoint(request: Request):
    user_id = require_authenticated_user(request)
    if not rate_limit_service.backend.check_and_increment(f"notif_create:{user_id}", max_requests=60, window_seconds=3600):
        return fastapi_api_error(ErrorCode.RATE_LIMITED, "Quá nhiều yêu cầu. Vui lòng thử lại sau.", status_code=429)
    try:
        notification, created = create_medication_reminder(user_id, await _json_body(request))
    except ValueError as exc:
        return fastapi_api_error(ErrorCode.VALIDATION_ERROR, str(exc), status_code=400)
    return JSONResponse(
        content={"success": True, "created": created, "notification": notification, "unread_count": unread_count(user_id)},
        status_code=201 if created else 200,
    )


@router.post("/read", summary="Đánh dấu đã đọc từng thông báo hoặc tất cả")
async def mark_notifications_read_endpoint(request: Request):
    user_id = require_authenticated_user(request)
    data = await _json_body(request)
    mark_all = data.get("all") is True
    ids = data.get("ids") if isinstance(data.get("ids"), list) else []
    if not mark_all and not ids:
        return fastapi_api_error(ErrorCode.VALIDATION_ERROR, "Thiếu danh sách thông báo cần đánh dấu.", status_code=400)
    updated = mark_read(user_id, ids=ids, mark_all=mark_all)
    return JSONResponse(content={"success": True, "updated": updated, "unread_count": unread_count(user_id)})
