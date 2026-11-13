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

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.middleware.wsgi import WSGIMiddleware
from starlette.routing import Route

from core.chat_service import process_clinical_chat
from core.health_context import validate_chat_request
from core.storage_service import decode_and_validate_base64_image
from core.gemini_service import GeminiMedicalService
from app import app as flask_app_instance

# Đường dẫn thư mục
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

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
    docs_url="/docs",
    redoc_url="/redoc"
)

# Cấu hình CORS an toàn (chống lộ Cookie phiên qua Wildcard Origin)
_allowed_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
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
        description="Tin nhắn mô tả triệu chứng hoặc câu hỏi sức khỏe của người dân",
        json_schema_extra={"example": "Tôi bị đau họng và sốt nhẹ từ hôm qua"}
    )
    history: List[Dict[str, Any]] = Field(
        default=[],
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
    health_context: Optional[Dict[str, Any]] = Field(default=None, description="Thông tin sức khỏe tự khai, tùy chọn cho lượt chat; không lưu hồ sơ tài khoản")


# ==============================================================================
# 1. GIAO DIỆN NGƯỜI DÙNG (FRONTEND ROUTE)
# ==============================================================================

@app.get("/", response_class=HTMLResponse, summary="Giao diện Web Trợ lý Sức khỏe MediMind")
async def get_index(request: Request):
    """Phục vụ toàn bộ giao diện Web."""
    return templates.TemplateResponse(
        request,
        "index.html",
        context={
            "request": request,
            "google_maps_api_key": os.getenv("GOOGLE_MAPS_API_KEY", "").strip(),
        },
    )


# ==============================================================================
# 2. HỆ THỐNG TƯ VẤN Y TẾ & CHATBOT LÂM SÀNG (OFFLOAD WORKER THREADPOOL)
# ==============================================================================

@app.post("/api/chat", summary="Tư vấn Triệu chứng Y tế (RAG + Gemini Vision + Double Guardrails)", tags=["1. Tư vấn Lâm sàng (Chatbot)"])
async def chat_endpoint(req: ChatMessageRequest):
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

    try:
        # Offload sang worker threadpool
        result = await run_in_threadpool(
            process_clinical_chat,
            message=user_message,
            history=payload["history"],
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
            lang=req.lang or "vi",
            gemini_service=gemini_service,
            health_context=payload["health_context"]
        )
        return JSONResponse(content=result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Đã xảy ra sự cố trong quá trình xử lý yêu cầu y tế.")


# ==============================================================================
# 3. ĐỌC KẾT QUẢ XÉT NGHIỆM & QUÉT ĐƠN THUỐC
# ==============================================================================

# The OCR review and its login share Flask's owner-bound session cookie.
flask_gateway = WSGIMiddleware(flask_app_instance)
for prefix in ("auth", "prescription"):
    app.router.routes.append(Route(f"/api/{prefix}/{{rest:path}}", flask_gateway,
                                   methods=["GET", "POST", "PUT", "DELETE"]))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print("=" * 65)
    print(f"🚀 MEDIMIND FASTAPI SERVER ĐANG CHẠY TẠI: http://127.0.0.1:{port}")
    print(f"📖 TÀI LIỆU SWAGGER UI TƯƠNG TÁC: http://127.0.0.1:{port}/docs")
    print(f"📄 TÀI LIỆU REDOC: http://127.0.0.1:{port}/redoc")
    print("=" * 65)
    uvicorn.run("main_fastapi:app", host="0.0.0.0", port=port, reload=False)
