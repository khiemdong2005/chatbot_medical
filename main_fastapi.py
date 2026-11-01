"""
================================================================================
🩺 MEDIMIND CLINICAL AI - FASTAPI BACKEND GATEWAY
================================================================================
Mục đích:
  - Máy chủ Backend xây dựng bằng FastAPI & Uvicorn.
  - Sử dụng chung hoàn toàn Application Services (core/chat_service, core/storage_service, core/auth_service)
    để đảm bảo tính tương đương và nhất quán 100% với Flask backend chính.
  - Không chặn event loop: Đưa các tác vụ nặng (OCR, LLM, RAG) sang worker thread pool bằng run_in_threadpool.
  - Tự động sinh tài liệu API tương tác trực quan (Swagger UI tại /docs, ReDoc tại /redoc).
================================================================================
"""

import os
import sys
import uuid
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

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from core.chat_service import process_clinical_chat
from core.storage_service import (
    decode_and_validate_base64_image,
    validate_file_content,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    is_safe_path
)
from core.prescription_service import get_preset_data, analyze_uploaded_document
from core.gemini_service import GeminiMedicalService
from core.auth_service import register_user, authenticate_user
from app import app as flask_app_instance

# Đường dẫn thư mục
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

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

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


class AuthLoginRequest(BaseModel):
    identifier: str = Field(
        ...,
        description="Email hoặc số điện thoại của người dân",
        json_schema_extra={"example": "benhnhan.an@gmail.com"}
    )
    password: str = Field(
        ...,
        description="Mật khẩu đăng nhập",
        json_schema_extra={"example": "MatKhau123@"}
    )


class AuthRegisterRequest(BaseModel):
    name: Optional[str] = Field(None, description="Họ và tên người dân", json_schema_extra={"example": "Nguyễn Văn An"})
    full_name: Optional[str] = None
    email: Optional[str] = None
    identifier: Optional[str] = None
    password: str = Field(..., description="Mật khẩu (tối thiểu 6 ký tự)", json_schema_extra={"example": "MatKhau123@"})
    dob: Optional[str] = None
    gender: Optional[str] = None
    role: Optional[str] = Field("patient", description="Vai trò luôn mặc định là patient")


# ==============================================================================
# 1. GIAO DIỆN NGƯỜI DÙNG (FRONTEND ROUTE)
# ==============================================================================

@app.get("/", response_class=HTMLResponse, summary="Giao diện Web Trợ lý Sức khỏe MediMind")
async def get_index(request: Request):
    """Phục vụ toàn bộ giao diện Web."""
    return templates.TemplateResponse(request, "index.html", context={"request": request})


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
    user_message = req.message.strip()
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
            history=req.history,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
            lang=req.lang or "vi",
            gemini_service=gemini_service
        )
        return JSONResponse(content=result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Đã xảy ra sự cố trong quá trình xử lý yêu cầu y tế.")


# ==============================================================================
# 3. ĐỌC KẾT QUẢ XÉT NGHIỆM & QUÉT ĐƠN THUỐC
# ==============================================================================

@app.post("/api/prescription/scan", summary="Quét & Phân tích Đơn thuốc / Xét nghiệm AI", tags=["2. Đọc Đơn thuốc & Xét nghiệm"])
async def scan_prescription_endpoint(request: Request):
    """
    Quét và phân tích đơn thuốc hoặc kết quả xét nghiệm:
    BẢO MẬT & HIỆU NĂNG:
      - Giới hạn Content-Length (10MB) trước khi đọc dữ liệu.
      - Kiểm tra magic bytes và chống Path Traversal bằng UUID ngẫu nhiên.
      - Offload tác vụ OCR/AI nặng sang run_in_threadpool.
    """
    content_type = request.headers.get("content-type", "")
    preset = request.query_params.get("preset")

    # Giới hạn kích thước request trước khi đọc
    content_len = request.headers.get("content-length")
    if content_len:
        try:
            if int(content_len) > MAX_FILE_SIZE_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"status": "failed", "message": "Dung lượng tệp vượt quá giới hạn cho phép (10 MB)."}
                )
        except ValueError:
            pass

    # 1. Xử lý tải tệp lên (FormData)
    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
            uploaded_file = form.get("file")
            if uploaded_file and hasattr(uploaded_file, "filename") and uploaded_file.filename:
                orig_filename = Path(uploaded_file.filename).name
                ext = orig_filename.rsplit(".", 1)[-1].lower() if "." in orig_filename else "bin"
                if ext not in ALLOWED_EXTENSIONS:
                    return JSONResponse(
                        status_code=400,
                        content={"status": "failed", "message": f"Định dạng '.{ext}' không được hỗ trợ. Vui lòng chọn JPG, PNG, PDF hoặc DOCX."}
                    )

                # Đọc dữ liệu có giới hạn kích thước
                file_bytes = await uploaded_file.read()
                if len(file_bytes) > MAX_FILE_SIZE_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"status": "failed", "message": "Dung lượng tệp vượt quá giới hạn 10 MB."}
                    )

                # Kiểm tra magic bytes
                if not validate_file_content(file_bytes, ext):
                    return JSONResponse(
                        status_code=400,
                        content={"status": "failed", "message": f"Nội dung tệp không khớp với định dạng .{ext}."}
                    )

                # Lưu với tên UUID ngẫu nhiên để chống path traversal và ghi đè
                safe_name = f"{uuid.uuid4().hex}.{ext}"
                save_path = (UPLOAD_FOLDER / safe_name).resolve()
                if not is_safe_path(save_path, UPLOAD_FOLDER):
                    return JSONResponse(status_code=400, content={"status": "failed", "message": "Đường dẫn không an toàn."})

                with open(save_path, "wb") as f:
                    f.write(file_bytes)

                # Offload phân tích tài liệu nặng sang worker thread
                result = await run_in_threadpool(analyze_uploaded_document, str(save_path), orig_filename)
                return JSONResponse(content=result)

            form_preset = form.get("preset")
            if form_preset:
                preset = form_preset
        except Exception as e:
            return JSONResponse(status_code=400, content={"status": "failed", "message": f"Lỗi xử lý tệp: {e}"})

    # 2. Xử lý JSON Body chọn Preset
    elif "application/json" in content_type:
        try:
            data = await request.json()
            if isinstance(data, dict) and "preset" in data:
                preset = data["preset"]
        except Exception:
            pass

    if preset:
        return JSONResponse(content=get_preset_data(preset))

    return JSONResponse(
        status_code=400,
        content={"status": "error", "message": "Vui lòng đính kèm tệp đơn thuốc hoặc chỉ định tham số preset."}
    )


# ==============================================================================
# 4. HỆ THỐNG XÁC THỰC NGƯỜI DÙNG (KẾT NỐI DỊCH VỤ TÀI KHOẢN THẬT)
# ==============================================================================

@app.post("/api/auth/login", summary="Đăng nhập Tài khoản Người Dân", tags=["4. Xác thực & Tài khoản"])
async def auth_login_endpoint(req: AuthLoginRequest):
    """Đăng nhập bằng Email hoặc Số điện thoại với CSDL thật."""
    with flask_app_instance.app_context():
        success, res_data, status_code = authenticate_user(
            raw_identifier=req.identifier,
            password=req.password
        )
        if success:
            return JSONResponse(
                status_code=status_code,
                content={"success": True, "message": "Đăng nhập thành công!", "user": res_data}
            )
        return JSONResponse(status_code=status_code, content={"success": False, "error": res_data.get("error")})


@app.post("/api/auth/register", summary="Đăng ký Tài khoản Sức khỏe Mới", tags=["4. Xác thực & Tài khoản"])
async def auth_register_endpoint(req: AuthRegisterRequest):
    """
    Đăng ký tài khoản mới:
    Lưu vào CSDL thật, luôn gán role patient, từ chối tự cấp quyền doctor/admin.
    """
    with flask_app_instance.app_context():
        identifier = req.identifier or req.email or ""
        name = req.full_name or req.name or "Bệnh nhân mới"
        success, res_data, status_code = register_user(
            raw_identifier=identifier,
            password=req.password,
            full_name=name,
            dob=req.dob,
            gender=req.gender
        )
        if success:
            return JSONResponse(
                status_code=status_code,
                content={"success": True, "message": "Đăng ký tài khoản thành công!", "user": res_data}
            )
        return JSONResponse(status_code=status_code, content={"success": False, "error": res_data.get("error")})


@app.get("/api/auth/me", summary="Kiểm tra Trạng thái Đăng nhập", tags=["4. Xác thực & Tài khoản"])
async def auth_me_endpoint():
    """Kiểm tra phiên đăng nhập (Không giả lập authenticated=True)."""
    return JSONResponse(content={"authenticated": False, "user": None})


@app.post("/api/auth/logout", summary="Đăng xuất", tags=["4. Xác thực & Tài khoản"])
async def auth_logout_endpoint():
    """Đăng xuất tài khoản."""
    return JSONResponse(content={"success": True, "message": "Đã đăng xuất thành công."})


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print("=" * 65)
    print(f"🚀 MEDIMIND FASTAPI SERVER ĐANG CHẠY TẠI: http://127.0.0.1:{port}")
    print(f"📖 TÀI LIỆU SWAGGER UI TƯƠNG TÁC: http://127.0.0.1:{port}/docs")
    print(f"📄 TÀI LIỆU REDOC: http://127.0.0.1:{port}/redoc")
    print("=" * 65)
    uvicorn.run("main_fastapi:app", host="0.0.0.0", port=port, reload=False)
