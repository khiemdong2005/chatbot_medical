"""
core/routers/facilities.py
FastAPI native router cho danh mục Cơ sở Y tế, Bộ lọc và Bản đồ CSKCB (TP.HCM, Hà Nội).
"""
from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from core.facilities_service import (
    get_facilities,
    get_facilities_filters,
    get_facilities_map_markers
)

router = APIRouter(prefix="/api/facilities", tags=["2. Cơ sở Y tế (Facilities)"])


@router.get("", summary="Danh sách cơ sở y tế (Phân trang & Lọc)")
@router.get("/", include_in_schema=False)
async def list_facilities_endpoint(
    page: int = Query(1, ge=1, description="Số thứ tự trang (1-based)"),
    limit: int = Query(12, ge=1, le=50, description="Số lượng mục trên mỗi trang"),
    search: Optional[str] = Query("", description="Từ khóa tìm kiếm (tên, địa chỉ, chuyên khoa)"),
    loai_hinh: Optional[str] = Query("", description="Loại hình cơ sở (Bệnh viện, Phòng khám,...)"),
    chuyen_khoa: Optional[str] = Query("", description="Chuyên khoa"),
    quan_huyen: Optional[str] = Query("", description="Quận / Huyện"),
    tinh_tp: Optional[str] = Query("", description="Tỉnh / Thành phố (TP Hồ Chí Minh, TP Hà Nội, hcm, hanoi)"),
    region: Optional[str] = Query("", description="Khu vực địa lý (hcm, hanoi)")
):
    """Lấy danh sách các cơ sở khám chữa bệnh với bộ lọc và phân trang chuẩn xác."""
    result = get_facilities(
        page=page,
        limit=limit,
        search=search or "",
        loai_hinh=loai_hinh or "",
        chuyen_khoa=chuyen_khoa or "",
        quan_huyen=quan_huyen or "",
        tinh_tp=tinh_tp or "",
        region=region or ""
    )
    return JSONResponse(content=result)


@router.get("/filters", summary="Thống kê các tiêu chí bộ lọc cơ sở y tế")
async def facilities_filters_endpoint(
    tinh_tp: Optional[str] = Query("", description="Lọc thống kê theo Tỉnh/TP"),
    region: Optional[str] = Query("", description="Lọc thống kê theo khu vực (hcm, hanoi)")
):
    """Trả về thống kê số lượng loại hình, quận huyện và chuyên khoa phục vụ giao diện lọc."""
    result = get_facilities_filters(tinh_tp=tinh_tp or "", region=region or "")
    return JSONResponse(content=result)


@router.get("/map-markers", summary="Dữ liệu tọa độ Markers trên bản đồ y tế")
async def facilities_map_markers_endpoint(
    tinh_tp: Optional[str] = Query("", description="Lọc markers theo Tỉnh/TP"),
    region: Optional[str] = Query("", description="Lọc markers theo khu vực (hcm, hanoi)")
):
    """Trả về danh sách tinh gọn các cơ sở y tế có tọa độ GPS để vẽ marker lên bản đồ."""
    result = get_facilities_map_markers(tinh_tp=tinh_tp or "", region=region or "")
    return JSONResponse(content=result)
