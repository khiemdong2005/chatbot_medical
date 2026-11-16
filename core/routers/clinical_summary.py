"""
core/routers/clinical_summary.py
FastAPI native router cho Phiếu tóm tắt trước khám lâm sàng (Pre-visit Clinical Summary).
"""
from typing import Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from core.routers.deps import require_authenticated_user
from core.consultation_service import get_clinical_summary
from core.api_errors import fastapi_api_error, ErrorCode

router = APIRouter(prefix="/api/clinical-summary", tags=["5. Hồ sơ Lâm sàng (Clinical Summary)"])


@router.get("", summary="Lấy bản tóm tắt trước khám chuẩn y tế")
@router.get("/", include_in_schema=False)
async def get_clinical_summary_endpoint(
    request: Request,
    conversation_id: Optional[str] = Query(None, description="Mã phiên cuộc trò chuyện cần xem tóm tắt")
):
    """
    Trích xuất bản tóm tắt trước khám từ phiên tư vấn thực tế của tài khoản hiện tại.
    Bảo đảm phân lập dữ liệu người dùng tuyệt đối.
    """
    user_id = require_authenticated_user(request)
    success, result_payload, status_code = get_clinical_summary(
        user_id=user_id,
        conversation_id=conversation_id
    )

    if not success:
        return fastapi_api_error(
            ErrorCode.INTERNAL_ERROR,
            result_payload.get("error", "Lỗi tải hồ sơ tóm tắt lâm sàng."),
            status_code=status_code
        )

    return JSONResponse(content=result_payload, status_code=status_code)
