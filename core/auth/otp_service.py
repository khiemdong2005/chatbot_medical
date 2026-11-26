# ==============================================================
# MEDIMIND CLINICAL AI - CRYPTOGRAPHIC OTP SERVICE (IN-MEMORY + REDIS)
# Quản lý mã OTP 6 số, giới hạn tần suất (Rate Limiting) & Thời gian sống (TTL)
# Tự động dùng Redis dùng chung khi cấu hình REDIS_URL (Multi-EC2 / ASG),
# giữ nguyên In-Memory fallback an toàn cho Local Dev & Testing.
# ==============================================================

import json
import logging
import os
import secrets
import threading
import time
from typing import Tuple, Dict, Any, Optional

from core.auth.email_service import email_service
from core.auth.sms_service import sms_service

try:
    import redis as _redis_mod
except ImportError:
    _redis_mod = None

logger = logging.getLogger("OtpService")


class OtpManager:
    """Trình quản lý mã OTP an toàn đa luồng (Thread-safe, hỗ trợ Redis đa nút)."""

    _REDIS_CODE_PREFIX = "medimind:otp:code:"
    _REDIS_VERIFIED_PREFIX = "medimind:otp:verified:"

    def __init__(
        self,
        ttl_seconds: int = 120,
        cooldown_seconds: int = 60,
        max_attempts: int = 5,
        max_entries: int = 5000,
        redis_client: Optional[Any] = None,
    ):
        self.ttl = ttl_seconds
        self.cooldown = cooldown_seconds
        self.max_attempts = max_attempts
        self.max_entries = max(100, int(max_entries))
        self._store: Dict[str, Dict[str, Any]] = {}
        self._verified_store: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._redis_client = redis_client
        self._redis_initialized = redis_client is not None

    def _get_redis(self) -> Optional[Any]:
        """Khởi tạo kết nối Redis lười biếng chỉ khi REDIS_URL được cấu hình rõ ràng."""
        if self._redis_initialized:
            return self._redis_client
        self._redis_initialized = True
        redis_url = (os.getenv("REDIS_URL") or "").strip()
        if not redis_url or _redis_mod is None:
            return None
        try:
            client = _redis_mod.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2,
            )
            client.ping()
            self._redis_client = client
            logger.info("[OtpService] Đã kết nối Redis dùng chung cho OTP đa nút.")
        except Exception as exc:
            self._redis_client = None
            logger.warning("[OtpService] Không thể kết nối Redis (%s). Fallback sang In-Memory OTP.", type(exc).__name__)
        return self._redis_client

    def _r_code_key(self, key: str) -> str:
        return f"{self._REDIS_CODE_PREFIX}{key}"

    def _r_verified_key(self, key: str) -> str:
        return f"{self._REDIS_VERIFIED_PREFIX}{key}"

    def _load_entry(self, key: str) -> Optional[Dict[str, Any]]:
        client = self._get_redis()
        if client is not None:
            try:
                raw = client.get(self._r_code_key(key))
                if raw is not None:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return data
                    return None
            except Exception as exc:
                logger.warning("[OtpService] Redis read error (%s), fallback In-Memory.", type(exc).__name__)
        return self._store.get(key)

    def _save_entry(self, key: str, entry: Dict[str, Any], ttl_seconds: Optional[float] = None) -> None:
        client = self._get_redis()
        if client is not None:
            try:
                ttl = max(1, int(ttl_seconds if ttl_seconds is not None else self.ttl))
                client.setex(self._r_code_key(key), ttl, json.dumps(entry))
                return
            except Exception as exc:
                logger.warning("[OtpService] Redis write error (%s), fallback In-Memory.", type(exc).__name__)
        self._store[key] = entry

    def _delete_entry(self, key: str, expected_code: Optional[str] = None) -> None:
        client = self._get_redis()
        if client is not None:
            try:
                rkey = self._r_code_key(key)
                if expected_code is not None:
                    raw = client.get(rkey)
                    if raw is not None:
                        data = json.loads(raw)
                        if isinstance(data, dict) and data.get("code") == expected_code:
                            client.delete(rkey)
                else:
                    client.delete(rkey)
            except Exception as exc:
                logger.warning("[OtpService] Redis delete error (%s), fallback In-Memory.", type(exc).__name__)
        if expected_code is not None:
            existing = self._store.get(key)
            if existing and existing.get("code") == expected_code:
                del self._store[key]
        else:
            self._store.pop(key, None)

    def _mark_verified(self, key: str, now: float) -> None:
        client = self._get_redis()
        if client is not None:
            try:
                client.setex(self._r_verified_key(key), max(1, int(self.ttl)), "1")
                return
            except Exception as exc:
                logger.warning("[OtpService] Redis verified-set error (%s), fallback In-Memory.", type(exc).__name__)
        self._verified_store[key] = now + self.ttl

    def _cleanup_expired(self):
        """Dọn dẹp các mã OTP đã hết hạn và giới hạn kích thước bộ nhớ tạm."""
        now = time.time()
        expired_keys = [k for k, v in self._store.items() if now > v["expires_at"]]
        for k in expired_keys:
            del self._store[k]
        expired_verified = [k for k, exp in self._verified_store.items() if now > exp]
        for k in expired_verified:
            del self._verified_store[k]
        if len(self._store) >= self.max_entries:
            drop_count = max(1, self.max_entries // 5)
            oldest = sorted(self._store.items(), key=lambda item: item[1]["expires_at"])[:drop_count]
            for k, _ in oldest:
                self._store.pop(k, None)

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
        # Kiểm tra trước số điện thoại nếu là kênh SMS (Chỉ hỗ trợ đầu số Việt Nam, chặn quốc tế)
        if channel == "sms":
            if not sms_service.normalize_phone(identifier):
                return False, "Hệ thống chỉ hỗ trợ gửi mã OTP qua số điện thoại nội địa Việt Nam (+84). Đã chặn gửi OTP quốc tế.", 0

        with self._lock:
            self._cleanup_expired()
            key = f"{channel}:{identifier.strip().lower()}"
            now = time.time()

            # Kiểm tra thời gian chờ gửi lại (Cooldown 60s)
            entry = self._load_entry(key)
            if entry is not None:
                elapsed = now - entry["created_at"]
                if elapsed < self.cooldown:
                    remaining = int(self.cooldown - elapsed)
                    return False, f"Vui lòng đợi {remaining} giây trước khi yêu cầu mã mới.", remaining

            # Tạo mã OTP 6 chữ số ngẫu nhiên chuẩn mật mã (CSPRNG)
            otp_code = f"{secrets.randbelow(900000) + 100000}"

            pending = {
                "code": otp_code,
                "created_at": now,
                "expires_at": now + self.ttl,
                "attempts": 0,
                "purpose": purpose,
                "full_name": full_name,
                "verified": False
            }
            self._save_entry(key, pending, ttl_seconds=self.ttl)

        # Tiến hành gửi qua kênh tương ứng ngoài Lock
        try:
            if channel == "email":
                sent = email_service.send_verification_otp(
                    identifier,
                    otp_code,
                    full_name=full_name,
                    purpose=purpose,
                    ttl_seconds=self.ttl,
                )
            else:
                sent = sms_service.send_otp_sms(identifier, otp_code, ttl_seconds=self.ttl)
        except Exception:
            sent = False

        if sent:
            return True, f"Mã xác thực đã được gửi tới {identifier}.", self.cooldown
        with self._lock:
            self._delete_entry(key, expected_code=otp_code)
        return False, "Không thể gửi mã xác thực. Vui lòng thử lại sau.", 0

    def verify_otp(self, identifier: str, channel: str, code: str, purpose: Optional[str] = None) -> Tuple[bool, str]:
        """
        Xác minh mã OTP người dùng nhập vào.
        """
        with self._lock:
            self._cleanup_expired()
            key = f"{channel}:{identifier.strip().lower()}"
            ttl_minutes = max(1, self.ttl // 60)
            entry = self._load_entry(key)
            if entry is None:
                return False, f"Mã xác thực không tồn tại hoặc đã hết hạn (sau {ttl_minutes} phút)."

            now = time.time()

            if now > entry["expires_at"]:
                self._delete_entry(key)
                return False, "Mã xác thực đã hết hạn. Vui lòng yêu cầu mã mới."

            if entry["attempts"] >= self.max_attempts:
                self._delete_entry(key)
                return False, f"Bạn đã nhập sai quá {self.max_attempts} lần. Mã đã bị hủy vì lý do an toàn."

            if purpose and entry.get("purpose") != purpose:
                return False, "Mã xác thực không khớp với mục đích yêu cầu."

            if not secrets.compare_digest(str(entry["code"]), code.strip()):
                entry["attempts"] += 1
                remaining_attempts = self.max_attempts - entry["attempts"]
                if remaining_attempts <= 0:
                    self._delete_entry(key)
                    return False, f"Bạn đã nhập sai quá {self.max_attempts} lần. Mã đã bị hủy vì lý do an toàn."
                self._save_entry(key, entry, ttl_seconds=max(1, int(entry["expires_at"] - now)))
                return False, f"Mã xác thực không chính xác. Bạn còn {remaining_attempts} lần thử."

            # Đánh dấu đã xác thực thành công và xóa mã OTP dùng một lần
            self._mark_verified(key, now)
            self._delete_entry(key)
            return True, "Xác thực danh tính thành công."

    def get_active_code(self, identifier: str, channel: str) -> Optional[str]:
        """Lấy mã OTP đang hoạt động phục vụ Dev mode."""
        with self._lock:
            key = f"{channel}:{identifier.strip().lower()}"
            entry = self._load_entry(key)
            if entry and time.time() <= entry["expires_at"]:
                return entry["code"]
            return None

    def is_verified(self, identifier: str, channel: str, consume: bool = True) -> bool:
        """Kiểm tra xem định danh đã vượt qua kiểm tra OTP gần đây hay chưa."""
        with self._lock:
            key = f"{channel}:{identifier.strip().lower()}"
            client = self._get_redis()
            if client is not None:
                try:
                    rkey = self._r_verified_key(key)
                    val = client.get(rkey)
                    if val is not None:
                        if consume:
                            client.delete(rkey)
                        return True
                    # Kiểm tra tiếp in-memory phòng trường hợp vừa fallback
                except Exception as exc:
                    logger.warning("[OtpService] Redis verified-check error (%s), fallback In-Memory.", type(exc).__name__)
            exp = self._verified_store.get(key)
            if exp and time.time() <= exp:
                if consume:
                    del self._verified_store[key]
                return True
            if key in self._verified_store:
                del self._verified_store[key]
            return False


otp_manager = OtpManager()
