"""Medical facilities directory, filters, map markers and maps config routes."""

import os

from flask import jsonify, request


def register_facilities_routes(app):
    # ==============================================================
    from core.facilities.facilities_service import (
        load_facilities_data,
        get_facilities as service_get_facilities,
        get_facilities_filters as service_get_facilities_filters,
        get_facilities_map_markers as service_get_facilities_map_markers
    )

    @app.route("/api/facilities", methods=["GET"])
    def get_facilities():
        """
        API danh sách cơ sở y tế có phân trang và bộ lọc:
        - page: int (1-based, default: 1)
        - limit: int (default: 12)
        - search: từ khóa tìm kiếm (tên, địa chỉ, tags)
        - loai_hinh: loại hình cơ sở (Phòng khám, Bệnh viện,...)
        - chuyen_khoa: chuyên khoa (Tai Mũi Họng, Nội tổng hợp,...)
        - quan_huyen: quận huyện (Quận 10, Quận 1,...)
        - tinh_tp / region: khu vực tỉnh thành (hcm, hanoi,...)
        """
        page = max(1, request.args.get("page", 1, type=int))
        limit = min(50, max(1, request.args.get("limit", 12, type=int)))
        search = request.args.get("search", "").strip()
        loai_hinh = request.args.get("loai_hinh", "").strip()
        chuyen_khoa = request.args.get("chuyen_khoa", "").strip()
        quan_huyen = request.args.get("quan_huyen", "").strip()
        tinh_tp = request.args.get("tinh_tp", "").strip() or request.args.get("region", "").strip()

        result = service_get_facilities(
            page=page,
            limit=limit,
            search=search,
            loai_hinh=loai_hinh,
            chuyen_khoa=chuyen_khoa,
            quan_huyen=quan_huyen,
            tinh_tp=tinh_tp
        )
        return jsonify(result)

    @app.route("/api/facilities/filters", methods=["GET"])
    def get_facilities_filters():
        """Trả về thống kê số lượng loại hình, chuyên khoa và quận huyện thực tế."""
        tinh_tp = request.args.get("tinh_tp", "").strip() or request.args.get("region", "").strip()
        return jsonify(service_get_facilities_filters(tinh_tp=tinh_tp))

    @app.route("/api/facilities/map-markers", methods=["GET"])
    def get_facilities_map_markers():
        """Trả về dữ liệu tinh gọn của tất cả cơ sở có tọa độ để vẽ markers lên bản đồ."""
        tinh_tp = request.args.get("tinh_tp", "").strip() or request.args.get("region", "").strip()
        return jsonify(service_get_facilities_map_markers(tinh_tp=tinh_tp))

    @app.route("/api/config/maps", methods=["GET"])
    def get_maps_config():
        """Cung cấp cấu hình Google Maps API cho frontend."""
        from core.shared.settings import get_settings
        settings = get_settings()
        key = (settings.security.google_maps_api_key or os.getenv("GOOGLE_MAPS_API_KEY", "") or "").strip()
        return jsonify({
            "has_key": bool(key),
            "key": key if key else ""
        })

