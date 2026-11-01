from typing import Tuple, Dict, Any, Optional
from core.models import db, User


def register_user(
    raw_identifier: str,
    password: str,
    full_name: Optional[str] = None,
    phone_number: Optional[str] = None,
    dob: Optional[str] = None,
    gender: Optional[str] = "Nam"
) -> Tuple[bool, Dict[str, Any], int]:
    """
    Đăng ký người dùng mới:
    BẢO MẬT: Bắt buộc role là 'patient', không chấp nhận cấp quyền doctor/admin.
    """
    raw_id = (raw_identifier or "").strip()
    pwd = (password or "").strip()
    name = (full_name or "").strip() or "Bệnh nhân mới"

    if not raw_id or not pwd:
        return False, {"error": "Vui lòng điền đầy đủ Email/SĐT và mật khẩu."}, 400

    if len(pwd) < 6:
        return False, {"error": "Mật khẩu phải có tối thiểu 6 ký tự."}, 400

    phone = (phone_number or "").strip()
    if "@" in raw_id:
        email = raw_id
        if not phone:
            phone = None
    else:
        clean_phone = "".join(filter(str.isdigit, raw_id))
        if len(clean_phone) < 9 or len(clean_phone) > 11:
            return False, {"error": "Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số)."}, 400
        phone = clean_phone
        email = f"{clean_phone}@phone.medimind"

    # Kiểm tra trùng lặp
    existing = User.query.filter(
        (User.email == email) | 
        ((User.phone_number == phone) & (User.phone_number.isnot(None)))
    ).first()
    if existing:
        return False, {"error": "Tài khoản (Email hoặc Số điện thoại) này đã được sử dụng."}, 409

    new_user = User(
        email=email,
        full_name=name,
        role="patient",
        phone_number=phone,
        dob=(dob or "").strip(),
        gender=(gender or "Nam").strip(),
        license_code=None
    )
    new_user.set_password(pwd)
    db.session.add(new_user)
    db.session.commit()

    return True, new_user.to_dict(), 201


def authenticate_user(
    raw_identifier: str,
    password: str,
    role: Optional[str] = None
) -> Tuple[bool, Dict[str, Any], int]:
    """
    Xác thực đăng nhập người dùng.
    """
    raw_id = (raw_identifier or "").strip()
    pwd = (password or "").strip()

    if not raw_id or not pwd:
        return False, {"error": "Vui lòng nhập định danh tài khoản và mật khẩu."}, 400

    clean_phone = "".join(filter(str.isdigit, raw_id))
    user = User.query.filter(
        (User.email == raw_id) | 
        (User.phone_number == raw_id) |
        (User.phone_number == clean_phone) |
        (User.email == f"{clean_phone}@phone.medimind")
    ).first()

    if not user:
        return False, {"error": "Tài khoản không tồn tại trên hệ thống."}, 404

    if role and user.role != role:
        return False, {"error": f"Tài khoản này không có quyền truy cập vai trò '{role}'."}, 403

    if not user.check_password(pwd):
        return False, {"error": "Mật khẩu không chính xác. Vui lòng kiểm tra lại."}, 401

    return True, user.to_dict(), 200

