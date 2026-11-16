"""
core/logging_redaction.py
Bộ lọc che giấu dữ liệu nhạy cảm (PII / Secrets / Tokens) tập trung cho Logging (Phase 8.3).
Ngăn chặn rò rỉ API Keys, Session Tokens, Mật khẩu, Email, Số điện thoại trong Log hệ thống.
"""
import re
import logging
from typing import Any

# Các biểu thức chính quy nhận diện mẫu dữ liệu nhạy cảm
REDACTION_PATTERNS = [
    # 1. Google Gemini / Cloud API Key
    (re.compile(r"AIzaSy[A-Za-z0-9_-]{25,50}"), "[API_KEY_REDACTED]"),
    # 2. Bearer Tokens & Auth Headers
    (re.compile(r"(?i)(Authorization:\s*Bearer\s+)[A-Za-z0-9_\-\.]{10,}"), r"\1[TOKEN_REDACTED]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.]{15,}"), "Bearer [TOKEN_REDACTED]"),
    # 3. Session Cookies trong HTTP Headers
    (re.compile(r"(?i)(session=)[A-Za-z0-9_\.\-]{15,}"), r"\1[SESSION_REDACTED]"),
    # 4. Parameters nhạy cảm: token, secret, password
    (
        re.compile(r"(?i)(password|passwd|matkhau|secret|access_token|refresh_token|id_token|guest_token)([\"']?\s*[:=]\s*[\"']?)[^\"',\s&]+"),
        r"\1\2[REDACTED]"
    ),
    # 5. Địa chỉ Email
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL_REDACTED]"),
    # 6. Số điện thoại Việt Nam (10 chữ số bắt đầu bằng 0 hoặc +84)
    (re.compile(r"(?:\+84|0)(?:3|5|7|8|9)\d{8}\b"), "[PHONE_REDACTED]"),
]


def redact_sensitive_text(text: Any) -> str:
    """Áp dụng toàn bộ quy tắc che giấu dữ liệu nhạy cảm lên một chuỗi văn bản."""
    if not isinstance(text, str):
        text = str(text)

    redacted = text
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class SensitiveDataRedactionFilter(logging.Filter):
    """Logging Filter tự động lọc bỏ PII và Secrets trước khi ghi vào log handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if record.args:
                try:
                    formatted_msg = record.msg % record.args
                    record.msg = redact_sensitive_text(formatted_msg)
                    record.args = ()
                except Exception:
                    record.msg = redact_sensitive_text(record.msg)
                    if isinstance(record.args, dict):
                        record.args = {k: redact_sensitive_text(v) if isinstance(v, str) else v for k, v in record.args.items()}
                    elif isinstance(record.args, (list, tuple)):
                        record.args = tuple(redact_sensitive_text(v) if isinstance(v, str) else v for v in record.args)
            elif isinstance(record.msg, str):
                record.msg = redact_sensitive_text(record.msg)
        except Exception:
            pass

        return True


def setup_logging_redaction() -> None:
    """Kích hoạt và gắn bộ lọc SensitiveDataRedactionFilter vào root logger và các handler hiện hữu."""
    filter_instance = SensitiveDataRedactionFilter()
    root_logger = logging.getLogger()

    # Tránh gắn trùng lặp filter
    if not any(isinstance(f, SensitiveDataRedactionFilter) for f in root_logger.filters):
        root_logger.addFilter(filter_instance)

    for handler in root_logger.handlers:
        if not any(isinstance(f, SensitiveDataRedactionFilter) for f in handler.filters):
            handler.addFilter(filter_instance)
