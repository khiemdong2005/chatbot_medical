# 18. Google Developer Knowledge — Tìm tài liệu Google chính thức

## 📌 Tổng quan
MCP Server chính thức từ Google tra cứu tài liệu Gemini API, Google GenAI SDK, Google Cloud Platform, Firebase và Android. Đảm bảo mã nguồn sinh ra luôn tuân thủ đúng phương thức của SDK mới nhất.

## 🚀 Cấu hình có sẵn trong Antigravity
Hệ thống Antigravity đã tích hợp sẵn server:
* `gemini-api_gemini-api-docs`: Cung cấp 2 công cụ `gemini_search_docs` và `gemini_get_doc`.

## 💡 Mẹo dùng với Antigravity
* Khi viết code gọi model mới (như `gemini-1.5-flash` hay `gemini-2.0-flash`), Agent tự động tra cứu tài liệu để dùng đúng cú pháp `client.models.generate_content`.
