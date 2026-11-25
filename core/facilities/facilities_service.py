"""
core/facilities_service.py
Dịch vụ tra cứu và lọc dữ liệu Cơ sở Y tế (CSKCB) tích hợp đa khu vực (TP.HCM, Hà Nội).
Dùng chung giữa FastAPI native routers và Flask legacy handlers.
"""
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.shared.settings import get_settings

logger = logging.getLogger("FacilitiesService")

_facilities_lock = threading.Lock()
_facilities_cache: Optional[List[Dict[str, Any]]] = None


def get_facilities_data_path() -> Path:
    """Trả về đường dẫn tệp dữ liệu cơ sở y tế chuẩn hóa (TP.HCM) cho tính tương thích ngược."""
    settings = get_settings()
    file_path = settings.paths.data_dir / "CSKCB_Data" / "danh_sach_co_so_kcb_normalized.json"
    if not file_path.exists():
        fallback = Path(__file__).resolve().parents[2] / "data" / "CSKCB_Data" / "danh_sach_co_so_kcb_normalized.json"
        if fallback.exists():
            return fallback
    return file_path


def get_facilities_data_paths() -> List[Path]:
    """Trả về danh sách đường dẫn các tệp dữ liệu cơ sở y tế chuẩn hóa (TP.HCM và Hà Nội)."""
    settings = get_settings()
    base_dir = settings.paths.data_dir / "CSKCB_Data"
    if not base_dir.exists():
        base_dir = Path(__file__).resolve().parents[2] / "data" / "CSKCB_Data"

    paths: List[Path] = []
    # 1. Cơ sở y tế TP.HCM
    hcm_file = base_dir / "danh_sach_co_so_kcb_normalized.json"
    if hcm_file.exists():
        paths.append(hcm_file)

    # 2. Cơ sở y tế Hà Nội
    hn_file = base_dir / "danh_sach_co_so_kcb_hanoi_normalized.json"
    if hn_file.exists():
        paths.append(hn_file)

    return paths


def load_facilities_data() -> List[Dict[str, Any]]:
    """Tải và lưu đệm dữ liệu cơ sở y tế (TP.HCM + Hà Nội) một cách an toàn đa luồng."""
    global _facilities_cache
    if _facilities_cache is not None:
        return _facilities_cache

    with _facilities_lock:
        if _facilities_cache is not None:
            return _facilities_cache

        combined: List[Dict[str, Any]] = []
        data_files = get_facilities_data_paths()
        for data_file in data_files:
            try:
                with open(data_file, "r", encoding="utf-8") as f:
                    items = json.load(f)
                    if isinstance(items, list):
                        combined.extend(items)
                        logger.info("Đã nạp %d cơ sở y tế từ %s", len(items), data_file.name)
            except Exception as e:
                logger.error("Lỗi khi đọc file dữ liệu cơ sở y tế (%s): %s", data_file, e)

        _facilities_cache = combined
        logger.info("Tổng cộng đã nạp %d cơ sở y tế (TP.HCM + Hà Nội) vào bộ nhớ đệm.", len(_facilities_cache))

    return _facilities_cache or []


def invalidate_facilities_cache() -> None:
    """Xóa bộ đệm dữ liệu cơ sở y tế (chủ yếu dùng cho test hoặc khi cập nhật file)."""
    global _facilities_cache
    with _facilities_lock:
        _facilities_cache = None


def _matches_region(tinh_tp_field: str, target_region: str) -> bool:
    """Kiểm tra một cơ sở y tế có thuộc khu vực địa lý mục tiêu không."""
    if not target_region or target_region.lower() == "all":
        return True
    norm_val = (tinh_tp_field or "").lower()
    target = target_region.lower()
    if target in ("hcm", "tp.hcm", "tp hcm", "hồ chí minh", "tp hồ chí minh", "tp. hồ chí minh"):
        return "hồ chí minh" in norm_val or "thủ đức" in norm_val
    elif target in ("hn", "hanoi", "hà nội", "tp hà nội", "tp. hà nội"):
        return "hà nội" in norm_val
    return target in norm_val


def get_facilities(
    page: int = 1,
    limit: int = 12,
    search: str = "",
    loai_hinh: str = "",
    chuyen_khoa: str = "",
    quan_huyen: str = "",
    tinh_tp: str = "",
    region: str = ""
) -> Dict[str, Any]:
    """
    Tra cứu danh sách cơ sở y tế có phân trang và bộ lọc:
    - page: int (1-based, mặc định: 1)
    - limit: int (mặc định: 12, tối đa: 50)
    - search: từ khóa tìm kiếm (tên, địa chỉ, tags)
    - loai_hinh: loại hình cơ sở (Phòng khám, Bệnh viện,...)
    - chuyen_khoa: chuyên khoa (Tai Mũi Họng, Nội tổng hợp,...)
    - quan_huyen: quận huyện (Quận 10, Quận 1, Quận Ba Đình,...)
    - tinh_tp / region: khu vực tỉnh thành (hcm, hanoi, TP Hồ Chí Minh, TP Hà Nội,...)
    """
    data = load_facilities_data()

    safe_page = max(1, page)
    safe_limit = min(50, max(1, limit))
    search_clean = (search or "").strip().lower()
    loai_hinh_clean = (loai_hinh or "").strip()
    chuyen_khoa_clean = (chuyen_khoa or "").strip()
    quan_huyen_clean = (quan_huyen or "").strip()
    tinh_tp_clean = (tinh_tp or region or "").strip()

    filtered = data

    if tinh_tp_clean and tinh_tp_clean.lower() != "all":
        filtered = [x for x in filtered if _matches_region(x.get("tinh_tp") or "", tinh_tp_clean)]

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


def get_facilities_filters(tinh_tp: str = "", region: str = "") -> Dict[str, Any]:
    """Trả về thống kê số lượng loại hình, quận huyện, chuyên khoa và tỉnh thành thực tế."""
    data = load_facilities_data()
    target_reg = (tinh_tp or region or "").strip()

    if target_reg and target_reg.lower() != "all":
        filtered_data = [x for x in data if _matches_region(x.get("tinh_tp") or "", target_reg)]
    else:
        filtered_data = data

    type_counts: Dict[str, int] = {}
    district_counts: Dict[str, int] = {}
    spec_counts: Dict[str, int] = {}
    region_counts: Dict[str, int] = {"TP Hồ Chí Minh": 0, "TP Hà Nội": 0}

    for x in data:
        t_tp = x.get("tinh_tp") or ""
        if "hà nội" in t_tp.lower():
            region_counts["TP Hà Nội"] += 1
        else:
            region_counts["TP Hồ Chí Minh"] += 1

    for x in filtered_data:
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
        "total": len(filtered_data),
        "total_all_regions": len(data),
        "loai_hinh": type_counts,
        "quan_huyen": top_districts,
        "chuyen_khoa": top_specs,
        "tinh_tp": region_counts
    }


def get_facilities_map_markers(tinh_tp: str = "", region: str = "") -> Dict[str, Any]:
    """Trả về dữ liệu tinh gọn của tất cả cơ sở có tọa độ để vẽ markers bản đồ."""
    data = load_facilities_data()
    target_reg = (tinh_tp or region or "").strip()

    if target_reg and target_reg.lower() != "all":
        data = [x for x in data if _matches_region(x.get("tinh_tp") or "", target_reg)]

    markers = []
    for x in data:
        lat = x.get("lat")
        lng = x.get("lng")
        if lat is not None and lng is not None:
            try:
                t_tp = (x.get("tinh_tp") or "").lower()
                reg_code = "hanoi" if "hà nội" in t_tp else "hcm"
                markers.append({
                    "id": str(x.get("id")),
                    "name": x.get("ten_ngan") or x.get("ten"),
                    "type": x.get("loai_hinh") or "",
                    "spec": x.get("chuyen_khoa") or "",
                    "district": x.get("quan_huyen") or "",
                    "region": reg_code,
                    "address": x.get("dia_chi_hien_thi_tren_web") or x.get("dia_chi") or "",
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
