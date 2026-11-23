"""Authentication, Profile, OTP, Forgot Password & Google OAuth routes."""

import json
import logging
import os
import secrets
from datetime import datetime
from flask import jsonify, redirect, request, session, url_for

from core.api_errors import ErrorCode, flask_api_error
from core.db_utils import commit_or_rollback
from core.models import User, db
from core.otp_service import otp_manager
from core.settings import settings, is_configured_secret

logger = logging.getLogger("MediMindApp")


def _start_authenticated_session(user):
    guest_token = session.get("guest_token") if not session.get("user_id") else None
    session.clear()
    session["user_id"] = user.id
    session["user_role"] = user.role
    if guest_token:
        session["guest_token"] = guest_token


def register_auth_routes(app, *, get_request_client_ip, valid_birth_date, find_login_user):
    # ==============================================================
    # HỆ THỐNG XÁC THỰC DANH TÍNH & PHÂN QUYỀN (RBAC)
    # ==============================================================

    # SECURITY (VULN-02): Generic error response — không tiết lộ tình trạng tồn tại tài khoản.
    # Dùng chung cho mọi trường hợp đăng nhập thất bại (user not found / wrong password / role mismatch).
    _LOGIN_FAILURE_RESPONSE = {"success": False, "error": "Thông tin đăng nhập không chính xác. Vui lòng kiểm tra lại."}

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        """Đăng nhập hệ thống: Xác thực Email/Số điện thoại và Mật khẩu băm trong CSDL."""
        data = request.get_json(silent=True) or {}
        raw_identifier = (data.get("identifier") or data.get("email") or "").strip()
        password = data.get("password", "").strip()
        role = data.get("role")

        if not raw_identifier or not password:
            return jsonify({"success": False, "error": "Vui lòng nhập định danh tài khoản và mật khẩu."}), 400

        from core.rate_limit_service import rate_limit_service
        client_ip = get_request_client_ip()
        if not rate_limit_service.check_login_ip_rate_limit(client_ip, max_attempts=30, window_seconds=900):
            return flask_api_error(
                ErrorCode.RATE_LIMITED,
                "Địa chỉ IP tạm khóa 15 phút do phát hiện quá nhiều yêu cầu đăng nhập liên tiếp. Vui lòng thử lại sau.",
                status_code=429
            )
        if not rate_limit_service.check_login_rate_limit(client_ip, raw_identifier, max_attempts=5, window_seconds=300):
            return flask_api_error(
                ErrorCode.RATE_LIMITED,
                "Tài khoản hoặc IP tạm khóa 5 phút do thử đăng nhập sai quá 5 lần liên tiếp. Vui lòng thử lại sau.",
                status_code=429
            )

        user = find_login_user(raw_identifier)

        if not user:
            # SECURITY (VULN-02): Timing-equalization — chạy dummy scrypt để cân bằng
            # thời gian phản hồi với trường hợp user tồn tại (tránh timing side-channel).
            # Dùng check_password_hash với hash giả cùng thuật toán scrypt mặc định của werkzeug.
            from werkzeug.security import check_password_hash as _chk
            _chk("scrypt:32768:8:1$medimind_dummy_salt_v2$" + "a" * 64, password)
            return jsonify(_LOGIN_FAILURE_RESPONSE), 401

        # Kiểm tra phân quyền truy cập
        # SECURITY (VULN-02): Role mismatch cũng trả 401 + generic message,
        # nhưng vẫn chạy check_password để không tiết lộ sớm qua timing.
        if role and user.role != role:
            user.check_password(password)  # timing equalization
            return jsonify(_LOGIN_FAILURE_RESPONSE), 401

        # Xác thực mật khẩu
        if not user.check_password(password):
            return jsonify(_LOGIN_FAILURE_RESPONSE), 401

        if getattr(user, "account_status", "active") != "active":
            return jsonify({
                "success": False,
                "error": "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ quản trị viên."
            }), 403

        # Xóa bộ đếm sai mật khẩu sau khi đăng nhập thành công
        rate_limit_service.reset_login_attempts(client_ip, raw_identifier)

        # Khởi tạo phiên làm việc (Session) & Chống Session Fixation
        _start_authenticated_session(user)

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
            client_ip = get_request_client_ip()
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

        # SECURITY (VULN-04): Enforce minimum password length 8 chars (OWASP ASVS Level 1)
        if len(password) < 8:
            return jsonify({"success": False, "error": "Mật khẩu phải có tối thiểu 8 ký tự."}), 400

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
            account_status="active",
            phone_number=phone_number,
            dob=dob,
            gender=gender,
            license_code=None
        )
        new_user.set_password(password)
        db.session.add(new_user)
        try:
            commit_or_rollback()
        except Exception:
            return jsonify({"success": False, "error": "Không thể lưu thông tin tài khoản vào cơ sở dữ liệu."}), 500

        _start_authenticated_session(new_user)

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
        if not user or getattr(user, "account_status", "active") != "active":
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
            commit_or_rollback()
        except Exception as e:
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

        if len(new_password) < 8:
            return jsonify({"success": False, "error": "Mật khẩu mới phải có tối thiểu 8 ký tự."}), 400

        if not user.check_password(current_password):
            return jsonify({"success": False, "error": "Mật khẩu hiện tại không chính xác."}), 401

        user.set_password(new_password)
        try:
            commit_or_rollback()
        except Exception:
            return jsonify({"success": False, "error": "Không thể cập nhật mật khẩu vào cơ sở dữ liệu."}), 500
        return jsonify({"success": True, "message": "Đã thay đổi mật khẩu thành công!"})


    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        """Đăng xuất và hủy phiên làm việc."""
        session.clear()
        resp = jsonify({"success": True, "message": "Đã đăng xuất thành công."})
        cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
        resp.delete_cookie(
            cookie_name,
            httponly=True,
            samesite="Lax",
            secure=settings.server.is_production or settings.security.session_cookie_secure
        )
        return resp

    # ==============================================================
    # HỆ THỐNG XÁC THỰC OTP (EMAIL / SMS) & GOOGLE OAUTH 2.0
    # ==============================================================

    @app.route("/api/auth/otp/send", methods=["POST"])
    def auth_send_otp():
        """
        Gửi mã xác thực OTP 6 số qua Gmail hoặc SMS SpeedSMS (Nội địa Việt Nam).
        Rate-limit: cooldown 60s, TTL 5 phút, CSPRNG.
        Đã loại bỏ cổng Twilio và chặn gửi OTP tới các số điện thoại quốc tế.
        """
        data = request.get_json(silent=True) or {}
        identifier = (data.get("identifier") or data.get("email") or data.get("phone") or "").strip()
        channel = (data.get("channel") or "").strip().lower()
        purpose = (data.get("purpose") or "register").strip()
        full_name = (data.get("full_name") or data.get("name") or "").strip()

        if not identifier:
            return jsonify({"success": False, "error": "Vui lòng nhập Email hoặc Số điện thoại."}), 400

        # SECURITY (H-04): Giới hạn tần suất gửi OTP theo địa chỉ IP chống SMS/Email Bombing
        from core.rate_limit_service import rate_limit_service
        client_ip = get_request_client_ip()
        if not rate_limit_service.check_otp_send_ip_rate_limit(client_ip, max_requests=5, window_seconds=900):
            return flask_api_error(
                ErrorCode.RATE_LIMITED,
                "Bạn đã yêu cầu gửi mã OTP quá nhiều lần từ địa chỉ IP này. Vui lòng thử lại sau 15 phút.",
                status_code=429
            )

        # Tự động nhận diện kênh gửi nếu client không truyền channel
        if not channel:
            channel = "email" if "@" in identifier else "sms"

        if channel == "email":
            if "@" not in identifier:
                return jsonify({"success": False, "error": "Địa chỉ email không hợp lệ."}), 400
        else:
            from core.sms_service import sms_service
            norm_vn = sms_service.normalize_phone(identifier)
            if not norm_vn:
                return jsonify({
                    "success": False,
                    "error": "Chỉ hỗ trợ gửi mã OTP tới số điện thoại di động nội địa Việt Nam (đầu số 03, 05, 07, 08, 09 hoặc +84). Đã chặn gửi OTP quốc tế."
                }), 400
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
                # SECURITY (VULN-02): Generic response — không tiết lộ tài khoản đã tồn tại
                # qua HTTP status 409. Trả 200 với message trung lập để bảo vệ quyền riêng tư.
                # Không tạo OTP, không gửi SMS/Email, không tạo tài khoản trùng.
                return jsonify({
                    "success": True,
                    "message": "Nếu thông tin đăng ký hợp lệ, mã xác minh sẽ được gửi. Nếu bạn đã có tài khoản, vui lòng đăng nhập hoặc sử dụng chức năng Quên mật khẩu.",
                    "channel": channel,
                    "identifier": identifier,
                    "cooldown": 59,
                    "expires_in": otp_manager.ttl
                }), 200
        elif purpose == "login_2fa":
            exist_acc = find_login_user(identifier)
            if not exist_acc:
                # SECURITY (VULN-02): Silent no-op — không tiết lộ tài khoản không tồn tại.
                # Trả 200 với cùng cấu trúc JSON như OTP thật. Không tạo OTP, không gửi SMS/Email.
                return jsonify({
                    "success": True,
                    "message": "Nếu tài khoản tồn tại, mã OTP đã được gửi.",
                    "channel": channel,
                    "identifier": identifier,
                    "cooldown": 59,
                    "expires_in": otp_manager.ttl
                }), 200
        elif purpose == "reset_pwd":
            exist_acc = find_login_user(identifier)
            if not exist_acc:
                # SECURITY (VULN-02): Silent no-op — phản hồi đồng nhất tuyệt đối với trường hợp tồn tại tài khoản.
                return jsonify({
                    "success": True,
                    "message": "Nếu tài khoản tồn tại, mã xác thực đặt lại mật khẩu đã được gửi.",
                    "channel": channel,
                    "identifier": identifier,
                    "cooldown": otp_manager.cooldown,
                    "expires_in": otp_manager.ttl
                }), 200
            full_name = exist_acc.full_name or full_name

        success, msg, cooldown = otp_manager.request_otp(
            identifier=identifier,
            channel=channel,
            purpose=purpose,
            full_name=full_name or "Quý khách"
        )

        if not success:
            return jsonify({"success": False, "error": msg, "cooldown": cooldown}), 429 if cooldown > 0 else 400

        res_message = (
            "Nếu tài khoản tồn tại, mã xác thực đặt lại mật khẩu đã được gửi."
            if purpose == "reset_pwd"
            else msg
        )
        res_data = {
            "success": True,
            "message": res_message,
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

        # Validate password policy before consuming the OTP so invalid registration or reset input never burns the user's OTP code.
        if purpose == "register" and isinstance(user_data, dict) and user_data:
            raw_reg_pw = (user_data.get("password") or "").strip()
            if raw_reg_pw and len(raw_reg_pw) < 8:
                return jsonify({"success": False, "error": "Mật khẩu phải có tối thiểu 8 ký tự."}), 400
        elif purpose == "reset_pwd":
            raw_reset_pw = (
                (user_data.get("new_password") if isinstance(user_data, dict) else "")
                or data.get("new_password")
                or ""
            ).strip()
            if not raw_reset_pw:
                return jsonify({"success": False, "error": "Vui lòng nhập mật khẩu mới."}), 400
            if len(raw_reset_pw) < 8:
                return jsonify({"success": False, "error": "Mật khẩu mới phải có tối thiểu 8 ký tự."}), 400

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

            # SECURITY (VULN-04): Enforce minimum password length 8 chars (OWASP ASVS Level 1)
            # Note: auto-generated passwords (token_urlsafe(12)) always exceed 8 chars — this check
            # only rejects explicitly-provided passwords that are too short.
            elif len(password) < 8:
                return jsonify({"success": False, "error": "Mật khẩu phải có tối thiểu 8 ký tự."}), 400

            new_user = User(
                email=email,
                full_name=full_name,
                role="patient",
                account_status="active",
                phone_number=phone_number,
                dob=dob,
                gender=gender
            )
            new_user.set_password(password)
            db.session.add(new_user)
            try:
                commit_or_rollback()
            except Exception:
                return jsonify({"success": False, "error": "Không thể lưu thông tin tài khoản vào cơ sở dữ liệu."}), 500

            _start_authenticated_session(new_user)

            return jsonify({
                "success": True,
                "message": "Xác thực danh tính và đăng ký tài khoản thành công!",
                "user": new_user.to_dict()
            }), 201

        # Nếu là kịch bản Đặt lại mật khẩu (Forgot Password with OTP)
        if purpose == "reset_pwd":
            new_password = (
                (user_data.get("new_password") if isinstance(user_data, dict) else "")
                or data.get("new_password")
                or ""
            ).strip()
            if len(new_password) < 8:
                return jsonify({"success": False, "error": "Mật khẩu mới phải có tối thiểu 8 ký tự."}), 400

            user = find_login_user(identifier)
            if not user:
                # SECURITY (VULN-02): Trả 400 generic thay vì 404 để không tiết lộ tài khoản không tồn tại.
                return jsonify({"success": False, "error": "Mã OTP không hợp lệ hoặc đã hết hạn."}), 400

            user.set_password(new_password)
            try:
                commit_or_rollback()
            except Exception:
                return jsonify({"success": False, "error": "Không thể cập nhật mật khẩu mới vào cơ sở dữ liệu."}), 500

            # Dọn trạng thái otp_verified_store vừa tạo (không giữ dư thừa sau khi reset xong)
            otp_manager.is_verified(identifier, channel, consume=True)
            # Mở khóa bộ đếm đăng nhập nếu trước đó bị khóa do quên mật khẩu & làm mới session
            from core.rate_limit_service import rate_limit_service
            rate_limit_service.reset_login_attempts(get_request_client_ip(), identifier)
            session.clear()

            return jsonify({
                "success": True,
                "reset_completed": True,
                "message": "Đặt lại mật khẩu thành công! Vui lòng đăng nhập bằng mật khẩu mới."
            })

        # Nếu là kịch bản Đăng nhập 2FA (2FA Login)
        if purpose == "login_2fa":
            user = find_login_user(identifier)

            if not user:
                # SECURITY (VULN-02): Trả 400 generic thay vì 404 để không tiết lộ tài khoản không tồn tại.
                # Edge case: OTP hợp lệ nhưng tài khoản đã bị xóa sau khi OTP được tạo.
                return jsonify({"success": False, "error": "Mã OTP không hợp lệ hoặc đã hết hạn."}), 400

            if getattr(user, "account_status", "active") != "active":
                return jsonify({
                    "success": False,
                    "error": "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ quản trị viên."
                }), 403

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
        import time

        if not app.secret_key:
            raise RuntimeError("SECRET_KEY chưa được cấu hình cho Google OAuth state.")
        clean_intent = "register" if intent == "register" else "login"
        payload = json.dumps({
            "n": secrets.token_urlsafe(12),
            "i": clean_intent,
            "t": int(time.time())
        }, separators=(",", ":")).encode("utf-8")
        b64_payload = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        secret = str(app.secret_key).encode("utf-8")
        sig = hmac.new(secret, b64_payload.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{b64_payload}.{sig}"

    def _verify_google_oauth_state(state_token: str):
        import base64
        import hashlib
        import hmac
        import time

        if not state_token or "." not in state_token or not app.secret_key:
            return None
        try:
            b64_payload, sig = state_token.rsplit(".", 1)
            secret = str(app.secret_key).encode("utf-8")
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

        if not is_configured_secret(client_id) or not is_configured_secret(client_secret):
            if request.args.get("format") == "json":
                return jsonify({
                    "success": False,
                    "configured": False,
                    "error": "Đăng nhập bằng Google chưa được cấu hình trên máy chủ (thiếu GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET hợp lệ trong .env)."
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

        if not is_configured_secret(client_id) or not is_configured_secret(client_secret):
            logger.warning("Google OAuth callback từ chối: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET chưa cấu hình hợp lệ.")
            return redirect("/?google_auth=error&error_reason=unconfigured")

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
            if getattr(user, "account_status", "active") != "active":
                return redirect("/?google_auth=error&error_reason=account_suspended")
            if avatar_url:
                user.avatar_url = avatar_url
            if full_name and (not user.full_name or user.full_name == "Bệnh nhân mới"):
                user.full_name = full_name
            commit_or_rollback()

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
        commit_or_rollback()

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
        Cổng xác thực Google ID Token (Bảo mật Fail-Closed - VULN-01):
        - Bắt buộc cấu hình GOOGLE_CLIENT_ID (nếu thiếu trả về HTTP 503).
        - Bắt buộc cung cấp Google ID Token/Credential (nếu thiếu trả về HTTP 400).
        - Xác minh chữ ký, audience, expiration với Google.
        - Tuyệt đối không tin cậy email/name/avatar gửi trực tiếp trong body JSON.
        """
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
        if not is_configured_secret(client_id):
            logger.warning("Google OAuth từ chối xác thực: GOOGLE_CLIENT_ID chưa được cấu hình hợp lệ.")
            return flask_api_error(
                ErrorCode.AI_UNAVAILABLE,
                "Dịch vụ xác thực Google chưa được cấu hình trên máy chủ.",
                status_code=503
            )

        data = request.get_json(silent=True) or {}
        credential = data.get("credential") or data.get("token")
        if not credential or not isinstance(credential, str) or not credential.strip():
            return flask_api_error(
                ErrorCode.VALIDATION_ERROR,
                "Yêu cầu thiếu Google credential/token hợp lệ.",
                status_code=400
            )

        try:
            token_info = id_token.verify_oauth2_token(
                credential.strip(),
                google_requests.Request(),
                client_id
            )
        except Exception as ex:
            logger.warning("Xác thực Google ID Token thất bại: %s", type(ex).__name__)
            return flask_api_error(
                ErrorCode.INVALID_CREDENTIALS,
                "Google ID Token không hợp lệ hoặc đã hết hạn.",
                status_code=401
            )

        if token_info.get("aud") != client_id:
            return flask_api_error(
                ErrorCode.FORBIDDEN,
                "Google ID Token không thuộc ứng dụng MediMind.",
                status_code=403
            )

        email = (token_info.get("email") or "").strip().lower()
        full_name = (token_info.get("name") or "").strip()
        avatar_url = (token_info.get("picture") or "").strip()

        if not email or "@" not in email:
            return flask_api_error(
                ErrorCode.VALIDATION_ERROR,
                "Google token không chứa địa chỉ email hợp lệ.",
                status_code=400
            )

        if not full_name:
            full_name = email.split("@")[0].capitalize()

        # Tìm hoặc tạo người dùng
        user = User.query.filter_by(email=email).first()
        if user:
            if getattr(user, "account_status", "active") != "active":
                return flask_api_error(
                    ErrorCode.FORBIDDEN,
                    "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ quản trị viên.",
                    status_code=403,
                )
            # Đồng bộ lại Avatar và Họ tên từ Google nếu chưa có
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
            if full_name and (not user.full_name or user.full_name == "Bệnh nhân mới"):
                user.full_name = full_name
            commit_or_rollback()
        else:
            user = User(
                email=email,
                full_name=full_name,
                role="patient",
                avatar_url=avatar_url or None
            )
            user.set_password(secrets.token_urlsafe(24))
            db.session.add(user)
            commit_or_rollback()

        # Khởi tạo Session & Chống Session Fixation
        _start_authenticated_session(user)

        return jsonify({
            "success": True,
            "message": f"Đăng nhập thành công với tài khoản Google ({user.email})!",
            "user": user.to_dict()
        })


