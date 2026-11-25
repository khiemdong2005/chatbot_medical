"""
================================================================================
🩺 MEDIMIND LIGHTWEIGHT CIRCUIT BREAKER FOR AI SERVICES
================================================================================
Mục đích:
  - Ngăn chặn việc liên tục gửi request khi Google Gemini hoặc Network gặp sự cố
    nghiêm trọng (Cascading Failure Prevention).
  - 3 trạng thái chuẩn:
      1. CLOSED: Hoạt động bình thường. Mọi request được chuyển tiếp đến AI.
      2. OPEN: Khi có quá nhiều lỗi tạm thời liên tiếp (vượt ngưỡng threshold),
               ngắt mạch hoàn toàn trong thời gian cooldown. Mọi request AI bị
               từ chối ngay lập tức (fail-fast 0ms) để chuyển sang Fallback Engine.
      3. HALF_OPEN: Sau khi hết thời gian cooldown, cho phép 1 request thử nghiệm.
                    Nếu thành công -> đóng mạch (CLOSED); nếu thất bại -> tiếp tục OPEN.
  - An toàn lâm sàng tuyệt đối:
      Circuit Breaker chỉ bảo vệ tầng gọi AI; KHÔNG BAO GIỜ can thiệp hay ảnh hưởng
      đến bộ lọc cấp cứu (Emergency Pre-check). Cấp cứu luôn trả phản hồi tức thì.
================================================================================
"""

import os
import time
import logging
import threading
from enum import Enum
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from core.ai_types import ErrorClassification
from core.settings import settings

load_dotenv()
logger = logging.getLogger("CircuitBreaker")


class CircuitState(str, Enum):
    """Trạng thái của Circuit Breaker."""
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Ngoại lệ ném ra khi mạch đang ở trạng thái OPEN."""
    pass


class CircuitBreaker:
    """
    Bộ ngắt mạch an toàn nhẹ cho các cuộc gọi AI.
    Hỗ trợ Thread-Safe và cấu hình động qua biến môi trường.
    """

    def __init__(
        self,
        name: str = "gemini_ai",
        failure_threshold: Optional[int] = None,
        cooldown_seconds: Optional[float] = None,
        enabled: Optional[bool] = None
    ):
        self.name = name
        self.enabled = (
            enabled if enabled is not None
            else settings.circuit_breaker.enabled
        )
        self.failure_threshold = (
            failure_threshold if failure_threshold is not None
            else settings.circuit_breaker.failure_threshold
        )
        self.cooldown_seconds = (
            cooldown_seconds if cooldown_seconds is not None
            else settings.circuit_breaker.cooldown_seconds
        )

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float = 0.0
        self._lock = threading.Lock()
        self._half_open_in_flight = False

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._check_state_transition()
            return self._state

    def _check_state_transition(self):
        """Kiểm tra xem trạng thái OPEN đã đủ điều kiện chuyển sang HALF_OPEN chưa."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.cooldown_seconds:
                logger.info(
                    "🔄 [CIRCUIT-%s] Cooldown (%.1fs) hoàn tất. Chuyển OPEN -> HALF_OPEN (cho phép 1 request thử).",
                    self.name, self.cooldown_seconds
                )
                self._state = CircuitState.HALF_OPEN
                self._half_open_in_flight = False

    def can_execute(self) -> bool:
        """
        Kiểm tra xem request có được phép thực thi không.
        - Nếu disabled hoặc CLOSED: Cho phép.
        - Nếu OPEN: Từ chối ngay lập tức (fail fast).
        - Nếu HALF_OPEN: Cho phép đúng 1 request thử nghiệm.
        """
        if not self.enabled:
            return True

        with self._lock:
            self._check_state_transition()

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                return False

            if self._state == CircuitState.HALF_OPEN:
                if not self._half_open_in_flight:
                    self._half_open_in_flight = True
                    return True
                return False

            return False

    def record_success(self):
        """Ghi nhận lượt gọi AI thành công."""
        if not self.enabled:
            return

        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    "✅ [CIRCUIT-%s] Request thử nghiệm thành công! Chuyển HALF_OPEN -> CLOSED (Mạch đã phục hồi).",
                    self.name
                )
                self._state = CircuitState.CLOSED
                self._consecutive_failures = 0
                self._half_open_in_flight = False
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures = 0

    def record_failure(self, classification: ErrorClassification):
        """
        Ghi nhận lượt gọi AI thất bại.
        Chỉ tính các lỗi transient (Rate limit, Server error, Timeout, Network error).
        Các lỗi client như 400 hoặc 401 không được tính vào để tránh ngắt mạch sai.
        """
        if not self.enabled:
            return

        transient_classes = {
            ErrorClassification.RATE_LIMIT,
            ErrorClassification.SERVER_ERROR,
            ErrorClassification.TIMEOUT,
            ErrorClassification.NETWORK_ERROR
        }

        if classification not in transient_classes:
            return

        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.warning(
                    "❌ [CIRCUIT-%s] Request thử nghiệm thất bại (%s)! Chuyển lại HALF_OPEN -> OPEN (cooldown %.1fs).",
                    self.name, classification.value, self.cooldown_seconds
                )
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                self._half_open_in_flight = False
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures += 1
                logger.debug(
                    "[CIRCUIT-%s] Lỗi transient %s ghi nhận (%d/%d).",
                    self.name, classification.value, self._consecutive_failures, self.failure_threshold
                )
                if self._consecutive_failures >= self.failure_threshold:
                    logger.warning(
                        "🚨 [CIRCUIT-%s] Đã đạt %d lỗi transient liên tiếp! NGẮT MẠCH: CLOSED -> OPEN trong %.1fs.",
                        self.name, self._consecutive_failures, self.cooldown_seconds
                    )
                    self._state = CircuitState.OPEN
                    self._opened_at = time.monotonic()

    def reset(self):
        """Đặt lại trạng thái ban đầu (dùng cho test hoặc manual override)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = 0.0
            self._half_open_in_flight = False

    def trip_for_test(self):
        """Chủ động ngắt mạch (dùng cho kiểm thử độ bền)."""
        with self._lock:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            self._consecutive_failures = self.failure_threshold

    def get_status(self) -> Dict[str, Any]:
        """Lấy trạng thái chi tiết của Circuit Breaker."""
        with self._lock:
            self._check_state_transition()
            cooldown_rem = 0.0
            if self._state == CircuitState.OPEN and self._opened_at > 0:
                elapsed = time.monotonic() - self._opened_at
                cooldown_rem = max(0.0, round(self.cooldown_seconds - elapsed, 2))
            return {
                "name": self.name,
                "enabled": self.enabled,
                "state": self._state.value,
                "failure_count": self._consecutive_failures,
                "consecutive_failures": self._consecutive_failures,
                "failure_threshold": self.failure_threshold,
                "cooldown_seconds": self.cooldown_seconds,
                "cooldown_remaining": cooldown_rem,
                "opened_at": self._opened_at
            }


# Thể hiện Singleton dùng chung toàn hệ thống cho Gemini AI
gemini_circuit_breaker = CircuitBreaker(name="gemini_main")
groq_circuit_breaker = CircuitBreaker(name="groq_main")

_circuit_breakers: Dict[str, CircuitBreaker] = {
    "gemini_main": gemini_circuit_breaker,
    "groq_main": groq_circuit_breaker,
    "chat": gemini_circuit_breaker
}
_breakers_lock = threading.Lock()


def get_circuit_breaker(name: str = "gemini_main") -> CircuitBreaker:
    """
    Lấy hoặc khởi tạo Circuit Breaker độc lập theo tên workload / profile.
    Đảm bảo tính cách ly: sự cố ở workload này (như nutrition) không làm sập workload khác (như chat).
    """
    with _breakers_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name=name)
        return _circuit_breakers[name]


def reset_all_circuit_breakers() -> None:
    """Reset toàn bộ các circuit breakers về trạng thái CLOSED (phục vụ test)."""
    with _breakers_lock:
        for cb in _circuit_breakers.values():
            cb.reset()


