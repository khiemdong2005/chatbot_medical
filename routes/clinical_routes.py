"""Clinical summary, consultations and medical appointments routes."""

from flask import jsonify, request, session


def register_clinical_routes(app):
    # ==============================================================
    # PHIẾU CHUẨN BỊ TRƯỚC KHÁM CHO NGƯỜI DÂN (PRE-VISIT SUMMARY)
    # ==============================================================

    @app.route("/api/clinical-summary", methods=["GET"])
    def clinical_summary():
        """
        Bản tóm tắt trước khám chuẩn 2 phần:
        - Đồng bộ với quy trình Intake Session theo tiêu chí y tế.
        - Trích xuất từ phiên tư vấn thực tế của tài khoản hiện tại.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Vui lòng đăng nhập để xem hồ sơ."}), 401
        conversation_id = request.args.get("conversation_id")
        from core.chat.consultation_service import get_clinical_summary
        _, payload, status_code = get_clinical_summary(user_id, conversation_id=conversation_id)
        return jsonify(payload), status_code

    @app.route("/api/consultations", methods=["GET"])
    def get_consultations():
        """Lấy danh sách các phiên tư vấn đã lưu của tài khoản hiện tại (VULN-05 RBAC)."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem danh sách phiên tư vấn.", "consultations": []}), 401
        from core.chat.consultation_service import get_user_consultations
        consultations = get_user_consultations(user_id)
        return jsonify({"status": "success", "consultations": consultations}), 200

    @app.route("/api/consultations/<int:cid>", methods=["DELETE"])
    def delete_consultation(cid):
        """Xóa một phiên tư vấn theo ID của người dùng."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Vui lòng đăng nhập."}), 401
        from core.chat.consultation_service import delete_user_consultation
        _, payload, status_code = delete_user_consultation(
            user_id=user_id,
            cid=cid,
            guest_token=session.get("guest_token")
        )
        return jsonify(payload), status_code


    # ==============================================================
    # HỆ THỐNG ĐẶT LỊCH HẸN KHÁM CƠ SỞ Y TẾ (APPOINTMENT BOOKING)
    # ==============================================================

    @app.route("/api/appointments", methods=["GET"])
    def get_appointments():
        """Lấy danh sách các lịch hẹn khám của tài khoản đang đăng nhập."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem lịch hẹn khám.", "appointments": []}), 401
        from core.facilities.appointment_service import get_user_appointments
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
        from core.facilities.appointment_service import create_user_appointment
        _, payload, status_code = create_user_appointment(user_id, data)
        return jsonify(payload), status_code

    @app.route("/api/appointments/<int:appt_id>", methods=["DELETE"])
    def delete_appointment(appt_id):
        """Hủy một lịch hẹn khám của người dùng."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập."}), 401
        from core.facilities.appointment_service import delete_user_appointment
        _, payload, status_code = delete_user_appointment(user_id, appt_id)
        return jsonify(payload), status_code

    # ==============================================================
