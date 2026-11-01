# 12. planning-with-files — Lưu kế hoạch qua nhiều phiên làm việc

## 📌 Tổng quan
Khi làm việc với các dự án lớn kéo dài qua nhiều ngày hoặc nhiều phiên chat, ngữ cảnh có thể bị reset hoặc trôi đi. Kỹ thuật `planning-with-files` sử dụng các tệp markdown chuyên dụng để duy trì trạng thái công việc bền vững (Session Persistence).

## 📂 Các tệp trạng thái cốt lõi
* `TASK_PLAN.md`: Kế hoạch tổng thể và danh sách việc cần làm (Todo checklist).
* `DECISIONS.md`: Ghi lại các quyết định kiến trúc quan trọng (Architectural Decision Records - ADR) để Agent không bao giờ hỏi lại.
* `PROGRESS.md`: Nhật ký những việc đã hoàn thành, lỗi đã gặp và giải pháp đã thử.

## 📝 Mẫu Task Checklist
```markdown
# Kế hoạch Triển khai
- [x] Bước 1: Khởi tạo database và migrations
- [x] Bước 2: Viết core triage logic
- [/] Bước 3: Tích hợp OpenCV EasyOCR (Đang thực hiện)
- [ ] Bước 4: Viết unit tests kiểm thử
- [ ] Bước 5: Đóng gói Docker
```

## 💡 Mẹo dùng với Antigravity
* Luôn yêu cầu Agent cập nhật file `TASK_PLAN.md` sau khi hoàn thành từng bước.
