# 23. Vitest — Kiểm thử dự án JavaScript hiện đại

## 📌 Tổng quan
Vitest là test runner thế hệ mới xây dựng trên nền Vite. Tương thích hoàn toàn với cú pháp Jest nhưng chạy nhanh hơn gấp nhiều lần nhờ cơ chế ESM native và multithreading.

## 🚀 Cài đặt nhanh
```powershell
npm install --save-dev vitest
```

## ⚙️ Chạy test
```powershell
npx vitest run
```

## 💡 Mẹo dùng với Antigravity
* Phù hợp kiểm thử các hàm tiện ích JavaScript (formatting date, parsing API response) trong thư mục `static/js/`.
