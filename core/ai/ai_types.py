"""
core/ai_types.py
Định nghĩa các bảng mã phân loại lỗi và kiểu dữ liệu dùng chung cho hạ tầng AI.
Tách biệt khỏi retry_policy và circuit_breaker để triệt tiêu phụ thuộc vòng lặp (Circular Dependency).
"""
from enum import Enum


class ErrorClassification(str, Enum):
    """Bảng mã phân loại lỗi chuẩn hóa cho toàn bộ hệ thống AI."""
    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    SERVER_ERROR = "SERVER_ERROR"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    SCHEMA_ERROR = "SCHEMA_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    UNKNOWN = "UNKNOWN"
