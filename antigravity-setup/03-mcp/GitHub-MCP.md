# 14. GitHub MCP — Làm việc với issue, PR và repository

## 📌 Tổng quan
GitHub MCP Server chính thức từ GitHub cho phép Antigravity đọc commit history, xem các pull request đang mở, tìm kiếm code trên toàn bộ GitHub, và tự động tạo issue hoặc PR thông qua giao thức MCP an toàn.

## 🚀 Cấu hình MCP trong Antigravity
```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

## 💡 Mẹo dùng với Antigravity
* Tạo Personal Access Token (classic) với quyền `repo` và `read:org`.
* Cho phép Agent tự động đọc feedback trong PR để sửa code tương ứng.
