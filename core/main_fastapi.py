"""
================================================================================
🩺 MEDIMIND CLINICAL AI - FASTAPI BACKEND GATEWAY
================================================================================
Mục đích:
  - Máy chủ Backend xây dựng bằng FastAPI & Uvicorn.
  - Chat dùng chung dịch vụ xử lý lâm sàng; xác thực và đơn thuốc dùng chung luồng Flask.
  - Không chặn event loop: Đưa các tác vụ nặng (OCR, LLM, RAG) sang worker thread pool bằng run_in_threadpool.
  - Tự động sinh tài liệu API tương tác trực quan (Swagger UI tại /docs, ReDoc tại /redoc).
================================================================================
"""

import os
import sys
import time
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# Đảm bảo console Windows xuất ký tự tiếng Việt UTF-8 chuẩn xác
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

from pydantic import field_validator

from fastapi import FastAPI, Request, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
# VULN-11: starlette.middleware.wsgi.WSGIMiddleware is deprecated in Starlette ≥ 0.21.
# Preferred replacement: a2wsgi (https://github.com/abersheeran/a2wsgi).
# If a2wsgi is not installed, fall back to the starlette implementation with a logged warning.
try:
    from a2wsgi import WSGIMiddleware  # preferred: pip install a2wsgi
except ImportError:
    import warnings as _warnings
    _warnings.warn(
        "VULN-11 [MediMind Security]: a2wsgi is not installed. Falling back to the deprecated "
        "starlette.middleware.wsgi.WSGIMiddleware. Install a2wsgi to resolve this: pip install a2wsgi",
        DeprecationWarning,
        stacklevel=1,
    )
    from starlette.middleware.wsgi import WSGIMiddleware  # deprecated fallback
from starlette.routing import Route

from core.api_errors import fastapi_api_error, status_code_to_error_code, ErrorCode

from core.chat_service import process_clinical_chat, execute_chat_workflow
from core.health_context import validate_chat_request
from core.storage_service import decode_and_validate_base64_image
from core.gemini_service import GeminiMedicalService
from core.observability import metrics_collector, record_http_metrics
from core.rag_service import medical_rag_service
from core.circuit_breaker import gemini_circuit_breaker
from core.rate_limit_service import rate_limit_service
from core.security_patch import get_rate_limit_identity, check_chat_rate_limit
from core.routers.deps import require_admin
from core.settings import get_settings
from core.network_utils import get_trusted_client_ip, is_request_https
from core.security_headers import get_security_headers
from core.logging_redaction import setup_logging_redaction, redact_sensitive_text
from app import app as flask_app_instance

setup_logging_redaction()

logger = logging.getLogger("FastAPI")

# Đường dẫn thư mục
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

settings = get_settings()
is_production = settings.server.is_production
docs_url = None if is_production else "/docs"
redoc_url = None if is_production else "/redoc"
openapi_url = None if is_production else "/openapi.json"

# Khởi tạo FastAPI App
app = FastAPI(
    title="🩺 MediMind Clinical AI - Trợ lý Sức khỏe Toàn diện",
    description="""
### 🏥 API Gateway cho Hệ thống Chatbot Y tế Lâm sàng phục vụ Người Dân
Được đồng bộ dịch vụ lõi với Flask backend chính:
* **Grounded RAG Engine:** Truy xuất dữ liệu chuẩn MedlinePlus lưu trong ChromaDB.
* **LLM Reasoning:** Sử dụng Google Gemini Flash với System Prompt y tế ân cần.
* **Double Guardrails:** Tiền kiểm cờ đỏ cấp cứu và hậu kiểm can thiệp kháng sinh.
* **Asynchronous Non-blocking:** Toàn bộ tác vụ OCR/LLM được offload sang Thread Pool.
* **Storage Protection:** Giới hạn request size, kiểm tra magic bytes và chống path traversal.
    """,
    version="2.5.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url
)

# Cấu hình CORS
cors_origins = list(settings.security.cors_allowed_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Bơm đồng nhất Security Headers cho các route native của FastAPI (Phase 8.3) và ghi nhận HTTP RED metrics."""
    start_time = time.time()
    response = await call_next(request)
    is_https = is_request_https(
        request.url.scheme == "https",
        dict(request.headers),
        trust_proxy=settings.security.trust_proxy_headers
    )
    for k, v in get_security_headers(is_https=is_https).items():
        response.headers[k] = v

    path = request.url.path
    is_wsgi_compat = (
        path == "/metrics"
        or path.startswith("/uploads/")
        or any(path == f"/api/{p}" or path.startswith(f"/api/{p}/") for p in FLASK_COMPAT_PREFIXES)
    )
    if not is_wsgi_compat and not path.startswith("/static/"):
        record_http_metrics(request.method, path, response.status_code, max(0.0, time.time() - start_time))
    return response


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    """Bảo vệ chống tấn công CSRF trên các mutating routes của FastAPI Gateway (Phase 8.2)."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        from core.csrf_protection import validate_csrf_request

        is_valid, error_msg = validate_csrf_request(
            request.method,
            dict(request.headers),
            dict(request.cookies),
            request.url.netloc
        )
        if not is_valid:
            return fastapi_api_error(
                ErrorCode.FORBIDDEN,
                error_msg or "Yêu cầu bị từ chối do vi phạm chính sách bảo vệ CSRF.",
                status_code=403
            )

    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Normalize FastAPI HTTP exceptions vào canonical error envelope."""
    code = status_code_to_error_code(exc.status_code)
    return fastapi_api_error(code, str(exc.detail), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Normalize Pydantic request validation exceptions."""
    errors = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
    first_msg = errors[0].get("msg", "Dữ liệu yêu cầu không hợp lệ.") if errors else "Dữ liệu yêu cầu không hợp lệ."
    return fastapi_api_error(ErrorCode.VALIDATION_ERROR, first_msg, status_code=400, details=errors)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Bắt và chuẩn hóa toàn bộ unhandled exceptions, che giấu stack trace nhạy cảm (Phase 8.3)."""
    logger.error("Unhandled server exception (%s): %s", type(exc).__name__, redact_sensitive_text(str(exc)))
    return fastapi_api_error(
        ErrorCode.INTERNAL_ERROR,
        "Đã có lỗi nội bộ xảy ra trong quá trình xử lý.",
        status_code=500
    )


# Mount thư mục Static Files & Templates
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

import jinja2
@jinja2.pass_context
def compat_url_for(context: dict, name: str, **path_params):
    if name == "static" and "filename" in path_params and "path" not in path_params:
        path_params["path"] = path_params.pop("filename")
    request = context["request"]
    return request.url_for(name, **path_params)

templates.env.globals["url_for"] = compat_url_for

# Khởi tạo dịch vụ Gemini AI dùng chung
gemini_service = GeminiMedicalService()


# ==============================================================================
# PYDANTIC SCHEMAS
# ==============================================================================

class ChatMessageRequest(BaseModel):
    message: str = Field(
        ...,
        max_length=2000,
        description="Tin nhắn mô tả triệu chứng hoặc câu hỏi sức khỏe của người dân",
        json_schema_extra={"example": "Tôi bị đau họng và sốt nhẹ từ hôm qua"}
    )
    history: List[Dict[str, Any]] = Field(
        default=[],
        max_length=50,
        description="Lịch sử các lượt chat gần nhất để duy trì ngữ cảnh (Memory)",
        json_schema_extra={"example": []}
    )
    image: Optional[str] = Field(
        default=None,
        description="Dữ liệu ảnh chụp tổn thương dạng Base64 Data URL (data:image/jpeg;base64,...)"
    )
    lang: Optional[str] = Field(
        default="vi",
        description="Ngôn ngữ tư vấn ('vi' hoặc 'en')",
        json_schema_extra={"example": "vi"}
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Mã phiên cuộc trò chuyện để liên kết Intake & Bệnh sử lâm sàng",
        json_schema_extra={"example": "conv_12345"}
    )
    health_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Thông tin sức khỏe tự khai, tùy chọn cho lượt chat; không lưu hồ sơ tài khoản"
    )

    @field_validator("history")
    @classmethod
    def validate_history_turns(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for turn in v:
            if not isinstance(turn, dict):
                raise ValueError("Mỗi lượt lịch sử phải là một đối tượng dict.")
            role = turn.get("role")
            if role not in ("user", "assistant"):
                raise ValueError("Role trong lịch sử phải là 'user' hoặc 'assistant'.")
            content = turn.get("content")
            if not isinstance(content, str) or len(content) > 12000:
                raise ValueError("Nội dung tin nhắn lịch sử phải là chuỗi và không vượt quá 12.000 ký tự.")
        return v


# ==============================================================================
# 1. GIAO DIỆN NGƯỜI DÙNG (FRONTEND ROUTE)
# ==============================================================================

@app.get("/", response_class=HTMLResponse, summary="Giao diện Web Trợ lý Sức khỏe MediMind")
async def get_index(request: Request):
    """Phục vụ toàn bộ giao diện Web."""
    google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    return templates.TemplateResponse(
        request,
        "index.html",
        context={"request": request, "google_maps_api_key": google_maps_api_key},
    )


def extract_request_identity(request: Request) -> tuple[Optional[int], Optional[str], bool]:
    """
    Trích xuất (user_id, guest_token, is_new_guest) từ cookie / header.
    Nếu chưa có guest_token, tự động sinh mới một mã gst_...
    """
    user_id = None
    guest_token = None
    is_new = False

    # 1. Đọc từ Flask session cookie nếu có
    cookie_name = getattr(flask_app_instance, "session_cookie_name", "session")
    raw_cookie = request.cookies.get(cookie_name)
    if raw_cookie:
        try:
            serializer = flask_app_instance.session_interface.get_signing_serializer(flask_app_instance)
            if serializer:
                data = serializer.loads(raw_cookie)
                if isinstance(data, dict):
                    user_id = data.get("user_id")
                    guest_token = data.get("guest_token")
        except Exception:
            pass

    # 2. Đọc từ cookie guest_token riêng nếu có
    if not guest_token:
        guest_token = request.cookies.get("guest_token")

    # 3. Đọc từ header X-Guest-Token nếu có
    if not guest_token:
        guest_token = request.headers.get("X-Guest-Token")

    # 4. Nếu vẫn chưa có guest_token (phiên khách mới tinh), tự động sinh mới
    if not guest_token:
        guest_token = f"gst_{uuid.uuid4().hex[:12]}"
        is_new = True

    return user_id, guest_token, is_new


# ==============================================================================
# 2. HỆ THỐNG TƯ VẤN Y TẾ & CHATBOT LÂM SÀNG (OFFLOAD WORKER THREADPOOL)
# ==============================================================================

@app.post("/api/chat", summary="Tư vấn Triệu chứng Y tế (RAG + Gemini Vision + Double Guardrails)", tags=["1. Tư vấn Lâm sàng (Chatbot)"])
async def chat_endpoint(request: Request, req: ChatMessageRequest):
    """
    Sử dụng chung dịch vụ process_clinical_chat và offload sang thread pool để không block asyncio loop:
    1. Tiền kiểm cờ đỏ cấp cứu
    2. Truy vấn tri thức RAG từ ChromaDB
    3. Bộ não AI Gemini Flash + Fallback nội bộ
    4. Hậu kiểm màng lọc chặn kê đơn kháng sinh
    """
    try:
        payload = validate_chat_request(req.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    user_message = payload["message"]
    if not user_message and not req.image:
        raise HTTPException(status_code=400, detail="Vui lòng nhập nội dung tin nhắn hoặc tải ảnh.")

    # Giải mã ảnh an toàn nếu có
    image_bytes = None
    image_mime_type = "image/jpeg"
    if req.image:
        img_bytes, mime, err = decode_and_validate_base64_image(req.image)
        if err:
            raise HTTPException(status_code=400, detail=f"Tệp ảnh không hợp lệ: {err}")
        image_bytes = img_bytes
        image_mime_type = mime

    user_id, guest_token, is_new_guest = extract_request_identity(request)
    client_ip = get_trusted_client_ip(
        request.client.host if request.client else "127.0.0.1",
        dict(request.headers),
        trust_proxy=settings.security.trust_proxy_headers,
        trusted_proxy_count=settings.security.trusted_proxy_count
    )
    rate_id = get_rate_limit_identity(user_id=user_id, guest_token=guest_token, client_ip=client_ip)
    is_testing = os.getenv("TESTING", "").lower() in ("1", "true") or getattr(flask_app_instance, "testing", False)
    if not rate_limit_service.check_chat_ip_rate_limit(client_ip, max_requests=60, window_seconds=60, enforce=not is_testing):
        raise HTTPException(status_code=429, detail="Quá nhiều yêu cầu từ địa chỉ mạng của bạn. Vui lòng thử lại sau.")
    if not check_chat_rate_limit(rate_id, max_requests=25, window_seconds=60, enforce=not is_testing):
        raise HTTPException(status_code=429, detail="Bạn đang gửi tin nhắn quá nhanh. Vui lòng đợi ít phút rồi thử lại.")

    try:
        # Offload sang worker threadpool
        result = await run_in_threadpool(
            execute_chat_workflow,
            message=user_message,
            history=payload["history"],
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
            lang=payload.get("lang") or "vi",
            conversation_id=payload.get("conversation_id"),
            health_context=payload.get("health_context"),
            gemini_service=gemini_service,
            user_id=user_id,
            guest_token=guest_token,
            chat_processor=process_clinical_chat
        )
        response = JSONResponse(content=result)
        if is_new_guest and guest_token:
            cookie_secure = bool(settings.server.is_production or settings.security.session_cookie_secure)
            response.set_cookie(
                key="guest_token",
                value=guest_token,
                httponly=True,
                samesite="lax",
                secure=cookie_secure,
            )
        return response
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except KeyError:
        raise HTTPException(status_code=409, detail="Cuộc trò chuyện đã được xóa trong lúc xử lý. Hãy bắt đầu cuộc trò chuyện mới.")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Error in chat_endpoint: %s", e)
        raise HTTPException(status_code=500, detail="Đã xảy ra sự cố trong quá trình xử lý yêu cầu y tế.")


# ==============================================================================
# 2.1 GIÁM SÁT HỆ THỐNG & SỨC KHỎE RUNTIME (LOCAL OBSERVABILITY & HEALTH)
# ==============================================================================

@app.get("/health", summary="Liveness Probe", tags=["0. Giám sát & Sức khỏe (Observability)"])
async def health_endpoint():
    """Kiểm tra tiến trình còn sống (Process Liveness) cực nhanh, không gọi network hay Gemini."""
    return {"status": "ok"}


@app.get("/ready", summary="Readiness Probe", tags=["0. Giám sát & Sức khỏe (Observability)"])
async def ready_endpoint():
    """
    Kiểm tra mức độ sẵn sàng phục vụ (Readiness Probe):
    - Kiểm tra RAG index & ChromaDB
    - Kiểm tra trạng thái Circuit Breaker
    """
    rag_ready = medical_rag_service.is_available()
    cb_status = gemini_circuit_breaker.get_status()
    cb_state = cb_status.get("state", "CLOSED")

    gemini_status = "degraded" if cb_state == "OPEN" else "ready"
    rag_status = "ready" if rag_ready else "not_ready"

    if not rag_ready:
        overall_status = "not_ready"
        status_code = 503
    elif cb_state == "OPEN":
        overall_status = "degraded"
        status_code = 200
    else:
        overall_status = "ready"
        status_code = 200

    payload = {
        "status": overall_status,
        "rag": rag_status,
        "gemini": gemini_status,
        "circuit_breaker": cb_state
    }
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/api/system/metrics", summary="Local System Metrics Snapshot", tags=["0. Giám sát & Sức khỏe (Observability)"])
async def system_metrics_endpoint(request: Request):
    """Trả về toàn bộ số liệu thống kê hiệu năng, lỗi và độ trễ (Zero-PHI)."""
    require_admin(request)
    if not metrics_collector.is_enabled():
        raise HTTPException(status_code=403, detail="System metrics endpoint is disabled.")
    return JSONResponse(content=metrics_collector.get_summary())


@app.post("/api/system/metrics/reset", summary="Reset Local System Metrics", tags=["0. Giám sát & Sức khỏe (Observability)"])
async def reset_system_metrics_endpoint(request: Request):
    """Đặt lại toàn bộ số liệu thống kê về 0 (Chỉ dùng cho Local Testing & Development)."""
    require_admin(request)
    if not metrics_collector.is_enabled():
        raise HTTPException(status_code=403, detail="System metrics endpoint is disabled.")
    metrics_collector.reset()
    return JSONResponse(content={"status": "reset_successful"})


@app.get("/system", response_class=HTMLResponse, summary="Local Observability Dashboard", tags=["0. Giám sát & Sức khỏe (Observability)"])
@app.get("/admin/system", response_class=HTMLResponse, summary="Local Observability Dashboard", tags=["0. Giám sát & Sức khỏe (Observability)"])
async def system_dashboard_page(request: Request):
    """Trang giao diện Dashboard giám sát sức khỏe và độ trễ cục bộ."""
    require_admin(request)
    return templates.TemplateResponse(request, "system_dashboard.html", context={"request": request})


# ==============================================================================
# 2.2 FASTAPI NATIVE API ROUTERS (MIGRATED ROUTE FAMILIES)
# ==============================================================================

from core.routers.facilities import router as facilities_router
from core.routers.config import router as config_router
from core.routers.appointments import router as appointments_router
from core.routers.consultations import router as consultations_router
from core.routers.clinical_summary import router as clinical_summary_router

app.include_router(facilities_router)
app.include_router(config_router)
app.include_router(appointments_router)
app.include_router(consultations_router)
app.include_router(clinical_summary_router)


# ==============================================================================
# 3. FLASK COMPATIBILITY GATEWAY (WSGI MOUNT)
# ==============================================================================

# Đồng bộ Flask app instance cho tầng lưu trữ Intake & CSDL dùng chung
from core.intake_service import set_flask_app
from core.db_utils import set_flask_app as set_db_flask_app
set_flask_app(flask_app_instance)
set_db_flask_app(flask_app_instance)

# Cấu hình WSGIMiddleware kết nối các nhánh endpoint còn lại từ Flask
flask_gateway = WSGIMiddleware(flask_app_instance)

FLASK_COMPAT_PREFIXES = (
    "auth",
    "prescription",
    "intake",
    "nutrition",
    "scan-files",
    "upload-lab",
)

for prefix in FLASK_COMPAT_PREFIXES:
    app.router.routes.append(Route(f"/api/{prefix}", flask_gateway,
                                   methods=["GET", "POST", "PUT", "DELETE", "PATCH"]))
    app.router.routes.append(Route(f"/api/{prefix}/", flask_gateway,
                                   methods=["GET", "POST", "PUT", "DELETE", "PATCH"]))
    app.router.routes.append(Route(f"/api/{prefix}/{{rest:path}}", flask_gateway,
                                   methods=["GET", "POST", "PUT", "DELETE", "PATCH"]))

# Mount Flask handlers for uploaded document previews and Prometheus metrics (keeping Flask guards intact)
app.router.routes.append(Route("/uploads/{rest:path}", flask_gateway, methods=["GET"]))
app.router.routes.append(Route("/metrics", flask_gateway, methods=["GET"]))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print("=" * 65)
    print(f"🚀 MEDIMIND FASTAPI SERVER ĐANG CHẠY TẠI: http://127.0.0.1:{port}")
    print(f"📖 TÀI LIỆU SWAGGER UI TƯƠNG TÁC: http://127.0.0.1:{port}/docs")
    print(f"📄 TÀI LIỆU REDOC: http://127.0.0.1:{port}/redoc")
    print("=" * 65)
    uvicorn.run("core.main_fastapi:app", host="0.0.0.0", port=port, reload=False)
