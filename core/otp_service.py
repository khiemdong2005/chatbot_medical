# ==============================================================
# MEDIMIND CLINICAL AI - IN-MEMORY CRYPTOGRAPHIC OTP SERVICE
# Quản lý mã OTP 6 số, giới hạn tần suất (Rate Limiting) & Thời gian sống (TTL)
# ==============================================================

import time
import secrets
import threading
from typing import Tuple, Dict, Any, Optional

from core.email_service import email_service
from core.sms_service import sms_service


class OtpManager:
    """Trình quản lý mã OTP an toàn đa luồng (Thread-safe)."""
    def __init__(self, ttl_seconds: int = 300, cooldown_seconds: int = 60, max_attempts: int = 3):
        self.ttl = ttl_seconds
        self.cooldown = cooldown_seconds
        self.max_attempts = max_attempts
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _cleanup_expired(self):
        """Dọn dẹp các mã OTP đã hết hạn."""
        now = time.time()
        expired_keys = [k for k, v in self._store.items() if now > v["expires_at"]]
        for k in expired_keys:
            del self._store[k]

    def request_otp(
        self,
        identifier: str,
        channel: str = "email",  # "email" hoặc "sms"
        purpose: str = "register",  # "register", "login_2fa", "reset_pwd"
        full_name: Optional[str] = None
    ) -> Tuple[bool, str, int]:
        """
        Khởi tạo và gửi mã OTP 6 số qua Email hoặc SMS.
        Trả về: (thành công, thông báo, thời gian chờ còn lại tính bằng giây)
        """
        with self._lock:
            self._cleanup_expired()
            key = f"{channel}:{identifier.strip().lower()}"
            now = time.time()

            # Kiểm tra thời gian chờ gửi lại (Cooldown 60s)
            if key in self._store:
                entry = self._store[key]
                elapsed = now - entry["created_at"]
                if elapsed < self.cooldown:
                    remaining = int(self.cooldown - elapsed)
                    return False, f"Vui lòng đợi {remaining} giây trước khi yêu cầu mã mới.", remaining

            # Tạo mã OTP 6 chữ số ngẫu nhiên chuẩn mật mã (CSPRNG)
            otp_code = f"{secrets.randbelow(900000) + 100000}"

            self._store[key] = {
                "code": otp_code,
                "created_at": now,
                "expires_at": now + self.ttl,
                "attempts": 0,
                "purpose": purpose,
                "full_name": full_name,
                "verified": False
            }

        # Tiến hành gửi qua kênh tương ứng ngoài Lock
        if channel == "email":
            sent = email_service.send_verification_otp(identifier, otp_code, full_name=full_name, purpose=purpose)
        else:
            sent = sms_service.send_otp_sms(identifier, otp_code)

        if sent:
            return True, f"Mã xác thực đã được gửi tới {identifier}.", self.cooldown
        else:
            return False, "Không thể gửi mã xác thực. Vui lòng thử lại sau.", 0

    def verify_otp(self, identifier: str, channel: str, code: str, purpose: Optional[str] = None) -> Tuple[bool, str]:
        """
        Xác minh mã OTP người dùng nhập vào.
        """
        with self._lock:
            self._cleanup_expired()
            key = f"{channel}:{identifier.strip().lower()}"
            if key not in self._store:
                return False, "Mã xác thực không tồn tại hoặc đã hết hạn (sau 5 phút)."

            entry = self._store[key]
            now = time.time()

            if now > entry["expires_at"]:
                del self._store[key]
                return False, "Mã xác thực đã hết hạn. Vui lòng yêu cầu mã mới."

            if entry["attempts"] >= self.max_attempts:
                del self._store[key]
                return False, "Bạn đã nhập sai quá 3 lần. Mã đã bị hủy vì lý do an toàn."

            if purpose and entry.get("purpose") != purpose:
                return False, "Mã xác thực không khớp với mục đích yêu cầu."

            if entry["code"] != code.strip():
                entry["attempts"] += 1
                remaining_attempts = self.max_attempts - entry["attempts"]
                return False, f"Mã xác thực không chính xác. Bạn còn {remaining_attempts} lần thử."

            # Đánh dấu đã xác thực thành công và xóa mã
            entry["verified"] = True
            del self._store[key]
            return True, "Xác thực danh tính thành công."

    def get_active_code(self, identifier: str, channel: str) -> Optional[str]:
        """Lấy mã OTP đang hoạt động phục vụ Dev mode."""
        with self._lock:
            key = f"{channel}:{identifier.strip().lower()}"
            entry = self._store.get(key)
            if entry and time.time() <= entry["expires_at"]:
                return entry["code"]
            return None

    def is_verified(self, identifier: str, channel: str) -> bool:
        """Kiểm tra xem định danh đã vượt qua kiểm tra OTP gần đây hay chưa."""
        with self._lock:
            key = f"{channel}:{identifier.strip().lower()}"
            return self._store.get(key, {}).get("verified", False)


otp_manager = OtpManager()
