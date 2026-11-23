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
# MEDIMIND CLINICAL AI - CỔNG DỊCH VỤ Y TẾ LÂM SÀNG
# Thiết kế theo tiêu chuẩn Bộ Y Tế & MedlinePlus (NIH Hoa Kỳ)
# ==============================================================

import os
import time
import json
import logging
import uuid
import secrets
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv

# Tải cấu hình môi trường (.env)
load_dotenv()
from core.settings import settings, is_configured_secret

# Nạp cơ sở dữ liệu và các mô hình
from core.models import db, User, MedicalDocument, ClinicalConsultation, init_db
from core.db_utils import commit_or_rollback
from core.otp_service import otp_manager
from core.storage_service import (
    process_secure_upload,
    decode_and_validate_base64_image,
    is_safe_path
)
from core.chat_service import process_clinical_chat, execute_chat_workflow
from core.health_context import validate_chat_request
from core.gemini_service import GeminiMedicalService
from core.prescription_service import get_preset_data
from core.intake_service import intake_service
from core.pipeline_orchestrator import HEADER_FIELDS, REVIEW_FIELDS, finalize_reviewed_document, process_medical_document_pipeline
from core.reconciliation_service import is_plausible_medication_name
from core.api_errors import flask_api_error, ErrorCode
from core.routers.deps import check_flask_admin
from core.network_utils import get_trusted_client_ip, is_request_https
from core.security_headers import get_security_headers
from core.logging_redaction import setup_logging_redaction, redact_sensitive_text

setup_logging_redaction()

logger = logging.getLogger("MediMindApp")


def get_request_client_ip() -> str:
    """Xác định Client IP từ Flask request tuân thủ chính sách Proxy tin cậy (Phase 8.3)."""
    return get_trusted_client_ip(
        request.remote_addr,
        dict(request.headers),
        trust_proxy=settings.security.trust_proxy_headers,
        trusted_proxy_count=settings.security.trusted_proxy_count
    )

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



def valid_birth_date(value, formats=("%d/%m/%Y",)):
    for fmt in formats:
        try:
            if datetime.strptime(value, fmt).strftime(fmt) == value:
                return True
        except ValueError:
            continue
    return False


def _phone_lookup_variants(raw_phone: str):
    digits = "".join(filter(str.isdigit, raw_phone or ""))
    if not digits:
        return []
    variants = [raw_phone.strip(), digits]
    if digits.startswith("84") and len(digits) in (11, 12):
        variants.append("0" + digits[2:])
    elif digits.startswith("0") and len(digits) in (10, 11):
        variants.append("84" + digits[1:])
    # Giữ thứ tự và loại trùng lặp
    return list(dict.fromkeys(v for v in variants if v))


def find_login_user(identifier):
    if "@" in identifier:
        # Prefer the exact spelling for legacy accounts that differ only by case.
        exact = User.query.filter_by(email=identifier).first()
        if exact:
            return exact
        matches = User.query.filter(db.func.lower(User.email) == identifier.lower()).limit(2).all()
        return matches[0] if len(matches) == 1 else None
    phone_variants = _phone_lookup_variants(identifier)
    if not phone_variants:
        return None
    pseudo_emails = [f"{v}@phone.medimind" for v in phone_variants]
    return User.query.filter(
        User.phone_number.in_(phone_variants) | User.email.in_(pseudo_emails)
    ).first()


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
    db_uri = os.getenv("DATABASE_URL") or settings.paths.database_url
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if not str(db_uri).startswith("sqlite"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
            "pool_recycle": 300,
        }
    app.config["JSON_AS_ASCII"] = False
    # Refresh edited templates locally even when the debugger is disabled.
    app.config["TEMPLATES_AUTO_RELOAD"] = not settings.server.is_production

    # Cấu hình Cookie và Thời hạn phiên an toàn bảo vệ Session (Phase 8.2)
    from datetime import timedelta
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=settings.security.session_lifetime_minutes)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = settings.server.is_production or settings.security.session_cookie_secure
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # Giới hạn 16MB chống tràn bộ nhớ DoS (VULN-04)

    @app.before_request
    def validate_csrf_and_origin():
        """Bảo vệ chống tấn công CSRF trên các endpoint thay đổi trạng thái (POST, PUT, DELETE, PATCH)."""
        request._start_time = time.time()
        from core.csrf_protection import validate_csrf_request

        is_valid, error_msg = validate_csrf_request(
            request.method,
            request.headers,
            request.cookies,
            request.host
        )
        if not is_valid:
            return flask_api_error(
                ErrorCode.FORBIDDEN,
                error_msg or "Yêu cầu bị từ chối do vi phạm chính sách bảo vệ CSRF.",
                status_code=403
            )

    @app.after_request
    def apply_security_headers(response):
        """Bơm bộ khiên bảo mật HTTP chống Clickjacking, MIME-Sniffing, XSS & Protocol Downgrade (Phase 8.3)."""
        is_https = is_request_https(
            request.is_secure,
            dict(request.headers),
            trust_proxy=settings.security.trust_proxy_headers
        )
        for k, v in get_security_headers(is_https=is_https).items():
            response.headers[k] = v

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
            status_code=500
        )

    # Thư mục lưu trữ tệp tin mặc định (cho phép ghi đè qua UPLOAD_FOLDER cho môi trường test/deploy)
    default_upload_folder = (
        os.getenv("UPLOAD_FOLDER")
        or os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    )
    app.config["UPLOAD_FOLDER"] = default_upload_folder

    # Ghi đè cấu hình kiểm thử nếu có TRƯỚC KHI init_db
    if test_config:
        app.config.update(test_config)
    elif settings.server.is_production:
        app.config["DEBUG"] = False
        app.debug = False

    # VULN-06 FIX: Warn when SESSION_COOKIE_SECURE=False in a non-development environment.
    # Placed AFTER test_config update so test overrides are respected.
    # This guard does NOT block startup or change .env — warning only.
    _flask_env = (os.getenv("FLASK_ENV") or os.getenv("ENV") or "").lower().strip()
    _is_dev_env = _flask_env in ("development", "dev", "") or settings.server.testing
    _session_secure = app.config.get("SESSION_COOKIE_SECURE", False)
    if not _is_dev_env and not _session_secure and not is_testing:
        logger.warning(
            "CẢNH BÁO BẢO MẬT [VULN-06]: SESSION_COOKIE_SECURE=False trong môi trường non-development! "
            "Session cookie sẽ được gửi qua kết nối HTTP không mã hóa, dễ bị đánh cắp. "
            "Vui lòng thiết lập SESSION_COOKIE_SECURE=true trong file .env khi triển khai với HTTPS. "
            f"[FLASK_ENV={_flask_env or 'unset'}, is_production={settings.server.is_production}]"
        )

    # VULN-12 FIX: Startup warning — OPENROUTER_API_KEY rotation reminder.
    # This is a documentation-only warning (no key rotation performed here).
    # Rotate OPENROUTER_API_KEY, OPENROUTER_CHAT_API_KEY, and OPENROUTER_NUTRITION_API_KEY
    # periodically in the .env file and restart the application.
    _openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    _is_placeholder_key = (
        not is_configured_secret(_openrouter_key)
        or len(_openrouter_key) < 10
    )
    if not is_testing:
        if _is_placeholder_key:
            logger.warning(
                "CẢNH BÁO BẢO MẬT [VULN-12]: OPENROUTER_API_KEY chưa được cấu hình hoặc "
                "đang dùng giá trị placeholder. Vui lòng cấu hình API key hợp lệ trong .env."
            )
        else:
            logger.info(
                "BẢO MẬT [VULN-12]: OPENROUTER_API_KEY đã được cấu hình. "
                "Nhắc nhở: Rotate API key định kỳ (khuyến nghị mỗi 90 ngày) và cập nhật .env."
            )

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Đảm bảo thư mục CSDL tồn tại nếu dùng SQLite cục bộ
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if db_uri and str(db_uri).startswith("sqlite:///"):
        sqlite_file = str(db_uri).replace("sqlite:///", "")
        if sqlite_file and sqlite_file != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(sqlite_file)), exist_ok=True)
            if hasattr(app, "instance_path") and not os.path.isabs(sqlite_file):
                os.makedirs(os.path.dirname(os.path.abspath(os.path.join(app.instance_path, sqlite_file))), exist_ok=True)

    # Khởi tạo cơ sở dữ liệu an toàn theo đúng URI đã cấu hình
    init_db(app)

    # Khởi tạo dịch vụ trí tuệ nhân tạo Gemini
    gemini_service = GeminiMedicalService()


    # ==============================================================
    # ĐĂNG KÝ CÁC PHÂN KHU ROUTE THEO TÍNH NĂNG (MODULAR ROUTES)
    # ==============================================================
    from routes.auth_routes import register_auth_routes
    from routes.chat_routes import register_chat_routes
    from routes.ocr_routes import register_ocr_routes
    from routes.nutrition_routes import register_nutrition_routes
    from routes.facilities_routes import register_facilities_routes

    register_auth_routes(
        app,
        get_request_client_ip=get_request_client_ip,
        valid_birth_date=valid_birth_date,
        find_login_user=find_login_user,
    )
    register_chat_routes(
        app,
        gemini_service=gemini_service,
        get_request_client_ip=get_request_client_ip,
    )
    register_ocr_routes(app, default_upload_folder=default_upload_folder)
    register_nutrition_routes(app)
    register_facilities_routes(app)

    # ==============================================================
    # GIAO DIỆN NGƯỜI DÙNG WEB (UI)
    # ==============================================================

    @app.get("/.well-known/security.txt")
    def security_txt():
        """Chính sách tiếp nhận báo cáo lỗ hổng bảo mật chuẩn RFC 9116."""
        from flask import Response
        body = (
            "Contact: mailto:security@medimind.local\n"
            "Expires: 2027-12-31T23:59:59.000Z\n"
            "Preferred-Languages: vi, en\n"
        )
        return Response(body, status=200, mimetype="text/plain; charset=utf-8")

    @app.get("/openapi.json")
    def api_spec():
        if settings.server.is_production:
            return jsonify({"error": "Not Found"}), 404
        import re

        paths = {}
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/api/"):
                continue
            path = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", rule.rule)
            parameters = [
                {"name": name, "in": "path", "required": True,
                 "schema": {"type": "integer" if f"<int:{name}>" in rule.rule else "string"}}
                for name in sorted(rule.arguments)
            ]
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                paths.setdefault(path, {})[method.lower()] = {
                    "tags": [path.split("/")[2]],
                    "summary": (app.view_functions[rule.endpoint].__doc__ or rule.endpoint).strip().splitlines()[0],
                    "parameters": parameters,
                    "responses": {"default": {"description": "Phản hồi từ API"}},
                }
        return jsonify(openapi="3.0.3", info={"title": "MediMind Flask API", "version": "1"}, paths=paths)

    @app.get("/docs")
    def api_docs():
        if settings.server.is_production:
            return jsonify({"error": "Not Found"}), 404
        return render_template("api_docs.html", paths=api_spec().get_json()["paths"])


    @app.route("/favicon.ico")
    def favicon():
        """Biểu tượng trang web giúp tránh lỗi 404 trên trình duyệt."""
        from flask import send_from_directory
        return send_from_directory(
            os.path.join(app.root_path, "static", "images"),
            "floating-launcher-reference.png",
            mimetype="image/png",
        )

    @app.route("/")
    def index():
        """Trang chủ ứng dụng y tế MediMind."""
        raw_maps_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
        google_maps_api_key = raw_maps_key if is_configured_secret(raw_maps_key) else ""
        return render_template("index.html", google_maps_api_key=google_maps_api_key)

    @app.route("/health")
    def health_check():
        return jsonify({"status": "ok"})

    @app.route("/ready")
    def readiness_check():
        from core.rag_service import medical_rag_service
        from core.circuit_breaker import gemini_circuit_breaker
        rag_ready = medical_rag_service.is_available()
        cb_status = gemini_circuit_breaker.get_status()
        cb_state = cb_status.get("state", "CLOSED")
        gemini_status = "degraded" if cb_state == "OPEN" else "ready"
        rag_status = "ready" if rag_ready else "not_ready"
        if not rag_ready:
            overall = "not_ready"
            code = 503
        elif cb_state == "OPEN":
            overall = "degraded"
            code = 200
        else:
            overall = "ready"
            code = 200
        return jsonify({
            "status": overall,
            "rag": rag_status,
            "gemini": gemini_status,
            "circuit_breaker": cb_state
        }), code

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
    from core.intake_service import set_flask_app
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
