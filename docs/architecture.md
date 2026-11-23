# Kiến trúc hiện tại

Tài liệu mô tả các đường dẫn và luồng đang có trong kho mã. Những đề xuất chưa triển khai nằm trong [archive/](archive/).

## Website Flask

`app.py` là điểm chạy chính. `create_app()` cấu hình ứng dụng, khởi tạo SQLAlchemy, chạy migration và đăng ký route. `python app.py` phục vụ giao diện Jinja2 cùng các API tại cùng một địa chỉ.

| Khu vực | Thành phần |
|---|---|
| Giao diện | `templates/`, `static/css/`, `static/js/`, `static/images/` |
| Chat và kiểm tra dữ liệu đầu vào | `core/chat_service.py`, `core/health_context.py` |
| Phân luồng triệu chứng | `core/triage.py`, `core/intake_service.py` |
| Gemini và kết quả có cấu trúc | `core/gemini_service.py`, `core/gemini_schema_service.py` |
| OCR và tài liệu | `core/prescription_service.py`, `core/ocr_extractor.py`, `core/pipeline_orchestrator.py` |
| Dinh dưỡng | `core/nutrition_ai.py`, `core/nutrition_rules.py`, `core/recipe_catalog.py` |
| Tài khoản, bảng dữ liệu, migration | `core/models.py`, `core/migrations.py`, các route `/api/auth/` trong `app.py` |
| Lưu trữ file | `core/storage_service.py`; mặc định ghi vào `uploads/` |
| Cơ sở y tế | Các route `/api/facilities` trong `app.py`; dữ liệu tại `data/CSKCB_Data/` |

Giao diện gọi các API bằng JavaScript. Nội dung tài liệu tải lên cần được kiểm tra và xác nhận trước khi sử dụng kết quả trích xuất.

## Gateway FastAPI

`main_fastapi.py` là gateway riêng: phục vụ chat, giao diện và chuyển một phần route xác thực/đơn thuốc sang Flask qua `WSGIMiddleware`. Đây chưa phải bản thay thế đầy đủ cho `app.py`; không nên dùng nó làm entrypoint cho toàn bộ website.

## Truy xuất tài liệu

1. `ingest.py` đọc JSON trong `data/curated/ready_documents/` và chia nội dung thành các đoạn.
2. Script tạo một collection ChromaDB mới, thêm tài liệu, kiểm tra số lượng rồi ghi `medical_vectordb/active_collection.json`.
3. `core/rag_service.py` mở chỉ mục tại `medical_vectordb/` và đọc tên collection đang hoạt động từ metadata.
4. Truy xuất từ khóa là chế độ mặc định. `RAG_VECTOR_SEARCH_ENABLED=true` cho phép truy vấn vector.
5. Chat sử dụng các tài liệu tìm được cùng dịch vụ Gemini; khi chỉ mục hoặc AI không khả dụng, luồng xử lý có cơ chế dự phòng.

Chỉ mục ChromaDB phải được tạo cục bộ sau khi clone. Các file `.bin` riêng lẻ không đủ để khôi phục cơ sở dữ liệu. Sao lưu toàn bộ thư mục chỉ mục ra ngoài dự án trước khi nạp lại. Ingestion và truy vấn vector có thể cần tải model embedding.

## Dữ liệu và cấu hình

| Đường dẫn | Vai trò | Có đưa lên Git? |
|---|---|---|
| `.env.example` | Tên biến và giá trị mẫu không chứa khóa thật | Có |
| `.env` | Khóa, thông tin kết nối và cấu hình riêng | Không |
| `data/` | Corpus nguồn, danh mục cơ sở y tế và công thức | Có, kèm thông tin nguồn |
| `medical_vectordb/` | Chỉ mục ChromaDB được tạo cục bộ | Không |
| `instance/` | SQLite của Flask, có thể chứa tài khoản và hồ sơ | Không |
| `uploads/` | Tài liệu người dùng tải lên | Chỉ giữ `.gitkeep` |
| `docs/design/` | Bản thiết kế tham khảo | Có |
| `docs/archive/` | Roadmap, đề xuất và ghi chú lịch sử | Có |

Mặc định ứng dụng dùng `sqlite:///medimind.db`, được Flask đặt dưới `instance/`. Các bảng và migration được chạy khi khởi tạo ứng dụng. Tạo tài khoản mẫu chỉ xảy ra khi bật `SEED_DEMO_ACCOUNTS`.

## Kiểm thử và phạm vi thay đổi

`tests/` kiểm tra các hợp đồng dữ liệu, quyền truy cập, xử lý tài liệu, dinh dưỡng, RAG và bố cục giao diện. Phụ thuộc kiểm thử được liệt kê trong `requirements-dev.txt`; công cụ nhập dữ liệu dùng thêm `requirements-tools.txt`.

Xem [CONTRIBUTING.md](../CONTRIBUTING.md) trước khi gửi Pull Request và [data/README.md](../data/README.md) trước khi thay đổi dữ liệu hoặc chạy ingestion. Không đưa cơ sở dữ liệu runtime, tài liệu người dùng hoặc khóa truy cập vào commit.
