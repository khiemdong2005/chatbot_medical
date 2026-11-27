# MediMind Clinical AI — Project Directory Structure

Cấu trúc dự án tuân theo kiến trúc **Modular Monolith (Hybrid Structure 1.4)**: điểm vào mỏng (`app.py`, `main_fastapi.py`), tách lớp HTTP (`routes/`), phân chia miền nghiệp vụ độc lập trong `core/`, và tách biệt dữ liệu tĩnh, kiểm thử và công cụ vận hành.

```text
Medical ChatBOT/
├── app.py                      # Flask App Factory mỏng (đăng ký routes + middleware)
├── main_fastapi.py             # FastAPI Gateway entrypoint (bọc WSGI Flask + route native)
├── ingest.py                   # Entrypoint nạp dữ liệu RAG (ủy quyền scripts/ingest.py)
├── Dockerfile                  # Cấu hình build container production
├── docker-compose.yml          # Triển khai production
├── docker-compose.dev.yml      # Triển khai phát triển cục bộ
├── requirements.txt            # Thư viện Python cốt lõi (runtime / Docker)
├── requirements/               # Thư viện bổ trợ (dev.txt, tools.txt, reranker.txt, lock.txt)
├── pytest.ini / ruff.toml      # Cấu hình kiểm thử & linter
│
├── routes/                     # Lớp HTTP Endpoints phân theo miền
│   ├── __init__.py             # Đăng ký tập trung toàn bộ route modules
│   ├── auth_routes.py          # Đăng nhập, đăng ký, OTP, Google OAuth, hồ sơ cá nhân
│   ├── chat_routes.py          # Chat y khoa, phiên hỏi bệnh Intake
│   ├── clinical_routes.py      # Tóm tắt trước khám, lịch sử tư vấn, đặt lịch khám
│   ├── facilities_routes.py    # Tra cứu & bản đồ cơ sở y tế (CSKCB)
│   ├── notification_routes.py  # Thông báo chuông theo tài khoản
│   ├── nutrition_routes.py     # Khảo sát BMR/TDEE, lập thực đơn & danh mục công thức
│   ├── ocr_routes.py           # Quét đơn thuốc / phiếu xét nghiệm OCR & lịch sử
│   ├── system_routes.py        # Healthcheck, trang chủ, cấu hình client
│   └── shared_helpers.py       # Hàm dùng chung cho routes
│
├── core/                       # Lõi nghiệp vụ (Modular Monolith — 8 subpackages)
│   ├── __init__.py             # Dynamic alias resolver cho legacy `core.<mod>` imports
│   ├── main_fastapi.py         # Ứng dụng FastAPI Gateway chính
│   ├── shared/                 # Hạ tầng dùng chung (settings, models, migrations, cache, storage)
│   ├── auth/                   # Xác thực, OTP, CSRF, rate limit, security headers, email/SMS
│   ├── ai/                     # LLM Provider (Groq/Gemini), circuit breaker, retry, prompts
│   ├── chat/                   # Tư vấn lâm sàng, triage, intake, RAG, reranker, grounding
│   ├── ocr/                    # Pipeline OCR song song, cắt ảnh đơn thuốc, chuẩn hóa & đối chiếu
│   ├── nutrition/              # Lập thực đơn BMR/TDEE, quy tắc lâm sàng, danh mục Món Ngon Mỗi Ngày
│   ├── facilities/             # Dịch vụ cơ sở y tế & quản lý lịch hẹn khám
│   └── routers/                # FastAPI native routers
│
├── frontend/                   # Giao diện Web (HTML Jinja2 + tài nguyên tĩnh)
│   ├── templates/              # Giao diện HTML (Jinja2 SPA shell: index.html, partials/)
│   └── static/                 # Tài nguyên Frontend (JS, CSS, hình ảnh — phục vụ tại /static/)
│       ├── css/                # Stylesheets (bao gồm nutrition-flow.css)
│       ├── js/                 # Logic SPA (app.js, nutrition-flow.js, nutrition-catalog.js, ...)
│       └── images/             # Ảnh giao diện, ảnh tinh bột mâm cơm (canonical_staple_*.jpg)
│
├── data/                       # Kho dữ liệu tham chiếu tĩnh
│   ├── CSKCB_Data/             # 2.144 cơ sở y tế chuẩn hóa (TP.HCM + Hà Nội)
│   ├── recipes/                # Nguồn Dinh dưỡng duy nhất: monngonmoingay_recipes_with_kcal.json (2.500 món)
│   ├── curated/                # 364 tài liệu y khoa chuẩn hóa phục vụ build RAG
│   ├── processed/              # Tài liệu y khoa MedlinePlus đã xử lý
│   └── Medical_book.pdf        # Tài liệu y khoa tham chiếu gốc
│
├── medical_vectordb/           # ChromaDB Vector Store (RAG y khoa — active_collection.json)
├── instance/                   # CSDL SQLite cục bộ (medimind.db — không track trên Git)
├── uploads/                    # Tệp tải lên của người dùng (không track trên Git)
│
├── scripts/                    # Công cụ dòng lệnh & pipeline vận hành
│   ├── __init__.py             # Alias resolver cho các script di chuyển vào subpackages
│   ├── check_config.py         # CI: Kiểm tra cấu hình môi trường
│   ├── check_quality_gates.py  # CI: Kiểm tra chất lượng RAG & an toàn lâm sàng
│   ├── check_repository_hygiene.py # CI: Kiểm tra vệ sinh Git & cú pháp Python
│   ├── docker_entrypoint.py    # Docker: Tự động kiểm tra data & auto-ingest ChromaDB khi deploy mới
│   ├── ingest.py               # Pipeline nạp dữ liệu vào ChromaDB
│   ├── test_docker_local.py    # CI: Kiểm thử build/chạy Docker cục bộ
│   ├── rag/                    # Script xây dựng, làm giàu song ngữ & kích hoạt RAG v4
│   ├── eval/                   # Script đánh giá chất lượng truy xuất, trả lời & an toàn
│   └── ops/                    # Script vận hành DB & kết nối (view_db, update_db, scan_env_vars, ...)
│
├── evaluation/                 # Bộ dữ liệu & kết quả đánh giá RAG / Safety
├── tests/                      # Bộ kiểm thử tự động (pytest)
└── docs/                       # Tài liệu kiến trúc, báo cáo, thiết kế UI & lưu trữ
```
