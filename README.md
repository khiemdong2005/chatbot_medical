# 🩺 MediMind Clinical AI — Nền Tảng Tư Vấn Y Tế Lâm Sàng, Đọc Đơn Thuốc & Dinh Dưỡng Trị Liệu

> **Cổng dịch vụ y tế số hỗ trợ sàng lọc triệu chứng, bóc tách đơn thuốc lâm sàng, gợi ý dinh dưỡng theo bệnh lý và tra cứu mạng lưới cơ sở y tế toàn quốc.**  
> Thiết kế theo **Kiến trúc Phân khu Nghiệp vụ (Feature-Sliced Modular Monolith)** với **Clinical Triage Protocol**, **RAG MedlinePlus** và **Medical Safety Guardrails**.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Framework-Flask%203.1-009688.svg)](https://flask.palletsprojects.com/)
[![ChromaDB](https://img.shields.io/badge/RAG-ChromaDB%20(725%20docs)-orange.svg)](https://www.trychroma.com/)
[![AI Providers](https://img.shields.io/badge/AI-Groq%20%7C%20OpenRouter%20%7C%20Gemini-6366F1.svg)](#5-cấu-hình-ai-provider-groq--openrouter)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#)

---

## 📖 1. Giới Thiệu Tổng Quan

**MediMind Clinical AI** là nền tảng trợ lý y tế số đa chức năng dành cho người dân và cơ sở y tế, hỗ trợ xuyên suốt từ sàng lọc triệu chứng ban đầu, chuẩn bị phiếu tiền khám (*Pre-Visit Summary*), số hóa đơn thuốc thành lịch uống thuốc 4 cữ, xây dựng thực đơn dinh dưỡng an toàn theo thể trạng đến tra cứu bản đồ cơ sở khám chữa bệnh.

Mọi phản hồi y khoa được thiết kế với rào chắn an toàn chặt chẽ:
- **Ưu tiên phát hiện cờ đỏ cấp cứu** (*đau thắt ngực, khó thở dữ dội, đột quỵ, xuất huyết...*) để điều hướng **Cấp cứu 115** tức thì (<10ms).
- **Đối chiếu nguồn y văn chuẩn** từ kho tri thức **MedlinePlus (NIH)** qua ChromaDB + BM25 Hybrid RAG.
- **Không kê đơn kháng sinh hay kết luận chẩn đoán áp đặt**; luôn bảo vệ người dùng khỏi khuyến nghị thiếu căn cứ.

---

## 🌟 2. Tính Năng Cốt Lõi

| Phân khu | Mô tả chi tiết |
| :--- | :--- |
| **💬 ChatBOT Lâm Sàng & Intake** | Sàng lọc triệu chứng đa lượt (`/api/chat`, `/api/intake/*`), nhận diện cờ đỏ cấp cứu 115, truy xuất RAG MedlinePlus (725 tài liệu ChromaDB + 364 tài liệu BM25 dự phòng), kiểm chứng bằng chứng y khoa (`grounded_points`), hỗ trợ song ngữ **Tiếng Việt / Tiếng Anh** và xuất phiếu tóm tắt trước khám. |
| **💊 Đọc Đơn Thuốc Lâm Sàng (Hybrid OCR)** | Kiến trúc đa tầng kết hợp **OpenCV + EasyOCR tiếng Việt cục bộ**, cắt phóng to vùng thuốc chuẩn **LANCZOS** gửi **Vision AI** (OpenRouter/Gemini), tự động chuẩn hóa văn bản OCR bằng **Groq LLM** khi Vision API bận, cho phép đối chiếu trực tiếp ảnh gốc và tạo **lịch uống thuốc 4 cữ (Sáng – Trưa – Chiều/Tối – Trước ngủ)**. Hỗ trợ 3 đơn mẫu lâm sàng (*Tiêu hóa*, *Hô hấp*, *Tim mạch*). |
| **🥗 Dinh Dưỡng Trị Liệu** | Lọc công thức theo bệnh lý & dị ứng từ kho chuẩn **ViFoodRec & Wikibooks**, tích hợp rào chắn từ chối lâm sàng (*clinical safeguard*) cho nhóm bệnh cần chỉ định bác sĩ, xếp hạng món ăn thông minh bằng **Groq (`openai/gpt-oss-20b`)**, gợi ý nhóm thực phẩm nên ăn / nên tránh và bữa ăn hoàn chỉnh. |
| **🗺️ Bản Đồ Cơ Sở Y Tế & Đặt Lịch** | Tra cứu **2,144 cơ sở y tế** (TP.HCM & Hà Nội) trên bản đồ tương tác **Leaflet + OpenStreetMap**, lọc theo tỉnh thành, quận huyện, loại hình, chuyên khoa và lưu lịch hẹn khám cá nhân. |
| **🔐 Xác Thực & Bảo Mật** | Đăng nhập / Đăng ký (bắt buộc xác thực OTP 6 số), **Google OAuth 2.0**, Quên mật khẩu & Đổi mật khẩu, gửi OTP qua **Gmail SMTP** và **SpeedSMS Việt Nam**, bảo vệ **CSRF Origin/Referer**, **Rate Limiting**, **Security Headers (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy)** và Zero-PHI Logging. |
| **🌐 Song Ngữ (VI ↔ EN)** | Chuyển đổi ngôn ngữ tức thì trên toàn bộ giao diện (Trang chủ, ChatBOT, Đơn thuốc, Dinh dưỡng, Bản đồ, Modal Đăng nhập) và đồng bộ ngôn ngữ phản hồi của AI. |

---

## 🏗️ 3. Kiến Trúc & Cấu Trúc Thư Mục

Hệ thống được tổ chức theo mô hình **Feature-Sliced Modular Monolith**: tách mỏng `app.py` (465 dòng), phân chia routes theo 5 miền tính năng tại `routes/` và gom lõi nghiệp vụ thành **7 phân khu trong `core/`** (kèm facade tương thích ngược tại `core/<module>.py`).

```text
Medical ChatBOT/
├── app.py                            # Application Factory, Security Middleware, /health, /ready, /favicon.ico, /docs
├── main_fastapi.py                   # Điểm vào FastAPI Gateway (tùy chọn)
├── ingest.py                         # Điểm vào nạp dữ liệu RAG
├── requirements.txt                  # Thư viện runtime chính
├── .env.example                      # Mẫu biến môi trường
│
├── routes/                           # 5 phân khu Flask routes độc lập
│   ├── auth_routes.py                #   /api/auth/* (Login, Register, Profile, OTP, Forgot Password, Google OAuth)
│   ├── chat_routes.py                #   /api/chat, /api/intake/*, /api/clinical-summary, /api/consultations
│   ├── ocr_routes.py                 #   /api/prescription/*, /api/scan-files, /api/upload-lab, /uploads/*
│   ├── nutrition_routes.py           #   /api/nutrition/options, /api/nutrition/analyze
│   └── facilities_routes.py          #   /api/facilities/*, /api/appointments/*
│
├── core/                             # 7 phân khu lõi nghiệp vụ (có shim tương thích tại core/*.py)
│   ├── ai/                           #   llm_provider (Groq/OpenRouter/Gemini), prompts, retry_policy, circuit_breaker
│   ├── chat/                         #   chat_service, gemini_service, rag_service, query_expansion, reranker, grounding, intake, triage
│   ├── ocr/                          #   pipeline_orchestrator, gemini_schema_service, prescription_crop, ocr_extractor, reconciliation
│   ├── nutrition/                    #   nutrition_options, nutrition_ai, nutrition_rules, nutrition_service, recipe_catalog
│   ├── auth/                         #   otp_service, email_service, sms_service, csrf_protection, rate_limit, security_headers
│   ├── facilities/                   #   facilities_service, appointment_service
│   └── shared/                       #   settings, models, migrations, db_utils, api_errors, validation_service, logging_redaction
│
├── templates/                        # Giao diện HTML (index.html, api_docs.html)
├── static/                           # Tài nguyên frontend (css/, js/, images/, vendor/)
├── data/                             # Dữ liệu runtime đã tối ưu
│   ├── CSKCB_Data/                   #   2,144 cơ sở khám chữa bệnh (TP.HCM & Hà Nội)
│   ├── curated/ready_documents/      #   364 tài liệu y khoa chuẩn cho BM25 fallback
│   └── recipes/                      #   Công thức chuẩn ViFoodRec & Wikibooks (recipes.json)
├── medical_vectordb/                 # ChromaDB Vector Store (collection v4 active: 725 tài liệu)
├── instance/                         # Cơ sở dữ liệu SQLite cục bộ (medimind.db)
├── uploads/                          # Kho tệp tải lên được bảo vệ theo owner_id
├── scripts/                          # Script CI/bảo trì (check_config, check_repository_hygiene, ingest, ...) & scripts/offline/
└── tests/                            # Bộ kiểm thử tự động pytest
```

---

## 🔌 4. Danh Mục API Chính

| Nhóm | Phương thức | Endpoint | Chức năng |
| :--- | :---: | :--- | :--- |
| **Hệ thống** | `GET` | `/`, `/health`, `/ready`, `/docs`, `/openapi.json` | Giao diện web, kiểm tra sống/sẵn sàng và tài liệu OpenAPI |
| **ChatBOT** | `POST` | `/api/chat` | Tư vấn lâm sàng 4 tầng (Emergency → RAG → LLM → Safety Guardrails) |
| **ChatBOT** | `POST` / `GET` | `/api/intake/session`, `/api/intake/message`, `/api/clinical-summary` | Hỏi bệnh có cấu trúc & phiếu tóm tắt tiền khám |
| **Đơn thuốc** | `POST` | `/api/prescription/scan`, `/api/prescription/confirm` | Quét ảnh/preset đơn thuốc & xác nhận tạo lịch uống 4 cữ |
| **Đơn thuốc** | `GET` / `DELETE` | `/api/prescription/history`, `/api/scan-files` | Quản lý lịch sử đơn thuốc & tài liệu đã quét (yêu cầu đăng nhập) |
| **Dinh dưỡng** | `POST` | `/api/nutrition/options`, `/api/nutrition/analyze` | Gợi ý danh sách công thức AI-ranked & phân tích thực phẩm theo bệnh lý |
| **Cơ sở y tế** | `GET` | `/api/facilities`, `/api/facilities/filters`, `/api/facilities/map-markers` | Tra cứu, lọc và hiển thị 2,144 cơ sở y tế trên bản đồ |
| **Đặt lịch** | `GET` / `POST` / `DELETE` | `/api/appointments` | Quản lý lịch hẹn khám cá nhân |
| **Xác thực** | `POST` / `GET` | `/api/auth/login`, `/register`, `/me`, `/otp/send`, `/otp/verify`, `/google/login` | Đăng nhập, đăng ký OTP, hồ sơ cá nhân, quên mật khẩu & Google OAuth |

---

## ⚙️ 5. Cấu Hình AI Provider (Groq + OpenRouter)

Hệ thống hỗ trợ chuyển đổi linh hoạt giữa **Groq**, **OpenRouter** và **Google Gemini** qua `core/ai/llm_provider.py`.  
Khuyến nghị dùng **Groq Free Tier** làm provider chính cho **ChatBOT & Dinh dưỡng** (tốc độ cao ~500–1,000 tok/s, 1,000 req/ngày, tự động dự phòng đa bucket `gpt-oss-120b → gpt-oss-20b → qwen3.8-27b`) kết hợp **OpenRouter (`:free` Vision)** cho nhánh đọc ảnh OCR:

```env
PORT=8000
FLASK_DEBUG=true
SECRET_KEY=<chuỗi-bí-mật-ngẫu-nhiên-64-ký-tự>

# AI Provider chính: Groq (ChatBOT, Dinh dưỡng, Chuẩn hóa văn bản OCR)
AI_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_CHAT_MODEL=openai/gpt-oss-120b
GROQ_EXPANSION_MODEL=openai/gpt-oss-20b
GROQ_NUTRITION_MODEL=openai/gpt-oss-20b
GROQ_INTERPRETATION_MODEL=openai/gpt-oss-120b

# OpenRouter Vision Fallback cho Đọc đơn thuốc (ảnh toàn trang + ảnh cắt LANCZOS)
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_OCR_MODEL=nvidia/nemotron-3.5-super-vl:free

# Google OAuth 2.0, Gmail SMTP OTP & SpeedSMS VN (tùy chọn)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SPEEDSMS_AUTH_TOKEN=...
```

---

## 🚀 6. Hướng Dẫn Cài Đặt & Khởi Chạy

### Cách 1: Chạy trực tiếp trên máy Local (Python `.venv` — Khuyến nghị)

```powershell
# 1. Clone kho mã nguồn
git clone https://github.com/khiemdong2005/chatbot_medical.git
cd chatbot_medical

# 2. Tạo và kích hoạt môi trường ảo .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# (Linux/macOS: source .venv/bin/activate)

# 3. Cài đặt thư viện (bao gồm ChromaDB và EasyOCR cho đọc đơn thuốc cục bộ)
pip install -r requirements.txt
pip install easyocr

# 4. Tạo file cấu hình .env từ mẫu và điền API keys
Copy-Item .env.example .env

# 5. Khởi chạy server bằng đúng Python trong .venv
.\.venv\Scripts\python.exe app.py
```

> ⚠️ **Lưu ý quan trọng trên Windows:** Luôn khởi chạy bằng **`.\.venv\Scripts\python.exe app.py`** (hoặc kích hoạt `.venv` trước) thay vì `python app.py` toàn hệ thống để đảm bảo nạp đủ `chromadb`, `easyocr` và `opencv`.

Truy cập ứng dụng tại:
- 🏥 **Giao diện Web MediMind**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- 📖 **Tài liệu API (Swagger / OpenAPI)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 🩺 **Kiểm tra trạng thái**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) • [http://127.0.0.1:8000/ready](http://127.0.0.1:8000/ready)

### Cách 2: Khởi chạy bằng Docker Compose

```bash
cp .env.example .env
docker compose up -d
docker compose logs -f
# Dừng hệ thống:
docker compose down
```

---

## 🧪 7. Kiểm Tra Chất Lượng & Kiểm Thử

```powershell
# Kiểm tra cấu hình môi trường & kết nối cơ bản
.\.venv\Scripts\python.exe scripts/check_config.py

# Kiểm tra vệ sinh kho mã nguồn & cú pháp toàn bộ file Python
.\.venv\Scripts\python.exe scripts/check_repository_hygiene.py

# Kiểm tra Linter (Ruff) & cú pháp JavaScript
.\.venv\Scripts\python.exe -m ruff check app.py routes/ core/
node --check static/js/app.js
node --check static/js/nutrition-flow.js

# Chạy bộ kiểm thử pytest
.\.venv\Scripts\python.exe -m pytest -q
```

---

## ⚖️ 8. Tuyên Bố Miễn Trừ Trách Nhiệm Y Tế

> **CẢNH BÁO QUAN TRỌNG:**  
> MediMind Clinical AI là công cụ hỗ trợ tra cứu, sàng lọc thông tin sức khỏe và quản lý đơn thuốc tham khảo, **không thay thế** cho việc khám bệnh trực tiếp, chẩn đoán xác định hoặc kê đơn từ bác sĩ có chứng chỉ hành nghề.  
> Khi xuất hiện dấu hiệu nguy hiểm đến tính mạng (*đau thắt ngực, khó thở dữ dội, yếu liệt nửa người, co giật, chảy máu nặng...*), hãy gọi ngay **Cấp cứu 115** hoặc đến khoa Cấp cứu gần nhất.
