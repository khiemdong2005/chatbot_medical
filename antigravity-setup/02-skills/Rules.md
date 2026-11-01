# 08. Rules — Đặt quy tắc cho dự án và agent

## 📌 Tổng quan
Rules thiết lập các nguyên tắc "bất di bất dịch" mà AI Agent bắt buộc phải tuân thủ trong toàn bộ quá trình lập trình, đọc mã nguồn và xuất kết quả.

## 📂 Vị trí đặt Rules trong Antigravity
* Cấu hình theo dự án: `.gemini/rules/` hoặc `AGENTS.md` tại thư mục gốc của repository.
* Cấu hình toàn cục cho mọi dự án: `~/.gemini/antigravity/rules/`.

## 📜 Bộ quy tắc vàng mẫu cho dự án Python / Web
```markdown
# Project Core Rules
1. Luôn duy trì tính toàn vẹn của tài liệu: Không tự ý xóa docstring hay comment có sẵn.
2. Không bao giờ lưu cứng secrets: API keys, mật khẩu phải lưu trong biến môi trường (.env).
3. Code Clean & Type Hints: Luôn khai báo type annotations cho function arguments và return.
4. Git Commit Convention: Áp dụng chuẩn Conventional Commits (feat, fix, docs, refactor, test).
5. Error Handling: Mọi hàm gọi API bên ngoài phải có try/except và logging rõ ràng.
```

## 💡 Mẹo dùng với Antigravity
* Đặt quy tắc ngắn gọn, súc tích, chia nhóm rõ ràng theo: Kiến trúc, Bảo mật, Quy chuẩn code và Kiểm thử.
