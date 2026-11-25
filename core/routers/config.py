"""
core/routers/config.py
FastAPI native router cho cấu hình công khai phục vụ frontend (Maps, client public configs).
"""
import os
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from core.shared.settings import get_settings

router = APIRouter(prefix="/api/config", tags=["0. Cấu hình Hệ thống (System Config)"])


@router.get("/maps", summary="Cấu hình Google Maps API cho frontend")
async def get_maps_config_endpoint():
    """Cung cấp trạng thái và khóa Google Maps API phục vụ bản đồ cơ sở y tế."""
    settings = get_settings()
    key = (settings.security.google_maps_api_key or os.getenv("GOOGLE_MAPS_API_KEY", "") or "").strip()
    return JSONResponse(content={
        "has_key": bool(key),
        "key": key if key else ""
    })
