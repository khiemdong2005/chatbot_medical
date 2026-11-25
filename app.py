import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==============================================================
# MEDIMIND CLINICAL AI - CỔNG DỊCH VỤ Y TẾ LÂM SÀNG (Thin Entrypoint)
# Hybrid Structure 1.4: Entrypoint chỉ bootstrap, middleware & gắn routes/
# ==============================================================

from datetime import timedelta
import logging
import os
import time

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

# Tải cấu hình môi trường (.env)
load_dotenv()

from core.ai.gemini_service import GeminiMedicalService
from core.auth.security_headers import get_security_headers
from core.chat.chat_service import process_clinical_chat
from core.routers.deps import check_flask_admin
from core.shared.api_errors import ErrorCode, flask_api_error
from core.shared.db_utils import commit_or_rollback
from core.shared.logging_redaction import redact_sensitive_text, setup_logging_redaction
from core.shared.models import User, db, init_db
from core.shared.network_utils import is_request_https
from core.shared.settings import settings
from routes import register_all_routes
from routes.shared_helpers import (
    find_login_user,
    get_request_client_ip,
    start_authenticated_session as _start_authenticated_session,
    valid_birth_date,
)

__all__ = [
    "ServerMaskMiddleware",
    "app",
    "commit_or_rollback",
    "create_app",
    "find_login_user",
    "get_request_client_ip",
    "process_clinical_chat",
    "valid_birth_date",
    "_start_authenticated_session",
]

setup_logging_redaction()

logger = logging.getLogger("MediMindApp")


class ServerMaskMiddleware:
    """WSGI Middleware ghi đè header Server để che giấu thông tin công nghệ nền tảng."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            clean_headers = [(k, v) for k, v in headers if k.lower() != 'server']
            clean_headers.append(('Server', 'MediMind-Clinical-Engine'))
            return start_response(status, clean_headers, exc_info)

        return self.wsgi_app(environ, custom_start_response)


def create_app(test_config=None):
    """
    Application Factory Pattern:
    Khởi tạo ứng dụng Flask với cấu hình tùy biến linh hoạt.
    Khi kiểm thử, nạp test_config (SQLite in-memory) TRƯỚC KHI kết nối CSDL,
    bảo vệ 100% dữ liệu thật khỏi nguy cơ bị ghi đè hoặc drop_all.
    """
    app = Flask(__name__)

    is_testing = bool(test_config and test_config.get("TESTING"))
    app.secret_key = settings.get_effective_secret_key(testing=is_testing)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL") or settings.paths.database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JSON_AS_ASCII"] = False
    app.config["TEMPLATES_AUTO_RELOAD"] = not settings.server.is_production

    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=settings.security.session_lifetime_minutes)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = settings.server.is_production or settings.security.session_cookie_secure
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    @app.before_request
    def validate_csrf_and_origin():
        """Bảo vệ chống tấn công CSRF trên các endpoint thay đổi trạng thái (POST, PUT, DELETE, PATCH)."""
        request._start_time = time.time()
        from core.auth.csrf_protection import validate_csrf_request

        is_valid, error_msg = validate_csrf_request(
            request.method,
            request.headers,
            request.cookies,
            request.host,
        )
        if not is_valid:
            return flask_api_error(
                ErrorCode.FORBIDDEN,
                error_msg or "Yêu cầu bị từ chối do vi phạm chính sách bảo vệ CSRF.",
                status_code=403,
            )

    @app.after_request
    def apply_security_headers(response):
        """Bơm bộ khiên bảo mật HTTP chống Clickjacking, MIME-Sniffing, XSS & Protocol Downgrade (Phase 8.3)."""
        is_https = is_request_https(
            request.is_secure,
            dict(request.headers),
            trust_proxy=settings.security.trust_proxy_headers,
        )
        from core.auth.security_headers import is_sensitive_api_path
        for k, v in get_security_headers(is_https=is_https).items():
            response.headers[k] = v
        if is_sensitive_api_path(request.path):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Pragma"] = "no-cache"

        if hasattr(request, "_start_time"):
            duration = time.time() - request._start_time
            from core.observability import record_http_metrics
            record_http_metrics(request.method, request.path, response.status_code, duration)

        return response

    @app.errorhandler(500)
    @app.errorhandler(Exception)
    def handle_unhandled_exception(e):
        """Bắt và chuẩn hóa toàn bộ lỗi ngoại lệ nội bộ, ngăn ngừa lộ lọt stack trace hay thông tin nhạy cảm."""
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        logger.error("Unhandled Flask exception (%s): %s", type(e).__name__, redact_sensitive_text(str(e)))
        return flask_api_error(
            ErrorCode.INTERNAL_ERROR,
            "Đã có lỗi hệ thống xảy ra. Vui lòng thử lại sau.",
            status_code=500,
        )

    default_upload_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    app.config["UPLOAD_FOLDER"] = default_upload_folder

    if test_config:
        app.config.update(test_config)
    elif settings.server.is_production:
        app.config["DEBUG"] = False
        app.debug = False

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if db_uri and str(db_uri).startswith("sqlite:///"):
        sqlite_file = str(db_uri).replace("sqlite:///", "")
        if sqlite_file and sqlite_file != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(sqlite_file)), exist_ok=True)
            if hasattr(app, "instance_path") and not os.path.isabs(sqlite_file):
                os.makedirs(os.path.dirname(os.path.abspath(os.path.join(app.instance_path, sqlite_file))), exist_ok=True)

    init_db(app)

    @app.context_processor
    def inject_current_user():
        """Tiêm thông tin người dùng hiện tại vào toàn bộ Jinja2 templates dùng chung header."""
        user_id = session.get("user_id")
        if not user_id:
            return {"current_user": None, "user": None}
        current = db.session.get(User, user_id)
        if not current:
            return {"current_user": None, "user": None}
        user_data = current.to_dict()
        return {"current_user": user_data, "user": user_data}

    gemini_service = GeminiMedicalService()

    # Đăng ký toàn bộ tầng routes/ theo kiến trúc Hybrid 1.4
    register_all_routes(app, gemini_service)

    @app.route("/api/system/metrics", methods=["GET"])
    def get_system_metrics():
        err = check_flask_admin()
        if err:
            return err
        from core.observability import metrics_collector
        if not metrics_collector.is_enabled():
            return jsonify({"error": "Metrics endpoint is disabled"}), 403
        return jsonify(metrics_collector.get_summary())

    @app.route("/api/system/metrics/reset", methods=["POST"])
    def reset_system_metrics():
        err = check_flask_admin()
        if err:
            return err
        from core.observability import metrics_collector
        if not metrics_collector.is_enabled():
            return jsonify({"error": "Metrics endpoint is disabled"}), 403
        metrics_collector.reset()
        return jsonify({"status": "reset_successful"})

    @app.route("/system")
    @app.route("/admin/system")
    def system_dashboard():
        err = check_flask_admin()
        if err:
            return err
        return render_template("system_dashboard.html")

    @app.route("/metrics", methods=["GET"])
    def prometheus_metrics():
        """Cổng Scraping chuẩn OpenMetrics cho Prometheus TSDB & Grafana."""
        import ipaddress
        from core.observability import get_prometheus_metrics_response
        client_ip = (request.remote_addr or "").strip()
        expected_key = os.getenv("PROMETHEUS_SCRAPE_KEY", os.getenv("ADMIN_MONITORING_KEY", ""))
        req_key = request.headers.get("X-Metrics-Key") or request.headers.get("X-Admin-Key") or request.args.get("key")
        is_internal = client_ip in ("localhost", "testclient")
        if not is_internal and client_ip:
            try:
                addr = ipaddress.ip_address(client_ip)
                is_internal = any(
                    addr in net for net in (
                        ipaddress.ip_network("127.0.0.0/8"),
                        ipaddress.ip_network("::1/128"),
                        ipaddress.ip_network("10.0.0.0/8"),
                        ipaddress.ip_network("172.16.0.0/12"),
                        ipaddress.ip_network("192.168.0.0/16"),
                    )
                )
            except ValueError:
                is_internal = False
        is_auth = bool(expected_key and req_key == expected_key)
        if not is_internal and not is_auth:
            return jsonify({
                "error": "Forbidden: Metrics endpoint is restricted to Prometheus scrapers."
            }), 403
        return get_prometheus_metrics_response()

    app.wsgi_app = ServerMaskMiddleware(app.wsgi_app)
    return app


# Export singleton app instance for WSGI / CLI
app = create_app()
try:
    from core.chat.intake_service import set_flask_app
    set_flask_app(app)
except Exception:
    pass

if __name__ == "__main__":
    try:
        from werkzeug.serving import WSGIRequestHandler
        WSGIRequestHandler.server_version = "MediMind-Clinical-Engine"
        WSGIRequestHandler.sys_version = ""
    except Exception:
        pass
    flask_debug = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true")
    port = int(os.getenv("PORT", 8000))
    print("==================================================")
    print("  MEDIMIND CLINICAL AI - HỆ THỐNG Y TẾ SỐ ĐANG CHẠY")
    print(f"  Giao diện Web: http://127.0.0.1:{port}")
    print(f"  Chế độ Debug: {flask_debug}")
    print("  Chuẩn kiến trúc: Phân tầng lâm sàng an toàn")
    print("==================================================")
    default_host = "127.0.0.1" if flask_debug else "0.0.0.0"

    bind_host = os.getenv("HOST", default_host)

    app.run(host=bind_host, port=port, debug=flask_debug)
