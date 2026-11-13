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
from datetime import datetime
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv

# Tải cấu hình môi trường (.env)
load_dotenv()

# Nạp cơ sở dữ liệu và các mô hình
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from core.models import (
    db,
    User,
    AuthIdentity,
    MedicalDocument,
    ClinicalConsultation,
    MedicalAppointment,
    init_db,
    is_synthetic_phone_email,
    extract_phone_from_synthetic_email,
    normalize_email,
    normalize_phone_e164,
    phone_lookup_candidates,
    sync_user_identities,
)
from core.otp_service import otp_manager
from core.storage_service import (
    process_secure_upload,
    decode_and_validate_base64_image,
    is_safe_path
)
from core.chat_service import process_clinical_chat
from core.health_context import validate_chat_request
from core.gemini_service import GeminiMedicalService
from core.prescription_service import get_preset_data, analyze_uploaded_document
from core.intake_service import intake_service
from core.pipeline_orchestrator import HEADER_FIELDS, REVIEW_FIELDS, finalize_reviewed_document, process_medical_document_pipeline
from core.observability import (
    record_http_metrics,
    record_clinical_triage,
    record_ai_latency,
    record_prescription_scan,
    record_security_event,
    get_prometheus_metrics_response,
)

logger = logging.getLogger("MediMindApp")
_DUMMY_PASSWORD_HASH = generate_password_hash("MediMindTimingProtectionConstant2026!")

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


def normalize_login_rate_key(identifier: str) -> str:
    """Chuẩn hóa khóa rate-limit để ngăn vượt rào bằng các biến thể định dạng SĐT/Email."""
    raw = (identifier or "").strip()
    if "@" in raw and not is_synthetic_phone_email(raw):
        return f"login:email:{raw.lower()}"
    norm_phone = extract_phone_from_synthetic_email(raw) if is_synthetic_phone_email(raw) else normalize_phone_e164(raw)
    if norm_phone:
        return f"login:phone:{norm_phone}"
    return f"login:raw:{raw.lower()}"


def find_login_user(identifier):
    """
    Tra cứu người dùng tối ưu qua B-Tree Index (ix_users_email, ix_users_phone_number, ix_auth_identities_provider_subject):
      - Email: tra cứu trực tiếp qua email đã chuẩn hóa lowercase.
      - SĐT: chuẩn hóa E.164 (+84...) và tra cứu trực tiếp qua phone_number (kèm tương thích ngược).
    """
    if not identifier or not isinstance(identifier, str):
        return None
    raw = identifier.strip()
    if not raw:
        return None

    if "@" in raw and not is_synthetic_phone_email(raw):
        norm_em = normalize_email(raw) or raw.lower()
        # 1. Index lookup trực tiếp trên cột email lowercase
        user = User.query.filter_by(email=norm_em).first()
        if user:
            return user
        # 2. Tương thích ngược cho tài khoản cũ chưa lowercase
        if raw != norm_em:
            exact = User.query.filter_by(email=raw).first()
            if exact:
                return exact
        matches = User.query.filter(db.func.lower(User.email) == norm_em).limit(2).all()
        if len(matches) == 1:
            return matches[0]
        # 3. Tra cứu qua bảng liên kết đa định danh auth_identities
        identity = AuthIdentity.query.filter_by(provider="email", provider_subject=norm_em).first()
        return identity.user if identity else None

    # Tra cứu theo Số điện thoại (E.164 + tương thích ngược)
    candidates = phone_lookup_candidates(raw)
    if not candidates:
        return None

    user = User.query.filter(User.phone_number.in_(candidates)).first()
    if user:
        return user

    identity = AuthIdentity.query.filter(
        AuthIdentity.provider == "phone",
        AuthIdentity.provider_subject.in_(candidates)
    ).first()
    if identity and identity.user:
        return identity.user

    # Fallback cuối cho bản ghi synthetic email chưa kịp migrate
    digits = "".join(filter(str.isdigit, raw.split("@")[0]))
    if digits:
        return User.query.filter(
            User.email.in_([f"{digits}@phone.medimind", f"{digits}@phone.medimind.vn"])
        ).first()
    return None


def create_app(test_config=None):
    """
    Application Factory Pattern:
    Khởi tạo ứng dụng Flask với cấu hình tùy biến linh hoạt.
    Khi kiểm thử, nạp test_config (SQLite in-memory) TRƯỚC KHI kết nối CSDL,
    bảo vệ 100% dữ liệu thật khỏi nguy cơ bị ghi đè hoặc drop_all.
    """
    app = Flask(__name__)

    is_prod = os.getenv("FLASK_ENV") == "production" or os.getenv("ENV") == "production"
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        if is_prod and not (test_config and test_config.get("TESTING")):
            raise RuntimeError("Yêu cầu cấu hình SECRET_KEY an toàn trong môi trường Production!")
        # Ponytail: dev fallback using CSPRNG to prevent hardcoded secret forgery
        import secrets
        secret_key = secrets.token_hex(32)
        logger.warning("CẢNH BÁO BẢO MẬT: Không tìm thấy SECRET_KEY trong .env! Đã tự động tạo khóa mật mã ngẫu nhiên cho phiên này.")

    app.secret_key = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///medimind.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }
    app.config["JSON_AS_ASCII"] = False
    # Refresh edited templates locally even when the debugger is disabled.
    app.config["TEMPLATES_AUTO_RELOAD"] = not is_prod

    # Cấu hình Cookie an toàn bảo vệ Session
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = is_prod or (os.getenv("SESSION_COOKIE_SECURE", "false").lower() in ("true", "1"))
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # Giới hạn 16MB chống tràn bộ nhớ DoS (VULN-04)

    @app.before_request
    def record_request_start_time():
        """Đo đạc chính xác thời gian bắt đầu tiếp nhận gói tin (Latency Tracking)."""
        request._start_time = time.time()

    @app.before_request
    def validate_csrf_and_origin():
        """Bảo vệ chống tấn công CSRF trên các endpoint thay đổi trạng thái (POST, PUT, DELETE)."""
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("Origin")
            if origin:
                origin_clean = origin.split("://")[-1].rstrip("/").split(":")[0]
                host_clean = request.host.split(":")[0]
                if origin_clean != host_clean and origin_clean != "localhost" and origin_clean != "127.0.0.1":
                    return jsonify({
                        "error": "Yêu cầu bị từ chối do vi phạm chính sách cùng nguồn gốc (Origin Policy Mismatch)."
                    }), 403

    @app.after_request
    def apply_security_headers(response):
        """Bơm bộ khiên bảo mật HTTP chống Clickjacking, MIME-Sniffing, XSS & Protocol Downgrade."""
        # Che giấu thông tin công nghệ máy chủ (Information Disclosure Hardening)
        response.headers["Server"] = "MediMind-Clinical-Engine"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), payment=()")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")

        # Content-Security-Policy (CSP) bảo vệ giao diện chống XSS và nạp tài nguyên trái phép
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://accounts.google.com/gsi/client https://cdnjs.cloudflare.com https://unpkg.com https://maps.googleapis.com https://maps.gstatic.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://unpkg.com; "
            "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data: blob: https://*.googleusercontent.com https://images.unsplash.com https://unpkg.com https://image.cooky.vn https://monngonmoingay.com https://tile.openstreetmap.org https://*.tile.openstreetmap.org https://maps.googleapis.com https://maps.gstatic.com; "
            "connect-src 'self' https://accounts.google.com/gsi/ https://maps.googleapis.com https://mapsresources-pa.googleapis.com https://maps.gstatic.com; "
            "frame-src 'self' https://accounts.google.com/gsi/ https://www.google.com https://maps.google.com; "
            "base-uri 'self';"
        )
        response.headers.setdefault("Content-Security-Policy", csp_policy)

        if is_prod or request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

        # Ghi nhận chỉ số RED & SRE Golden Signals
        if hasattr(request, "_start_time"):
            duration = time.time() - request._start_time
            record_http_metrics(request.method, request.path, response.status_code, duration)

        return response

    # Thư mục lưu trữ tệp tin mặc định
    default_upload_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    app.config["UPLOAD_FOLDER"] = default_upload_folder

    # Ghi đè cấu hình kiểm thử nếu có TRƯỚC KHI init_db
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Khởi tạo cơ sở dữ liệu an toàn theo đúng URI đã cấu hình
    init_db(app)

    # Khởi tạo dịch vụ trí tuệ nhân tạo Gemini
    gemini_service = GeminiMedicalService()

    # ==============================================================
    # HỆ THỐNG XÁC THỰC DANH TÍNH & PHÂN QUYỀN (RBAC)
    # ==============================================================

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        """
        Đăng nhập hệ thống chuẩn hóa:
          - Email: tra cứu qua email đã chuẩn hóa lowercase.
          - SĐT: chuẩn hóa E.164 (+84...) và tra cứu qua phone_number.
          - Bảo mật: Chống dò tài khoản (Anti-Enumeration) và chống kênh kề thời gian (Timing-Safe Hash Check).
        """
        data = request.get_json(silent=True) or {}
        raw_identifier = (data.get("identifier") or data.get("email") or data.get("phone_number") or "").strip()
        password = data.get("password", "").strip()
        role = data.get("role")

        if not raw_identifier or not password:
            return jsonify({"success": False, "error": "Vui lòng nhập định danh tài khoản và mật khẩu."}), 400

        from core.security_patch import check_otp_attempts, reset_otp_attempts
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
        rate_key = normalize_login_rate_key(raw_identifier)
        if not check_otp_attempts(rate_key, max_attempts=5):
            record_security_event(
                "LOGIN_BRUTE_FORCE_LOCKED",
                severity="CRITICAL",
                client_ip=client_ip,
                identifier=raw_identifier,
                endpoint="/api/auth/login",
                status_code=429,
            )
            return jsonify({
                "success": False,
                "error": "Tài khoản tạm khóa 5 phút do nhập sai mật khẩu quá 5 lần liên tiếp. Vui lòng thử lại sau."
            }), 429

        user = find_login_user(raw_identifier)

        if not user:
            # Thực hiện băm giả để cân bằng thời gian phản hồi, chống Timing Attack & Account Enumeration
            check_password_hash(_DUMMY_PASSWORD_HASH, password)
            record_security_event(
                "LOGIN_FAILED",
                severity="WARNING",
                client_ip=client_ip,
                identifier=raw_identifier,
                endpoint="/api/auth/login",
                status_code=401,
                details={"reason": "unknown_identifier"},
            )
            return jsonify({
                "success": False,
                "error": "Thông tin tài khoản hoặc mật khẩu không chính xác."
            }), 401

        if getattr(user, "account_status", "active") not in (None, "active"):
            return jsonify({
                "success": False,
                "error": "Tài khoản này hiện đang bị khóa hoặc tạm ngưng hoạt động."
            }), 403

        if not user.check_password(password):
            record_security_event(
                "LOGIN_FAILED",
                severity="WARNING",
                client_ip=client_ip,
                identifier=raw_identifier,
                endpoint="/api/auth/login",
                status_code=401,
                details={"reason": "invalid_password", "user_id": user.id},
            )
            return jsonify({
                "success": False,
                "error": "Thông tin tài khoản hoặc mật khẩu không chính xác."
            }), 401

        # Kiểm tra phân quyền truy cập (chỉ kiểm tra sau khi đã xác thực đúng mật khẩu)
        if role and user.role != role:
            return jsonify({
                "success": False,
                "error": f"Tài khoản này không có quyền truy cập vai trò '{role}'."
            }), 403

        # Xóa bộ đếm sai mật khẩu sau khi đăng nhập thành công
        reset_otp_attempts(rate_key)

        # Khởi tạo phiên làm việc (Session)
        session["user_id"] = user.id
        session["user_role"] = user.role

        return jsonify({
            "success": True,
            "message": f"Chào mừng {user.full_name} đã quay trở lại!",
            "user": user.to_dict(),
            "redirect_url": None
        })


    @app.route("/api/auth/register", methods=["POST"])
    def auth_register():
        """
        Đăng ký tài khoản người dùng chuẩn hóa:
          - Đăng ký bằng Email: email = normalized_email, phone_number = E.164 (nếu có) hoặc NULL.
          - Đăng ký bằng SĐT: email = NULL (tuyệt đối không tạo @phone.medimind), phone_number = E.164 (+84...).
          - Luôn tạo tài khoản với vai trò 'patient', đồng bộ bảng auth_identities trong cùng transaction.
        """
        data = request.get_json(silent=True) or {}
        if not app.config.get("TESTING"):
            from core.security_patch import check_otp_attempts
            client_ip = request.remote_addr or "local"
            reg_rate_key = f"register_ip:{client_ip}"
            if not check_otp_attempts(reg_rate_key, max_attempts=10):
                return jsonify({
                    "success": False,
                    "error": "Bạn đã gửi quá nhiều yêu cầu tạo tài khoản từ địa chỉ IP này. Vui lòng thử lại sau 5 phút."
                }), 429

        raw_identifier = (data.get("identifier") or data.get("email") or data.get("phone_number") or "").strip()
        password = (data.get("password") or "").strip()
        full_name = (data.get("full_name") or "").strip() or (data.get("name") or "").strip()
        raw_phone = (data.get("phone_number") or "").strip()
        raw_email = (data.get("email") or "").strip()
        dob = (data.get("dob") or "").strip()
        if dob and not valid_birth_date(dob, ("%d/%m/%Y", "%Y-%m-%d")):
            return jsonify({"success": False, "error": "Ngày sinh phải đúng định dạng DD/MM/YYYY (VD: 15/08/1995)."}), 400
        gender = (data.get("gender") or "").strip() or "Nam"

        role = "patient"

        if not raw_identifier or not password:
            return jsonify({"success": False, "error": "Vui lòng điền đầy đủ Email/SĐT và mật khẩu."}), 400

        if len(password) < 6:
            return jsonify({"success": False, "error": "Mật khẩu phải có tối thiểu 6 ký tự."}), 400

        if not full_name:
            full_name = "Bệnh nhân mới"

        if "@" in raw_identifier and not is_synthetic_phone_email(raw_identifier):
            email = normalize_email(raw_identifier)
            if not email:
                return jsonify({"success": False, "error": "Địa chỉ email không hợp lệ."}), 400
            if raw_phone and raw_phone != raw_identifier:
                phone_number = normalize_phone_e164(raw_phone)
                if not phone_number:
                    return jsonify({"success": False, "error": "Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số)."}), 400
            else:
                phone_number = None
            reg_channel = "email"
        else:
            phone_Input = extract_phone_from_synthetic_email(raw_identifier) if is_synthetic_phone_email(raw_identifier) else raw_identifier
            phone_number = normalize_phone_e164(phone_Input)
            if not phone_number:
                return jsonify({"success": False, "error": "Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số)."}), 400
            # Nếu client đồng thời cung cấp email thật hợp lệ thì lưu, nếu không thì email = None (NULL)
            if raw_email and "@" in raw_email and raw_email != raw_identifier and not is_synthetic_phone_email(raw_email):
                email = normalize_email(raw_email)
                if not email:
                    return jsonify({"success": False, "error": "Địa chỉ email không hợp lệ."}), 400
            else:
                email = None
            reg_channel = "sms"

        # Kiểm tra trùng lặp trên cả email và phone_number đã chuẩn hóa
        if email:
            dup_email = User.query.filter(db.func.lower(User.email) == email).first()
            if dup_email:
                return jsonify({"success": False, "error": "Tài khoản (Email hoặc Số điện thoại) này đã được sử dụng."}), 409
        if phone_number:
            candidates = phone_lookup_candidates(phone_number)
            dup_phone = User.query.filter(User.phone_number.in_(candidates)).first()
            if dup_phone:
                return jsonify({"success": False, "error": "Tài khoản (Email hoặc Số điện thoại) này đã được sử dụng."}), 409

        if not app.config.get("TESTING"):
            if reg_channel == "email":
                verified = otp_manager.is_verified(email, "email", consume=True)
            else:
                verified = False
                for cand in phone_lookup_candidates(phone_number):
                    if otp_manager.is_verified(cand, "sms", consume=True):
                        verified = True
                        break
            if not verified:
                return jsonify({
                    "success": False,
                    "error": "Vui lòng xác thực mã OTP 6 số trước khi tạo tài khoản."
                }), 403

        try:
            new_user = User(
                email=email,
                full_name=full_name,
                role=role,
                account_status="active",
                phone_number=phone_number,
                dob=dob,
                gender=gender,
                license_code=None
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()
            sync_user_identities(new_user, verified=True)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"success": False, "error": "Tài khoản (Email hoặc Số điện thoại) này đã được sử dụng."}), 409

        session["user_id"] = new_user.id
        session["user_role"] = new_user.role

        return jsonify({
            "success": True,
            "message": "Đăng ký tài khoản thành công!",
            "user": new_user.to_dict()
        }), 201


    @app.route("/api/auth/me", methods=["GET"])
    def auth_me():
        """Kiểm tra trạng thái phiên đăng nhập của người dân."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"authenticated": False, "user": None})

        user = db.session.get(User, user_id)
        if not user or getattr(user, "account_status", "active") not in (None, "active"):
            session.clear()
            return jsonify({"authenticated": False, "user": None})

        return jsonify({"authenticated": True, "user": user.to_dict()})


    @app.route("/api/auth/profile", methods=["POST", "PUT"])
    def auth_update_profile():
        """
        Cập nhật thông tin cá nhân:
        BẢO MẬT: Bắt buộc session đăng nhập hợp lệ. Chuẩn hóa SĐT E.164 và Email, đồng bộ bảng auth_identities.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập để cập nhật thông tin."}), 401

        user = db.session.get(User, user_id)
        if not user:
            session.clear()
            return jsonify({"success": False, "error": "Không tìm thấy thông tin tài khoản."}), 404

        data = request.get_json(silent=True) or {}
        full_name = (data.get("name") or "").strip() or (data.get("full_name") or "").strip()
        gender = (data.get("gender") or "").strip()
        dob = (data.get("dob") or "").strip()
        raw_phone = (data.get("phone_number") or "").strip()
        address = (data.get("address") or "").strip()
        bhyt = (data.get("bhyt") or "").strip()
        raw_email = (data.get("email") or "").strip()

        if full_name:
            user.full_name = full_name
        if gender:
            user.gender = gender
        if dob:
            if not valid_birth_date(dob):
                return jsonify({"success": False, "error": "Ngày sinh phải đúng định dạng DD/MM/YYYY (VD: 15/08/1995)."}), 400
            user.dob = dob
        if raw_phone and "•" not in raw_phone:
            norm_phone = normalize_phone_e164(raw_phone)
            if not norm_phone:
                return jsonify({"success": False, "error": "Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số)."}), 400
            candidates = phone_lookup_candidates(norm_phone)
            dup_phone = User.query.filter(
                (User.id != user.id) &
                (User.phone_number.in_(candidates))
            ).first()
            dup_phone_id = AuthIdentity.query.filter(
                (AuthIdentity.user_id != user.id) &
                (AuthIdentity.provider == "phone") &
                (AuthIdentity.provider_subject.in_(candidates))
            ).first()
            if dup_phone or dup_phone_id:
                return jsonify({"success": False, "error": "Số điện thoại này đã được liên kết với một tài khoản khác."}), 409
            user.phone_number = norm_phone
        if "address" in data:
            user.address = address
        if bhyt and "•" not in bhyt:
            user.bhyt = bhyt
        if raw_email and "•" not in raw_email and "@" in raw_email and not is_synthetic_phone_email(raw_email):
            norm_email = normalize_email(raw_email)
            if not norm_email:
                return jsonify({"success": False, "error": "Địa chỉ Email không hợp lệ."}), 400
            dup_email = User.query.filter((User.id != user.id) & (db.func.lower(User.email) == norm_email)).first()
            dup_email_id = AuthIdentity.query.filter(
                (AuthIdentity.user_id != user.id) &
                (AuthIdentity.provider == "email") &
                (AuthIdentity.provider_subject == norm_email)
            ).first()
            if dup_email or dup_email_id:
                return jsonify({"success": False, "error": "Địa chỉ Email này đã được sử dụng bởi một tài khoản khác."}), 409
            user.email = norm_email

        extra_profile = json.loads(user.clinical_profile or "{}")
        profile_fields = (
            "ethnicity", "religion", "province", "ward", "address", "cccd",
            "issue_date", "issue_place", "facility", "valid_from", "valid_to",
            "nationality", "blood_type", "allergies", "height", "weight",
        )
        for field in profile_fields:
            if field in data and isinstance(data[field], str):
                extra_profile[field] = data[field].strip()
        if not extra_profile.get("nationality"):
            extra_profile["nationality"] = "VN"
        user.clinical_profile = json.dumps(extra_profile, ensure_ascii=False)

        try:
            sync_user_identities(user, verified=True)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Lỗi lưu hồ sơ cá nhân: {e}")
            return jsonify({"success": False, "error": "Không thể cập nhật thông tin do xung đột dữ liệu."}), 409

        return jsonify({
            "success": True,
            "message": "Cập nhật thông tin cá nhân thành công!",
            "user": user.to_dict()
        })


    @app.route("/api/auth/change-password", methods=["POST"])
    def auth_change_password():
        """Đổi mật khẩu tài khoản đang đăng nhập."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập để đổi mật khẩu."}), 401

        user = db.session.get(User, user_id)
        if not user:
            session.clear()
            return jsonify({"success": False, "error": "Không tìm thấy tài khoản."}), 404

        data = request.get_json(silent=True) or {}
        current_password = (data.get("current_password") or data.get("old_password") or "").strip()
        new_password = (data.get("new_password") or "").strip()

        if not current_password or not new_password:
            return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ mật khẩu hiện tại và mật khẩu mới."}), 400

        if len(new_password) < 6:
            return jsonify({"success": False, "error": "Mật khẩu mới phải có tối thiểu 6 ký tự."}), 400

        if not user.check_password(current_password):
            return jsonify({"success": False, "error": "Mật khẩu hiện tại không chính xác."}), 401

        user.set_password(new_password)
        db.session.commit()
        return jsonify({"success": True, "message": "Đã thay đổi mật khẩu thành công!"})


    @app.route("/api/auth/forgot-password", methods=["POST"])
    def auth_forgot_password():
        """
        Yêu cầu đặt lại mật khẩu (Forgot Password) qua Email hoặc SĐT:
          - Giới hạn tần suất chống spam.
          - Không tiết lộ sự tồn tại của tài khoản ra thông báo lỗi.
        """
        data = request.get_json(silent=True) or {}
        raw_identifier = (data.get("identifier") or data.get("email") or data.get("phone_number") or "").strip()
        if not raw_identifier:
            return jsonify({"success": False, "error": "Vui lòng nhập Email hoặc Số điện thoại khôi phục."}), 400

        if "@" in raw_identifier:
            norm_id = normalize_email(raw_identifier)
            if not norm_id:
                return jsonify({"success": False, "error": "Địa chỉ email không hợp lệ."}), 400
            channel = "email"
        else:
            norm_id = normalize_phone_e164(raw_identifier)
            if not norm_id:
                return jsonify({"success": False, "error": "Số điện thoại không hợp lệ."}), 400
            channel = "sms"

        user = find_login_user(norm_id)
        if not user:
            # Phản hồi thành công giả định để chống dò tài khoản (Anti-Enumeration)
            return jsonify({
                "success": True,
                "message": "Nếu tài khoản tồn tại, mã xác thực khôi phục mật khẩu đã được gửi.",
                "channel": channel,
                "cooldown": otp_manager.cooldown
            }), 200

        success, msg, cooldown = otp_manager.request_otp(
            identifier=norm_id,
            channel=channel,
            purpose="reset_pwd",
            full_name=user.full_name
        )
        if not success:
            return jsonify({"success": False, "error": msg, "cooldown": cooldown}), 429 if cooldown > 0 else 400

        res_data = {
            "success": True,
            "message": "Nếu tài khoản tồn tại, mã xác thực khôi phục mật khẩu đã được gửi.",
            "channel": channel,
            "cooldown": cooldown
        }
        from core.email_service import email_service
        from core.sms_service import sms_service
        is_real_channel = email_service.is_configured() if channel == "email" else sms_service.is_configured()
        if not is_real_channel and (app.debug or app.config.get("TESTING") or os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true")):
            res_data["dev_otp"] = otp_manager.get_active_code(norm_id, channel)
        return jsonify(res_data), 200


    @app.route("/api/auth/reset-password", methods=["POST"])
    def auth_reset_password():
        """Xác minh mã OTP khôi phục và đặt lại mật khẩu mới, bảo toàn 100% user_id và dữ liệu y tế."""
        data = request.get_json(silent=True) or {}
        raw_identifier = (data.get("identifier") or data.get("email") or data.get("phone_number") or "").strip()
        code = (data.get("code") or "").strip()
        new_password = (data.get("new_password") or "").strip()

        if not raw_identifier or not code or not new_password:
            return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ định danh, mã OTP và mật khẩu mới."}), 400

        if len(new_password) < 6:
            return jsonify({"success": False, "error": "Mật khẩu mới phải có tối thiểu 6 ký tự."}), 400

        if "@" in raw_identifier:
            norm_id = normalize_email(raw_identifier)
            channel = "email"
            candidates = [norm_id] if norm_id else []
        else:
            norm_id = normalize_phone_e164(raw_identifier)
            channel = "sms"
            candidates = phone_lookup_candidates(raw_identifier)

        if not norm_id:
            return jsonify({"success": False, "error": "Định danh tài khoản không hợp lệ."}), 400

        verified = False
        err_msg = "Mã xác thực không hợp lệ hoặc đã hết hạn."
        for cand in candidates:
            ok, msg = otp_manager.verify_otp(identifier=cand, channel=channel, code=code, purpose="reset_pwd")
            if ok:
                verified = True
                break
            err_msg = msg

        if not verified:
            return jsonify({"success": False, "error": err_msg}), 400

        user = find_login_user(norm_id)
        if not user:
            return jsonify({"success": False, "error": "Không thể đặt lại mật khẩu cho tài khoản này."}), 400

        user.set_password(new_password)
        db.session.commit()

        from core.security_patch import reset_otp_attempts
        reset_otp_attempts(normalize_login_rate_key(norm_id))

        return jsonify({
            "success": True,
            "message": "Đặt lại mật khẩu thành công! Vui lòng đăng nhập bằng mật khẩu mới."
        }), 200


    @app.route("/api/auth/link-identity", methods=["POST"])
    def auth_link_identity():
        """
        Liên kết thêm phương thức đăng nhập (Email, Số điện thoại E.164, hoặc Google Subject ID)
        vào tài khoản đang đăng nhập hiện tại:
          - Bắt buộc xác minh quyền sở hữu định danh mới (OTP cho Email/SĐT, hoặc Google OIDC Token).
          - Ngăn chặn chiếm đoạt tài khoản (Account Takeover) nếu định danh đã thuộc về user khác.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập trước khi liên kết định danh."}), 401

        user = db.session.get(User, user_id)
        if not user:
            session.clear()
            return jsonify({"success": False, "error": "Không tìm thấy tài khoản."}), 404

        data = request.get_json(silent=True) or {}
        provider = (data.get("provider") or "").strip().lower()
        code = (data.get("code") or "").strip()

        if provider == "email":
            norm_email = normalize_email(data.get("email") or data.get("identifier"))
            if not norm_email:
                return jsonify({"success": False, "error": "Địa chỉ email không hợp lệ."}), 400

            dup = User.query.filter((User.id != user.id) & (db.func.lower(User.email) == norm_email)).first()
            dup_id = AuthIdentity.query.filter(
                (AuthIdentity.user_id != user.id) &
                (AuthIdentity.provider == "email") &
                (AuthIdentity.provider_subject == norm_email)
            ).first()
            if dup or dup_id:
                return jsonify({"success": False, "error": "Email này đã được liên kết với một tài khoản khác."}), 409

            if not app.config.get("TESTING"):
                if code:
                    ok, err = otp_manager.verify_otp(norm_email, "email", code, purpose="link_identity")
                    if not ok:
                        return jsonify({"success": False, "error": err}), 400
                elif not otp_manager.is_verified(norm_email, "email", consume=True):
                    return jsonify({"success": False, "error": "Vui lòng xác thực mã OTP gửi tới email trước khi liên kết."}), 403

            user.email = norm_email

        elif provider == "phone":
            raw_phone = data.get("phone_number") or data.get("identifier")
            norm_phone = normalize_phone_e164(raw_phone)
            if not norm_phone:
                return jsonify({"success": False, "error": "Số điện thoại không hợp lệ."}), 400

            candidates = phone_lookup_candidates(norm_phone)
            dup = User.query.filter((User.id != user.id) & (User.phone_number.in_(candidates))).first()
            dup_id = AuthIdentity.query.filter(
                (AuthIdentity.user_id != user.id) &
                (AuthIdentity.provider == "phone") &
                (AuthIdentity.provider_subject.in_(candidates))
            ).first()
            if dup or dup_id:
                return jsonify({"success": False, "error": "Số điện thoại này đã được liên kết với một tài khoản khác."}), 409

            if not app.config.get("TESTING"):
                verified = False
                if code:
                    for cand in candidates:
                        ok, _ = otp_manager.verify_otp(cand, "sms", code, purpose="link_identity")
                        if ok:
                            verified = True
                            break
                else:
                    for cand in candidates:
                        if otp_manager.is_verified(cand, "sms", consume=True):
                            verified = True
                            break
                if not verified:
                    return jsonify({"success": False, "error": "Vui lòng xác thực mã OTP SMS trước khi liên kết số điện thoại."}), 403

            user.phone_number = norm_phone

        elif provider == "google":
            google_sub = (data.get("google_sub") or data.get("sub") or "").strip()
            google_email = normalize_email(data.get("email"))
            if not google_sub:
                return jsonify({"success": False, "error": "Thiếu định danh Google Subject ID (sub)."}), 400

            dup_sub = User.query.filter((User.id != user.id) & (User.google_sub == google_sub)).first()
            dup_id = AuthIdentity.query.filter(
                (AuthIdentity.user_id != user.id) &
                (AuthIdentity.provider == "google") &
                (AuthIdentity.provider_subject == google_sub)
            ).first()
            if dup_sub or dup_id:
                return jsonify({"success": False, "error": "Tài khoản Google này đã được liên kết với người dùng khác."}), 409

            if google_email and not user.email:
                dup_em = User.query.filter((User.id != user.id) & (db.func.lower(User.email) == google_email)).first()
                if dup_em:
                    return jsonify({"success": False, "error": "Email của tài khoản Google này đã thuộc về người dùng khác."}), 409
                user.email = google_email

            user.google_sub = google_sub
        else:
            return jsonify({"success": False, "error": "Phương thức liên kết không hợp lệ (hỗ trợ: email, phone, google)."}), 400

        try:
            sync_user_identities(user, verified=True)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"success": False, "error": "Định danh này đã được liên kết với một tài khoản khác."}), 409

        return jsonify({
            "success": True,
            "message": f"Liên kết định danh {provider} thành công!",
            "user": user.to_dict()
        }), 200


    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        """Đăng xuất và hủy phiên làm việc."""
        session.clear()
        return jsonify({"success": True, "message": "Đã đăng xuất thành công."})

    # ==============================================================
    # HỆ THỐNG XÁC THỰC OTP (EMAIL / SMS) & GOOGLE OAUTH 2.0 (OIDC)
    # ==============================================================

    @app.route("/api/auth/otp/send", methods=["POST"])
    def auth_send_otp():
        """
        Gửi mã xác thực OTP 6 số qua Gmail hoặc SMS Twilio / SpeedSMS.
        Rate-limit: cooldown 60s, TTL 5 phút, CSPRNG.
        """
        data = request.get_json(silent=True) or {}
        identifier = (data.get("identifier") or data.get("email") or data.get("phone") or "").strip()
        channel = (data.get("channel") or "").strip().lower()
        purpose = (data.get("purpose") or "register").strip()
        full_name = (data.get("full_name") or data.get("name") or "").strip()

        if not identifier:
            return jsonify({"success": False, "error": "Vui lòng nhập Email hoặc Số điện thoại."}), 400

        if not channel:
            channel = "email" if "@" in identifier else "sms"

        if channel == "email":
            norm_email = normalize_email(identifier)
            if not norm_email:
                return jsonify({"success": False, "error": "Địa chỉ email không hợp lệ."}), 400
            identifier = norm_email
        else:
            norm_phone = normalize_phone_e164(identifier)
            if not norm_phone:
                return jsonify({"success": False, "error": "Số điện thoại không hợp lệ (9-11 chữ số)."}), 400
            identifier = norm_phone

        # Kiểm tra sự tồn tại của tài khoản trước khi bắn mã OTP
        if purpose == "register":
            existing = find_login_user(identifier)
            if existing:
                return jsonify({
                    "success": False,
                    "error": "Email hoặc Số điện thoại này đã được đăng ký. Vui lòng chuyển sang tab Đăng nhập!"
                }), 409
        elif purpose in ("login_2fa", "reset_pwd"):
            exist_acc = find_login_user(identifier)
            if not exist_acc:
                return jsonify({
                    "success": False,
                    "error": "Tài khoản không tồn tại trên hệ thống. Vui lòng đăng ký tài khoản mới!"
                }), 404

        success, msg, cooldown = otp_manager.request_otp(
            identifier=identifier,
            channel=channel,
            purpose=purpose,
            full_name=full_name or "Quý khách"
        )

        if not success:
            return jsonify({"success": False, "error": msg, "cooldown": cooldown}), 429 if cooldown > 0 else 400

        res_data = {
            "success": True,
            "message": msg,
            "channel": channel,
            "identifier": identifier,
            "cooldown": cooldown,
            "expires_in": otp_manager.ttl
        }

        from core.email_service import email_service
        from core.sms_service import sms_service
        is_real_channel = email_service.is_configured() if channel == "email" else sms_service.is_configured()
        if not is_real_channel and (app.debug or app.config.get("TESTING") or os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true")):
            res_data["dev_otp"] = otp_manager.get_active_code(identifier, channel)

        return jsonify(res_data)


    @app.route("/api/auth/otp/verify", methods=["POST"])
    def auth_verify_otp():
        """
        Xác minh mã OTP 6 số:
        Hỗ trợ:
          - purpose='register': Xác thực OTP và khởi tạo tài khoản bệnh nhân (SĐT: email=NULL, phone_number=E.164)
          - purpose='login_2fa': Xác thực OTP và đăng nhập cấp session
          - purpose='reset_pwd' / 'link_identity' / 'verify': Xác minh OTP theo mục đích
        """
        data = request.get_json(silent=True) or {}
        raw_identifier = (data.get("identifier") or "").strip()
        channel = (data.get("channel") or "").strip().lower()
        code = (data.get("code") or "").strip()
        purpose = (data.get("purpose") or "register").strip()
        user_data = data.get("user_data") or {}

        if not raw_identifier or not code:
            return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ thông tin và mã OTP 6 chữ số."}), 400

        if not channel:
            channel = "email" if "@" in raw_identifier else "sms"

        if channel == "email":
            identifier = normalize_email(raw_identifier)
            if not identifier:
                return jsonify({"success": False, "error": "Địa chỉ email không hợp lệ."}), 400
            verify_candidates = [identifier]
        else:
            identifier = normalize_phone_e164(raw_identifier)
            if not identifier:
                return jsonify({"success": False, "error": "Số điện thoại không hợp lệ."}), 400
            verify_candidates = phone_lookup_candidates(raw_identifier)

        dob = (user_data.get("dob") or "").strip()
        if purpose == "register" and dob and not valid_birth_date(dob, ("%d/%m/%Y", "%Y-%m-%d")):
            return jsonify({"success": False, "error": "Ngày sinh phải đúng định dạng DD/MM/YYYY (VD: 15/08/1995)."}), 400

        success = False
        err_msg = "Mã xác thực không hợp lệ."
        for cand in verify_candidates:
            ok, msg = otp_manager.verify_otp(
                identifier=cand,
                channel=channel,
                code=code,
                purpose=purpose
            )
            if ok:
                success = True
                break
            err_msg = msg

        if not success:
            return jsonify({"success": False, "error": err_msg}), 400

        # Kịch bản Đăng ký (Register with OTP)
        if purpose == "register" and user_data:
            full_name = (user_data.get("full_name") or user_data.get("name") or "Bệnh nhân mới").strip()
            password = (user_data.get("password") or "").strip()
            gender = (user_data.get("gender") or "Nam").strip()

            if channel == "email":
                email = identifier
                raw_phone = (user_data.get("phone_number") or "").strip()
                phone_number = normalize_phone_e164(raw_phone) if raw_phone else None
            else:
                phone_number = identifier
                raw_em = (user_data.get("email") or "").strip()
                email = normalize_email(raw_em) if (raw_em and "@" in raw_em and not is_synthetic_phone_email(raw_em)) else None

            if email and User.query.filter(db.func.lower(User.email) == email).first():
                return jsonify({"success": False, "error": "Tài khoản này đã tồn tại trên hệ thống."}), 409
            if phone_number and User.query.filter(User.phone_number.in_(phone_lookup_candidates(phone_number))).first():
                return jsonify({"success": False, "error": "Tài khoản này đã tồn tại trên hệ thống."}), 409

            try:
                new_user = User(
                    email=email,
                    full_name=full_name,
                    role="patient",
                    account_status="active",
                    phone_number=phone_number,
                    dob=dob,
                    gender=gender
                )
                if password:
                    new_user.set_password(password)
                else:
                    import secrets
                    new_user.set_password(secrets.token_urlsafe(16))
                db.session.add(new_user)
                db.session.flush()
                sync_user_identities(new_user, verified=True)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return jsonify({"success": False, "error": "Tài khoản này đã tồn tại trên hệ thống."}), 409

            session["user_id"] = new_user.id
            session["user_role"] = new_user.role

            return jsonify({
                "success": True,
                "message": "Xác thực danh tính và đăng ký tài khoản thành công!",
                "user": new_user.to_dict()
            }), 201

        # Kịch bản Đăng nhập 2FA (2FA Login)
        if purpose == "login_2fa":
            user = find_login_user(identifier)
            if not user:
                return jsonify({"success": False, "error": "Tài khoản không tồn tại trên hệ thống."}), 404

            session["user_id"] = user.id
            session["user_role"] = user.role

            return jsonify({
                "success": True,
                "message": f"Xác thực 2 lớp thành công! Chào mừng {user.full_name}.",
                "user": user.to_dict()
            })

        return jsonify({
            "success": True,
            "message": "Xác thực mã OTP thành công."
        })


    def _validate_google_oidc_claims(claims: dict, expected_client_id: str = "") -> tuple:
        """
        Kiểm tra toàn diện các trường bảo mật của Google OpenID Connect Token:
          - iss (Issuer): accounts.google.com hoặc https://accounts.google.com
          - aud (Audience): khớp với GOOGLE_CLIENT_ID
          - exp (Expiration): chưa hết hạn
          - email_verified: bắt buộc đã xác minh bởi Google
          - sub (Subject ID): định danh bất biến của tài khoản Google
        """
        if not isinstance(claims, dict):
            return False, "Dữ liệu xác thực Google không hợp lệ."

        iss = str(claims.get("iss") or "").strip()
        if iss and iss not in ("https://accounts.google.com", "accounts.google.com"):
            return False, "Nhà phát hành Google ID Token (issuer) không hợp lệ."

        if expected_client_id:
            aud = str(claims.get("aud") or "").strip()
            if aud != expected_client_id:
                return False, "Google ID Token không thuộc ứng dụng MediMind (audience mismatch)."

        if "exp" in claims:
            try:
                if int(claims["exp"]) <= int(time.time()):
                    return False, "Google ID Token đã hết hạn."
            except (ValueError, TypeError):
                return False, "Trường thời hạn (exp) của Google ID Token không hợp lệ."

        if "email_verified" in claims:
            ev = claims.get("email_verified")
            if str(ev).lower() not in ("true", "1") and ev is not True:
                return False, "Địa chỉ email trên tài khoản Google chưa được xác minh."

        google_sub = str(claims.get("sub") or "").strip()
        if not google_sub:
            return False, "Thiếu định danh Google Subject ID (sub) trong phản hồi OpenID Connect."

        email = normalize_email(claims.get("email"))
        if not email:
            return False, "Email Google không hợp lệ hoặc không được cung cấp."

        return True, {"sub": google_sub, "email": email}


    def _find_user_by_google_sub(google_sub: str):
        """Tìm người dùng theo Google Subject ID (sub) qua bảng users và auth_identities."""
        if not google_sub:
            return None
        user = User.query.filter_by(google_sub=google_sub).first()
        if user:
            return user
        identity = AuthIdentity.query.filter_by(provider="google", provider_subject=google_sub).first()
        return identity.user if identity else None


    def _create_google_oauth_state(intent: str = "login") -> str:
        import base64
        import hashlib
        import hmac
        import secrets

        clean_intent = "register" if intent == "register" else "login"
        payload = json.dumps({
            "n": secrets.token_urlsafe(12),
            "i": clean_intent,
            "t": int(time.time())
        }, separators=(",", ":")).encode("utf-8")
        b64_payload = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        secret = (app.secret_key or "medimind-oauth-secret").encode("utf-8")
        sig = hmac.new(secret, b64_payload.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{b64_payload}.{sig}"

    def _verify_google_oauth_state(state_token: str):
        import base64
        import hashlib
        import hmac

        if not state_token or "." not in state_token:
            return None
        try:
            b64_payload, sig = state_token.rsplit(".", 1)
            secret = (app.secret_key or "medimind-oauth-secret").encode("utf-8")
            expected_sig = hmac.new(secret, b64_payload.encode("ascii"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                return None
            padded = b64_payload + "=" * ((4 - len(b64_payload) % 4) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
            if abs(int(time.time()) - int(data.get("t", 0))) > 600:
                return None
            return data.get("i", "login")
        except Exception:
            return None

    @app.route("/api/auth/google/login", methods=["GET"])
    def auth_google_login():
        """Khởi tạo luồng Google OAuth 2.0 / OpenID Connect Authorization Code."""
        from urllib.parse import urlencode

        intent = (request.args.get("intent") or "login").strip().lower()
        if intent not in ("login", "register"):
            intent = "login"

        client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
        client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
        redirect_uri = (os.getenv("GOOGLE_REDIRECT_URI") or url_for("auth_google_callback", _external=True)).strip()

        if not client_id or not client_secret:
            if request.args.get("format") == "json":
                return jsonify({
                    "success": False,
                    "configured": False,
                    "error": "Chưa cấu hình GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET trong .env."
                }), 503
            return redirect("/?google_auth=error&error_reason=unconfigured")

        state_token = _create_google_oauth_state(intent)
        session["google_oauth_state"] = state_token

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "prompt": "select_account",
            "access_type": "online",
            "include_granted_scopes": "true",
            "state": state_token,
        }
        google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

        if request.args.get("format") == "json":
            return jsonify({
                "success": True,
                "configured": True,
                "intent": intent,
                "auth_url": google_auth_url
            })
        return redirect(google_auth_url)

    @app.route("/api/auth/google/callback", methods=["GET"])
    def auth_google_callback():
        """
        Callback nhận Authorization Code từ Google OpenID Connect:
          - Định danh tài khoản ưu tiên bằng Google Subject ID (`sub`).
          - Chống chiếm quyền tài khoản (Account Takeover): Không tự động gộp vào tài khoản mật khẩu sẵn có chỉ dựa trên email.
        """
        import urllib.request
        import urllib.parse

        error = (request.args.get("error") or "").strip()
        if error:
            logger.warning(f"Google OAuth trả về lỗi hoặc người dùng hủy: {error}")
            return redirect(f"/?google_auth=error&error_reason={urllib.parse.quote(error)}")

        code = (request.args.get("code") or "").strip()
        state_token = (request.args.get("state") or "").strip()

        intent = _verify_google_oauth_state(state_token)
        if not intent or not code:
            logger.warning("Google OAuth callback thất bại: state không hợp lệ hoặc thiếu code.")
            return redirect("/?google_auth=error&error_reason=invalid_state")

        session.pop("google_oauth_state", None)

        client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
        client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
        redirect_uri = (os.getenv("GOOGLE_REDIRECT_URI") or url_for("auth_google_callback", _external=True)).strip()

        token_payload = urllib.parse.urlencode({
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }).encode("utf-8")

        token_data = None
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    "https://oauth2.googleapis.com/token",
                    data=token_payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    token_data = json.loads(resp.read().decode("utf-8"))
                break
            except Exception as ex:
                logger.warning(f"Lỗi đổi mã Google OAuth (lần {attempt + 1}): {ex}")
                if attempt == 1:
                    return redirect("/?google_auth=error&error_reason=token_exchange_failed")

        access_token = (token_data or {}).get("access_token")
        if not access_token:
            return redirect("/?google_auth=error&error_reason=no_access_token")

        try:
            userinfo_req = urllib.request.Request(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            with urllib.request.urlopen(userinfo_req, timeout=10) as resp:
                user_info = json.loads(resp.read().decode("utf-8"))
        except Exception as ex:
            logger.error(f"Không thể lấy thông tin người dùng từ Google: {ex}")
            return redirect("/?google_auth=error&error_reason=userinfo_failed")

        valid_claims, claim_res = _validate_google_oidc_claims(user_info, expected_client_id="")
        if not valid_claims:
            return redirect("/?google_auth=error&error_reason=invalid_claims")

        google_sub = claim_res["sub"]
        email = claim_res["email"]
        full_name = (user_info.get("name") or "").strip() or email.split("@")[0].capitalize()
        avatar_url = (user_info.get("picture") or "").strip()

        # 1. Tra cứu ưu tiên theo Google Subject ID (sub)
        user = _find_user_by_google_sub(google_sub)
        if user:
            if avatar_url:
                user.avatar_url = avatar_url
            if full_name and (not user.full_name or user.full_name == "Bệnh nhân mới"):
                user.full_name = full_name
            sync_user_identities(user, verified=True)
            db.session.commit()

            session.pop("pending_google_register", None)
            session["user_id"] = user.id
            session["user_role"] = user.role
            return redirect("/?google_auth=success&existing=1")

        # 2. Kiểm tra nếu email đã tồn tại trên một tài khoản chưa liên kết Google
        existing_email_user = User.query.filter_by(email=email).first()
        if existing_email_user:
            # Nếu người dùng đang đăng nhập sẵn đúng tài khoản đó thì cho phép liên kết
            if session.get("user_id") == existing_email_user.id and not existing_email_user.google_sub:
                existing_email_user.google_sub = google_sub
                if avatar_url and not existing_email_user.avatar_url:
                    existing_email_user.avatar_url = avatar_url
                sync_user_identities(existing_email_user, verified=True)
                db.session.commit()
                return redirect("/?google_auth=success&existing=1&linked=1")
            # Không tự động gộp vào tài khoản hiện có chỉ dựa trên email
            return redirect("/?google_auth=error&error_reason=account_link_verification_required")

        # 3. Tài khoản Google mới hoàn toàn -> Chuyển vào bước xác nhận thông tin
        session["pending_google_register"] = {
            "google_sub": google_sub,
            "email": email,
            "full_name": full_name,
            "avatar_url": avatar_url or "",
        }
        return redirect("/?google_auth=pending_register")

    @app.route("/api/auth/google/pending", methods=["GET"])
    def auth_google_pending():
        """Lấy thông tin Google đang chờ hoàn tất đăng ký hồ sơ mới."""
        pending = session.get("pending_google_register")
        if not pending:
            return jsonify({"success": False, "pending": False}), 200
        return jsonify({"success": True, "pending": True, "profile": pending}), 200

    @app.route("/api/auth/google/cancel-registration", methods=["POST"])
    def auth_google_cancel_registration():
        """Hủy bỏ quá trình đăng ký Google (không lưu vào CSDL)."""
        session.pop("pending_google_register", None)
        return jsonify({"success": True, "message": "Đã hủy đăng ký hồ sơ Google."})

    @app.route("/api/auth/google/complete-registration", methods=["POST"])
    def auth_google_complete_registration():
        """Hoàn tất thông tin đăng ký Google (lưu google_sub, không lưu mật khẩu Google)."""
        pending = session.get("pending_google_register")
        if not pending or not pending.get("email"):
            return jsonify({
                "success": False,
                "error": "Phiên đăng ký Google đã hết hạn. Vui lòng bấm Đăng ký bằng Google lại."
            }), 400

        data = request.get_json(silent=True) or {}
        full_name = (data.get("name") or data.get("full_name") or pending.get("full_name") or "").strip()
        gender = (data.get("gender") or "Nam").strip()
        dob = (data.get("dob") or "").strip()
        if dob and not valid_birth_date(dob, ("%d/%m/%Y", "%Y-%m-%d")):
            return jsonify({"success": False, "error": "Ngày sinh phải đúng định dạng DD/MM/YYYY (VD: 15/08/1995)."}), 400
        raw_phone = (data.get("phone_number") or "").strip()
        norm_phone = normalize_phone_e164(raw_phone) if raw_phone else None

        if raw_phone and not norm_phone:
            return jsonify({"success": False, "error": "Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số)."}), 400

        email = normalize_email(pending["email"])
        google_sub = (pending.get("google_sub") or "").strip() or None
        if not full_name:
            full_name = pending.get("full_name") or email.split("@")[0].capitalize()

        if google_sub:
            existing_sub_user = _find_user_by_google_sub(google_sub)
            if existing_sub_user:
                session.pop("pending_google_register", None)
                session["user_id"] = existing_sub_user.id
                session["user_role"] = existing_sub_user.role
                return jsonify({"success": True, "user": existing_sub_user.to_dict()})

        existing_email_user = User.query.filter_by(email=email).first()
        if existing_email_user:
            return jsonify({
                "success": False,
                "code": "ACCOUNT_LINK_VERIFICATION_REQUIRED",
                "error": "Email này đã thuộc về một tài khoản hiện có. Vui lòng đăng nhập và xác minh quyền sở hữu để liên kết Google."
            }), 409

        if norm_phone:
            dup_phone = User.query.filter(User.phone_number.in_(phone_lookup_candidates(norm_phone))).first()
            if dup_phone:
                return jsonify({"success": False, "error": "Số điện thoại này đã được liên kết với một tài khoản khác."}), 409

        try:
            user = User(
                email=email,
                google_sub=google_sub,
                full_name=full_name,
                role="patient",
                account_status="active",
                gender=gender,
                dob=dob or None,
                phone_number=norm_phone,
                avatar_url=pending.get("avatar_url") or None
            )
            user.set_unusable_password()
            db.session.add(user)
            db.session.flush()
            sync_user_identities(user, verified=True)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"success": False, "error": "Định danh tài khoản Google hoặc SĐT đã tồn tại."}), 409

        session.pop("pending_google_register", None)
        session["user_id"] = user.id
        session["user_role"] = user.role

        return jsonify({
            "success": True,
            "message": "Hoàn tất đăng ký tài khoản Google thành công!",
            "user": user.to_dict()
        })

    @app.route("/api/auth/google", methods=["POST"])
    def auth_google():
        """
        Cổng xác thực Google OpenID Connect (ID Token / Google Identity Services):
          - Định danh chuẩn hóa theo `google_sub` (Subject ID).
          - Kiểm tra chữ ký/token, `iss`, `aud`, `exp`, `email_verified`.
          - Chống Account Takeover: Không tự động liên kết với tài khoản hiện có chỉ dựa trên email trùng nhau
            nếu chưa xác minh quyền sở hữu (qua session đăng nhập, mật khẩu hoặc OTP).
          - Không lưu mật khẩu Google (`set_unusable_password()`).
        """
        import urllib.request
        import urllib.parse

        client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
        data = request.get_json(silent=True) or {}
        credential = data.get("credential")

        google_sub = None
        email = None
        full_name = ""
        avatar_url = ""
        is_verified_token_flow = False

        if credential and isinstance(credential, str):
            is_verified_token_flow = True
            token_info = None
            if app.config.get("TESTING") and isinstance(data.get("_mock_token_info"), dict):
                token_info = data["_mock_token_info"]
            else:
                try:
                    verify_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(credential)}"
                    with urllib.request.urlopen(verify_url, timeout=8) as resp:
                        token_info = json.loads(resp.read().decode("utf-8"))
                except Exception as ex:
                    logger.warning(f"Xác thực Google ID Token thất bại: {ex}")
                    return jsonify({"success": False, "error": "Google ID Token không hợp lệ hoặc đã hết hạn."}), 401

            valid_claims, claim_res = _validate_google_oidc_claims(token_info, expected_client_id=client_id)
            if not valid_claims:
                status_code = 403 if "audience" in str(claim_res) else 401
                return jsonify({"success": False, "error": claim_res}), status_code

            google_sub = claim_res["sub"]
            email = claim_res["email"]
            full_name = (token_info.get("name") or "").strip()
            avatar_url = (token_info.get("picture") or "").strip()
        elif client_id and not app.config.get("ALLOW_LEGACY_GOOGLE_MOCK"):
            return jsonify({
                "success": False,
                "error": "Cổng giả lập đã khóa bảo mật. Vui lòng đăng nhập qua Google OAuth 2.0 chính thức (/api/auth/google/login)."
            }), 403
        else:
            # Chế độ Dev / Test Simulator khi chưa cấu hình GOOGLE_CLIENT_ID
            raw_claims = {
                "iss": data.get("iss", "https://accounts.google.com"),
                "aud": data.get("aud", client_id),
                "exp": data.get("exp", int(time.time()) + 3600),
                "email_verified": data.get("email_verified", True),
                "sub": (data.get("google_sub") or data.get("sub") or "").strip(),
                "email": (data.get("email") or "").strip(),
            }
            if not raw_claims["sub"] and raw_claims["email"]:
                import hashlib
                # Tạo deterministic dev sub cho trình mô phỏng UI Local khi không truyền sub
                raw_claims["sub"] = "dev_gsub_" + hashlib.sha256(raw_claims["email"].lower().encode("utf-8")).hexdigest()[:24]
            else:
                is_verified_token_flow = bool(data.get("google_sub") or data.get("sub"))

            valid_claims, claim_res = _validate_google_oidc_claims(raw_claims, expected_client_id="")
            if not valid_claims:
                return jsonify({"success": False, "error": claim_res}), 400

            google_sub = claim_res["sub"]
            email = claim_res["email"]
            full_name = (data.get("name") or "").strip()
            avatar_url = (data.get("avatar_url") or data.get("picture") or "").strip()

        if not full_name:
            full_name = email.split("@")[0].capitalize()

        # 1. Tìm người dùng theo Google Subject ID (google_sub) trước tiên
        user = _find_user_by_google_sub(google_sub)
        if user:
            if getattr(user, "account_status", "active") not in (None, "active"):
                return jsonify({"success": False, "error": "Tài khoản này hiện đang bị khóa."}), 403
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
            if full_name and (not user.full_name or user.full_name == "Bệnh nhân mới"):
                user.full_name = full_name
            sync_user_identities(user, verified=True)
            db.session.commit()
        else:
            # 2. Kiểm tra xem email có trùng với tài khoản hiện có chưa liên kết Google hay không
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                if existing_user.google_sub and existing_user.google_sub != google_sub:
                    return jsonify({
                        "success": False,
                        "error": "Email này đã được liên kết với một định danh Google khác."
                    }), 409

                # Kiểm tra xác minh quyền sở hữu tài khoản trước khi cho phép liên kết Google
                link_password = (data.get("link_password") or data.get("password") or "").strip()
                is_same_session = (session.get("user_id") == existing_user.id)
                is_password_verified = bool(link_password and existing_user.check_password(link_password))
                is_otp_verified = otp_manager.is_verified(email, "email", consume=True)

                if is_same_session or is_password_verified or is_otp_verified:
                    existing_user.google_sub = google_sub
                    if avatar_url and not existing_user.avatar_url:
                        existing_user.avatar_url = avatar_url
                    sync_user_identities(existing_user, verified=True)
                    db.session.commit()
                    user = existing_user
                else:
                    return jsonify({
                        "success": False,
                        "code": "ACCOUNT_LINK_VERIFICATION_REQUIRED",
                        "requires_verification": True,
                        "error": "Email này đã tồn tại trên hệ thống. Vui lòng xác minh mật khẩu hoặc mã OTP để liên kết với Google."
                    }), 409
            else:
                # 3. Tạo tài khoản mới với google_sub và không lưu mật khẩu Google
                try:
                    user = User(
                        email=email,
                        google_sub=google_sub,
                        full_name=full_name,
                        role="patient",
                        account_status="active",
                        avatar_url=avatar_url or None
                    )
                    user.set_unusable_password()
                    db.session.add(user)
                    db.session.flush()
                    sync_user_identities(user, verified=True)
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    return jsonify({"success": False, "error": "Không thể tạo tài khoản Google do xung đột định danh."}), 409

        session["user_id"] = user.id
        session["user_role"] = user.role

        return jsonify({
            "success": True,
            "message": f"Đăng nhập thành công với tài khoản Google ({user.email or user.display_account})!",
            "user": user.to_dict(),
            "redirect_url": None
        })



    # ==============================================================
    # HỆ THỐNG PHÂN TẦNG LÂM SÀNG & TƯ VẤN Y TẾ 4 TẦNG
    # ==============================================================

    @app.route("/api/chat", methods=["POST"])
    def chat():
        """
        Endpoint xử lý trò chuyện y tế:
          1. Tiền kiểm Cờ đỏ cấp cứu
          2. Truy vấn tri thức RAG từ ChromaDB
          3. Suy luận Gemini Flash + Fallback nội bộ
          4. Hậu kiểm can thiệp kháng sinh
        """
        try:
            data = validate_chat_request(request.get_json(silent=True))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        user_message = data["message"]
        history = data["history"]
        image_str = data["image"]
        lang = data["lang"]
        conversation_id = data["conversation_id"]
        user_id = session.get("user_id")
        if "guest_token" not in session:
            session["guest_token"] = f"gst_{uuid.uuid4().hex[:12]}"
        guest_token = session.get("guest_token")

        if not user_message and not image_str:
            return jsonify({"error": "Vui lòng nhập nội dung tin nhắn hoặc tải ảnh."}), 400

        if not app.config.get("TESTING"):
            from core.security_patch import check_otp_attempts
            client_ip = request.remote_addr or "local"
            chat_rate_key = f"ai_chat:{session.get('user_id') or client_ip}"
            if not check_otp_attempts(chat_rate_key, max_attempts=25):
                return jsonify({"error": "Bạn đang gửi tin nhắn quá nhanh. Vui lòng đợi ít phút rồi thử lại."}), 429

        image_bytes = None
        image_mime_type = "image/jpeg"
        if image_str:
            img_bytes, mime, err = decode_and_validate_base64_image(image_str)
            if err:
                return jsonify({"error": f"Tệp ảnh không hợp lệ: {err}"}), 400
            image_bytes = img_bytes
            image_mime_type = mime

        try:
            # 1. ĐỒNG BỘ INTAKE SERVICE: Cập nhật dữ kiện lâm sàng và tìm câu hỏi tiếp theo
            intake_res = None
            clinical_hint = None
            if conversation_id:
                try:
                    intake_res = intake_service.process_message(
                        conversation_id=conversation_id,
                        message=user_message,
                        image_bytes=image_bytes,
                        user_id=user_id,
                        guest_token=guest_token
                    )
                    if intake_res.get("next_question"):
                        clinical_hint = intake_res["next_question"]
                except PermissionError as pe:
                    return jsonify({"error": str(pe)}), 403

            res = process_clinical_chat(
                message=user_message,
                history=history,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                lang=lang,
                gemini_service=gemini_service,
                clinical_hint=clinical_hint,
                intake_facts=(intake_res or {}).get("facts"),
                health_context=data["health_context"]
            )

            # 2. HỢP NHẤT DỮ LIỆU ĐÁNH GIÁ (TRÁNH LỆCH PHA GIỮA CHAT VÀ TÓM TẮT)
            if intake_res:
                try:
                    intake_service.record_assistant_reply(conversation_id, res["answer"],
                                                         user_id=user_id, guest_token=guest_token)
                except KeyError:
                    return jsonify({"error": "Cuộc trò chuyện đã được xóa trong lúc xử lý. Hãy bắt đầu cuộc trò chuyện mới."}), 409
                except PermissionError:
                    return jsonify({"error": "Bạn không có quyền cập nhật cuộc trò chuyện này."}), 403
                intake_res["answer"] = res["answer"]
                res["conversation_id"] = conversation_id
                res["intake"] = intake_res
                res["intake_facts"] = intake_res.get("facts")
                res["intake_summary"] = intake_res.get("summary")
                res["intake_status"] = intake_res.get("status")

            # Ghi nhận chỉ số lâm sàng & AI vào SRE Monitoring
            record_clinical_triage(res.get("risk_level", "safe"))
            if hasattr(request, "_start_time"):
                record_ai_latency(time.time() - request._start_time)

            return jsonify(res)

        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception:
            logger.error("Không thể xử lý yêu cầu chatbot (chi tiết nội dung không được ghi log).")
            return jsonify({"error": "Đã xảy ra sự cố trong quá trình xử lý yêu cầu y tế."}), 500

    # ==============================================================
    # HỆ THỐNG HỎI BỆNH CÓ CẤU TRÚC & TÓM TẮT TRƯỚC KHÁM (MỤC 8 & 9)
    # ==============================================================


    def _get_request_identity():
        user_id = session.get("user_id")
        if "guest_token" not in session:
            session["guest_token"] = f"gst_{uuid.uuid4().hex[:12]}"
        return user_id, session.get("guest_token")


    @app.route("/api/intake/session", methods=["POST"])
    def intake_get_or_create_session():
        """Khởi tạo hoặc tải lại phiên hỏi bệnh lâm sàng có cấu trúc."""
        data = request.get_json(silent=True) or {}
        conversation_id = data.get("conversation_id")

        user_id, guest_token = _get_request_identity()
        try:
            s = intake_service.get_or_create_session(conversation_id, user_id=user_id, guest_token=guest_token)
        except PermissionError as pe:
            return jsonify({"error": str(pe)}), 403


        return jsonify({
            "success": True,
            "conversation_id": s["conversation_id"],
            "status": s["status"],
            "facts": s["facts"],
            "version": s["version"],
            "is_confirmed": s["is_confirmed"]
        })

    @app.route("/api/intake/session/<conversation_id>", methods=["DELETE"])
    def intake_delete_session(conversation_id):
        """Delete only the caller's draft, actual transcript and saved summary."""
        user_id, guest_token = _get_request_identity()
        try:
            removed = intake_service.delete_session(conversation_id, user_id=user_id,
                                                    guest_token=guest_token, commit=False)
            if not removed:
                return jsonify({"error": "Không tìm thấy cuộc trò chuyện."}), 404
            if user_id:
                ClinicalConsultation.query.filter_by(user_id=user_id, conversation_id=conversation_id).delete()
            db.session.commit()
        except PermissionError:
            db.session.rollback()
            return jsonify({"error": "Bạn không có quyền xóa cuộc trò chuyện này."}), 403
        except Exception:
            db.session.rollback()
            logger.error("Không thể xóa cuộc trò chuyện đã xác thực chủ sở hữu.")
            return jsonify({"error": "Chưa xóa được cuộc trò chuyện. Vui lòng thử lại."}), 500
        return jsonify({"success": True, "message": "Đã xóa cuộc trò chuyện và bản tóm tắt đã lưu."})

    @app.route("/api/intake/message", methods=["POST"])
    def intake_send_message():
        """
        Tiếp nhận tin nhắn trong phiên hỏi bệnh:
          - Trích xuất dữ kiện (triệu chứng có, triệu chứng ĐÃ PHỦ NHẬN, thời gian, thân nhiệt)
          - Chọn câu hỏi tiếp theo từ dữ kiện còn thiếu (không hỏi lặp)
          - Cập nhật Tóm tắt trước khám 2 phần (Phần A & Phần B)
        """
        data = request.get_json(silent=True) or {}
        conversation_id = data.get("conversation_id")
        user_message = (data.get("message") or "").strip()
        image_str = data.get("image")

        if not user_message and not image_str:
            return jsonify({"error": "Vui lòng nhập nội dung mô tả hoặc đính kèm ảnh."}), 400

        image_bytes = None
        if image_str:
            img_bytes, mime, err = decode_and_validate_base64_image(image_str)
            if not err:
                image_bytes = img_bytes


        user_id, guest_token = _get_request_identity()
        if not app.config.get("TESTING"):
            from core.security_patch import check_otp_attempts
            client_ip = request.remote_addr or "local"
            intake_rate_key = f"intake_msg:{user_id or guest_token or client_ip}"
            if not check_otp_attempts(intake_rate_key, max_attempts=30):
                return jsonify({"error": "Bạn đang gửi thông tin quá nhanh. Vui lòng thử lại sau ít phút."}), 429

        try:
            result = intake_service.process_message(
                conversation_id=conversation_id,
                message=user_message,
                image_bytes=image_bytes,
                user_id=user_id,
                guest_token=guest_token
            )
        except PermissionError as pe:
            return jsonify({"error": str(pe)}), 403


        return jsonify(result)

    @app.route("/api/intake/update-fact", methods=["POST"])
    def intake_update_fact():
        """Chỉnh sửa 1 dữ kiện lâm sàng (tăng version và yêu cầu xác nhận lại)."""
        data = request.get_json(silent=True) or {}
        conversation_id = data.get("conversation_id")
        field = data.get("field")
        value = data.get("value")

        if not conversation_id or not field:
            return jsonify({"error": "Thiếu conversation_id hoặc trường cần cập nhật."}), 400


        user_id, guest_token = _get_request_identity()
        try:
            res = intake_service.update_fact(
                conversation_id,
                field,
                value,
                user_id=user_id,
                guest_token=guest_token
            )
        except PermissionError as pe:
            return jsonify({"error": str(pe)}), 403


        return jsonify(res)

    @app.route("/api/intake/confirm-summary", methods=["POST"])
    def intake_confirm_summary():
        """Bệnh nhân xác nhận: Bản tóm tắt phản ánh đúng lời khai thực tế."""
        data = request.get_json(silent=True) or {}
        conversation_id = data.get("conversation_id")
        if not conversation_id:
            return jsonify({"error": "Thiếu conversation_id."}), 400


        user_id, guest_token = _get_request_identity()
        try:
            draft = intake_service.get_summary(conversation_id, user_id=user_id, guest_token=guest_token)
        except PermissionError as pe:
            return jsonify({"error": str(pe)}), 403
        if not user_id:
            return jsonify({"error": "Vui lòng đăng nhập để lưu vào hồ sơ."}), 401
        if data.get("save_to_record") is not True:
            return jsonify({"error": "Cần xác nhận lưu bản tóm tắt vào hồ sơ."}), 400
        if (not draft or data.get("version") != draft.get("version")
                or data.get("reviewed_facts") != draft.get("part_a_patient_facts")):
            return jsonify({"error": "Bản nháp đã thay đổi. Hãy xem lại trước khi lưu."}), 409
        if draft.get("ready_to_finalize") is False:
            return jsonify({"error": "Phiếu đang là bản nháp. Hãy bổ sung vị trí đau, thời gian và tính chất hoặc mức độ đau."}), 422
        res = intake_service.confirm_summary(conversation_id, user_id=user_id, guest_token=guest_token)
        if not res.get("success"):
            return jsonify(res), 500
        snapshot = res["summary"]
        if snapshot["version"] != data["version"] or snapshot["part_a_patient_facts"] != data["reviewed_facts"]:
            return jsonify({"error": "Bản nháp đã thay đổi. Hãy xem lại trước khi lưu."}), 409
        facts = snapshot["part_a_patient_facts"]
        assessment = snapshot["part_b_system_assessment"]
        row = ClinicalConsultation.query.filter_by(user_id=user_id, conversation_id=conversation_id).first()
        if row is None:
            row = ClinicalConsultation(user_id=user_id, conversation_id=conversation_id)
            db.session.add(row)
        row.message = facts["chief_complaint"]
        row.answer = assessment["care_approach"]
        row.symptoms = json.dumps(facts["symptoms_present"], ensure_ascii=False)
        row.specialist = assessment["recommended_specialist"]
        row.risk_level = assessment["triage_status"]
        row.is_emergency = assessment["triage_badge"] == "emergency"
        row.confirmed_summary = json.dumps(snapshot, ensure_ascii=False)
        row.turns_json = None
        db.session.commit()
        return jsonify(res)

    @app.route("/api/intake/summary/<conversation_id>", methods=["GET"])
    def intake_get_summary(conversation_id):
        """Lấy bản tóm tắt trước khám 2 phần của phiên."""

        user_id, guest_token = _get_request_identity()
        try:
            summary = intake_service.get_summary(
                conversation_id,
                user_id=user_id,
                guest_token=guest_token
            )
        except PermissionError as pe:
            return jsonify({"error": str(pe)}), 403


        return jsonify({
            "conversation_id": conversation_id,
            "summary": summary
        })


    # ==============================================================
    # HỆ THỐNG QUẢN LÝ TÀI LIỆU Y TẾ & SCAN DATASET (RBAC & SECURE STORAGE)
    # ==============================================================

    @app.route("/api/upload-lab", methods=["POST"])
    def upload_lab():
        """
        Tiếp nhận tệp ảnh / PDF / Word phục vụ scan:
        BẢO MẬT: Bắt buộc đăng nhập, kiểm tra kích thước, magic bytes, lưu UUID ngẫu nhiên và gắn owner_id.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để tải lên tài liệu y tế."}), 401

        if not app.config.get("TESTING"):
            from core.security_patch import check_otp_attempts
            client_ip = request.remote_addr or "local"
            upload_rate_key = f"upload_rate:{user_id or client_ip}"
            if not check_otp_attempts(upload_rate_key, max_attempts=15):
                return jsonify({
                    "status": "error",
                    "message": "Bạn đã gửi yêu cầu tải lên quá nhiều lần liên tiếp. Vui lòng thử lại sau 5 phút."
                }), 429

        if "file" not in request.files:
            return jsonify({"status": "error", "message": "Không tìm thấy tệp đính kèm."}), 400

        file = request.files["file"]
        upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
        success, meta, err_msg = process_secure_upload(file, upload_folder)
        if not success:
            record_security_event(
                "MALICIOUS_FILE_UPLOAD_BLOCKED",
                severity="CRITICAL",
                client_ip=request.remote_addr or "127.0.0.1",
                identifier=str(user_id),
                endpoint="/api/upload-lab",
                status_code=400,
                details={"filename": getattr(file, "filename", ""), "reason": err_msg},
            )
            return jsonify({"status": "error", "message": err_msg}), 400

        try:
            new_doc = MedicalDocument(
                storage_filename=meta["storage_filename"],
                original_filename=meta["original_filename"],
                file_path=meta["file_path"],
                file_size=meta["file_size"],
                file_type=meta["file_type"],
                mime_type=meta["mime_type"],
                owner_id=user_id
            )
            db.session.add(new_doc)
            db.session.commit()

            upload_time = new_doc.created_at.strftime("%H:%M %d/%m/%Y")
            return jsonify({
                "status": "success",
                "document_id": new_doc.id,
                "file_name": new_doc.original_filename,
                "saved_as": new_doc.storage_filename,
                "file_size": new_doc.to_dict()["size"],
                "file_type": new_doc.file_type,
                "uploaded_at": upload_time,
                "message": "Đã lưu tài liệu an toàn vào hồ sơ sức khỏe."
            })
        except Exception as e:
            db.session.rollback()
            if os.path.exists(meta["absolute_path"]):
                try:
                    os.remove(meta["absolute_path"])
                except Exception:
                    pass
            return jsonify({"status": "error", "message": f"Không thể lưu thông tin tài liệu: {e}"}), 500


    @app.route("/api/scan-files", methods=["GET"])
    def get_scan_files():
        """
        Danh sách tài liệu thuộc sở hữu của người dùng hiện tại (owner_id).
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem danh sách tài liệu."}), 401

        docs = MedicalDocument.query.filter_by(owner_id=user_id).order_by(MedicalDocument.created_at.desc()).all()
        files = [d.to_dict() for d in docs]
        return jsonify({"status": "success", "files": files})


    @app.route("/api/scan-files/<doc_identifier>", methods=["DELETE"])
    def delete_scan_file(doc_identifier):
        """
        Xóa tệp khỏi danh sách tài liệu thuộc quyền sở hữu của người dùng.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để thực hiện thao tác."}), 401

        doc = None
        if doc_identifier.isdigit():
            doc = MedicalDocument.query.filter_by(id=int(doc_identifier), owner_id=user_id).first()

        if not doc:
            doc = MedicalDocument.query.filter_by(storage_filename=doc_identifier, owner_id=user_id).first()

        if not doc:
            doc = MedicalDocument.query.filter_by(original_filename=doc_identifier, owner_id=user_id).first()

        if not doc:
            return jsonify({"status": "error", "message": "Tài liệu không tồn tại hoặc bạn không có quyền xóa."}), 404

        upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
        file_disk_path = Path(upload_folder) / doc.storage_filename
        if is_safe_path(file_disk_path, Path(upload_folder)) and file_disk_path.exists():
            try:
                os.remove(file_disk_path)
            except Exception as e:
                logger.warning(f"Lỗi xóa file vật lý: {e}")

        db.session.delete(doc)
        db.session.commit()

        return jsonify({"status": "success", "message": f"Đã xóa tài liệu '{doc.original_filename}' thành công."})


    # ==============================================================
    # QUÉT & PHÂN TÍCH ĐƠN THUỐC / KẾT QUẢ XÉT NGHIỆM AI
    # ==============================================================

    @app.route("/api/prescription/scan", methods=["POST"])
    def scan_prescription():
        """
        Quét và phân tích đơn thuốc hoặc kết quả xét nghiệm:
        BẢO MẬT & TRUNG THỰC:
          - Bắt buộc đăng nhập khi tải file lên; lưu bản ghi MedicalDocument liên kết owner_id.
          - Khi OCR / AI thất bại, trả về status failed/needs_review; không bịa dữ liệu mẫu.
          - Presets chỉ hoạt động khi có tham số 'preset' cụ thể và luôn trả kèm is_demo=True.
          - Nếu không có file và không có preset, trả mã lỗi 400.
        """
        preset = request.args.get("preset") or request.form.get("preset")
        if not preset and request.is_json:
            data = request.get_json(silent=True) or {}
            preset = data.get("preset")

        # 1. Trường hợp người dùng tải tệp lên
        if "file" in request.files:
            user_id = session.get("user_id")
            if not user_id:
                return jsonify({
                    "status": "error",
                    "message": "Vui lòng đăng nhập để tải lên và phân tích tài liệu y tế."
                }), 401

            if not app.config.get("TESTING"):
                from core.security_patch import check_otp_attempts
                client_ip = request.remote_addr or "local"
                scan_rate_key = f"scan_rate:{user_id or client_ip}"
                if not check_otp_attempts(scan_rate_key, max_attempts=10):
                    return jsonify({
                        "status": "error",
                        "message": "Bạn đã gửi yêu cầu phân tích tài liệu quá nhiều lần liên tiếp. Vui lòng thử lại sau 5 phút."
                    }), 429

            file = request.files["file"]
            if not file or file.filename == "":
                return jsonify({"status": "error", "message": "Chưa chọn tệp hợp lệ."}), 400

            upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
            success, meta, err = process_secure_upload(file, upload_folder)
            if not success:
                return jsonify({"status": "failed", "needs_review": True, "message": err}), 400

            # Lưu liên kết chủ sở hữu vào CSDL
            doc_id = None
            try:
                doc = MedicalDocument(
                    storage_filename=meta["storage_filename"],
                    original_filename=meta["original_filename"],
                    file_path=meta["file_path"],
                    file_size=meta["file_size"],
                    file_type=meta["file_type"],
                    mime_type=meta["mime_type"],
                    doc_type="ocr_draft",
                    owner_id=user_id
                )
                db.session.add(doc)
                db.session.commit()
                doc_id = doc.id
            except Exception as e:
                db.session.rollback()
                logger.warning(f"Lỗi lưu MedicalDocument cho scan: {e}")

            mask_pii = request.form.get("mask_pii", "false").lower() in ("true", "1")
            user_obj = db.session.get(User, user_id)
            profile_allergies = (user_obj.to_dict().get("allergies") if user_obj else "") or ""
            user_allergies = [s.strip() for s in profile_allergies.split(",") if s.strip()] if isinstance(profile_allergies, str) else list(profile_allergies)
            req_allergies = request.form.get("allergies")
            if req_allergies:
                user_allergies.extend([a.strip() for a in req_allergies.split(",") if a.strip()])

            res = process_medical_document_pipeline(
                file_path=meta["absolute_path"],
                original_filename=meta["original_filename"],
                mask_pii=mask_pii,
                user_allergies=user_allergies
            )

            if not doc_id:
                return jsonify({"status": "error", "message": "Không tạo được bản nháp."}), 500
            res["document_id"] = doc_id
            if res.get("status") == "review":
                doc.parsed_data = json.dumps({"type": res["doc_type"], "allergies": user_allergies}, ensure_ascii=False)
                db.session.commit()
            return jsonify(res)

        # 2. Trường hợp yêu cầu kịch bản mẫu thử nghiệm (Preset)
        if preset:
            return jsonify(get_preset_data(preset))

        # Không có file và không có preset -> Báo lỗi Bad Request
        return jsonify({
            "status": "error",
            "message": "Vui lòng đính kèm tệp đơn thuốc/xét nghiệm hoặc chỉ định kịch bản mẫu thử nghiệm hợp lệ."
        }), 400


    # ==============================================================
    # QUẢN LÝ LỊCH SỬ TOA THUỐC & PHIẾU XÉT NGHIỆM ĐÃ IMPORT
    # ==============================================================

    @app.post("/api/prescription/<int:doc_id>/confirm")
    def confirm_reviewed_document(doc_id):
        owner = session.get("user_id")
        if not owner:
            return jsonify({"message": "Vui lòng đăng nhập."}), 401
        doc = MedicalDocument.query.filter_by(id=doc_id, owner_id=owner).first_or_404()
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict) or payload.get("confirmed") is not True:
            return jsonify({"message": "Cần xác nhận dữ liệu đã đối chiếu."}), 400
        if doc.doc_type != "ocr_draft" or not doc.parsed_data:
            return jsonify({"message": "Tài liệu không còn chờ xác nhận."}), 409
        draft = json.loads(doc.parsed_data)
        kind = draft["type"]
        key = "medications" if kind == "prescription" else "metrics"
        fields = REVIEW_FIELDS[key]
        rows = payload.get(key)
        if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
            return jsonify({"message": "Cần ít nhất một dòng dữ liệu đã kiểm tra."}), 400
        def clean(row, keys):
            if not isinstance(row, dict) or any(not isinstance(row.get(k, ""), str) or len(row.get(k, "")) > 2000 for k in keys):
                raise ValueError
            return {k: row.get(k, "").strip() for k in keys}
        try:
            reviewed = clean(payload, HEADER_FIELDS)
            reviewed[key] = [clean(row, fields) for row in rows]
            if any(not row[fields[0]] for row in reviewed[key]):
                raise ValueError
        except ValueError:
            return jsonify({"message": "Hãy kiểm tra tên và dữ liệu từng dòng."}), 400
        result = finalize_reviewed_document(reviewed, kind, doc.original_filename, draft["allergies"])
        result["document_id"] = doc.id
        changed = MedicalDocument.query.filter_by(id=doc.id, owner_id=owner, doc_type="ocr_draft").update({
            "doc_type": kind, "diagnosis": reviewed["diagnosis"], "facility": reviewed["facility"],
            "doctor": reviewed["doctor"], "patient_name": reviewed["patient_name"],
            "summary": ", ".join(row[fields[0]] for row in reviewed[key][:3]),
            "parsed_data": json.dumps(result, ensure_ascii=False)})
        if not changed:
            db.session.rollback()
            return jsonify({"message": "Tài liệu đã được xác nhận."}), 409
        db.session.commit()
        return jsonify(result)

    @app.route("/api/prescription/history", methods=["GET"])
    def get_prescription_history():
        """
        Lấy danh sách lịch sử các đơn thuốc và phiếu xét nghiệm mà user đã import:
        Bao gồm thời gian import, chẩn đoán bệnh, tóm tắt thuốc/chỉ số, cơ sở y tế.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem lịch sử hồ sơ."}), 401

        docs = MedicalDocument.query.filter_by(owner_id=user_id).filter(MedicalDocument.doc_type != "ocr_draft").order_by(MedicalDocument.created_at.desc()).all()
        history = [d.to_dict() for d in docs]
        return jsonify({"status": "success", "history": history, "total": len(history)})


    @app.route("/api/prescription/history/<int:doc_id>", methods=["GET"])
    def get_prescription_history_detail(doc_id):
        """
        Xem lại chi tiết toàn bộ dữ liệu đơn thuốc / xét nghiệm đã được bóc tách trước đó.
        Cho phép người dùng xem lại ngay kết quả phân tích mà không cần chụp/quét lại ảnh.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem chi tiết."}), 401

        doc = MedicalDocument.query.filter_by(id=doc_id, owner_id=user_id).first()
        if not doc or doc.doc_type == "ocr_draft":
            return jsonify({"status": "error", "message": "Không tìm thấy hồ sơ hoặc bạn không có quyền xem."}), 404

        if doc.parsed_data:
            try:
                parsed_json = json.loads(doc.parsed_data)
                parsed_json["document_id"] = doc.id
                parsed_json["uploaded_filename"] = doc.original_filename
                parsed_json["uploaded_at"] = doc.created_at.strftime("%H:%M %d/%m/%Y") if doc.created_at else ""
                return jsonify({"status": "success", "data": parsed_json})
            except Exception as json_err:
                logger.warning(f"Lỗi parse JSON doc {doc_id}: {json_err}")

        return jsonify({
            "status": "partial",
            "message": "Đơn thuốc này chưa có dữ liệu bóc tách chi tiết.",
            "doc": doc.to_dict()
        })


    @app.route("/api/prescription/history/<int:doc_id>", methods=["DELETE"])
    def delete_prescription_history_item(doc_id):
        """
        Xóa một đơn thuốc/phiếu xét nghiệm khỏi lịch sử hồ sơ của người dùng.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để thực hiện thao tác."}), 401

        doc = MedicalDocument.query.filter_by(id=doc_id, owner_id=user_id).first()
        if not doc:
            return jsonify({"status": "error", "message": "Tài liệu không tồn tại hoặc bạn không có quyền xóa."}), 404

        upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
        file_disk_path = Path(upload_folder) / doc.storage_filename
        if is_safe_path(file_disk_path, Path(upload_folder)) and file_disk_path.exists():
            try:
                os.remove(file_disk_path)
            except Exception as e:
                logger.warning(f"Lỗi xóa file vật lý: {e}")

        db.session.delete(doc)
        db.session.commit()
        return jsonify({"status": "success", "message": f"Đã xóa thành công '{doc.original_filename}' khỏi lịch sử."})


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
        conversation_id = request.args.get("conversation_id")
        user_id = session.get("user_id")

        if not user_id:
            return jsonify({"error": "Vui lòng đăng nhập để xem hồ sơ."}), 401
        records = ClinicalConsultation.query.filter_by(user_id=user_id).filter(
            ClinicalConsultation.confirmed_summary.isnot(None))
        if conversation_id:
            records = records.filter_by(conversation_id=conversation_id)
        record = records.order_by(ClinicalConsultation.id.desc()).first()
        if record is None:
            return jsonify({"status": "no_data", "message": "Chưa có dữ liệu tư vấn đã xác nhận để hiển thị trong hồ sơ."})
        user_obj = db.session.get(User, user_id)
        return jsonify({"status": "success", "summary": json.loads(record.confirmed_summary),
                        "patient_name": user_obj.full_name if user_obj else "Bệnh nhân",
                        "patient_id": f"BN-2026-{user_id:04d}"})

    @app.route("/api/consultations", methods=["GET"])
    def get_consultations():
        """Lấy danh sách các phiên tư vấn đã lưu của tài khoản hiện tại (VULN-05 RBAC)."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem danh sách phiên tư vấn.", "consultations": []}), 401
        consultations = ClinicalConsultation.query.filter_by(user_id=user_id).filter(ClinicalConsultation.confirmed_summary.isnot(None)).order_by(ClinicalConsultation.created_at.desc()).limit(20).all()
        return jsonify({"status": "success", "consultations": [c.to_dict() for c in consultations]}), 200

    @app.route("/api/consultations/<int:cid>", methods=["DELETE"])
    def delete_consultation(cid):
        """Xóa một phiên tư vấn theo ID của người dùng."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Vui lòng đăng nhập."}), 401
        c = ClinicalConsultation.query.filter_by(id=cid, user_id=user_id).first()
        if c:
            if c.conversation_id:
                try:
                    intake_service.delete_session(c.conversation_id, user_id=user_id,
                                                  guest_token=session.get("guest_token"), commit=False)
                except PermissionError:
                    db.session.rollback()
                    return jsonify({"error": "Không thể xóa phiên tư vấn không thuộc tài khoản này."}), 403
            db.session.delete(c)
            db.session.commit()
            return jsonify({"message": "Đã xóa phiên tư vấn thành công."}), 200
        return jsonify({"error": "Không tìm thấy phiên tư vấn."}), 404


    # ==============================================================
    # HỆ THỐNG ĐẶT LỊCH HẸN KHÁM CƠ SỞ Y TẾ (APPOINTMENT BOOKING)
    # ==============================================================

    @app.route("/api/appointments", methods=["GET"])
    def get_appointments():
        """Lấy danh sách các lịch hẹn khám của tài khoản đang đăng nhập."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"status": "error", "message": "Vui lòng đăng nhập để xem lịch hẹn khám.", "appointments": []}), 401

        appts = MedicalAppointment.query.filter_by(user_id=user_id).order_by(MedicalAppointment.created_at.desc()).all()
        return jsonify({"status": "success", "appointments": [a.to_dict() for a in appts]}), 200

    @app.route("/api/appointments", methods=["POST"])
    def create_appointment():
        """
        Tiếp nhận và lưu trữ lịch hẹn khám chữa bệnh:
        BẢO MẬT: Bắt buộc phiên đăng nhập hợp lệ (Session User ID).
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập hoặc tạo tài khoản để đặt lịch khám."}), 401

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "error": "Dữ liệu đặt lịch không hợp lệ."}), 400

        def _s(key: str, default: str = "", max_len: int = 255) -> str:
            val = data.get(key)
            if val is None:
                return default
            if not isinstance(val, str):
                raise ValueError(f"Trường '{key}' phải là chuỗi ký tự.")
            cleaned = val.strip()
            if len(cleaned) > max_len:
                raise ValueError(f"Trường '{key}' vượt quá độ dài cho phép ({max_len} ký tự).")
            return cleaned or default

        try:
            facility_id = _s("facility_id", "fac_unknown", 100)
            facility_name = _s("facility_name", "Cơ sở Y tế", 255)
            facility_address = _s("facility_address", "", 500)
            specialty = _s("specialty", "Đa khoa", 150)
            appointment_date = _s("appointment_date", "", 30)
            appointment_time = _s("appointment_time", "", 50)
            patient_name = _s("patient_name", "", 150)
            patient_phone = _s("patient_phone", "", 30)
            note = _s("note", "", 1000)
        except ValueError as ve:
            return jsonify({"success": False, "error": str(ve)}), 400

        if not appointment_date or not appointment_time or not patient_name or not patient_phone:
            return jsonify({"success": False, "error": "Vui lòng điền đầy đủ ngày khám, giờ khám, họ tên và số điện thoại."}), 400

        new_appt = MedicalAppointment(
            user_id=user_id,
            facility_id=facility_id,
            facility_name=facility_name,
            facility_address=facility_address,
            specialty=specialty,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            patient_name=patient_name,
            patient_phone=patient_phone,
            note=note,
            status="pending"
        )
        db.session.add(new_appt)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"Đặt lịch khám thành công tại {facility_name}!",
            "appointment": new_appt.to_dict()
        }), 201

    @app.route("/api/appointments/<int:appt_id>", methods=["DELETE"])
    def delete_appointment(appt_id):
        """Hủy một lịch hẹn khám của người dùng."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập."}), 401

        appt = MedicalAppointment.query.filter_by(id=appt_id, user_id=user_id).first()
        if not appt:
            return jsonify({"success": False, "error": "Không tìm thấy lịch hẹn hoặc bạn không có quyền hủy."}), 404

        db.session.delete(appt)
        db.session.commit()
        return jsonify({"success": True, "message": "Đã hủy lịch hẹn khám thành công."}), 200

    # ==============================================================
    # GIAO DIỆN NGƯỜI DÙNG WEB (UI)
    # ==============================================================

    @app.get("/openapi.json")
    def api_spec():
        import re

        paths = {}
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/api/") or rule.rule.startswith("/api/monitoring"):
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
        return render_template("api_docs.html", paths=api_spec().get_json()["paths"])

    @app.route("/api/nutrition/options", methods=["POST"])
    def nutrition_options():
        """Trả về danh sách món hoặc thức uống để người dùng tự chọn."""
        payload = request.get_json(silent=True) or {}
        condition = str(payload.get("condition") or "").strip()
        recipe_type = payload.get("recipe_type")
        if not condition:
            return jsonify({"success": False, "error": "Vui lòng nhập tâm trạng hoặc tình trạng sức khỏe."}), 400
        if len(condition) > 500:
            return jsonify({"success": False, "error": "Vui lòng mô tả tình trạng trong tối đa 500 ký tự."}), 400
        if recipe_type not in ("food", "drink"):
            return jsonify({"success": False, "error": "Vui lòng chọn thức ăn hoặc nước uống."}), 400
        exclude_ids = payload.get("exclude_recipe_ids", [])
        if (not isinstance(exclude_ids, list) or len(exclude_ids) > 5000
                or any(not isinstance(item, str) or len(item) > 100 for item in exclude_ids)):
            return jsonify({"success": False, "error": "Danh sách món đã xem không hợp lệ."}), 400
        from core.nutrition_options import get_nutrition_options
        return jsonify({"success": True, "data": get_nutrition_options(condition, recipe_type, exclude_ids)}), 200

    @app.route("/api/nutrition/analyze", methods=["POST"])
    def analyze_nutrition():
        """
        API Phân tích Dinh dưỡng Lâm sàng & Pha chế Bữa ăn Trị liệu theo Thể trạng.
        Nhận vào tên bệnh hoặc thể trạng (từ người dùng nhập) và trả về:
        - foods_to_eat (Nên nạp)
        - foods_to_avoid (Nên né)
        - recipe (Công thức 3 bước)
        """
        data = request.get_json(silent=True) or {}
        condition = (data.get("condition") or data.get("query") or "").strip()
        recipe_type = "drink" if data.get("recipe_type") == "drink" else "food"
        if not condition:
            return jsonify({"success": False, "error": "Vui lòng nhập tên bệnh lý hoặc thể trạng."}), 400

        from core.nutrition_service import get_nutrition_recommendation
        try:
            result = get_nutrition_recommendation(condition, recipe_type)
            return jsonify({"success": True, "data": result}), 200
        except Exception as e:
            logger.error(f"Lỗi phân tích dinh dưỡng: {e}")
            return jsonify({"success": False, "error": "Không thể phân tích dinh dưỡng lúc này."}), 500

    FACILITIES_DATA_FILE = os.path.join(
        os.path.dirname(__file__), "data", "CSKCB_Data", "danh_sach_co_so_kcb_normalized.json"
    )

    _FACILITIES_CACHE = None
    _FACILITIES_INDEX = None
    _FACILITIES_FILTERS_CACHE = None
    _FACILITIES_MARKERS_CACHE = None

    def load_facilities_data():
        # ponytail: in-memory pre-indexed cache for 1,505 static facilities; move to SQLite FTS5 when >50k rows
        nonlocal _FACILITIES_CACHE, _FACILITIES_INDEX, _FACILITIES_FILTERS_CACHE, _FACILITIES_MARKERS_CACHE
        if _FACILITIES_CACHE is None:
            if os.path.exists(FACILITIES_DATA_FILE):
                try:
                    with open(FACILITIES_DATA_FILE, "r", encoding="utf-8") as f:
                        _FACILITIES_CACHE = json.load(f)
                except Exception as e:
                    logger.error(f"Lỗi khi đọc file dữ liệu cơ sở y tế: {e}")
                    _FACILITIES_CACHE = []
            else:
                logger.warning(f"File cơ sở y tế không tồn tại: {FACILITIES_DATA_FILE}")
                _FACILITIES_CACHE = []

            index_entries = []
            type_counts = {}
            district_counts = {}
            spec_counts = {}
            markers = []

            for x in _FACILITIES_CACHE:
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

                lat = x.get("lat")
                lng = x.get("lng")
                if lat is not None and lng is not None:
                    markers.append({
                        "id": str(x.get("id")),
                        "name": x.get("ten_ngan") or x.get("ten"),
                        "type": x.get("loai_hinh") or "",
                        "spec": ck_str,
                        "address": x.get("dia_chi_hien_thi_tren_web") or x.get("dia_chi") or "",
                        "lat": float(lat),
                        "lng": float(lng),
                        "link": x.get("link") or ""
                    })

                search_blob = " ".join([
                    (x.get("ten") or ""),
                    (x.get("ten_ngan") or ""),
                    (x.get("dia_chi") or ""),
                    (x.get("dia_chi_hien_thi_tren_web") or ""),
                    ck_str,
                    " ".join(x.get("tags") or []),
                ]).lower()

                index_entries.append((
                    x,
                    (x.get("loai_hinh") or "").lower(),
                    ck_str.lower(),
                    (x.get("quan_huyen") or "").lower(),
                    search_blob,
                ))

            _FACILITIES_INDEX = index_entries
            _FACILITIES_FILTERS_CACHE = {
                "success": True,
                "total": len(_FACILITIES_CACHE),
                "loai_hinh": type_counts,
                "quan_huyen": sorted(district_counts.items(), key=lambda item: item[0]),
                "chuyen_khoa": sorted(spec_counts.items(), key=lambda item: item[1], reverse=True)[:15],
            }
            _FACILITIES_MARKERS_CACHE = {
                "success": True,
                "total": len(markers),
                "markers": markers,
            }
        return _FACILITIES_CACHE

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
        """
        load_facilities_data()

        page = max(1, request.args.get("page", 1, type=int))
        limit = min(50, max(1, request.args.get("limit", 12, type=int)))
        search = request.args.get("search", "").strip().lower()
        loai_hinh = request.args.get("loai_hinh", "").strip().lower()
        chuyen_khoa = request.args.get("chuyen_khoa", "").strip().lower()
        quan_huyen = request.args.get("quan_huyen", "").strip().lower()

        use_lh = bool(loai_hinh and loai_hinh != "all")
        use_ck = bool(chuyen_khoa and chuyen_khoa != "all")
        use_qh = bool(quan_huyen and quan_huyen != "all")
        use_s = bool(search)

        if not (use_lh or use_ck or use_qh or use_s):
            filtered = _FACILITIES_CACHE
        else:
            filtered = [
                item for item, lh_l, ck_l, qh_l, s_blob in _FACILITIES_INDEX
                if (not use_lh or loai_hinh in lh_l)
                and (not use_ck or chuyen_khoa in ck_l)
                and (not use_qh or quan_huyen in qh_l)
                and (not use_s or search in s_blob)
            ]

        total = len(filtered)
        total_pages = max(1, (total + limit - 1) // limit)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        items = filtered[start_idx:end_idx]

        return jsonify({
            "success": True,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "data": items
        })

    @app.route("/api/facilities/filters", methods=["GET"])
    def get_facilities_filters():
        """Trả về thống kê số lượng loại hình, chuyên khoa và quận huyện thực tế (O(1) precomputed)."""
        load_facilities_data()
        return jsonify(_FACILITIES_FILTERS_CACHE)

    @app.route("/api/facilities/map-markers", methods=["GET"])
    def get_facilities_map_markers():
        """Trả về dữ liệu tinh gọn của tất cả cơ sở có tọa độ để vẽ markers lên bản đồ (O(1) precomputed)."""
        load_facilities_data()
        return jsonify(_FACILITIES_MARKERS_CACHE)

    @app.route("/api/config/maps", methods=["GET"])
    def get_maps_config():
        """Cung cấp cấu hình Google Maps API cho frontend."""
        key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
        return jsonify({
            "has_key": bool(key),
            "key": key if key else ""
        })

    @app.route("/")
    def index():
        """Trang chủ ứng dụng y tế MediMind."""
        return render_template("index.html", google_maps_api_key=os.getenv("GOOGLE_MAPS_API_KEY", "").strip())

    # ==============================================================
    # HYBRID SECURITY OBSERVABILITY & SIEM (PROMETHEUS + WAZUH)
    # ==============================================================

    @app.errorhandler(500)
    def internal_server_error_handler(e):
        """Ghi nhận ngoại lệ 500 vào luồng Wazuh SIEM JSON Audit Log và Prometheus."""
        record_security_event(
            "UNHANDLED_SERVER_ERROR",
            severity="CRITICAL",
            client_ip=request.remote_addr or "127.0.0.1",
            endpoint=request.path,
            status_code=500,
            details={"exception": type(e).__name__, "error": str(e)[:200]},
        )
        return jsonify({
            "status": "error",
            "error": "Đã xảy ra sự cố nội bộ máy chủ."
        }), 500

    @app.route("/metrics", methods=["GET"])
    def prometheus_metrics():
        """Cổng Scraping chuẩn OpenMetrics cho Prometheus TSDB & Grafana."""
        client_ip = request.remote_addr or ""
        expected_key = os.getenv("PROMETHEUS_SCRAPE_KEY", os.getenv("ADMIN_MONITORING_KEY", ""))
        req_key = request.headers.get("X-Metrics-Key") or request.headers.get("X-Admin-Key") or request.args.get("key")
        is_internal = (
            client_ip in ("127.0.0.1", "::1", "localhost", "testclient")
            or client_ip.startswith(("10.", "172.", "192.168."))
        )
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

if __name__ == "__main__":
    try:
        from werkzeug.serving import WSGIRequestHandler
        WSGIRequestHandler.server_version = ""
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
