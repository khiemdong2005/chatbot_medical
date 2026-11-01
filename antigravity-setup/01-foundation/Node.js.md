# 02. Node.js LTS — Chạy công cụ npm và MCP Server

## 📌 Tổng quan
Node.js là runtime JavaScript/TypeScript cốt lõi để chạy các công cụ CLI hiện đại, thư viện npm, và đặc biệt là chạy các **Model Context Protocol (MCP) Servers** dựa trên `npx`.

## 🚀 Cài đặt trên Windows 11
```powershell
# Cài đặt Node.js phiên bản LTS (Long Term Support)
winget install OpenJS.NodeJS.LTS -e --source winget
```

## ⚙️ Kiểm tra phiên bản
```powershell
node -v
npm -v
npx -v
```

## 💡 Mẹo dùng với Antigravity
* Dùng `npx` để khởi chạy các MCP servers trực tiếp mà không cần cài đặt vĩnh viễn (như `@modelcontextprotocol/server-github`, `@modelcontextprotocol/server-filesystem`).
* Kích hoạt `pnpm` hoặc `corepack` nếu dự án có dung lượng lớn: `corepack enable`.
