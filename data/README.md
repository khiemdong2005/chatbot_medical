# Dữ liệu của MediMind

Thư mục này chứa dữ liệu nguồn và manifest được ứng dụng/công cụ nhập liệu sử dụng.

| Đường dẫn | Vai trò |
|---|---|
| `CSKCB_Data/danh_sach_co_so_kcb_normalized.json` | Danh mục công khai cho trang cơ sở y tế |
| `curated/ready_documents/` | Tài liệu chuẩn hóa đầu vào của `python ingest.py` |
| `recipes/` | Danh mục công thức, dữ liệu nhập và thông tin nguồn |
| `Medical_book.pdf` | Tài liệu nguồn tham khảo của dự án |

Ảnh của công thức nằm trong `static/images/recipes/`; tên ảnh được tham chiếu
trong các danh mục. Giữ các README, manifest và thông tin nguồn đi kèm dataset.

## Dữ liệu phát sinh ở máy

- Chroma tạo chỉ mục trong `medical_vectordb/` ở gốc repo. Chạy `python ingest.py`
  để tạo lại từ tài liệu chuẩn hóa; lần đầu có thể cần tải embedding model.
- Các file `.bin` không kèm database SQLite/catalog không tạo thành một bản
  Chroma đầy đủ. Không dùng Git để sao lưu riêng lẻ các mảnh này.
- Tài khoản và hồ sơ được lưu trong `instance/`; file người dùng nằm trong `uploads/`.
  Các thư mục này phải được sao lưu riêng, không đưa vào commit.
- `recipes/wikibooks/api_cache/` là cache HTTP có thể tạo lại của công cụ nhập liệu.

Không thêm hồ sơ, ảnh xét nghiệm, khóa API hoặc dữ liệu cá nhân vào các dataset
công khai. Kiểm thử dùng fixture và thư mục tạm.
