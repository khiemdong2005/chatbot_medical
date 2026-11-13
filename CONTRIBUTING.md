# Đóng góp cho MediMind

## Làm việc trên nhánh riêng

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/ten-thay-doi
```

Giữ thay đổi cùng mục đích trong một Pull Request. Mô tả vấn đề, cách sửa,
kết quả kiểm tra và yêu cầu cấu hình dữ liệu nếu có. Merge sau khi review.

## Cài đặt môi trường phát triển

Làm theo [README](README.md), sau đó cài công cụ kiểm thử:

```bash
python -m pip install -r requirements-dev.txt
python scripts/check_repository_hygiene.py
python -m pytest tests -q
```

`check_repository_hygiene.py` kiểm tra các đường dẫn Git đang theo dõi và cú pháp
Python. Check này không thay thế kiểm thử chức năng hoặc rà soát bảo mật.
GitHub Actions chạy check này cho PR và nhánh `main`.

Kiểm thử dùng dữ liệu giả hoặc fixture tạm; không dùng khóa AI thật hay hồ sơ người bệnh.

## Chọn file để commit

- Dùng `git add <đường-dẫn>` và xem `git diff --cached` trước khi commit.
- Giữ `.env`, database SQLite/Chroma, file upload, model tải cục bộ và cache ở máy.
- `.env.example` chỉ chứa tên biến và giá trị mẫu; không chép khóa thật vào đó.
- Các cấu hình IDE, bộ cài Antigravity và khóa cài skill thuộc môi trường cá nhân.
- Giữ dataset nguồn, manifest và ảnh mà ứng dụng đang tham chiếu. Hai ảnh giống
  nhau vẫn có thể cần hai tên file khác nhau trong dữ liệu.
- Đặt tài liệu kỹ thuật trong `docs/`; tài liệu kế hoạch cũ trong `docs/archive/`.
  Thiết kế tham khảo nằm trong `docs/design/`; không commit history/cache của editor.

## Khi cập nhật bản đang chạy

Dừng ứng dụng và sao lưu `.env`, `instance/`, `uploads/`, `medical_vectordb/`
ra ngoài thư mục repo trước khi cập nhật. Nếu lần cập nhật này bỏ theo dõi các
file chỉ mục cũ, Git có thể xóa bản đang được theo dõi khi pull. Khôi phục bản
sao lưu đầy đủ hoặc nạp lại bằng `python ingest.py` trước khi dùng RAG.
Không ghi đè dữ liệu nguồn hoặc database đang sử dụng chỉ để xử lý xung đột Git.
