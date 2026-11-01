# 17. Firecrawl MCP — Thu thập nội dung website

## 📌 Tổng quan
Firecrawl chuyển đổi bất kỳ trang web phức tạp nào thành định dạng Clean Markdown hoàn hảo cho LLM đọc. Tự động loại bỏ quảng cáo, popups, cookie banners và chỉ giữ lại nội dung văn bản cốt lõi.

## 🚀 Cấu hình MCP trong Antigravity
```json
{
  "mcpServers": {
    "firecrawl": {
      "command": "npx",
      "args": ["-y", "firecrawl-mcp"],
      "env": {
        "FIRECRAWL_API_KEY": "fc_your_api_key_here"
      }
    }
  }
}
```

## 💡 Mẹo dùng với Antigravity
* Thu thập tài liệu y tế hoặc bài báo khoa học trực tuyến về nạp vào Vector Database cho RAG.
