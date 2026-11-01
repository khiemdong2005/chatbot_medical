# Antigravity Setup Toolkit — Bộ Công Cụ Tăng Sức Mạnh AI Coding trên Windows 11

Thư mục này chứa đầy đủ hướng dẫn, cấu hình mẫu và script kiểm tra cho **30 công cụ khuyến nghị** giúp tối đa hóa sức mạnh của trợ lý lập trình AI Antigravity.

---

## 📂 CẤU TRÚC THƯ MỤC CHUẨN

```text
antigravity-setup/
├── 01-foundation/              # Nhóm 1: Nền tảng & Workflow (Git, Node.js, Python, uv, gh, Docker)
├── 02-skills/                  # Nhóm 2: Skills & Hướng dẫn (SKILL.md, Rules, Superpowers, UI/UX)
├── 03-mcp/                     # Nhóm 3: MCP & Kết nối (Context7, GitHub, Playwright, Chrome DevTools, Firecrawl)
├── 04-code-quality/            # Nhóm 4: Chất lượng mã nguồn (ESLint, Prettier, Ruff, pytest, Vitest, Gitleaks)
├── 05-productivity/            # Nhóm 5: Quan sát & Năng suất (Repomix, Beads, Postman, Bruno, DBeaver, GitLens)
├── check-30-tools.ps1          # Script PowerShell tự động kiểm tra trạng thái cài đặt trên Windows 11
├── 30-recommendations.md       # Bảng tổng hợp chi tiết 30 công cụ chuẩn infographic
└── README.md                   # Hướng dẫn sử dụng bộ toolkit
```

---

## ⚡ HƯỚNG DẪN KIỂM TRA MÔI TRƯỜNG NHANH

Chạy script PowerShell sau để kiểm tra xem máy tính Windows 11 của bạn đã cài đặt những công cụ nào:

```powershell
cd "d:\Ki_6\Vide code\chatbot_medical\antigravity-setup"
powershell -ExecutionPolicy Bypass -File .\check-30-tools.ps1
```

Script sẽ in ra bảng tổng kết trực quan với màu sắc:
* 🟢 **ĐÃ CÀI ĐẶT** (kèm phiên bản phát hiện)
* 🔴 **CHƯA CÓ** (kèm lệnh cài đặt một click qua `winget` hoặc `npm`)

---

## 🚀 CÀI ĐẶT NHANH CÁC CÔNG CỤ CÒN THIẾU

```powershell
# Cài đặt nền tảng bổ sung qua winget
winget install --id GitHub.cli -e
winget install gitleaks -e
winget install Usebruno.Bruno -e
winget install dbeaver.dbeaver -e

# Cài đặt công cụ Python siêu nhanh qua uv
uv tool install ruff

# Chạy công cụ JavaScript tiện ích trực tiếp qua npx
npx repomix
```

---

*Bộ tài liệu được thiết lập riêng biệt bên trong thư mục `chatbot_medical/antigravity-setup/`.*
