# MediMind AI - Nền tảng Trợ lý Lâm sàng & Sàng lọc Triệu chứng

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Framework-Flask%20%7C%20FastAPI-emerald.svg)](https://flask.palletsprojects.com/)

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
