"""
core/rate_limit_service.py
Dịch vụ kiểm soát tần suất yêu cầu (Rate Limiting) dùng chung cho MediMind.
Hỗ trợ kiến trúc Backend trừu tượng: InMemory (Thread-safe) và sẵn sàng cho Redis trong tương lai (Phase 8.2 Hardening).
"""
import time
import threading
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger("RateLimitService")


class BaseRateLimitBackend(ABC):
    """Giao diện trừu tượng cho tầng lưu trữ Rate Limit."""

    @abstractmethod
    def check_and_increment(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Trả về True nếu yêu cầu được phép (Allowed), False nếu vượt ngưỡng (Blocked)."""
        pass

    @abstractmethod
    def reset(self, key: str) -> None:
        """Xóa bộ đếm cho khóa chỉ định."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Xóa toàn bộ bộ nhớ rate limit."""
        pass


class MemoryRateLimitBackend(BaseRateLimitBackend):
    """Tầng lưu trữ Rate Limit trên bộ nhớ RAM tiến trình (Thread-safe, có dọn dẹp TTL)."""

    def __init__(self, max_entries: int = 10000, cleanup_interval: float = 60.0):
        self._lock = threading.RLock()
        self._store: Dict[str, Dict[str, Any]] = {}
        self._max_entries = max(100, int(max_entries))
        self._cleanup_interval = max(1.0, float(cleanup_interval))
        self._last_cleanup = time.time()

    def _evict_if_needed(self, now: float) -> None:
        """Dọn dẹp các bucket đã hết hạn và giới hạn trần bộ nhớ chống OOM."""
        if (now - self._last_cleanup) >= self._cleanup_interval or len(self._store) >= self._max_entries:
            expired_keys = [k for k, rec in self._store.items() if now > rec["expires_at"]]
            for k in expired_keys:
                self._store.pop(k, None)
            self._last_cleanup = now

            if len(self._store) >= self._max_entries:
                overflow = len(self._store) - self._max_entries + 1
                oldest_keys = sorted(self._store, key=lambda k: self._store[k]["expires_at"])[:overflow]
                for k in oldest_keys:
                    self._store.pop(k, None)

    def check_and_increment(self, key: str, max_requests: int, window_seconds: int) -> bool:
        with self._lock:
            now = time.time()
            self._evict_if_needed(now)
            record = self._store.get(key)
            if not record or now > record["expires_at"]:
                self._store[key] = {"count": 1, "expires_at": now + window_seconds}
                return True

            if record["count"] >= max_requests:
                return False

            record["count"] += 1
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._last_cleanup = time.time()


class RateLimitService:
    """Dịch vụ Rate Limiting toàn diện cho xác thực, OTP và trò chuyện."""

    def __init__(self, backend: Optional[BaseRateLimitBackend] = None):
        self.backend = backend or MemoryRateLimitBackend()

    def check_login_rate_limit(
        self,
        client_ip: str,
        identifier: str,
        max_attempts: int = 5,
        window_seconds: int = 300
    ) -> bool:
        """
        Bảo vệ brute-force form đăng nhập mật khẩu:
        Giới hạn tối đa 5 lần thử sai trong 5 phút theo IP + Tài khoản.
        """
        clean_id = (identifier or "").strip().lower()
        clean_ip = (client_ip or "127.0.0.1").strip()
        key = f"login:{clean_ip}:{clean_id}"
        allowed = self.backend.check_and_increment(key, max_attempts, window_seconds)
        if not allowed:
            logger.warning("Đăng nhập vượt ngưỡng thử sai (429) cho IP %s và tài khoản %s.", clean_ip, clean_id)
        return allowed

    def reset_login_attempts(self, client_ip: str, identifier: str) -> None:
        """Xóa bộ đếm đăng nhập sau khi xác thực thành công."""
        clean_id = (identifier or "").strip().lower()
        clean_ip = (client_ip or "127.0.0.1").strip()
        key = f"login:{clean_ip}:{clean_id}"
        self.backend.reset(key)

    def check_login_ip_rate_limit(
        self,
        client_ip: str,
        max_attempts: int = 30,
        window_seconds: int = 900
    ) -> bool:
        """
        Bảo vệ chống Password Spraying trên nhiều tài khoản từ cùng một địa chỉ IP:
        Giới hạn tổng số lần thử đăng nhập theo IP độc lập với identifier.
        """
        clean_ip = (client_ip or "127.0.0.1").strip()
        key = f"login_ip:{clean_ip}"
        allowed = self.backend.check_and_increment(key, max_attempts, window_seconds)
        if not allowed:
            logger.warning("Đăng nhập vượt ngưỡng tổng theo IP (429 - Password Spraying) cho IP %s.", clean_ip)
        return allowed

    def check_otp_send_ip_rate_limit(
        self,
        client_ip: str,
        max_requests: int = 5,
        window_seconds: int = 900
    ) -> bool:
        """
        Bảo vệ chống SMS/Email OTP Bombing theo địa chỉ IP:
        Giới hạn tối đa 5 yêu cầu gửi mã OTP trong 15 phút từ cùng một IP.
        """
        clean_ip = (client_ip or "127.0.0.1").strip()
        key = f"otp_send_ip:{clean_ip}"
        allowed = self.backend.check_and_increment(key, max_requests, window_seconds)
        if not allowed:
            logger.warning("Yêu cầu gửi OTP vượt ngưỡng theo IP (429 - OTP Bombing) cho IP %s.", clean_ip)
        return allowed

    def check_otp_rate_limit(
        self,
        target: str,
        max_attempts: int = 5,
        window_seconds: int = 300
    ) -> bool:
        """Giới hạn xác thực mã OTP: Tối đa 5 lần thử trong 5 phút."""
        clean_target = (target or "").strip().lower()
        key = f"otp:{clean_target}"
        allowed = self.backend.check_and_increment(key, max_attempts, window_seconds)
        if not allowed:
            logger.warning("Nhập sai mã OTP vượt ngưỡng (429) cho %s.", clean_target)
        return allowed

    def reset_otp_attempts(self, target: str) -> None:
        """Xóa bộ đếm OTP sau khi xác thực thành công."""
        clean_target = (target or "").strip().lower()
        key = f"otp:{clean_target}"
        self.backend.reset(key)

    def check_chat_rate_limit(
        self,
        identity: str,
        max_requests: int = 25,
        window_seconds: int = 60,
        enforce: bool = True
    ) -> bool:
        """Giới hạn tần suất chat lâm sàng: Tối đa 25 requests / 60 giây."""
        if not enforce:
            return True
        key = f"chat:{identity}"
        allowed = self.backend.check_and_increment(key, max_requests, window_seconds)
        if not allowed:
            logger.warning("Tin nhắn chat vượt ngưỡng tần suất (429) cho định danh %s.", identity.split(":")[0])
        return allowed

    def check_chat_ip_rate_limit(
        self,
        client_ip: str,
        max_requests: int = 60,
        window_seconds: int = 60,
        enforce: bool = True
    ) -> bool:
        """VULN-10: IP-level rate limit for /api/chat — secondary gate that cannot be
        bypassed by rotating guest tokens.

        Policy: max 60 requests per IP per 60 seconds (lenient enough for legitimate
        users behind shared NAT, tight enough to block token-rotation abuse).
        Applied in ADDITION to the existing identity-based limit.
        No Redis required — uses same in-memory backend.
        """
        if not enforce:
            return True
        clean_ip = (client_ip or "127.0.0.1").strip()
        key = f"chat_ip:{clean_ip}"
        allowed = self.backend.check_and_increment(key, max_requests, window_seconds)
        if not allowed:
            logger.warning(
                "VULN-10: Chat IP rate limit exceeded (429) for IP %s — possible guest-token rotation attack.",
                clean_ip
            )
        return allowed

    def get_chat_identity(
        self,
        user_id: Optional[int] = None,
        guest_token: Optional[str] = None,
        client_ip: Optional[str] = None
    ) -> str:
        """
        Chiến lược định danh cho Rate Limiting theo thứ tự ưu tiên:
        1. Authenticated User ID (nếu đã đăng nhập)
        2. Guest Token (nếu là khách có phiên)
        3. Client IP (fallback an toàn cuối cùng)
        """
        if user_id is not None:
            return f"user:{user_id}"
        if guest_token:
            return f"guest:{guest_token}"
        return f"ip:{client_ip or '127.0.0.1'}"

    def clear_all(self) -> None:
        """Xóa toàn bộ bộ đếm (dùng cho testing)."""
        self.backend.clear()


# Singleton instance toàn hệ thống
rate_limit_service = RateLimitService()
