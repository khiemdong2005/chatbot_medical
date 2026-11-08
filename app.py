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
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv

# Tải cấu hình môi trường (.env)
load_dotenv()

# Nạp cơ sở dữ liệu và các mô hình
from core.models import db, User, MedicalDocument, ClinicalConsultation, MedicalAppointment, init_db
from core.otp_service import otp_manager
from core.storage_service import (
    process_secure_upload,
    decode_and_validate_base64_image,
    is_safe_path
)
from core.chat_service import process_clinical_chat
from core.gemini_service import GeminiMedicalService
from core.prescription_service import get_preset_data, analyze_uploaded_document
from core.intake_service import intake_service
from core.pipeline_orchestrator import HEADER_FIELDS, REVIEW_FIELDS, finalize_reviewed_document, process_medical_document_pipeline

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



def valid_birth_date(value, formats=("%d/%m/%Y",)):
    for fmt in formats:
        try:
            if datetime.strptime(value, fmt).strftime(fmt) == value:
                return True
        except ValueError:
            continue
    return False


def find_login_user(identifier):
    if "@" in identifier:
        # Prefer the exact spelling for legacy accounts that differ only by case.
        exact = User.query.filter_by(email=identifier).first()
        if exact:
            return exact
        matches = User.query.filter(db.func.lower(User.email) == identifier.lower()).limit(2).all()
        return matches[0] if len(matches) == 1 else None
    phone = "".join(filter(str.isdigit, identifier))
    if not phone:
        return None
    return User.query.filter(
        (User.phone_number == identifier) | (User.phone_number == phone) |
        (User.email == f"{phone}@phone.medimind")
    ).first()


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
    app.config["JSON_AS_ASCII"] = False

    # Cấu hình Cookie an toàn bảo vệ Session
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = is_prod or (os.getenv("SESSION_COOKIE_SECURE", "false").lower() in ("true", "1"))
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # Giới hạn 16MB chống tràn bộ nhớ DoS (VULN-04)

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
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://accounts.google.com/gsi/client https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
            "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data: blob: https://*.googleusercontent.com https://images.unsplash.com; "
            "connect-src 'self' https://accounts.google.com/gsi/; "
            "frame-src 'self' https://accounts.google.com/gsi/; "
            "base-uri 'self';"
        )
        response.headers.setdefault("Content-Security-Policy", csp_policy)

        if is_prod or request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

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
        """Đăng nhập hệ thống: Xác thực Email/Số điện thoại và Mật khẩu băm trong CSDL."""
        data = request.get_json(silent=True) or {}
        raw_identifier = (data.get("identifier") or data.get("email") or "").strip()
        password = data.get("password", "").strip()
        role = data.get("role")

        if not raw_identifier or not password:
            return jsonify({"success": False, "error": "Vui lòng nhập định danh tài khoản và mật khẩu."}), 400

        from core.security_patch import check_otp_attempts, reset_otp_attempts
        rate_key = f"login:{raw_identifier.lower()}"
        if not check_otp_attempts(rate_key, max_attempts=5):
            return jsonify({
                "success": False,
                "error": "Tài khoản tạm khóa 5 phút do nhập sai mật khẩu quá 5 lần liên tiếp. Vui lòng thử lại sau."
            }), 429

        user = find_login_user(raw_identifier)

        if not user:
            return jsonify({"success": False, "error": "Tài khoản không tồn tại trên hệ thống."}), 404

        # Kiểm tra phân quyền truy cập
        if role and user.role != role:
            return jsonify({
                "success": False, 
                "error": f"Tài khoản này không có quyền truy cập vai trò '{role}'."
            }), 403

        # Xác thực mật khẩu
        if not user.check_password(password):
            return jsonify({"success": False, "error": "Mật khẩu không chính xác. Vui lòng kiểm tra lại."}), 401

        # Xóa bộ đếm sai mật khẩu sau khi đăng nhập thành công
        reset_otp_attempts(rate_key)

        # Khởi tạo phiên làm việc (Session)
        session["user_id"] = user.id
        session["user_role"] = user.role

        return jsonify({
            "success": True,
            "message": f"Chào mừng {user.full_name} đã quay trở lại!",
            "user": user.to_dict()
        })


    @app.route("/api/auth/register", methods=["POST"])
    def auth_register():
        """
        Đăng ký tài khoản người dùng:
        BẢO MẬT: Luôn tạo tài khoản với vai trò 'patient' (bệnh nhân).
        Tuyệt đối không cho phép client tự cấp quyền doctor hay admin.
        Đã trang bị Rate Limiting chống rải bom tạo tài khoản rác (DoS).
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
        raw_identifier = (data.get("identifier") or data.get("email") or "").strip()
        password = data.get("password", "").strip()
        full_name = data.get("full_name", "").strip() or data.get("name", "").strip()
        phone_number = data.get("phone_number", "").strip()
        dob = data.get("dob", "").strip()
        if dob and not valid_birth_date(dob, ("%d/%m/%Y", "%Y-%m-%d")):
            return jsonify({"success": False, "error": "Ngày sinh phải đúng định dạng DD/MM/YYYY (VD: 15/08/1995)."}), 400
        gender = data.get("gender", "").strip() or "Nam"

        # Bắt buộc vai trò là patient
        role = "patient"

        if not raw_identifier or not password:
            return jsonify({"success": False, "error": "Vui lòng điền đầy đủ Email/SĐT và mật khẩu."}), 400

        if not full_name:
            full_name = "Bệnh nhân mới"

        if "@" in raw_identifier:
            email = raw_identifier.lower()
            if not phone_number:
                phone_number = None
        else:
            clean_phone = "".join(filter(str.isdigit, raw_identifier))
            if len(clean_phone) < 9 or len(clean_phone) > 11:
                return jsonify({"success": False, "error": "Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số)."}), 400
            phone_number = clean_phone
            email = f"{clean_phone}@phone.medimind"

        existing_user = User.query.filter(
            (db.func.lower(User.email) == email.lower()) |
            ((User.phone_number == phone_number) & (User.phone_number.isnot(None)))
        ).first()
        if existing_user:
            return jsonify({"success": False, "error": "Tài khoản (Email hoặc Số điện thoại) này đã được sử dụng."}), 409

        if not app.config.get("TESTING"):
            reg_channel = "email" if "@" in raw_identifier else "sms"
            reg_id = email if reg_channel == "email" else phone_number
            if not otp_manager.is_verified(reg_id, reg_channel, consume=True):
                return jsonify({
                    "success": False,
                    "error": "Vui lòng xác thực mã OTP 6 số trước khi tạo tài khoản."
                }), 403

        new_user = User(
            email=email,
            full_name=full_name,
            role=role,
            phone_number=phone_number,
            dob=dob,
            gender=gender,
            license_code=None
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

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
        if not user:
            session.clear()
            return jsonify({"authenticated": False, "user": None})

        return jsonify({"authenticated": True, "user": user.to_dict()})


    @app.route("/api/auth/profile", methods=["POST", "PUT"])
    def auth_update_profile():
        """
        Cập nhật thông tin cá nhân:
        BẢO MẬT: Bắt buộc session đăng nhập hợp lệ. Bỏ fallback lấy id từ JSON body.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập để cập nhật thông tin."}), 401

        user = db.session.get(User, user_id)
        if not user:
            session.clear()
            return jsonify({"success": False, "error": "Không tìm thấy thông tin tài khoản."}), 404

        data = request.get_json(silent=True) or {}
        full_name = data.get("name", "").strip() or data.get("full_name", "").strip()
        gender = data.get("gender", "").strip()
        dob = data.get("dob", "").strip()
        phone_number = data.get("phone_number", "").strip()
        address = data.get("address", "").strip()
        bhyt = data.get("bhyt", "").strip()
        email = data.get("email", "").strip()

        if full_name:
            user.full_name = full_name
        if gender:
            user.gender = gender
        if dob:
            if not valid_birth_date(dob):
                return jsonify({"success": False, "error": "Ngày sinh phải đúng định dạng DD/MM/YYYY (VD: 15/08/1995)."}), 400
            user.dob = dob
        if phone_number:
            clean_phone = "".join(filter(str.isdigit, phone_number))
            if len(clean_phone) < 9 or len(clean_phone) > 11:
                return jsonify({"success": False, "error": "Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số)."}), 400
            if clean_phone:
                dup_phone = User.query.filter(
                    (User.id != user.id) &
                    ((User.phone_number == clean_phone) | (User.email == f"{clean_phone}@phone.medimind"))
                ).first()
                if dup_phone:
                    return jsonify({"success": False, "error": "Số điện thoại này đã được liên kết với một tài khoản khác."}), 409
                user.phone_number = clean_phone
        if "address" in data:
            user.address = address
        if bhyt:
            user.bhyt = bhyt
        if email and "@" in email and not email.endswith("@phone.medimind"):
            dup_email = User.query.filter((User.id != user.id) & (db.func.lower(User.email) == email.lower())).first()
            if dup_email:
                return jsonify({"success": False, "error": "Địa chỉ Email này đã được sử dụng bởi một tài khoản khác."}), 409
            user.email = email

        # Luu toan bo ho so mo rong vao JSON clinical_profile
        extra_profile = json.loads(user.clinical_profile or "{}")
        profile_fields = (
            "ethnicity", "religion", "province", "ward", "address", "cccd",
            "issue_date", "issue_place", "facility", "valid_from", "valid_to",
            "nationality", "blood_type", "allergies", "height", "weight",
        )
        for field in profile_fields:
            if field in data:
                extra_profile[field] = data[field].strip()
        if not extra_profile.get("nationality"):
            extra_profile["nationality"] = "VN"
        user.clinical_profile = json.dumps(extra_profile, ensure_ascii=False)

        try:
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
        current_password = (data.get("current_password") or "").strip()
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


    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        """Đăng xuất và hủy phiên làm việc."""
        session.clear()
        return jsonify({"success": True, "message": "Đã đăng xuất thành công."})

    # ==============================================================
    # HỆ THỐNG XÁC THỰC OTP (EMAIL / SMS) & GOOGLE OAUTH 2.0
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

        # Tự động nhận diện kênh gửi nếu client không truyền channel
        if not channel:
            channel = "email" if "@" in identifier else "sms"

        if channel == "email":
            if "@" not in identifier:
                return jsonify({"success": False, "error": "Địa chỉ email không hợp lệ."}), 400
        else:
            clean_phone = "".join(filter(str.isdigit, identifier))
            if len(clean_phone) < 9 or len(clean_phone) > 11:
                return jsonify({"success": False, "error": "Số điện thoại không hợp lệ (9-11 chữ số)."}), 400
            identifier = clean_phone

        # Kiểm tra sự tồn tại của tài khoản trước khi bắn mã OTP (BUG-01)
        if purpose == "register":
            dup_acc = User.query.filter(
                (db.func.lower(User.email) == identifier.lower()) |
                ((User.phone_number == identifier) & (User.phone_number.isnot(None))) |
                (User.email == f"{identifier}@phone.medimind")
            ).first()
            if dup_acc:
                return jsonify({
                    "success": False,
                    "error": "Email hoặc Số điện thoại này đã được đăng ký. Vui lòng chuyển sang tab Đăng nhập!"
                }), 409
        elif purpose == "login_2fa":
            exist_acc = User.query.filter(
                (db.func.lower(User.email) == identifier.lower()) |
                (User.phone_number == identifier) |
                (User.email == f"{identifier}@phone.medimind")
            ).first()
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



        return jsonify(res_data)


    @app.route("/api/auth/otp/verify", methods=["POST"])
    def auth_verify_otp():
        """
        Xác minh mã OTP 6 số:
        Hỗ trợ:
          - purpose='register': Xác thực OTP và khởi tạo tài khoản bệnh nhân an toàn
          - purpose='login_2fa': Xác thực OTP và đăng nhập cấp session
          - purpose='verify': Xác minh chung
        """
        data = request.get_json(silent=True) or {}
        identifier = (data.get("identifier") or "").strip()
        channel = (data.get("channel") or "").strip().lower()
        code = (data.get("code") or "").strip()
        purpose = (data.get("purpose") or "register").strip()
        user_data = data.get("user_data") or {}

        if not identifier or not code:
            return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ thông tin và mã OTP 6 chữ số."}), 400

        if not channel:
            channel = "email" if "@" in identifier else "sms"

        if channel == "sms":
            identifier = "".join(filter(str.isdigit, identifier))

        dob = (user_data.get("dob") or "").strip()
        if purpose == "register" and dob and not valid_birth_date(dob, ("%d/%m/%Y", "%Y-%m-%d")):
            return jsonify({"success": False, "error": "Ngày sinh phải đúng định dạng DD/MM/YYYY (VD: 15/08/1995)."}), 400

        success, err_msg = otp_manager.verify_otp(
            identifier=identifier,
            channel=channel,
            code=code,
            purpose=purpose
        )

        if not success:
            return jsonify({"success": False, "error": err_msg}), 400

        # Nếu là kịch bản Đăng ký (Register with OTP)
        if purpose == "register" and user_data:
            full_name = (user_data.get("full_name") or user_data.get("name") or "Bệnh nhân mới").strip()
            password = (user_data.get("password") or "").strip()
            gender = (user_data.get("gender") or "Nam").strip()

            if channel == "email":
                email = identifier.lower()
                phone_number = (user_data.get("phone_number") or "").strip() or None
            else:
                phone_number = identifier
                email = f"{identifier}@phone.medimind"

            # Kiểm tra tài khoản đã tồn tại chưa
            existing = User.query.filter(
                (db.func.lower(User.email) == email.lower()) |
                ((User.phone_number == phone_number) & (User.phone_number.isnot(None)))
            ).first()
            if existing:
                return jsonify({"success": False, "error": "Tài khoản này đã tồn tại trên hệ thống."}), 409

            if not password:
                import secrets
                password = secrets.token_urlsafe(12)

            new_user = User(
                email=email,
                full_name=full_name,
                role="patient",
                phone_number=phone_number,
                dob=dob,
                gender=gender
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()

            session["user_id"] = new_user.id
            session["user_role"] = new_user.role

            return jsonify({
                "success": True,
                "message": "Xác thực danh tính và đăng ký tài khoản thành công!",
                "user": new_user.to_dict()
            }), 201

        # Nếu là kịch bản Đăng nhập 2FA (2FA Login)
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


    def _create_google_oauth_state(intent: str = "login") -> str:
        import base64
        import hashlib
        import hmac
        import secrets
        import time

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
        import time

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
        """
        Khởi tạo luồng Google OAuth 2.0 Authorization Code (PKCE/State) chuẩn giống ForumFlash:
          - Nhận intent ('login' hoặc 'register')
          - Buộc hiển thị bảng chọn tài khoản thật của Google (prompt=select_account)
          - Hỗ trợ trả JSON (?format=json) cho pre-flight check hoặc Redirect 302 trực tiếp.
        """
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
        Callback nhận Authorization Code từ Google OAuth 2.0:
          - Xác thực chữ ký HMAC state chống CSRF
          - Đổi code lấy access_token & id_token (tự động retry 1 lần nếu mạng chập chờn)
          - Lấy hồ sơ xác thực từ Google UserInfo API
          - Phân nhánh Đăng nhập vs Đăng ký & kiểm tra hoàn tất hồ sơ (Onboarding)
        """
        import secrets
        import urllib.request
        import urllib.parse
        import urllib.error

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

        email = (user_info.get("email") or "").strip().lower()
        full_name = (user_info.get("name") or "").strip()
        avatar_url = (user_info.get("picture") or "").strip()

        if not email or "@" not in email:
            return redirect("/?google_auth=error&error_reason=invalid_email")

        if not full_name:
            full_name = email.split("@")[0].capitalize()

        user = User.query.filter_by(email=email).first()

        # TRƯỜNG HỢP 1: TỪ LẦN THỨ 2 TRỞ ĐI (Tài khoản Google đã có trong CSDL -> Vào luôn ngay lập tức)
        if user:
            if avatar_url:
                user.avatar_url = avatar_url
            if full_name and (not user.full_name or user.full_name == "Bệnh nhân mới"):
                user.full_name = full_name
            db.session.commit()

            session.pop("pending_google_register", None)
            session["user_id"] = user.id
            session["user_role"] = user.role

            query_out = {
                "google_auth": "success",
                "existing": "1",
            }
            return redirect(f"/?{urllib.parse.urlencode(query_out)}")

        # TRƯỜNG HỢP 2: LẦN ĐẦU TIÊN SỬ DỤNG GOOGLE (Chưa có trong CSDL -> Chuyển vào bước xác nhận thông tin)
        session["pending_google_register"] = {
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
        """Hoàn tất thông tin đăng ký Google và chính thức INSERT vào CSDL."""
        import secrets

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
        clean_phone = "".join(filter(str.isdigit, raw_phone))

        if not full_name:
            full_name = pending.get("full_name") or pending["email"].split("@")[0].capitalize()
        if clean_phone and (len(clean_phone) < 9 or len(clean_phone) > 11):
            return jsonify({"success": False, "error": "Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số)."}), 400

        email = pending["email"].strip().lower()
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            session.pop("pending_google_register", None)
            session["user_id"] = existing_user.id
            session["user_role"] = existing_user.role
            return jsonify({"success": True, "user": existing_user.to_dict()})

        dup_phone = User.query.filter(
            (User.phone_number == clean_phone) | (User.email == f"{clean_phone}@phone.medimind")
        ).first()
        if dup_phone:
            return jsonify({"success": False, "error": "Số điện thoại này đã được liên kết với một tài khoản khác."}), 409

        user = User(
            email=email,
            full_name=full_name,
            role="patient",
            gender=gender,
            dob=dob or None,
            phone_number=clean_phone or None,
            avatar_url=pending.get("avatar_url") or None
        )
        user.set_password(secrets.token_urlsafe(24))
        db.session.add(user)
        db.session.commit()

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
        Cổng xác thực Google ID Token (Đã khóa chống giả mạo email trần - VULN-01):
        Khi đã cấu hình GOOGLE_CLIENT_ID thực tế, bắt buộc xác minh chữ ký ID Token với máy chủ Google.
        """
        import urllib.request
        import urllib.parse

        client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
        data = request.get_json(silent=True) or {}
        credential = data.get("credential")

        if client_id and not app.config.get("ALLOW_LEGACY_GOOGLE_MOCK"):
            if not credential or not isinstance(credential, str):
                return jsonify({
                    "success": False,
                    "error": "Cổng giả lập đã khóa bảo mật. Vui lòng đăng nhập qua Google OAuth 2.0 chính thức (/api/auth/google/login)."
                }), 403
            try:
                verify_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(credential)}"
                with urllib.request.urlopen(verify_url, timeout=8) as resp:
                    token_info = json.loads(resp.read().decode("utf-8"))
                if token_info.get("aud") != client_id:
                    return jsonify({"success": False, "error": "Google ID Token không thuộc ứng dụng MediMind."}), 403
                email = (token_info.get("email") or "").strip().lower()
                full_name = (token_info.get("name") or "").strip()
                avatar_url = (token_info.get("picture") or "").strip()
            except Exception as ex:
                logger.warning(f"Xác thực Google ID Token thất bại: {ex}")
                return jsonify({"success": False, "error": "Google ID Token không hợp lệ hoặc đã hết hạn."}), 401
        else:
            email = (data.get("email") or "").strip().lower()
            full_name = (data.get("name") or "").strip()
            avatar_url = (data.get("avatar_url") or data.get("picture") or "").strip()



        if not email or "@" not in email:
            return jsonify({"success": False, "error": "Email Google không hợp lệ hoặc không được cung cấp."}), 400

        if not full_name:
            full_name = email.split("@")[0].capitalize()

        # Tìm hoặc tạo người dùng
        user = User.query.filter_by(email=email).first()
        if user:
            # Đồng bộ lại Avatar và Họ tên từ Google nếu chưa có
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
            if full_name and (not user.full_name or user.full_name == "Bệnh nhân mới"):
                user.full_name = full_name
            db.session.commit()
        else:
            user = User(
                email=email,
                full_name=full_name,
                role="patient",
                avatar_url=avatar_url or None
            )
            user.set_password(secrets.token_urlsafe(24))
            db.session.add(user)
            db.session.commit()

        # Khởi tạo Session
        session["user_id"] = user.id
        session["user_role"] = user.role

        return jsonify({
            "success": True,
            "message": f"Đăng nhập thành công với tài khoản Google ({user.email})!",
            "user": user.to_dict()
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
        data = request.get_json(silent=True) or {}
        user_message = data.get("message", "").strip()
        history = data.get("history", [])
        image_str = data.get("image")
        lang = data.get("lang", "vi")
        conversation_id = data.get("conversation_id")
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
                intake_facts=(intake_res or {}).get("facts")
            )

            # 2. HỢP NHẤT DỮ LIỆU ĐÁNH GIÁ (TRÁNH LỆCH PHA GIỮA CHAT VÀ TÓM TẮT)
            if intake_res:
                res["conversation_id"] = conversation_id
                res["intake"] = intake_res
                res["intake_facts"] = intake_res.get("facts")
                res["intake_summary"] = intake_res.get("summary")
                res["intake_status"] = intake_res.get("status")

            return jsonify(res)

        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            logger.error(f"Lỗi xử lý tư vấn y tế: {e}")
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

        if "file" not in request.files:
            return jsonify({"status": "error", "message": "Không tìm thấy tệp đính kèm."}), 400

        file = request.files["file"]
        upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
        success, meta, err_msg = process_secure_upload(file, upload_folder)
        if not success:
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
            profile_allergies = db.session.get(User, user_id).to_dict().get("allergies") or ""
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
        return jsonify({"status": "success", "summary": json.loads(record.confirmed_summary),
                        "patient_name": db.session.get(User, user_id).full_name,
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

        data = request.get_json(silent=True) or {}
        facility_id = (data.get("facility_id") or "fac_unknown").strip()
        facility_name = (data.get("facility_name") or "Cơ sở Y tế").strip()
        facility_address = (data.get("facility_address") or "").strip()
        specialty = (data.get("specialty") or "Đa khoa").strip()
        appointment_date = (data.get("appointment_date") or "").strip()
        appointment_time = (data.get("appointment_time") or "").strip()
        patient_name = (data.get("patient_name") or "").strip()
        patient_phone = (data.get("patient_phone") or "").strip()
        note = (data.get("note") or "").strip()

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

    @app.route("/")
    def index():
        """Trang chủ ứng dụng y tế MediMind."""
        return render_template("index.html")

    app.wsgi_app = ServerMaskMiddleware(app.wsgi_app)
    return app


# Export singleton app instance for WSGI / CLI
app = create_app()

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
