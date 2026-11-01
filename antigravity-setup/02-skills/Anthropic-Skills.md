# 09. Anthropic Skills — Bộ kỹ năng xử lý tài liệu

## 📌 Tổng quan
Anthropic Skills cung cấp các mẫu prompt và chiến lược trích xuất thông tin chuyên sâu từ tài liệu dài (PDF, văn bản hành chính, báo cáo tài chính, tài liệu y khoa) mà không bị mất mát ngữ cảnh.

## 🎯 Ứng dụng cốt lõi
* Trích xuất bảng biểu có cấu trúc từ file PDF scan hoặc ảnh đơn thuốc.
* Tóm tắt đa tầng: Executive summary (30s) -> Chi tiết chuyên sâu -> Danh mục hành động (Action items).
* Đối chiếu mâu thuẫn giữa 2 tài liệu chính sách hoặc phác đồ điều trị.

## 💡 Mẹo dùng với Antigravity
* Chia nhỏ tài liệu thành từng section trước khi phân tích nếu tài liệu vượt quá 50 trang.
* Yêu cầu Agent luôn trích dẫn số trang hoặc vị trí đoạn văn khi đưa ra kết luận.
