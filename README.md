# MediMind

Ứng dụng web hỗ trợ tra cứu thông tin sức khỏe, tiếp nhận mô tả triệu chứng, đọc tài liệu y tế và tìm cơ sở khám chữa bệnh. Backend chính dùng Flask; giao diện dùng Jinja2, JavaScript và CSS. Các tính năng AI tích hợp Google Gemini, kết hợp dữ liệu tham khảo qua ChromaDB.

Đây là dự án hỗ trợ tham khảo, không thay thế thăm khám, chẩn đoán hoặc chỉ định điều trị của bác sĩ.

## Tính năng

- Trò chuyện sức khỏe, thu thập thông tin triệu chứng và cảnh báo dấu hiệu cần hỗ trợ y tế.
- Tải lên tài liệu, trích xuất nội dung đơn thuốc/xét nghiệm và cho người dùng kiểm tra lại kết quả.
- Quản lý tài khoản, phiên đăng nhập và tài liệu theo tài khoản.
- Tra cứu cơ sở y tế, lọc danh sách và mở vị trí trên Google Maps.
- Gợi ý dinh dưỡng và tra cứu danh mục công thức món ăn.
- Truy xuất tài liệu tham khảo từ chỉ mục ChromaDB được tạo cục bộ.

## Chạy cục bộ

Yêu cầu: Git, Python 3.11 và kết nối mạng để cài thư viện. Gemini, Google Maps và một số tài nguyên giao diện cũng cần mạng khi sử dụng.

```powershell
git clone https://github.com/khiemdong2005/chatbot_medical.git
cd chatbot_medical
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Trên Linux/macOS, kích hoạt môi trường bằng `source .venv/bin/activate` và sao chép cấu hình bằng `cp .env.example .env`.

Mở `.env`, điền `GEMINI_API_KEY` nếu dùng AI và đặt `SECRET_KEY` riêng. Có thể tạo khóa phiên bằng lệnh dưới đây, sau đó chép kết quả vào `.env`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Khởi chạy giao diện đầy đủ từ thư mục gốc:

```bash
python app.py
```

Truy cập [http://127.0.0.1:8000](http://127.0.0.1:8000). SQLite và các bảng dữ liệu được ứng dụng khởi tạo trong `instance/`; tài liệu tải lên nằm trong `uploads/`. Không commit hai thư mục dữ liệu cá nhân này hoặc file `.env`.

## Cấu hình

Các biến được mô tả trong [.env.example](.env.example).

| Biến | Mục đích |
|---|---|
| `HOST`, `PORT` | Địa chỉ và cổng Flask; mẫu cấu hình chỉ mở trên máy cục bộ |
| `FLASK_DEBUG` | Bật/tắt chế độ debug; mặc định `false` |
| `SECRET_KEY` | Khóa ký phiên đăng nhập; cần giá trị riêng, ổn định |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Cấu hình Gemini; model phải khả dụng với tài khoản của bạn |
| `DATABASE_URL` | Kết nối SQLAlchemy; mặc định SQLite cục bộ |
| `SEED_DEMO_ACCOUNTS` | Tạo tài khoản mẫu khi được bật; mặc định `false` |
| `RAG_VECTOR_SEARCH_ENABLED` | Cho phép truy vấn vector; mặc định dùng truy xuất từ khóa trên chỉ mục |
| `GOOGLE_MAPS_API_KEY` | Tùy chọn cho Maps JavaScript API; bản đồ nhúng có thể dùng khi để trống |
| `GOOGLE_CLIENT_*`, `GOOGLE_REDIRECT_URI` | Tùy chọn cho đăng nhập Google OAuth |
| `SMTP_*` | Tùy chọn cho gửi email OTP |

Khi thiếu khóa AI hoặc chỉ mục tài liệu, một số luồng có thể trả phản hồi dự phòng. Việc tải được trang không xác nhận AI/OCR đã được cấu hình đầy đủ.

## Tạo chỉ mục tài liệu RAG

Kho mã lưu dữ liệu nguồn; chỉ mục ChromaDB là dữ liệu được tạo cục bộ, không được đưa lên Git. Sau khi clone hoặc pull bản dọn repo, hãy tạo chỉ mục trước khi dựa vào kết quả truy xuất RAG.

Nếu đã có thư mục `medical_vectordb/`, sao lưu **toàn bộ thư mục ra ngoài dự án** trước khi chạy ingestion. Đừng xóa cơ sở dữ liệu đang dùng hoặc chỉ giữ riêng các file `.bin`.

```bash
python ingest.py
```

Script đọc `data/curated/ready_documents/`, tạo collection mới trong `medical_vectordb/`, kiểm tra số lượng tài liệu rồi ghi `active_collection.json`. Lần đầu tạo embedding có thể cần mạng để tải model. Khi chưa có chỉ mục hợp lệ, RAG chuyển sang chế độ dự phòng.

Xem [hướng dẫn dữ liệu](data/README.md) để biết dữ liệu nào thuộc Git và dữ liệu nào cần giữ cục bộ.

## Kiểm thử và công cụ

Cài các phụ thuộc phát triển trước khi chạy bộ kiểm thử:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests
```

Chạy một kiểm tra bố cục nhanh:

```bash
python -m pytest tests/test_facility_page_layout.py -q
```

Các script nhập dữ liệu, khôi phục ảnh và xử lý dữ liệu nằm trong `scripts/`. Cài thêm `requirements-tools.txt` khi dùng các công cụ này. Một số tác vụ tải dữ liệu hoặc gọi AI cần cấu hình/mạng riêng; xem nội dung script trước khi chạy.

## Cấu trúc dự án

```text
app.py                 # Flask: giao diện và các API của website
main_fastapi.py        # Gateway FastAPI cho một phần API
ingest.py              # Tạo chỉ mục ChromaDB từ dữ liệu nguồn
core/                  # Xử lý nghiệp vụ, AI, tài khoản và lưu trữ
templates/  static/    # Giao diện và tài nguyên trình duyệt
data/                  # Dữ liệu nguồn, danh mục và thông tin nguồn
scripts/               # Công cụ nhập liệu và bảo trì
tests/                 # Bộ kiểm thử
docs/                  # Kiến trúc, tài liệu và bản thiết kế tham khảo
```

`main_fastapi.py` cung cấp chat và một số route xác thực/đơn thuốc, **chưa thay thế toàn bộ Flask website**. Để dùng đầy đủ giao diện, cơ sở y tế và dinh dưỡng, chạy `python app.py`.

## Tài liệu và đóng góp

- [Kiến trúc hiện tại](docs/architecture.md)
- [Nguồn dữ liệu và lưu trữ cục bộ](data/README.md)
- [Hướng dẫn đóng góp](CONTRIBUTING.md)
- [Kế hoạch và tài liệu lịch sử](docs/archive/)
- [Bản thiết kế tham khảo](docs/design/medimind-redesign/)

Các điều kiện sử dụng dữ liệu hoặc thư viện bên thứ ba cần được xem tại nguồn và thông báo giấy phép đi kèm. Kho mã hiện không công bố giấy phép riêng cho toàn bộ dự án.

## Lưu ý sử dụng

Đầu ra AI/OCR có thể sai và cần được người dùng kiểm tra. Không dùng ứng dụng để tự quyết định điều trị hoặc thay thế tư vấn chuyên môn. Trong tình huống cấp cứu tại Việt Nam, gọi 115 hoặc đến cơ sở y tế gần nhất.
