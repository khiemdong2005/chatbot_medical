# 19. ESLint — Phát hiện lỗi JavaScript/TypeScript

## 📌 Tổng quan
ESLint là công cụ tĩnh phân tích mã nguồn JavaScript/TypeScript để tìm kiếm cú pháp sai, biến chưa sử dụng, nguy cơ lỗi logic và vi phạm coding convention.

## 🚀 Cài đặt nhanh
```powershell
npm install --save-dev eslint @eslint/js
```

## ⚙️ Chạy kiểm tra
```powershell
npx eslint static/js/app.js
npx eslint . --fix
```

## 💡 Mẹo dùng với Antigravity
* Yêu cầu Agent chạy `npx eslint .` trước khi commit mã nguồn frontend để đảm bảo không còn cảnh báo vàng/đỏ.
