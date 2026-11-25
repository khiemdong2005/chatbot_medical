# Kiến Trúc & Danh Mục Thư Mục Dự Án (MediMind Clinical AI — Hybrid 1.4)

Tài liệu này mô tả cấu trúc thư mục chuẩn hóa theo mô hình **Hybrid 1.4 (Modular Monolith)** với phân tách rõ ràng giữa điểm khởi chạy, nghiệp vụ lõi, cổng API, giao diện, tài liệu và kiểm thử.

## 1. Điểm Khởi Chạy (Root Entrypoints & Config)
- `app.py`: Điểm khởi chạy Flask WSGI mỏng (< 350 dòng), ủy quyền toàn bộ route sang `routes/`.
- `main_fastapi.py`: Điểm khởi chạy FastAPI ASGI gốc (`uvicorn main_fastapi:app --port 8000`), forward sang `core/main_fastapi.py`.
- `ingest.py`: Trình kích hoạt pipeline nạp kho tri thức y khoa RAG (`scripts/ingest.py`).
- `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`: Cấu hình container hóa.
- `requirements*.txt`, `requirements.lock`, `pytest.ini`, `ruff.toml`, `.env.example`: Cấu hình phụ thuộc, kiểm thử và môi trường.

## 2. Lõi Nghiệp Vụ (`core/`)
- `core/shared/`: Hạ tầng dùng chung không phụ thuộc domain (`settings.py`, `models.py`, `migrations.py`, `db_utils.py`, `cache_service.py`, `storage_service.py`, `cleanup_service.py`, `api_errors.py`, `logging_redaction.py`, `network_utils.py`).
- `core/auth/`: Xác thực, OTP, CSRF, Rate Limiting, Security Headers (`otp_service.py`, `csrf_protection.py`, `rate_limit_service.py`, `security_headers.py`, `security_patch.py`, `email_service.py`, `sms_service.py`).
- `core/ai/`: Cổng Groq LLM thống nhất, Retry Policy, Circuit Breaker, Clinical Verification & Interpretation (`llm_provider.py`, `gemini_service.py`, `interpretation_service.py`, `prompts.py`, `circuit_breaker.py`, `retry_policy.py`, `ai_types.py`).
- `core/chat/`: Chatbot y tế lâm sàng, sàng lọc cấp cứu Triage, RAG MedlinePlus & tóm tắt trước khám (`chat_service.py`, `consultation_service.py`, `intake_service.py`, `triage.py`, `health_context.py`, `rag_service.py`, `document_chunker.py`, `query_expansion_service.py`, `reranker_service.py`, `grounding_service.py`).
- `core/ocr/`: Pipeline 2 giai đoạn quét đơn thuốc (EasyOCR + Groq Vision Dual-Image + Reconciliation + Validation).
- `core/nutrition/`: Gợi ý dinh dưỡng lâm sàng & lọc thực đơn theo bệnh lý/dị ứng.
- `core/facilities/`: Tra cứu cơ sở y tế và quản lý đặt lịch khám (`facilities_service.py`, `appointment_service.py`).
- `core/routers/`: Các FastAPI native routers (`appointments.py`, `clinical_summary.py`, `config.py`, `consultations.py`, `facilities.py`).
- `core/<module>.py`: Tầng shim tương thích ngược đảm bảo `core.<mod> is core.<pkg>.<mod>` (không tách trạng thái).

## 3. Tầng HTTP & Giao Diện (`routes/`, `templates/`, `static/`)
- `routes/`: Các nhóm route Flask tách theo miền (`auth_routes.py`, `chat_routes.py`, `ocr_routes.py`, `clinical_routes.py`, `nutrition_routes.py`, `facilities_routes.py`, `system_routes.py`, `shared_helpers.py`).
- `templates/`: Giao diện Jinja2 (`index.html`, `partials/previsit_intake.html`).
- `static/js/`: Logic phía trình duyệt đồng bộ song ngữ VI/EN (`app.js`, `chat-context.js`, `nutrition-flow.js`, `previsit-intake.js`).
- `static/css/`: Hệ thống giao diện Ocean Glass & Dark Mode.

## 4. Dữ Liệu, Tài Liệu, Công Cụ & Kiểm Thử
- `data/` & `medical_vectordb/`: Dữ liệu nguồn y khoa MedlinePlus, danh mục món ăn và chỉ mục vector ChromaDB.
- `docs/`:
  - `docs/architecture.md`, `docs/PROJECT_INVENTORY.md`, `docs/repository-maintenance.md`, tài liệu kỹ thuật từng phân khu.
  - `docs/reports/`: Các báo cáo kiểm toán tính năng và bảo mật (`FEATURE_AUDIT_REPORT.md`, `PENTEST_REPORT.md`).
  - `docs/design/`: Nguyên mẫu thiết kế UI (`medimind-redesign/`, `components/`).
  - `docs/archive/`: Tài liệu lịch sử và đề xuất cũ.
- `scripts/`: Công cụ nạp dữ liệu, đánh giá RAG và kiểm tra vệ sinh mã nguồn.
- `evaluation/`: Bộ dữ liệu và kết quả benchmark chất lượng truy xuất & an toàn lâm sàng.
- `tests/`: Bộ kiểm thử tự động (`pytest`).
- `instance/` & `uploads/`: Dữ liệu runtime cục bộ (CSDL SQLite và tệp tải lên; không commit vào Git).
