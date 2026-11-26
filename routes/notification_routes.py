"""In-app notification (bell) routes."""

from flask import jsonify, request, session


def register_notification_routes(app):
    @app.route("/api/notifications", methods=["GET"])
    def list_user_notifications():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập.", "notifications": [], "unread_count": 0}), 401
        from core.shared.notification_service import list_notifications
        limit = request.args.get("limit", 30, type=int)
        result = list_notifications(user_id, limit=limit)
        return jsonify({"success": True, **result}), 200

    @app.route("/api/notifications", methods=["POST"])
    def create_user_notification():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập."}), 401
        from core.auth.rate_limit_service import rate_limit_service
        if not rate_limit_service.backend.check_and_increment(f"notif_create:{user_id}", max_requests=60, window_seconds=3600):
            return jsonify({"success": False, "error": "Quá nhiều yêu cầu. Vui lòng thử lại sau."}), 429
        from core.shared.notification_service import create_medication_reminder, unread_count
        try:
            notification, created = create_medication_reminder(user_id, request.get_json(silent=True) or {})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        return jsonify({
            "success": True,
            "created": created,
            "notification": notification,
            "unread_count": unread_count(user_id),
        }), (201 if created else 200)

    @app.route("/api/notifications/read", methods=["POST"])
    def mark_user_notifications_read():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập."}), 401
        data = request.get_json(silent=True) or {}
        mark_all = data.get("all") is True
        ids = data.get("ids") if isinstance(data.get("ids"), list) else []
        if not mark_all and not ids:
            return jsonify({"success": False, "error": "Thiếu danh sách thông báo cần đánh dấu."}), 400
        from core.shared.notification_service import mark_read, unread_count
        updated = mark_read(user_id, ids=ids, mark_all=mark_all)
        return jsonify({"success": True, "updated": updated, "unread_count": unread_count(user_id)}), 200
