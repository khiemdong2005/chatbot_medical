# ==============================================================
# MEDIMIND CLINICAL AI - ENTERPRISE SECURITY & HARDENING MODULE
# ==============================================================

import os
import secrets
import html
from typing import Optional, Dict
from core.cache_service import cache_service

# 1. BẢO VỆ CHỮ KÝ TỆP TIN (MAGIC BYTES VERIFICATION)
# Ngăn chặn lỗ hổng Arbitrary File Upload ngụy trang đuôi mở rộng
MAGIC_SIGNATURES: Dict[str, list] = {
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "pdf": [b"%PDF"],
    "docx": [b"PK\x03\x04"],  # Standard Zip container (OpenXML)
    "doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"]  # OLE Compound File
}


def verify_file_signature(file_stream, ext: str) -> bool:
    """
    Kiểm tra Magic Bytes thực tế ở đầu tệp tin.
    Trả về True nếu chữ ký nhị phân khớp với định dạng khai báo.
    """
    ext = ext.lower().strip()
    expected_magics = MAGIC_SIGNATURES.get(ext)
    if not expected_magics:
        return False

    try:
        file_stream.seek(0)
        max_len = max(len(m) for m in expected_magics)
        header = file_stream.read(max_len)
        file_stream.seek(0)  # Reset con trỏ đọc về đầu tệp

        return any(header.startswith(magic) for magic in expected_magics)
    except Exception:
        return False


# 2. SINH MÃ XÁC THỰC OTP CHUẨN MẬT MÃ HỌC (CSPRNG)
def generate_secure_otp(length: int = 6) -> str:
    """
    Sinh mã OTP ngẫu nhiên chuẩn mật mã học bằng module secrets.
    Triệt tiêu 100% khả năng suy đoán chuỗi số giả ngẫu nhiên của PRNG (random.randint).
    """
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))


# 3. CHỐNG BRUTE-FORCE VÉT CẠN MÃ OTP (RATE LIMITING PER OTP)
def check_otp_attempts(email: str, max_attempts: int = 5) -> bool:
    """
    Giới hạn tối đa 5 lần nhập sai OTP.
    Nếu vượt quá 5 lần, khóa xác thực mã OTP đó để chống vét cạn.
    """
    attempt_key = f"otp_attempts:{email.lower().strip()}"
    attempts = cache_service.get(attempt_key) or 0
    if attempts >= max_attempts:
        return False
    cache_service.set(attempt_key, attempts + 1, ttl=300)
    return True


def reset_otp_attempts(email: str):
    """Xóa bỏ bộ đếm sau khi người dùng nhập đúng OTP thành công."""
    attempt_key = f"otp_attempts:{email.lower().strip()}"
    cache_service.delete(attempt_key)


# 4. LỌC VÀ LÀM SẠCH KÝ TỰ ĐỘC HẠI CHỐNG XSS
def sanitize_text(text: str) -> str:
    """Làm sạch ký tự HTML và JavaScript độc hại."""
    if not text:
        return ""
    return html.escape(text.strip(), quote=True)


# 5. GIỚI HẠN TẦN SUẤT TRÒ CHUYỆN (CHAT RATE LIMITING POLICY)
def get_rate_limit_identity(
    user_id: Optional[int] = None,
    guest_token: Optional[str] = None,
    client_ip: Optional[str] = None
) -> str:
    """
    Xác định khóa định danh cho Rate Limiting theo thứ tự ưu tiên:
    1. Authenticated User ID (nếu đã đăng nhập)
    2. Guest Token (nếu là khách có phiên)
    3. Client IP (fallback an toàn cuối cùng)
    """
    if user_id is not None:
        return f"user:{user_id}"
    if guest_token:
        return f"guest:{guest_token}"
    return f"ip:{client_ip or '127.0.0.1'}"


def check_chat_rate_limit(
    identity: str,
    max_requests: int = 25,
    window_seconds: int = 60,
    enforce: bool = True
) -> bool:
    """
    Kiểm tra giới hạn tần suất gửi tin nhắn trò chuyện y tế:
    Policy: Tối đa 25 requests trong 60 giây.
    Trả về True nếu được phép tiếp tục (Allowed);
    Trả về False nếu vượt quá ngưỡng (Rate Limited - HTTP 429).
    """
    if not enforce:
        return True

    rate_key = f"chat_rate:{identity}"
    blocked = cache_service.is_rate_limited(rate_key, max_requests=max_requests, window_seconds=window_seconds)
    if blocked:
        import logging
        logging.getLogger("Security").warning(
            "Tần suất gửi tin nhắn vượt ngưỡng cho phép (429 Rate Limit) đối với định danh %s.",
            identity.split(":")[0]  # Privacy-safe: chỉ ghi nhận loại identity (user/guest/ip)
        )
        return False
    return True
