# 13. Context7 — Tra cứu tài liệu thư viện cập nhật

## 📌 Tổng quan
Context7 MCP Server cung cấp tài liệu API và mã nguồn ví dụ mới nhất của hàng ngàn thư viện mã nguồn mở phổ biến (React, Tailwind, LangChain, Next.js, FastAPI), giúp AI Agent không bao giờ viết code theo cú pháp cũ đã lỗi thời.

## 🚀 Cấu hình MCP trong Antigravity
Thêm vào file cấu hình `mcp_servers.json`:
```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    }
  }
}
```

## 💡 Mẹo dùng với Antigravity
* Khi cần dùng thư viện mới phát hành hoặc bản nâng cấp lớn (ví dụ chuyển đổi từ Pydantic v1 sang v2), kích hoạt Context7 để tra cứu tài liệu mới nhất.
