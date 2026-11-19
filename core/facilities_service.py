"""
core/facilities_service.py
Dịch vụ tra cứu và lọc dữ liệu Cơ sở Y tế (CSKCB).
Dùng chung giữa FastAPI native routers và Flask legacy handlers.
"""
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.settings import get_settings

logger = logging.getLogger("FacilitiesService")

_facilities_lock = threading.Lock()
_facilities_cache: Optional[List[Dict[str, Any]]] = None


def get_facilities_data_path() -> Path:
    """Trả về đường dẫn tệp dữ liệu cơ sở y tế chuẩn hóa."""
    settings = get_settings()
    file_path = settings.paths.data_dir / "CSKCB_Data" / "danh_sach_co_so_kcb_normalized.json"
    if not file_path.exists():
        # Fallback vị trí tương đối thư mục project
        fallback = Path(__file__).resolve().parent.parent / "data" / "CSKCB_Data" / "danh_sach_co_so_kcb_normalized.json"
        if fallback.exists():
            return fallback
    return file_path


def load_facilities_data() -> List[Dict[str, Any]]:
    """Tải và lưu đệm dữ liệu cơ sở y tế một cách an toàn đa luồng."""
    global _facilities_cache
    if _facilities_cache is not None:
        return _facilities_cache

    with _facilities_lock:
        if _facilities_cache is not None:
            return _facilities_cache

        data_file = get_facilities_data_path()
        if data_file.exists():
            try:
                with open(data_file, "r", encoding="utf-8") as f:
                    _facilities_cache = json.load(f)
                    logger.info("Đã nạp %d cơ sở y tế vào bộ nhớ đệm.", len(_facilities_cache or []))
            except Exception as e:
                logger.error("Lỗi khi đọc file dữ liệu cơ sở y tế (%s): %s", data_file, e)
                _facilities_cache = []
        else:
            logger.warning("File cơ sở y tế không tồn tại tại: %s", data_file)
            _facilities_cache = []

    return _facilities_cache or []


def invalidate_facilities_cache() -> None:
    """Xóa bộ đệm dữ liệu cơ sở y tế (chủ yếu dùng cho test hoặc khi cập nhật file)."""
    global _facilities_cache
    with _facilities_lock:
        _facilities_cache = None


def get_facilities(
    page: int = 1,
    limit: int = 12,
    search: str = "",
    loai_hinh: str = "",
    chuyen_khoa: str = "",
    quan_huyen: str = ""
) -> Dict[str, Any]:
    """
    Tra cứu danh sách cơ sở y tế có phân trang và bộ lọc:
    - page: int (1-based, mặc định: 1)
    - limit: int (mặc định: 12, tối đa: 50)
    - search: từ khóa tìm kiếm (tên, địa chỉ, tags)
    - loai_hinh: loại hình cơ sở (Phòng khám, Bệnh viện,...)
    - chuyen_khoa: chuyên khoa (Tai Mũi Họng, Nội tổng hợp,...)
    - quan_huyen: quận huyện (Quận 10, Quận 1,...)
    """
    data = load_facilities_data()

    safe_page = max(1, page)
    safe_limit = min(50, max(1, limit))
    search_clean = (search or "").strip().lower()
    loai_hinh_clean = (loai_hinh or "").strip()
    chuyen_khoa_clean = (chuyen_khoa or "").strip()
    quan_huyen_clean = (quan_huyen or "").strip()

    filtered = data

    if loai_hinh_clean and loai_hinh_clean.lower() != "all":
        target = loai_hinh_clean.lower()
        filtered = [x for x in filtered if target in (x.get("loai_hinh") or "").lower()]

    if chuyen_khoa_clean and chuyen_khoa_clean.lower() != "all":
        target = chuyen_khoa_clean.lower()
        filtered = [x for x in filtered if target in (x.get("chuyen_khoa") or "").lower()]

    if quan_huyen_clean and quan_huyen_clean.lower() != "all":
        target = quan_huyen_clean.lower()
        filtered = [x for x in filtered if target in (x.get("quan_huyen") or "").lower()]

    if search_clean:
        def match_search(item: Dict[str, Any]) -> bool:
            s = search_clean
            ten = (item.get("ten") or "").lower()
            ten_ngan = (item.get("ten_ngan") or "").lower()
            dia_chi = (item.get("dia_chi") or "").lower()
            dia_chi_web = (item.get("dia_chi_hien_thi_tren_web") or "").lower()
            ck = (item.get("chuyen_khoa") or "").lower()
            tags = " ".join(item.get("tags") or []).lower()
            return (s in ten or s in ten_ngan or s in dia_chi or s in dia_chi_web or s in ck or s in tags)

        filtered = [x for x in filtered if match_search(x)]

    total = len(filtered)
    total_pages = max(1, (total + safe_limit - 1) // safe_limit)
    start_idx = (safe_page - 1) * safe_limit
    end_idx = start_idx + safe_limit
    items = filtered[start_idx:end_idx]

    return {
        "success": True,
        "total": total,
        "page": safe_page,
        "limit": safe_limit,
        "total_pages": total_pages,
        "data": items
    }


def get_facilities_filters() -> Dict[str, Any]:
    """Trả về thống kê số lượng loại hình, quận huyện và chuyên khoa thực tế."""
    data = load_facilities_data()

    type_counts: Dict[str, int] = {}
    district_counts: Dict[str, int] = {}
    spec_counts: Dict[str, int] = {}

    for x in data:
        lh = x.get("loai_hinh") or "Khác"
        type_counts[lh] = type_counts.get(lh, 0) + 1

        qh = x.get("quan_huyen") or "Khác"
        district_counts[qh] = district_counts.get(qh, 0) + 1

        ck_str = x.get("chuyen_khoa") or ""
        if ck_str:
            for part in ck_str.split(","):
                p = part.strip()
                if p:
                    spec_counts[p] = spec_counts.get(p, 0) + 1

    top_specs = sorted(spec_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    top_districts = sorted(district_counts.items(), key=lambda x: x[0])

    return {
        "success": True,
        "total": len(data),
        "loai_hinh": type_counts,
        "quan_huyen": top_districts,
        "chuyen_khoa": top_specs
    }


def get_facilities_map_markers() -> Dict[str, Any]:
    """Trả về dữ liệu tinh gọn của tất cả cơ sở có tọa độ để vẽ markers bản đồ."""
    data = load_facilities_data()
    markers = []
    for x in data:
        lat = x.get("lat")
        lng = x.get("lng")
        if lat is not None and lng is not None:
            try:
                markers.append({
                    "id": str(x.get("id")),
                    "name": x.get("ten_ngan") or x.get("ten"),
                    "type": x.get("loai_hinh") or "",
                    "spec": x.get("chuyen_khoa") or "",
                    "address": x.get("dia_chi_hien_thi_tren_web") or x.get("dia_chi") or "",
                    "so_giay_phep": x.get("so_giay_phep") or "",
                    "ngay_cap": x.get("ngay_cap") or "",
                    "lat": float(lat),
                    "lng": float(lng),
                    "link": x.get("link") or ""
                })
            except (ValueError, TypeError):
                continue

    return {
        "success": True,
        "total": len(markers),
        "markers": markers
    }
