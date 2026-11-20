"""
tests/test_hanoi_facilities_integration.py
Kiểm thử tích hợp dữ liệu cơ sở y tế Hà Nội và loại bỏ Đà Nẵng.
"""
import pytest
from fastapi.testclient import TestClient
from core.main_fastapi import app
from core.facilities_service import (
    invalidate_facilities_cache,
    load_facilities_data,
    get_facilities,
    get_facilities_filters,
    get_facilities_map_markers
)


@pytest.fixture(autouse=True)
def reset_cache():
    invalidate_facilities_cache()
    yield
    invalidate_facilities_cache()


def test_facilities_data_count():
    """Xác nhận nạp đủ 2144 cơ sở y tế (1505 TP.HCM + 639 Hà Nội)."""
    data = load_facilities_data()
    assert len(data) == 2144, f"Tổng số cơ sở y tế kỳ vọng 2144, thực tế: {len(data)}"
    
    hanoi_count = sum(1 for x in data if "hà nội" in (x.get("tinh_tp") or "").lower())
    assert hanoi_count == 639, f"Cơ sở y tế Hà Nội kỳ vọng 639, thực tế: {hanoi_count}"
    
    hcm_count = sum(1 for x in data if "hồ chí minh" in (x.get("tinh_tp") or "").lower() or "thủ đức" in (x.get("tinh_tp") or "").lower())
    assert hcm_count == 1505, f"Cơ sở y tế TP.HCM kỳ vọng 1505, thực tế: {hcm_count}"


def test_facilities_filter_by_region():
    """Kiểm tra lọc theo tỉnh thành / khu vực qua API service."""
    # Lọc Hà Nội
    hn_res = get_facilities(tinh_tp="hanoi", limit=20)
    assert hn_res["total"] == 639
    assert len(hn_res["data"]) == 20
    for item in hn_res["data"]:
        assert "hà nội" in (item.get("tinh_tp") or "").lower()

    # Lọc TP.HCM
    hcm_res = get_facilities(tinh_tp="hcm", limit=20)
    assert hcm_res["total"] == 1505
    assert len(hcm_res["data"]) == 20
    for item in hcm_res["data"]:
        tinh_tp = (item.get("tinh_tp") or "").lower()
        assert "hồ chí minh" in tinh_tp or "thủ đức" in tinh_tp


def test_facilities_hanoi_districts():
    """Kiểm tra tìm kiếm và lọc quận huyện Hà Nội (ví dụ: Quận Ba Đình, Quận Hoàn Kiếm)."""
    res = get_facilities(tinh_tp="hanoi", quan_huyen="Quận Ba Đình", limit=50)
    assert res["total"] > 0
    for item in res["data"]:
        assert "ba đình" in (item.get("quan_huyen") or "").lower()


def test_facilities_map_markers_metadata():
    """Kiểm tra markers bản đồ có đủ tọa độ và tag khu vực 'hcm'/'hanoi'."""
    markers_res = get_facilities_map_markers()
    assert markers_res["total"] == 2144
    
    regions = set(m.get("region") for m in markers_res["markers"])
    assert regions == {"hcm", "hanoi"}, f"Kỳ vọng chỉ có hcm và hanoi, thực tế: {regions}"
    assert "danang" not in regions


def test_fastapi_hanoi_endpoint():
    """Kiểm tra endpoint FastAPI /api/facilities hỗ trợ query param tinh_tp."""
    client = TestClient(app)
    
    # Query Hà Nội
    res = client.get("/api/facilities?tinh_tp=hanoi&limit=10")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["total"] == 639
    assert len(body["data"]) == 10
    
    # Filters thống kê
    res_filters = client.get("/api/facilities/filters")
    assert res_filters.status_code == 200
    filters_data = res_filters.json()
    assert "tinh_tp" in filters_data
    assert filters_data["tinh_tp"]["TP Hà Nội"] == 639
    assert filters_data["tinh_tp"]["TP Hồ Chí Minh"] == 1505
