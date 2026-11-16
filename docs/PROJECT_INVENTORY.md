# Kiểm kê cấu trúc dự án

Tài liệu này ghi nhận những đường dẫn đã đối chiếu với mã hiện tại; không khẳng định các thành phần khác là dư thừa.

- `app.py`, `core/main_fastapi.py`: các điểm chạy ứng dụng Flask và FastAPI.
- `core/`, `templates/`, `static/`: xử lý nghiệp vụ và giao diện.
- `data/`, `scripts/ingest.py`, `medical_vectordb/`: dữ liệu nguồn và chỉ mục truy xuất. Chỉ mục hiện được `core/rag_service.py` sử dụng.
- `evaluation/`, `scripts/`, `tests/`: benchmark, công cụ hỗ trợ và kiểm thử; các kết quả đánh giá có cấu hình và dấu vân tay dữ liệu cần được giữ để đối chiếu.
- `instance/`: cơ sở dữ liệu ứng dụng cục bộ, có thể chứa dữ liệu người dùng.
- `uploads/`: tệp tải lên; `app.py` dùng thư mục này mặc định.
- `models/`: trọng số mô hình tải cục bộ; reranker cần chúng khi được bật.
- `scratch/`: dữ liệu trung gian; một số script phục hồi ảnh trong `scripts/` tham chiếu đường dẫn tại đây. Cần kiểm tra từng tệp trước khi xóa.
- `designs/`, `docs/`: tài liệu và thiết kế; không nên suy ra nội dung không cần thiết chỉ vì ứng dụng không import trực tiếp.
- `docs/archive/`: yêu cầu khắc phục, roadmap và đề xuất workshop cũ được lưu lại để tham khảo; không thuộc đường chạy ứng dụng.

Thư mục `__pycache__/` và `.pytest_cache/` là cache tự sinh, có thể được Python hoặc pytest tạo lại. Các tệp `.env`, cơ sở dữ liệu, ảnh tải lên, dữ liệu nguồn và thay đổi chưa commit cần giữ cho đến khi xác định được phạm vi sử dụng của chúng.

Trong lần dọn hiện tại, ba module `core/auth_service.py`, `core/jwt_auth.py` và `core/observability.py` đã được loại sau khi rà soát import và lời gọi trong ứng dụng, script và kiểm thử. Đăng nhập hiện do các route trong `app.py` xử lý. Các bản audit cũ có thể vẫn nhắc đến các module đã loại vì đó là nội dung lịch sử.
