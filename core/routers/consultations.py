"""
core/routers/consultations.py
FastAPI native router cho danh sách các phiên tư vấn đã lưu (Clinical Consultations).
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from core.routers.deps import require_authenticated_user, extract_request_identity
from core.chat.consultation_service import (
    get_user_consultations,
    get_user_chatbot_sessions,
    delete_user_consultation
)
from core.shared.api_errors import fastapi_api_error, ErrorCode

router = APIRouter(prefix="/api/consultations", tags=["4. Lịch sử Tư vấn (Consultations)"])


@router.get("", summary="Lấy danh sách các phiên tư vấn của tài khoản")
@router.get("/", include_in_schema=False)
async def get_consultations_endpoint(request: Request):
    """Lấy danh sách tối đa 20 phiên tư vấn đã lưu gần nhất và các hội thoại chatbot thực tế của tài khoản."""
    user_id = require_authenticated_user(request)
    consultations = get_user_consultations(user_id)
    chatbot_sessions = get_user_chatbot_sessions(user_id)
    return JSONResponse(content={
        "status": "success",
        "consultations": consultations,
        "chatbot_sessions": chatbot_sessions,
    })


@router.delete("/{cid}", summary="Xóa một phiên tư vấn theo ID")
async def delete_consultation_endpoint(request: Request, cid: int):
    """Xóa một phiên tư vấn thuộc sở hữu của người dùng hiện tại."""
    user_id = require_authenticated_user(request)
    _, guest_token, _ = extract_request_identity(request)

    success, result_payload, status_code = delete_user_consultation(
        user_id=user_id,
        cid=cid,
        guest_token=guest_token
    )

    if not success:
        if status_code == 404:
            code = ErrorCode.NOT_FOUND
        elif status_code == 403:
            code = ErrorCode.FORBIDDEN
        else:
            code = ErrorCode.PERSISTENCE_ERROR
        return fastapi_api_error(code, result_payload.get("error", "Lỗi xóa phiên tư vấn."), status_code=status_code)

    return JSONResponse(content=result_payload, status_code=status_code)
