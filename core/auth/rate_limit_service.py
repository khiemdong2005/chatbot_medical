"""
core/rate_limit_service.py
Dịch vụ kiểm soát tần suất yêu cầu (Rate Limiting) dùng chung cho MediMind.
Hỗ trợ kiến trúc Backend trừu tượng: InMemory (Thread-safe) và sẵn sàng cho Redis trong tương lai (Phase 8.2 Hardening).
"""
import os
import time
import threading
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

try:
    import redis as _redis_mod
except ImportError:
    _redis_mod = None

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
    """Tầng lưu trữ Rate Limit trên bộ nhớ RAM tiến trình (Thread-safe, có giới hạn dung lượng chống phình RAM)."""

    def __init__(self, max_keys: int = 10000):
        self._lock = threading.RLock()
        self._store: Dict[str, Dict[str, Any]] = {}
        self._max_keys = max(100, int(max_keys))

    def _evict_if_needed(self, now: float) -> None:
        if len(self._store) < self._max_keys:
            return
        expired = [k for k, v in self._store.items() if now > v["expires_at"]]
        for k in expired:
            del self._store[k]
        if len(self._store) >= self._max_keys:
            # Loại bỏ 20% khóa cũ nhất (sắp hết hạn sớm nhất) để bảo vệ bộ nhớ
            drop_count = max(1, self._max_keys // 5)
            oldest = sorted(self._store.items(), key=lambda item: item[1]["expires_at"])[:drop_count]
            for k, _ in oldest:
                self._store.pop(k, None)

    def check_and_increment(self, key: str, max_requests: int, window_seconds: int) -> bool:
        with self._lock:
            now = time.time()
            record = self._store.get(key)
            if not record or now > record["expires_at"]:
                self._evict_if_needed(now)
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


class RedisRateLimitBackend(BaseRateLimitBackend):
    """Tầng lưu trữ Rate Limit dùng chung trên Redis cho đa nút (Multi-EC2), có fallback In-Memory."""

    _KEY_PREFIX = "medimind:ratelimit:"

    def __init__(
        self,
        redis_client: Optional[Any] = None,
        redis_url: Optional[str] = None,
        fallback: Optional[MemoryRateLimitBackend] = None,
    ):
        self._fallback = fallback or MemoryRateLimitBackend()
        self._client = redis_client
        if self._client is None and redis_url and _redis_mod is not None:
            try:
                client = _redis_mod.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_timeout=2,
                    socket_connect_timeout=2,
                )
                client.ping()
                self._client = client
                logger.info("[RateLimitService] Đã kết nối Redis dùng chung cho Rate Limit đa nút.")
            except Exception as exc:
                self._client = None
                logger.warning(
                    "[RateLimitService] Không thể kết nối Redis (%s). Fallback sang In-Memory Rate Limit.",
                    type(exc).__name__,
                )

    def _rkey(self, key: str) -> str:
        return f"{self._KEY_PREFIX}{key}"

    def check_and_increment(self, key: str, max_requests: int, window_seconds: int) -> bool:
        if self._client is not None:
            try:
                rkey = self._rkey(key)
                count = int(self._client.incr(rkey))
                if count == 1:
                    self._client.expire(rkey, max(1, int(window_seconds)))
                else:
                    ttl_fn = getattr(self._client, "ttl", None)
                    if callable(ttl_fn) and ttl_fn(rkey) == -1:
                        self._client.expire(rkey, max(1, int(window_seconds)))
                return count <= max_requests
            except Exception as exc:
                logger.warning("[RateLimitService] Redis error (%s), fallback In-Memory.", type(exc).__name__)
        return self._fallback.check_and_increment(key, max_requests, window_seconds)

    def reset(self, key: str) -> None:
        if self._client is not None:
            try:
                self._client.delete(self._rkey(key))
            except Exception as exc:
                logger.warning("[RateLimitService] Redis reset error (%s).", type(exc).__name__)
        self._fallback.reset(key)

    def clear(self) -> None:
        if self._client is not None:
            try:
                scan_iter = getattr(self._client, "scan_iter", None)
                if callable(scan_iter):
                    keys = list(scan_iter(match=f"{self._KEY_PREFIX}*"))
                    if keys:
                        self._client.delete(*keys)
            except Exception as exc:
                logger.warning("[RateLimitService] Redis clear error (%s).", type(exc).__name__)
        self._fallback.clear()


def _create_default_rate_limit_backend() -> BaseRateLimitBackend:
    """Tự động kích hoạt Redis backend khi REDIS_URL được cấu hình; mặc định giữ In-Memory."""
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    if redis_url and _redis_mod is not None:
        backend = RedisRateLimitBackend(redis_url=redis_url)
        if backend._client is not None:
            return backend
    return MemoryRateLimitBackend()


class RateLimitService:
    """Dịch vụ Rate Limiting toàn diện cho xác thực, OTP và trò chuyện."""

    def __init__(self, backend: Optional[BaseRateLimitBackend] = None):
        self.backend = backend or _create_default_rate_limit_backend()

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
