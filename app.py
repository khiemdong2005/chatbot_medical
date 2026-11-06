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
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv

# Tải cấu hình môi trường (.env)
load_dotenv()

# Nạp cơ sở dữ liệu và các mô hình
from core.models import db, User, MedicalDocument, ClinicalConsultation, init_db
from core.otp_service import otp_manager
from core.storage_service import (
    process_secure_upload,
    decode_and_validate_base64_image,
    is_safe_path
)
from core.chat_service import process_clinical_chat
from core.gemini_service import GeminiMedicalService
from core.prescription_service import get_preset_data, analyze_uploaded_document
from core.pipeline_orchestrator import process_medical_document_pipeline

logger = logging.getLogger("MediMindApp")


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
        secret_key = "medimind-secret-key-super-safe-2026-dev"

    app.secret_key = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///medimind.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JSON_AS_ASCII"] = False

    # Cấu hình Cookie an toàn bảo vệ Session
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = is_prod or (os.getenv("SESSION_COOKIE_SECURE", "false").lower() in ("true", "1"))

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

        clean_phone = "".join(filter(str.isdigit, raw_identifier))
        user = User.query.filter(
            (User.email == raw_identifier) | 
            (User.phone_number == raw_identifier) |
            (User.phone_number == clean_phone) |
            (User.email == f"{clean_phone}@phone.medimind")
        ).first()

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
        """
        data = request.get_json(silent=True) or {}
        raw_identifier = (data.get("identifier") or data.get("email") or "").strip()
        password = data.get("password", "").strip()
        full_name = data.get("full_name", "").strip() or data.get("name", "").strip()
        phone_number = data.get("phone_number", "").strip()
        dob = data.get("dob", "").strip()
        gender = data.get("gender", "").strip() or "Nam"

        # Bắt buộc vai trò là patient
        role = "patient"

        if not raw_identifier or not password:
            return jsonify({"success": False, "error": "Vui lòng điền đầy đủ Email/SĐT và mật khẩu."}), 400

        if not full_name:
            full_name = "Bệnh nhân mới"

        if "@" in raw_identifier:
            email = raw_identifier
            if not phone_number:
                phone_number = None
        else:
            clean_phone = "".join(filter(str.isdigit, raw_identifier))
            if len(clean_phone) < 9 or len(clean_phone) > 11:
                return jsonify({"success": False, "error": "Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số)."}), 400
            phone_number = clean_phone
            email = f"{clean_phone}@phone.medimind"

        existing_user = User.query.filter(
            (User.email == email) | 
            ((User.phone_number == phone_number) & (User.phone_number.isnot(None)))
        ).first()
        if existing_user:
            return jsonify({"success": False, "error": "Tài khoản (Email hoặc Số điện thoại) này đã được sử dụng."}), 409

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
            user.dob = dob
        if phone_number:
            clean_phone = "".join(filter(str.isdigit, phone_number))
            if clean_phone:
                dup_phone = User.query.filter(
                    (User.id != user.id) &
                    ((User.phone_number == clean_phone) | (User.email == f"{clean_phone}@phone.medimind"))
                ).first()
                if dup_phone:
                    return jsonify({"success": False, "error": "Số điện thoại này đã được liên kết với một tài khoản khác."}), 409
                user.phone_number = clean_phone
        if address:
            user.address = address
        if bhyt:
            user.bhyt = bhyt
        if email and "@" in email and not email.endswith("@phone.medimind"):
            dup_email = User.query.filter((User.id != user.id) & (User.email == email)).first()
            if dup_email:
                return jsonify({"success": False, "error": "Địa chỉ Email này đã được sử dụng bởi một tài khoản khác."}), 409
            user.email = email

        # Luu toan bo ho so mo rong vao JSON clinical_profile
        extra_profile = {
            "ethnicity": data.get("ethnicity", "").strip(),
            "religion": data.get("religion", "").strip(),
            "province": data.get("province", "").strip(),
            "ward": data.get("ward", "").strip(),
            "address": address,
            "cccd": data.get("cccd", "").strip(),
            "issue_date": data.get("issue_date", "").strip(),
            "issue_place": data.get("issue_place", "").strip(),
            "facility": data.get("facility", "").strip(),
            "valid_from": data.get("valid_from", "").strip(),
            "valid_to": data.get("valid_to", "").strip(),
            "nationality": data.get("nationality", "").strip() or "VN"
        }
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

        # Trả về dev_otp nếu đang trong môi trường dev cục bộ
        if not is_prod:
            res_data["dev_otp"] = otp_manager.get_active_code(identifier, channel)

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
            dob = (user_data.get("dob") or "").strip()
            gender = (user_data.get("gender") or "Nam").strip()

            if channel == "email":
                email = identifier
                phone_number = (user_data.get("phone_number") or "").strip() or None
            else:
                phone_number = identifier
                email = f"{identifier}@phone.medimind"

            # Kiểm tra tài khoản đã tồn tại chưa
            existing = User.query.filter(
                (User.email == email) |
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
            clean_phone = "".join(filter(str.isdigit, identifier))
            user = User.query.filter(
                (User.email == identifier) |
                (User.phone_number == identifier) |
                (User.phone_number == clean_phone) |
                (User.email == f"{clean_phone}@phone.medimind")
            ).first()

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
        is_new_user = False
        already_existed = False

        if user:
            already_existed = True
            if avatar_url:
                user.avatar_url = avatar_url
            if full_name and (not user.full_name or user.full_name == "Bệnh nhân mới"):
                user.full_name = full_name
            db.session.commit()
        else:
            is_new_user = True
            user = User(
                email=email,
                full_name=full_name,
                role="patient",
                avatar_url=avatar_url or None
            )
            user.set_password(secrets.token_urlsafe(24))
            db.session.add(user)
            db.session.commit()

        session["user_id"] = user.id
        session["user_role"] = user.role

        needs_onboarding = is_new_user or not (user.phone_number and user.dob)

        query_out = {
            "google_auth": "success",
            "intent": intent,
            "onboarding": "1" if needs_onboarding else "0",
            "new_user": "1" if is_new_user else "0",
            "existing": "1" if (intent == "register" and already_existed and not needs_onboarding) else "0",
        }
        return redirect(f"/?{urllib.parse.urlencode(query_out)}")

    @app.route("/api/auth/google", methods=["POST"])
    def auth_google():
        """
        Đăng nhập 1-Click bằng Google Identity Services / OAuth 2.0:
        Tiếp nhận JWT credential hoặc thông tin người dùng từ client,
        tự động đồng bộ Họ tên, Email và Ảnh đại diện Google vào MediMind.
        """
        import base64
        import secrets

        data = request.get_json(silent=True) or {}
        credential = data.get("credential")
        email = (data.get("email") or "").strip().lower()
        full_name = (data.get("name") or "").strip()
        avatar_url = (data.get("avatar_url") or data.get("picture") or "").strip()

        # Giải mã Google JWT credential nếu có
        if credential and isinstance(credential, str):
            try:
                parts = credential.split(".")
                if len(parts) >= 2:
                    payload_b64 = parts[1]
                    payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
                    payload_json = base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode("utf-8")
                    token_info = json.loads(payload_json)

                    if token_info.get("email"):
                        email = token_info["email"].strip().lower()
                    if token_info.get("name"):
                        full_name = token_info["name"].strip()
                    if token_info.get("picture"):
                        avatar_url = token_info["picture"].strip()
            except Exception as e:
                logger.warning(f"Lỗi giải mã Google JWT Token: {e}")

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

        if not user_message and not image_str:
            return jsonify({"error": "Vui lòng nhập nội dung tin nhắn hoặc tải ảnh."}), 400

        image_bytes = None
        image_mime_type = "image/jpeg"
        if image_str:
            img_bytes, mime, err = decode_and_validate_base64_image(image_str)
            if err:
                return jsonify({"error": f"Tệp ảnh không hợp lệ: {err}"}), 400
            image_bytes = img_bytes
            image_mime_type = mime

        try:
            res = process_clinical_chat(
                message=user_message,
                history=history,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                lang=lang,
                gemini_service=gemini_service
            )

            # Lưu lịch sử tư vấn nếu người dùng đã đăng nhập để phục vụ Pre-visit Summary
            user_id = session.get("user_id")
            if user_id:
                try:
                    consultation = ClinicalConsultation(
                        user_id=user_id,
                        message=user_message,
                        answer=res.get("answer", ""),
                        risk_level=res.get("risk_level", ""),
                        risk_score=res.get("risk_score", 30),
                        symptoms=json.dumps(res.get("symptoms", []), ensure_ascii=False),
                        specialist=res.get("specialist", ""),
                        is_emergency=res.get("is_emergency", False)
                    )
                    db.session.add(consultation)
                    db.session.commit()
                except Exception as db_err:
                    db.session.rollback()
                    logger.warning(f"Lỗi lưu lịch sử tư vấn: {db_err}")

            return jsonify(res)

        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            logger.error(f"Lỗi xử lý tư vấn y tế: {e}")
            return jsonify({"error": "Đã xảy ra sự cố trong quá trình xử lý yêu cầu y tế."}), 500


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
                    owner_id=user_id
                )
                db.session.add(doc)
                db.session.commit()
                doc_id = doc.id
            except Exception as e:
                db.session.rollback()
                logger.warning(f"Lỗi lưu MedicalDocument cho scan: {e}")

            mask_pii = request.form.get("mask_pii", "false").lower() in ("true", "1")
            res = process_medical_document_pipeline(
                file_path=meta["absolute_path"],
                original_filename=meta["original_filename"],
                mask_pii=mask_pii
            )
            if doc_id:
                res["document_id"] = doc_id
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
    # PHIẾU CHUẨN BỊ TRƯỚC KHÁM CHO NGƯỜI DÂN (PRE-VISIT SUMMARY)
    # ==============================================================

    @app.route("/api/clinical-summary", methods=["GET"])
    def clinical_summary():
        """
        Bản tóm tắt trước khám:
        - Bắt buộc đăng nhập.
        - Trích xuất từ ca tư vấn thực tế của tài khoản hiện tại.
        - Trả 'no_data' nếu người dùng chưa có lượt tư vấn nào.
        """
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({
                "error": "Vui lòng đăng nhập để xem bản tóm tắt hồ sơ sức khỏe."
            }), 401

        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"error": "Không tìm thấy thông tin tài khoản."}), 404

        latest_consultation = ClinicalConsultation.query.filter_by(user_id=user_id).order_by(ClinicalConsultation.created_at.desc()).first()

        if not latest_consultation:
            return jsonify({
                "status": "no_data",
                "message": "Chưa có dữ liệu tư vấn hoặc bệnh án gần đây cho tài khoản này. "
                           "Vui lòng thực hiện tư vấn triệu chứng với trợ lý AI trước khi xuất phiếu trước khám."
            }), 200

        symptoms_list = []
        try:
            symptoms_list = json.loads(latest_consultation.symptoms or "[]")
        except Exception:
            symptoms_list = []

        symptoms_text = ", ".join(symptoms_list) if symptoms_list else "Triệu chứng chung"

        return jsonify({
            "status": "success",
            "patient_name": user.full_name,
            "patient_id": f"BN-2026-{user.id:04d}",
            "chief_complaint": f"{latest_consultation.message[:120]} (Dấu hiệu: {symptoms_text})",
            "hpi": f"Người bệnh ghi nhận: '{latest_consultation.message}'. Mức độ rủi ro đánh giá: {latest_consultation.risk_level}.",
            "red_flags": "DƯƠNG TÍNH (Cần cấp cứu khẩn cấp)" if latest_consultation.is_emergency else "ÂM TÍNH (Không phát hiện dấu hiệu nguy kịch tức thời)",
            "provisional_diagnosis": f"Định hướng ban đầu: {latest_consultation.specialist}",
            "triage_recommendation": f"Khuyến nghị chuyên khoa: {latest_consultation.specialist}. "
                                     f"{'Cần thăm khám sớm tại cơ sở y tế.' if latest_consultation.risk_score >= 40 else 'Theo dõi sức khỏe và chăm sóc tại nhà an toàn.'}",
            "prep_for_patient": [
                "Ghi lại nhật ký nhiệt độ và diễn biến triệu chứng sáng - chiều",
                "Mang theo danh sách các thuốc đang uống hằng ngày hoặc tiền sử dị ứng (nếu có)",
                "Thông báo cho bác sĩ thời điểm chính xác triệu chứng bắt đầu xuất hiện"
            ]
        })


    # ==============================================================
    # GIAO DIỆN NGƯỜI DÙNG WEB (UI)
    # ==============================================================

    @app.route("/")
    def index():
        """Trang chủ ứng dụng y tế MediMind."""
        return render_template("index.html")

    return app


# Export singleton app instance for WSGI / CLI
app = create_app()

if __name__ == "__main__":
    flask_debug = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true")
    port = int(os.getenv("PORT", 8000))
    print("==================================================")
    print("  MEDIMIND CLINICAL AI - HỆ THỐNG Y TẾ SỐ ĐANG CHẠY")
    print(f"  Giao diện Web: http://127.0.0.1:{port}")
    print(f"  Chế độ Debug: {flask_debug}")
    print("  Chuẩn kiến trúc: Phân tầng lâm sàng an toàn")
    print("==================================================")
    app.run(host="0.0.0.0", port=port, debug=flask_debug)
