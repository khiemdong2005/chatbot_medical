# 28. Bruno — Kiểm thử API bằng collection trong Git

## 📌 Tổng quan
Bruno là ứng dụng API Client mã nguồn mở thế hệ mới (thay thế Postman/Insomnia nhẹ hơn nhiều). Điểm đột phá của Bruno là lưu toàn bộ API Collections dưới dạng **plain-text file (`.bru`) ngay trong thư mục Git** của dự án. Không cần đồng bộ cloud, không lo rò rỉ dữ liệu y tế.

## 🚀 Cài đặt trên Windows 11
```powershell
winget install Usebruno.Bruno -e --source winget
```

## 💡 Mẹo dùng với Antigravity
* Tạo thư mục `bruno-collections/` ngay trong repo. AI Agent có thể trực tiếp viết và chỉnh sửa các kịch bản test API mà không cần mở GUI.
