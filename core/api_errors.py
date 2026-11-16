"""
core/api_errors.py
Chuẩn hóa kiến trúc Error Boundary và Response Schema cho MediMind.
Cung cấp canonical schema {"error": {"code": ..., "message": ...}}
đồng thời duy trì lớp bọc transitional (detail, message, success, status)
để đảm bảo tương thích ngược 100% với cả FastAPI, Flask và Frontend hiện tại.
"""
from enum import Enum
from typing import Any, Dict, Optional, Union


class ErrorCode(str, Enum):
    """Bảng mã lỗi chuẩn hóa toàn hệ thống (Public Error Codes)."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def status_code_to_error_code(status_code: int) -> ErrorCode:
    """Ánh xạ HTTP status code sang canonical ErrorCode."""
    if status_code == 400:
        return ErrorCode.VALIDATION_ERROR
    elif status_code == 401:
        return ErrorCode.AUTH_REQUIRED
    elif status_code == 403:
        return ErrorCode.FORBIDDEN
    elif status_code == 404:
        return ErrorCode.NOT_FOUND
    elif status_code == 429:
        return ErrorCode.RATE_LIMITED
    elif status_code in (502, 503, 504):
        return ErrorCode.AI_UNAVAILABLE
    else:
        return ErrorCode.INTERNAL_ERROR


def make_error_payload(
    code: Union[ErrorCode, str],
    message: str,
    details: Optional[Any] = None,
    legacy_status: str = "error"
) -> Dict[str, Any]:
    """
    Tạo cấu trúc phản hồi lỗi canonical chuẩn y tế.
    Schema canonical:
      {
        "error": {
          "code": "VALIDATION_ERROR",
          "message": "..."
        }
      }
    Trường tương thích ngược kèm theo:
      - "message": message (cho frontend legacy đọc data.message)
      - "detail": message (cho client FastAPI / Starlette đọc data.detail)
      - "success": False (cho endpoint kiểu Flask API)
      - "status": legacy_status
    """
    code_str = code.value if isinstance(code, ErrorCode) else str(code)
    clean_msg = str(message or "Đã xảy ra lỗi trong quá trình xử lý.")

    payload: Dict[str, Any] = {
        "error": {
            "code": code_str,
            "message": clean_msg
        },
        "success": False,
        "message": clean_msg,
        "detail": clean_msg,
        "status": legacy_status
    }

    if details is not None:
        payload["error"]["details"] = details

    return payload


def flask_api_error(
    code: Union[ErrorCode, str],
    message: str,
    status_code: int = 400,
    details: Optional[Any] = None
):
    """Tạo Flask response chứa error payload chuẩn."""
    from flask import jsonify
    return jsonify(make_error_payload(code, message, details=details)), status_code


def fastapi_api_error(
    code: Union[ErrorCode, str],
    message: str,
    status_code: int = 400,
    details: Optional[Any] = None
):
    """Tạo FastAPI/Starlette JSONResponse chứa error payload chuẩn."""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content=make_error_payload(code, message, details=details)
    )


class APIError(Exception):
    """Ngoại lệ chuẩn cho các tầng nghiệp vụ độc lập framework."""
    def __init__(
        self,
        code: Union[ErrorCode, str],
        message: str,
        status_code: int = 400,
        details: Optional[Any] = None
    ):
        super().__init__(message)
        self.code = code if isinstance(code, ErrorCode) else ErrorCode(str(code))
        self.message = message
        self.status_code = status_code
        self.details = details

    def to_dict(self) -> Dict[str, Any]:
        return make_error_payload(self.code, self.message, details=self.details)
