"""Authentication, profile, OTP and Google OAuth routes."""

import json
import logging
import os
from pathlib import Path
import re
import secrets
import uuid

from flask import jsonify, redirect, request, session, url_for

from core.auth.otp_service import otp_manager
from core.shared.api_errors import ErrorCode, flask_api_error
from core.shared.models import User, db
from core.shared.settings import settings
from core.shared.storage_service import inspect_upload_safety, is_safe_path, process_secure_upload
from routes.shared_helpers import (
    DEFAULT_UPLOAD_FOLDER as default_upload_folder,
    commit_or_rollback,
    find_login_user,
    get_request_client_ip,
    start_authenticated_session as _start_authenticated_session,
    valid_birth_date,
)

logger = logging.getLogger("MediMindApp")


def _validate_reset_password_strength(password: str):
    """Kiểm tra độ mạnh mật khẩu mới (2B): >= 8 ký tự, có chữ hoa, chữ thường và chữ số."""
    if not password or len(password) < 8:
        return "Mật khẩu mới phải có tối thiểu 8 ký tự (gồm chữ hoa, chữ thường và chữ số)."
    if not re.search(r"[A-Z]", password) or not re.search(r"[a-z]", password) or not re.search(r"\d", password):
        return "Mật khẩu mới phải bao gồm ít nhất 1 chữ hoa, 1 chữ thường và 1 chữ số."
    return None


def _is_account_active(user) -> bool:
    """Kiểm tra trạng thái tài khoản có đang hoạt động (active) hay đã bị tạm khóa (suspended)."""
    return (getattr(user, "account_status", "active") or "active").strip().lower() == "active"


_PROFILE_EMAIL_RE = re.compile(r"^[^@\s\r\n]+@[^@\s\r\n]+\.[^@\s\r\n]+$")


def _verify_avatar_image_bytes(raw_bytes: bytes, ext: str):
    """Xác minh thực sự cấu trúc ảnh đại diện bằng Pillow (chống tệp giả mạo header RIFF/WEBP)."""
    try:
        import io
        from PIL import Image
        with Image.open(io.BytesIO(raw_bytes)) as img:
            img.verify()
            fmt = (img.format or "").upper()
            allowed_formats = {"JPEG", "JPG"} if ext in ("jpg", "jpeg") else {ext.upper()}
            if fmt and fmt not in allowed_formats:
                return False, f"Nội dung ảnh ({fmt}) không khớp định dạng .{ext}."
    except Exception:
        return False, "Tệp ảnh đại diện không hợp lệ hoặc đã bị hỏng."
    return True, None


def register_auth_routes(app):
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

        from core.auth.rate_limit_service import rate_limit_service
        client_ip = get_request_client_ip()
        if not rate_limit_service.check_login_rate_limit(client_ip, raw_identifier, max_attempts=5, window_seconds=300):
            return flask_api_error(
                ErrorCode.RATE_LIMITED,
                "Tài khoản hoặc IP tạm khóa 5 phút do thử đăng nhập sai quá 5 lần liên tiếp. Vui lòng thử lại sau.",
                status_code=429
            )

        user = find_login_user(raw_identifier)

        if not user:
            return jsonify({"success": False, "error": "Tài khoản không tồn tại trên hệ thống."}), 404

        if not _is_account_active(user):
            return jsonify({"success": False, "error": "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ hỗ trợ."}), 403

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
        rate_limit_service.reset_login_attempts(client_ip, raw_identifier)

        # Khởi tạo phiên làm việc (Session) & Chống Session Fixation
        session.permanent = True
        _start_authenticated_session(user)
        session["user_role"] = user.role
        user_dict = user.to_dict()

        return jsonify({
            "success": True,
            "message": f"Chào mừng {user.full_name} đã quay trở lại!",
            "needs_onboarding": bool(user_dict.get("needs_onboarding")),
            "user": user_dict
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
            from core.auth.security_patch import check_otp_attempts
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

        pwd_err = _validate_reset_password_strength(password)
        if pwd_err:
            return jsonify({"success": False, "error": pwd_err}), 400

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
            license_code=None,
            clinical_profile=json.dumps({"onboarding_completed": False}, ensure_ascii=False),
        )
        new_user.set_password(password)
        db.session.add(new_user)
        try:
            commit_or_rollback()
        except Exception:
            return jsonify({"success": False, "error": "Không thể lưu thông tin tài khoản vào cơ sở dữ liệu."}), 500

        # Sau khi đăng ký thành công, yêu cầu người dùng đăng nhập trước khi vào hệ thống
        session.clear()

        return jsonify({
            "success": True,
            "requires_login": True,
            "message": "Đăng ký tài khoản thành công! Vui lòng đăng nhập để bắt đầu sử dụng.",
            "user": new_user.to_dict()
        }), 201


    @app.route("/api/auth/me", methods=["GET"])
    def auth_me():
        """Kiểm tra trạng thái phiên đăng nhập của người dân."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"authenticated": False, "user": None})

        user = db.session.get(User, user_id)
        if not user or not _is_account_active(user):
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
        if not _is_account_active(user):
            session.clear()
            return jsonify({"success": False, "error": "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ hỗ trợ."}), 403

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "error": "Dữ liệu hồ sơ không hợp lệ."}), 400

        def _profile_str(key: str, max_len: int = 255):
            raw = data.get(key)
            if raw is None:
                return "", None
            if not isinstance(raw, str):
                return None, f"Trường '{key}' phải có định dạng văn bản hợp lệ."
            val = raw.strip()
            if len(val) > max_len:
                return None, f"Trường '{key}' vượt quá độ dài tối đa ({max_len} ký tự)."
            return val, None

        name_a, err = _profile_str("name", 120)
        if err:
            return jsonify({"success": False, "error": err}), 400
        name_b, err = _profile_str("full_name", 120)
        if err:
            return jsonify({"success": False, "error": err}), 400
        full_name = name_a or name_b
        gender, err = _profile_str("gender", 30)
        if err:
            return jsonify({"success": False, "error": err}), 400
        dob, err = _profile_str("dob", 50)
        if err:
            return jsonify({"success": False, "error": err}), 400
        phone_number, err = _profile_str("phone_number", 30)
        if err:
            return jsonify({"success": False, "error": err}), 400
        address, err = _profile_str("address", 255)
        if err:
            return jsonify({"success": False, "error": err}), 400
        bhyt, err = _profile_str("bhyt", 50)
        if err:
            return jsonify({"success": False, "error": err}), 400
        email, err = _profile_str("email", 120)
        if err:
            return jsonify({"success": False, "error": err}), 400

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
        if email and _PROFILE_EMAIL_RE.match(email) and not email.lower().endswith("@phone.medimind"):
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
                fval, ferr = _profile_str(field, 500)
                if ferr:
                    return jsonify({"success": False, "error": ferr}), 400
                extra_profile[field] = fval
        if not extra_profile.get("nationality"):
            extra_profile["nationality"] = "VN"
        extra_profile["onboarding_completed"] = True
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


    @app.route("/api/auth/avatar", methods=["POST"])
    def auth_upload_avatar():
        """Tải lên và lưu bền vững ảnh đại diện của người dùng đang đăng nhập."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập để cập nhật ảnh đại diện."}), 401

        user = db.session.get(User, user_id)
        if not user:
            session.clear()
            return jsonify({"success": False, "error": "Không tìm thấy thông tin tài khoản."}), 404
        if not _is_account_active(user):
            session.clear()
            return jsonify({"success": False, "error": "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ hỗ trợ."}), 403

        file = request.files.get("file") or request.files.get("avatar")
        if not file or not file.filename:
            return jsonify({"success": False, "error": "Chưa chọn tệp ảnh đại diện hợp lệ."}), 400

        ext = os.path.basename(file.filename).rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in {"jpg", "jpeg", "png", "webp"}:
            return jsonify({"success": False, "error": "Chỉ hỗ trợ ảnh JPG, JPEG, PNG hoặc WEBP."}), 400

        upload_folder = app.config.get("UPLOAD_FOLDER", default_upload_folder)
        if ext == "webp":
            file_bytes = file.read()
            if len(file_bytes) == 0 or len(file_bytes) > 10 * 1024 * 1024:
                return jsonify({"success": False, "error": "Dung lượng ảnh đại diện không hợp lệ (tối đa 10MB)."}), 400
            if not (file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP"):
                return jsonify({"success": False, "error": "Nội dung tệp không khớp định dạng .webp."}), 400
            is_safe, safety_err = inspect_upload_safety(file_bytes, "webp")
            if not is_safe:
                return jsonify({"success": False, "error": safety_err or "Ảnh tải lên không đạt kiểm tra an toàn."}), 400
            img_ok, img_err = _verify_avatar_image_bytes(file_bytes, "webp")
            if not img_ok:
                return jsonify({"success": False, "error": img_err}), 400
            storage_filename = f"{uuid.uuid4().hex}.webp"
            base_folder_path = Path(upload_folder).resolve()
            base_folder_path.mkdir(parents=True, exist_ok=True)
            dest_path = base_folder_path / storage_filename
            if not is_safe_path(dest_path, base_folder_path):
                return jsonify({"success": False, "error": "Đường dẫn lưu trữ không an toàn."}), 400
            with open(dest_path, "wb") as f:
                f.write(file_bytes)
        else:
            raw_bytes = file.read()
            if len(raw_bytes) == 0 or len(raw_bytes) > 10 * 1024 * 1024:
                return jsonify({"success": False, "error": "Dung lượng ảnh đại diện không hợp lệ (tối đa 10MB)."}), 400
            img_ok, img_err = _verify_avatar_image_bytes(raw_bytes, ext)
            if not img_ok:
                return jsonify({"success": False, "error": img_err}), 400
            file.seek(0)
            success, meta, err_msg = process_secure_upload(file, upload_folder)
            if not success:
                return jsonify({"success": False, "error": err_msg or "Không thể lưu ảnh đại diện."}), 400
            storage_filename = meta["storage_filename"]

        user.avatar_url = f"/uploads/{storage_filename}"
        try:
            commit_or_rollback()
        except Exception as e:
            logger.error(f"Lỗi lưu ảnh đại diện: {e}")
            return jsonify({"success": False, "error": "Không thể lưu ảnh đại diện vào hồ sơ."}), 500

        return jsonify({
            "success": True,
            "message": "Đã cập nhật ảnh đại diện thành công!",
            "avatar_url": user.avatar_url,
            "avatar": user.avatar_url,
            "user": user.to_dict(),
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
        if not _is_account_active(user):
            session.clear()
            return jsonify({"success": False, "error": "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ hỗ trợ."}), 403

        data = request.get_json(silent=True) or {}
        current_password = (data.get("current_password") or "").strip() if isinstance(data.get("current_password"), str) else ""
        new_password = (data.get("new_password") or "").strip() if isinstance(data.get("new_password"), str) else ""

        if not current_password or not new_password:
            return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ mật khẩu hiện tại và mật khẩu mới."}), 400

        from core.auth.rate_limit_service import rate_limit_service
        client_ip = get_request_client_ip()
        chgpwd_key = f"chgpwd:{client_ip}:{user.id}"
        if not rate_limit_service.backend.check_and_increment(chgpwd_key, max_requests=5, window_seconds=900):
            return jsonify({
                "success": False,
                "error": "Bạn đã thử đổi mật khẩu sai quá nhiều lần. Vui lòng thử lại sau 15 phút."
            }), 429

        pwd_err = _validate_reset_password_strength(new_password)
        if pwd_err:
            return jsonify({"success": False, "error": pwd_err}), 400

        if not user.check_password(current_password):
            return jsonify({"success": False, "error": "Mật khẩu hiện tại không chính xác."}), 401

        if user.check_password(new_password):
            return jsonify({"success": False, "error": "Mật khẩu mới không được trùng với mật khẩu hiện tại."}), 400

        rate_limit_service.backend.reset(chgpwd_key)
        user.set_password(new_password)
        try:
            commit_or_rollback()
        except Exception:
            return jsonify({"success": False, "error": "Không thể cập nhật mật khẩu vào cơ sở dữ liệu."}), 500

        # Xoay vòng phiên sau khi đổi mật khẩu
        session.permanent = True
        _start_authenticated_session(user)
        session["user_role"] = user.role
        return jsonify({"success": True, "message": "Đã thay đổi mật khẩu thành công!"})

    @app.route("/api/auth/preferences", methods=["GET"])
    def auth_get_preferences():
        """Lấy cài đặt cá nhân hóa (ngôn ngữ, múi giờ, định dạng ngày, thông báo đẩy) của tài khoản hiện tại."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập để xem cài đặt cá nhân hóa."}), 401

        user = db.session.get(User, user_id)
        if not user:
            session.clear()
            return jsonify({"success": False, "error": "Không tìm thấy tài khoản."}), 404
        if not _is_account_active(user):
            session.clear()
            return jsonify({"success": False, "error": "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ hỗ trợ."}), 403

        return jsonify({"success": True, "preferences": user.get_preferences()})

    @app.route("/api/auth/preferences", methods=["PUT", "POST"])
    def auth_update_preferences():
        """Lưu cài đặt cá nhân hóa (lang, timezone, date_format, push_notif) vào CSDL."""
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"success": False, "error": "Vui lòng đăng nhập để lưu cài đặt lên tài khoản."}), 401

        user = db.session.get(User, user_id)
        if not user:
            session.clear()
            return jsonify({"success": False, "error": "Không tìm thấy tài khoản."}), 404
        if not _is_account_active(user):
            session.clear()
            return jsonify({"success": False, "error": "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ hỗ trợ."}), 403

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "error": "Dữ liệu cài đặt không hợp lệ."}), 400

        try:
            updated = user.set_preferences(data)
        except ValueError as ve:
            return jsonify({"success": False, "error": str(ve)}), 400

        try:
            commit_or_rollback()
        except Exception:
            return jsonify({"success": False, "error": "Không thể lưu cài đặt vào cơ sở dữ liệu."}), 500

        return jsonify({
            "success": True,
            "message": "Đã lưu cài đặt cá nhân hóa thành công!",
            "preferences": updated,
        })

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
        from core.auth.rate_limit_service import rate_limit_service
        client_ip = get_request_client_ip()
        if not rate_limit_service.check_otp_rate_limit(f"send_ip:{client_ip}", max_attempts=15, window_seconds=900):
            return jsonify({
                "success": False,
                "error": "Bạn đã gửi quá nhiều yêu cầu mã OTP từ địa chỉ IP này. Vui lòng thử lại sau 15 phút."
            }), 429

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
            from core.auth.sms_service import sms_service
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
                return jsonify({
                    "success": False,
                    "error": "Email hoặc Số điện thoại này đã được đăng ký. Vui lòng chuyển sang tab Đăng nhập!"
                }), 409
        elif purpose in ("login_2fa", "reset_pwd"):
            exist_acc = find_login_user(identifier)
            if not exist_acc:
                return jsonify({
                    "success": False,
                    "error": "Tài khoản không tồn tại trên hệ thống. Vui lòng kiểm tra lại hoặc đăng ký tài khoản mới!"
                }), 404
            if not full_name and exist_acc.full_name:
                full_name = exist_acc.full_name

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
        from core.auth.rate_limit_service import rate_limit_service
        client_ip = get_request_client_ip()
        if not rate_limit_service.check_otp_rate_limit(f"verify_ip:{client_ip}", max_attempts=15, window_seconds=900):
            return jsonify({
                "success": False,
                "error": "Bạn đã thử xác minh OTP quá nhiều lần từ địa chỉ IP này. Vui lòng thử lại sau 15 phút."
            }), 429

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

        if purpose == "register":
            reg_pwd = (user_data.get("password") or "").strip()
            if reg_pwd:
                reg_pwd_err = _validate_reset_password_strength(reg_pwd)
                if reg_pwd_err:
                    return jsonify({"success": False, "error": reg_pwd_err}), 400

        new_password = (user_data.get("new_password") or data.get("new_password") or "").strip()
        if purpose == "reset_pwd":
            pwd_err = _validate_reset_password_strength(new_password)
            if pwd_err:
                return jsonify({"success": False, "error": pwd_err}), 400

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
                account_status="active",
                phone_number=phone_number,
                dob=dob,
                gender=gender,
                clinical_profile=json.dumps({"onboarding_completed": False}, ensure_ascii=False),
            )
            new_user.set_password(password)
            db.session.add(new_user)
            try:
                commit_or_rollback()
            except Exception:
                return jsonify({"success": False, "error": "Không thể lưu thông tin tài khoản vào cơ sở dữ liệu."}), 500

            # Sau khi xác thực OTP đăng ký thành công, chuyển về bước Đăng nhập trước khi vào website
            session.clear()

            return jsonify({
                "success": True,
                "purpose": "register",
                "identifier": identifier,
                "requires_login": True,
                "message": "Đăng ký tài khoản thành công! Vui lòng đăng nhập để bắt đầu sử dụng.",
                "user": new_user.to_dict()
            }), 201

        # Nếu là kịch bản Đăng nhập 2FA (2FA Login)
        if purpose == "login_2fa":
            user = find_login_user(identifier)

            if not user:
                return jsonify({"success": False, "error": "Tài khoản không tồn tại trên hệ thống."}), 404

            if not _is_account_active(user):
                return jsonify({"success": False, "error": "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ hỗ trợ."}), 403

            session.permanent = True
            _start_authenticated_session(user)
            session["user_role"] = user.role

            user_dict = user.to_dict()
            return jsonify({
                "success": True,
                "message": f"Xác thực 2 lớp thành công! Chào mừng {user.full_name}.",
                "user": user_dict,
                "needs_onboarding": bool(user_dict.get("needs_onboarding")),
            })

        # Nếu là kịch bản Quên mật khẩu / Đặt lại mật khẩu (Reset Password with OTP)
        if purpose == "reset_pwd":
            user = find_login_user(identifier)
            if not user:
                return jsonify({"success": False, "error": "Tài khoản không tồn tại trên hệ thống."}), 404

            if user.check_password(new_password):
                return jsonify({
                    "success": False,
                    "error": "Mật khẩu mới không được trùng với mật khẩu hiện tại."
                }), 400

            user.set_password(new_password)
            try:
                commit_or_rollback()
            except Exception:
                return jsonify({"success": False, "error": "Không thể cập nhật mật khẩu mới vào cơ sở dữ liệu."}), 500

            # 3A: Xóa phiên đăng nhập cũ và yêu cầu đăng nhập lại bằng mật khẩu mới
            session.clear()
            return jsonify({
                "success": True,
                "purpose": "reset_pwd",
                "identifier": identifier,
                "requires_login": True,
                "message": "Đặt lại mật khẩu thành công! Vui lòng đăng nhập lại bằng mật khẩu mới."
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
        import urllib.request
        import urllib.parse
        import urllib.error

        error = (request.args.get("error") or "").strip()
        if error:
            logger.warning(f"Google OAuth trả về lỗi hoặc người dùng hủy: {error}")
            return redirect(f"/?google_auth=error&error_reason={urllib.parse.quote(error)}")

        import hmac

        code = (request.args.get("code") or "").strip()
        state_token = (request.args.get("state") or "").strip()

        intent = _verify_google_oauth_state(state_token)
        expected_state = session.pop("google_oauth_state", None)
        if not intent or not code or not expected_state or not hmac.compare_digest(expected_state, state_token):
            logger.warning("Google OAuth callback thất bại: state không hợp lệ hoặc thiếu code.")
            return redirect("/?google_auth=error&error_reason=invalid_state")

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
        google_sub = (user_info.get("sub") or "").strip() or None

        if user_info.get("email_verified") is not True:
            return redirect("/?google_auth=error&error_reason=email_unverified")

        if not email or "@" not in email:
            return redirect("/?google_auth=error&error_reason=invalid_email")

        if not full_name:
            full_name = email.split("@")[0].capitalize()

        user = User.query.filter_by(email=email).first()

        # TRƯỜNG HỢP 1: TỪ LẦN THỨ 2 TRỞ ĐI (Tài khoản Google đã có trong CSDL -> Vào luôn ngay lập tức)
        if user:
            if not _is_account_active(user):
                return redirect("/?google_auth=error&error_reason=account_suspended")
            if user.google_sub and google_sub and user.google_sub != google_sub:
                return redirect("/?google_auth=error&error_reason=account_mismatch")
            if google_sub and not user.google_sub:
                user.google_sub = google_sub
            if avatar_url:
                user.avatar_url = avatar_url
            if full_name and (not user.full_name or user.full_name == "Bệnh nhân mới"):
                user.full_name = full_name
            commit_or_rollback()

            session.pop("pending_google_register", None)
            session.permanent = True
            _start_authenticated_session(user)
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
            "google_sub": google_sub or "",
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
            if not _is_account_active(existing_user):
                session.pop("pending_google_register", None)
                return jsonify({"success": False, "error": "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ hỗ trợ."}), 403
            session.pop("pending_google_register", None)
            session.permanent = True
            _start_authenticated_session(existing_user)
            session["user_role"] = existing_user.role
            return jsonify({"success": True, "user": existing_user.to_dict()})

        if clean_phone:
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
            avatar_url=pending.get("avatar_url") or None,
            google_sub=(pending.get("google_sub") or "").strip() or None,
            clinical_profile=json.dumps({"onboarding_completed": True}, ensure_ascii=False),
        )
        user.set_password(secrets.token_urlsafe(24))
        db.session.add(user)
        commit_or_rollback()

        session.pop("pending_google_register", None)
        session.permanent = True
        _start_authenticated_session(user)
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
        if not client_id:
            logger.warning("Google OAuth từ chối xác thực: GOOGLE_CLIENT_ID chưa được cấu hình.")
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
        google_sub = (token_info.get("sub") or "").strip() or None
        email_verified = token_info.get("email_verified")

        if email_verified is False or ("email_verified" in token_info and email_verified is not True):
            return flask_api_error(
                ErrorCode.FORBIDDEN,
                "Tài khoản Google chưa xác minh địa chỉ email.",
                status_code=403
            )

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
            if not _is_account_active(user):
                return flask_api_error(
                    ErrorCode.FORBIDDEN,
                    "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ hỗ trợ.",
                    status_code=403
                )
            if user.google_sub and google_sub and user.google_sub != google_sub:
                return flask_api_error(
                    ErrorCode.FORBIDDEN,
                    "Định danh tài khoản Google không khớp với tài khoản đã liên kết.",
                    status_code=403
                )
            if google_sub and not user.google_sub:
                user.google_sub = google_sub
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
                avatar_url=avatar_url or None,
                google_sub=google_sub,
            )
            user.set_password(secrets.token_urlsafe(24))
            db.session.add(user)
            commit_or_rollback()

        # Khởi tạo Session & Chống Session Fixation
        session.permanent = True
        _start_authenticated_session(user)
        session["user_role"] = user.role

        return jsonify({
            "success": True,
            "message": f"Đăng nhập thành công với tài khoản Google ({user.email})!",
            "user": user.to_dict()
        })


