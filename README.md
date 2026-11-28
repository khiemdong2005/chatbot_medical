# MediMind AI - Nền tảng Trợ lý Lâm sàng & Sàng lọc Triệu chứng

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![HTML5](https://img.shields.io/badge/HTML5-E34F26?logo=html5&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/HTML)
[![CSS3](https://img.shields.io/badge/CSS3-1572B6?logo=css3&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/CSS)
[![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?logo=javascript&logoColor=black)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)
[![Jinja2](https://img.shields.io/badge/Jinja2-B41717?logo=jinja&logoColor=white)](https://jinja.palletsprojects.com/)
[![Flask](https://img.shields.io/badge/Flask-3.1.0-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Starlette](https://img.shields.io/badge/Starlette-2B2B2B)](https://www.starlette.io/)
[![Uvicorn](https://img.shields.io/badge/Uvicorn-499848)](https://www.uvicorn.org/)
[![Gunicorn](https://img.shields.io/badge/Gunicorn-499848?logo=gunicorn&logoColor=white)](https://gunicorn.org/)
[![Pydantic](https://img.shields.io/badge/Pydantic-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Google Gemini](https://img.shields.io/badge/Google%20Gemini-8E75B2?logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![Groq](https://img.shields.io/badge/Groq-F55036)](https://groq.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-FF6F00)](https://www.trychroma.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?logo=opencv&logoColor=white)](https://opencv.org/)
[![Pillow](https://img.shields.io/badge/Pillow-3776AB)](https://python-pillow.org/)
[![NumPy](https://img.shields.io/badge/NumPy-013243?logo=numpy&logoColor=white)](https://numpy.org/)
[![PyPDF](https://img.shields.io/badge/PyPDF-EC1C24)](https://pypdf.readthedocs.io/)
[![BeautifulSoup4](https://img.shields.io/badge/BeautifulSoup4-43B02A)](https://www.crummy.com/software/BeautifulSoup/)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![AWS](https://img.shields.io/badge/AWS%20Boto3-232F3E?logo=amazonaws&logoColor=white)](https://aws.amazon.com/)
[![Google OAuth](https://img.shields.io/badge/Google%20OAuth-4285F4?logo=google&logoColor=white)](https://developers.google.com/identity)
[![Google Maps](https://img.shields.io/badge/Google%20Maps-4285F4?logo=googlemaps&logoColor=white)](https://developers.google.com/maps)
[![JWT](https://img.shields.io/badge/JWT-000000?logo=jsonwebtokens&logoColor=white)](https://jwt.io/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Docker Compose](https://img.shields.io/badge/Docker%20Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?logo=prometheus&logoColor=white)](https://prometheus.io/)
[![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Ruff](https://img.shields.io/badge/Ruff-D7FF64?logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/)

---

## Tổng quan

MediMind AI là hệ thống trợ lý y tế số hỗ trợ sàng lọc triệu chứng ban đầu, đánh giá mức độ nguy cơ lâm sàng, phân tích phiếu xét nghiệm/đơn thuốc (OCR), tư vấn dinh dưỡng cá nhân hóa và kết xuất bản tóm tắt tiền khám cho bác sĩ. Hệ thống tích hợp xác thực người dùng (bao gồm Google OAuth) và quản lý hồ sơ sức khỏe theo từng tài khoản.

---

## Kiến trúc hệ thống

```text
[ Người dùng (Web UI - frontend/) ]
        │
        ├──► POST /api/chat              ──► core/chat/ (sàng lọc triệu chứng, tính điểm nguy cơ)
        ├──► POST /api/upload-lab        ──► core/ocr/  (trích xuất chỉ số xét nghiệm)
        ├──► POST /api/nutrition/*       ──► core/nutrition/ (gợi ý thực đơn & phân tích dinh dưỡng)
        └──► GET  /api/clinical-summary  ──► core/routers/ & routes/ (bản tóm tắt tiền khám)
```

Dự án tổ chức theo cấu trúc **Hybrid 1.4**:
- `app.py` – Điểm vào **Flask** (phục vụ giao diện web và các route trong `routes/`).
- `main_fastapi.py` / `core/main_fastapi.py` – Điểm vào **FastAPI** (ASGI gateway cho triển khai Docker/Uvicorn).
- `core/` – Lõi xử lý nghiệp vụ: `ai/`, `auth/`, `chat/`, `facilities/`, `nutrition/`, `ocr/`, `routers/`, `shared/`, `observability.py`.
- `routes/` – Tầng định tuyến Flask ánh xạ các endpoint HTTP tới `core/`.
- `frontend/` – Giao diện người dùng (`frontend/templates/` và `frontend/static/`).

---

## Cài đặt & Khởi chạy nhanh

### Cách 1: Sử dụng Docker Compose (FastAPI + Uvicorn)
```bash
# Sao chép tệp cấu hình môi trường và điều chỉnh nếu cần
cp .env.example .env

# Xây dựng và khởi chạy container (chạy core.main_fastapi:app)
docker compose up -d
```
- Truy cập giao diện tại `http://localhost:8000`.
- Tài liệu Swagger/OpenAPI tại `http://localhost:8000/docs` (chỉ khả dụng ở môi trường development; tự động tắt khi chạy chế độ production).
- Các endpoint kiểm tra trạng thái: `/health`, `/ready`.

### Cách 2: Chạy trực tiếp trên máy (Python Local)
Nếu bạn vừa clone repository từ GitHub, hãy di chuyển vào thư mục dự án (bỏ qua bước `cd` nếu bạn đã đứng sẵn trong `chatbot_medical`):
```bash
cd chatbot_medical
```

Tạo và kích hoạt môi trường ảo:
```bash
python -m venv venv
```
- **Windows (PowerShell):** `.\venv\Scripts\Activate.ps1`
- **Windows (CMD):** `.\venv\Scripts\activate.bat`
- **Linux / macOS / Git Bash:** `source venv/bin/activate` (hoặc `source venv/Scripts/activate` trên Git Bash Windows)

Cài đặt thư viện và cấu hình môi trường:
```bash
pip install -r requirements.txt
cp .env.example .env
```

Khởi chạy server theo một trong hai điểm vào:
- **Chạy Flask server:**
  ```bash
  python app.py
  ```
- **Chạy FastAPI gateway (Uvicorn):**
  ```bash
  uvicorn core.main_fastapi:app --host 0.0.0.0 --port 8000
  ```
  *(Hoặc `python main_fastapi.py`)*

---

## Đặc tả API chính

| Phương thức | Đường dẫn | Mô tả | Ghi chú |
|:-----------|:----------|:------|:--------|
| `GET` | `/` | Phục vụ giao diện Web SPA | Trả về HTML từ `frontend/templates/` |
| `POST` | `/api/chat` | Phân tích triệu chứng & phân tầng nguy cơ | Yêu cầu JSON (`message`, `history`) |
| `POST` | `/api/upload-lab` | Tiếp nhận ảnh phiếu xét nghiệm, trích xuất chỉ số | `multipart/form-data` (file ảnh) |
| `GET` | `/api/clinical-summary` | Kết xuất bản tóm tắt tiền khám cho bác sĩ | Yêu cầu phiên đăng nhập hợp lệ |
| `POST` | `/api/nutrition/options` | Gợi ý tùy chọn dinh dưỡng theo hồ sơ | Dựa trên thông tin người dùng |
| `GET` | `/health` | Kiểm tra trạng thái hoạt động (liveness) | Trả về JSON trạng thái |
| `GET` | `/ready` | Kiểm tra mức độ sẵn sàng (readiness) | Trả về JSON trạng thái |

*(Các nhóm API chi tiết khác như `/api/auth/*`, `/api/intake/*`, `/api/facilities/*`, `/api/notifications/*`, `/api/prescription/*` được định nghĩa trong `routes/` và `core/routers/`.)*

---

## Cấu trúc dự án

```text
chatbot_medical/
├── app.py                 # Điểm vào Flask & đăng ký route
├── main_fastapi.py        # Điểm vào FastAPI ở thư mục gốc
├── ingest.py              # Script nạp dữ liệu RAG
├── core/                  # Lõi nghiệp vụ
│   ├── ai/                # Tích hợp Gemini & prompt an toàn y khoa
│   ├── auth/              # Xác thực, CSRF, security headers
│   ├── chat/              # Sàng lọc triệu chứng & hội thoại
│   ├── facilities/        # Tra cứu cơ sở y tế
│   ├── nutrition/         # Tùy chọn & thực đơn dinh dưỡng
│   ├── ocr/               # Đọc phiếu xét nghiệm & đơn thuốc
│   ├── routers/           # Các router FastAPI
│   ├── shared/            # Models, cấu hình, tiện ích dùng chung
│   └── main_fastapi.py    # Khởi tạo ứng dụng FastAPI
├── routes/                # Các route Flask
├── frontend/              # Giao diện web (templates/ và static/)
├── tests/                 # Kiểm thử tự động (pytest)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Lưu ý phát triển

- Dự án hỗ trợ hai điểm vào: **Flask** (`app.py`) và **FastAPI** (`core/main_fastapi.py` / `main_fastapi.py`).
- Thông tin cấu hình Google OAuth (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) và khóa API cần được thiết lập trong tệp `.env`.
- Khi bổ sung endpoint mới, cần đăng ký tương ứng trong `routes/__init__.py` (cho Flask) hoặc `core/routers/` (cho FastAPI).
- Chạy kiểm thử đơn vị bằng lệnh `pytest`.
