# 27. Postman — Kiểm thử và quản lý REST API

## 📌 Tổng quan
Postman là nền tảng số 1 thế giới về kiểm thử, phát triển và lập tài liệu API. Hỗ trợ gửi HTTP requests (GET, POST, PUT, DELETE), kiểm tra mã trạng thái, header, auth token và tự động hóa test scripts.

## 🚀 Cài đặt trên Windows 11
```powershell
winget install Postman.Postman -e --source winget
```

## 💡 Mẹo dùng với Antigravity
* Xuất file OpenAPI / Swagger từ backend Flask/FastAPI và import vào Postman để kiểm thử toàn diện các endpoint:
  * `POST /api/chat`
  * `POST /api/prescription/scan`
  * `GET /api/clinical-summary`
