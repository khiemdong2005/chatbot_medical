# 15. Playwright MCP — Kiểm thử trình duyệt tự động

## 📌 Tổng quan
Playwright MCP cung cấp cho AI Agent một trình duyệt web thực tế (Chromium/Firefox/WebKit) chạy dưới chế độ headless hoặc giao diện. Agent có thể click, gõ chữ, chụp ảnh màn hình, test đăng nhập và bắt lỗi console JavaScript.

## 🚀 Cấu hình MCP trong Antigravity
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@executeautomation/playwright-mcp-server"]
    }
  }
}
```

## 💡 Mẹo dùng với Antigravity
* Kiểm thử giao diện Web: *"Hãy dùng Playwright mở http://127.0.0.1:8000, kiểm tra xem nút Đặt khám có hoạt động không và chụp lại màn hình."*
* Bắt lỗi console: Tự động phát hiện lỗi 404 hoặc script crash trên frontend.
