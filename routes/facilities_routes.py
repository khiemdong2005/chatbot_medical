"""Medical Facilities (CSKCB), Map Markers & Appointment Booking routes."""

import logging
from flask import jsonify, request, session

logger = logging.getLogger("MediMindApp")


def register_facilities_routes(app):
    # ==============================================================
    # HỆ THỐNG ĐẶT LỊCH HẸN KHÁM CƠ SỞ Y TẾ (APPOINTMENT BOOKING)
    # ==============================================================

    @app.route("/api/appointments", methods=["GET"])
    def get_appointments():
        """Lấy danh sách các lịch hẹn khám của tài khoản đang đăng nhập."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem lịch hẹn khám.", "appointments": []}), 401
        from core.appointment_service import get_user_appointments
        appts = get_user_appointments(user_id)
        return jsonify({"status": "success", "appointments": appts}), 200

    @app.route("/api/appointments", methods=["POST"])
    def create_appointment():
        """
        Tiếp nhận và lưu trữ lịch hẹn khám chữa bệnh:
        BẢO MẬT: Bắt buộc phiên đăng nhập hợp lệ (Session User ID).
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập hoặc tạo tài khoản để đặt lịch khám."}), 401
        data = request.get_json(silent=True) or {}
        from core.appointment_service import create_user_appointment
        _, payload, status_code = create_user_appointment(user_id, data)
        return jsonify(payload), status_code

    @app.route("/api/appointments/<int:appt_id>", methods=["DELETE"])
    def delete_appointment(appt_id):
        """Hủy một lịch hẹn khám của người dùng."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập."}), 401
        from core.appointment_service import delete_user_appointment
        _, payload, status_code = delete_user_appointment(user_id, appt_id)
        return jsonify(payload), status_code


    # ==============================================================
    # QUẢN LÝ DỮ LIỆU CƠ SỞ Y TẾ (CSKCB REST API)
    # ==============================================================
    from core.facilities_service import (
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

