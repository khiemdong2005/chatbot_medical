"""
core/routers/appointments.py
FastAPI native router cho hệ thống Đặt lịch hẹn khám cơ sở y tế (Medical Appointments).
Bảo vệ bằng session authentication và kiểm tra tính toàn vẹn giao dịch.
"""
from typing import Any, Dict
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from core.routers.deps import require_authenticated_user
from core.facilities.appointment_service import (
    get_user_appointments,
    create_user_appointment,
    delete_user_appointment
)
from core.shared.api_errors import fastapi_api_error, ErrorCode

router = APIRouter(prefix="/api/appointments", tags=["3. Đặt lịch khám (Appointments)"])


@router.get("", summary="Lấy danh sách các lịch hẹn khám của tài khoản")
@router.get("/", include_in_schema=False)
async def get_appointments_endpoint(request: Request):
    """Lấy toàn bộ lịch hẹn khám của tài khoản hiện tại."""
    user_id = require_authenticated_user(request)
    appts = get_user_appointments(user_id)
    return JSONResponse(content={
        "status": "success",
        "appointments": appts
    })


@router.post("", summary="Tạo mới lịch hẹn khám chữa bệnh")
@router.post("/", include_in_schema=False)
async def create_appointment_endpoint(request: Request):
    """Tiếp nhận thông tin và lưu trữ lịch hẹn khám mới."""
    user_id = require_authenticated_user(request)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    success, result_payload, status_code = create_user_appointment(user_id, payload)
    if not success:
        code = ErrorCode.VALIDATION_ERROR if status_code == 400 else ErrorCode.PERSISTENCE_ERROR
        return fastapi_api_error(code, result_payload.get("error", "Lỗi tạo lịch hẹn."), status_code=status_code)

    return JSONResponse(content=result_payload, status_code=status_code)


@router.delete("/{appt_id}", summary="Hủy một lịch hẹn khám")
async def delete_appointment_endpoint(request: Request, appt_id: int):
    """Hủy lịch hẹn theo ID thuộc sở hữu của người dùng hiện tại."""
    user_id = require_authenticated_user(request)
    success, result_payload, status_code = delete_user_appointment(user_id, appt_id)

    if not success:
        code = ErrorCode.NOT_FOUND if status_code == 404 else ErrorCode.PERSISTENCE_ERROR
        return fastapi_api_error(code, result_payload.get("error", "Không thể hủy lịch hẹn."), status_code=status_code)

    return JSONResponse(content=result_payload, status_code=status_code)
