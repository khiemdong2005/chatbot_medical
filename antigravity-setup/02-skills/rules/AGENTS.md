# Antigravity Project Rules

## 1. Nguyên tắc An toàn & Toàn vẹn Mã nguồn
- Giữ nguyên các comment, docstrings và logic hiện có, chỉ sửa đúng phạm vi được yêu cầu.
- Không bao giờ lưu cứng secrets, mật khẩu, API key vào mã nguồn. Luôn đọc từ biến môi trường.

## 2. Tiêu chuẩn Code Python & Web
- Sử dụng Type Hints (`from typing import Optional, List, Dict`).
- Format code bằng Ruff/Black với độ dài dòng tối đa 100 ký tự.
- Xử lý ngoại lệ đầy đủ với `try/except` và log lỗi chi tiết qua module `logging`.

## 3. Git Commit Convention
- Áp dụng Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`.
