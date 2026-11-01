# 25. Repomix — Đóng gói mã nguồn cho AI đọc

## 📌 Tổng quan
Repomix (tên cũ là Repopack) là công cụ CLI mạnh mẽ đóng gói toàn bộ cấu trúc thư mục và mã nguồn của repository thành một file text/markdown duy nhất, tối ưu token để đưa vào ngữ cảnh của AI LLM.

## 🚀 Cài đặt & Chạy ngay
```powershell
# Chạy trực tiếp qua npx không cần cài đặt
npx repomix

# Hoặc cài toàn cục
npm install -g repomix
```

## ⚙️ Lệnh tiện ích
```powershell
# Đóng gói xuất file markdown kèm sơ đồ cây
repomix --style markdown --output repomix-output.md
```

## 💡 Mẹo dùng với Antigravity
* Rất hữu dụng khi bạn cần copy toàn bộ context dự án sang một phiên hỏi đáp sâu hoặc gửi cho cố vấn xem xét tổng thể.
