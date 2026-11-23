# Quy ước lưu trữ repository

## Thuộc kho mã

- Mã nguồn Flask/FastAPI, giao diện, ảnh đang tham chiếu và bộ kiểm thử.
- Dataset nguồn, danh mục cơ sở y tế, công thức, manifest và thông tin nguồn.
- `requirements*.txt`, `.env.example`, hướng dẫn chạy và công cụ bảo trì.
- Artboard hiện tại trong `docs/design/`; tài liệu kế hoạch cũ trong `docs/archive/`.

## Thuộc môi trường cục bộ

- `.env`, SQLite trong `instance/`, file người dùng trong `uploads/`.
- ChromaDB trong `medical_vectordb/`, model tải xuống trong `models/`.
- Cache Python/pytest, log, thư mục thử nghiệm `scratch/`.
- Bộ cài `antigravity-setup/`, `skills-lock.json`, cấu hình `.agents/`, `.claude/`, `.gemini/`.
- History và trạng thái phiên của trình chỉnh sửa thiết kế.

Các mẫu này được `.gitignore` chặn. `.gitignore` không tự bỏ theo dõi file đã
commit; khi rà soát cần kiểm tra thêm `git ls-files` và `git diff --cached`.
`python scripts/check_repository_hygiene.py` kiểm tra các loại file cục bộ chính
và cú pháp Python mà không phải cài phụ thuộc ứng dụng.

## Chuyển từ bản cũ

PR dọn repo bỏ theo dõi 8 mảnh chỉ mục Chroma `.bin`, 27 file history của editor,
46 file bộ cài công cụ cá nhân và `skills-lock.json`. Các bản cũ vẫn nằm trong
lịch sử Git; không sửa hoặc force-push lịch sử repository.

Trước khi pull trên máy đang có dữ liệu:

1. Dừng ứng dụng và sao lưu `.env`, `instance/`, `uploads/`, toàn bộ
   `medical_vectordb/` ra ngoài thư mục repo.
2. Pull bản đã được merge. File đã được Git theo dõi có thể bị xóa khi pull;
   `.gitignore` không ngăn việc đó.
3. Khôi phục bản Chroma đầy đủ đã sao lưu, hoặc chạy `python ingest.py` để tạo
   chỉ mục từ dữ liệu nguồn. Lần đầu có thể cần mạng để tải embedding model.
4. Khởi động ứng dụng và xác nhận truy xuất RAG có dữ liệu. Trang web có thể mở
   được trong khi RAG đang dùng phản hồi dự phòng.

Các file chỉ mục cũ trong Git thiếu SQLite/catalog nên không phải một bản
database hoàn chỉnh để chia sẻ qua clone. Dữ liệu nguồn và code ingestion được giữ.
