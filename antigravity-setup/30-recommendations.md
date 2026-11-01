# 30 Thứ Nên Cài Cho Antigravity — Bộ Công Cụ Tăng Sức Mạnh AI Coding trên Windows 11

> Tổng hợp 30 công cụ, kỹ năng (skills), máy chủ ngữ cảnh (MCP Servers) và tiện ích mở rộng giúp tối đa hóa hiệu năng lập trình cùng trợ lý AI Antigravity.

---

## 📋 MỤC LỤC TỔNG QUAN

| Nhóm | Danh mục | Số lượng | Mô tả trọng tâm |
|:---:|:---|:---:|:---|
| **Nhóm 1** | [Nền tảng & Workflow](#nhóm-1-nền-tảng--workflow) | 01 – 06 | Thiết lập môi trường runtime, terminal và container. |
| **Nhóm 2** | [Skills & Hướng dẫn](#nhóm-2-skills--hướng-dẫn) | 07 – 12 | Thư viện kỹ năng, prompt và quy tắc cho AI Agent. |
| **Nhóm 3** | [MCP & Kết nối](#nhóm-3-mcp--kết-nối) | 13 – 18 | Kết nối dữ liệu ngoài, trình duyệt và API docs. |
| **Nhóm 4** | [Chất lượng mã nguồn](#nhóm-4-chất-lượng-mã-nguồn) | 19 – 24 | Linter, formatter, kiểm thử tự động và quét bảo mật. |
| **Nhóm 5** | [Quan sát & Năng suất](#nhóm-5-quan-sát--năng-suất) | 25 – 30 | Đóng gói context, quản lý API, CSDL và lịch sử Git. |

---

## 🔹 Nhóm 1. Nền tảng & Workflow
*Các công cụ nền tảng giúp thiết lập môi trường phát triển trên Windows 11.*

| STT | Tên công cụ | Chức năng chính | Lệnh cài đặt nhanh (PowerShell / winget) | Tài liệu chi tiết |
|:---:|:---|:---|:---|:---:|
| **01** | **Git** | Quản lý phiên bản và lịch sử thay đổi mã nguồn. | `winget install --id Git.Git -e` | [Git.md](01-foundation/Git.md) |
| **02** | **Node.js LTS** | Chạy công cụ npm, npx và các MCP Server. | `winget install OpenJS.NodeJS.LTS -e` | [Node.js.md](01-foundation/Node.js.md) |
| **03** | **Python** | Runtime cho backend, data science và AI tools. | `winget install Python.Python.3.11 -e` | [Python.md](01-foundation/Python.md) |
| **04** | **uv** | Quản lý môi trường và package Python nhanh hơn pip 10x. | `irm https://astral.sh/uv/install.ps1 \| iex` | [uv.md](01-foundation/uv.md) |
| **05** | **GitHub CLI (`gh`)** | Quản lý repository, issue, PR và secret qua CLI. | `winget install --id GitHub.cli -e` | [GitHub-CLI.md](01-foundation/GitHub-CLI.md) |
| **06** | **Docker Desktop** | Chạy dịch vụ, microservices và container thử nghiệm. | `winget install Docker.DockerDesktop -e` | [Docker.md](01-foundation/Docker.md) |

---

## 🔸 Nhóm 2. Skills & Hướng dẫn
*Thư viện kỹ năng và hướng dẫn cho AI Agent tối ưu hóa quy trình làm việc.*

| STT | Tên công cụ / Skill | Chức năng chính | Lợi ích khi dùng Antigravity | Tài liệu chi tiết |
|:---:|:---|:---|:---|:---:|
| **07** | **SKILL.md** | Định nghĩa kỹ năng Agent tái sử dụng qua YAML frontmatter. | Giúp Agent nắm vững quy trình lặp lại mà không cần nhắc lại prompt. | [SKILL.md](02-skills/SKILL.md) |
| **08** | **Rules** | Đặt quy tắc bắt buộc cho dự án (`.gemini/rules`, `AGENTS.md`). | Kiểm soát chặt chẽ phong cách code, bảo mật và commit conventions. | [Rules.md](02-skills/Rules.md) |
| **09** | **Anthropic Skills** | Bộ kỹ năng xử lý và trích xuất tài liệu dài chuyên sâu. | Tối ưu hóa phân tích file PDF, docx lớn mà không mất ngữ cảnh. | [Anthropic-Skills.md](02-skills/Anthropic-Skills.md) |
| **10** | **Superpowers** | Quy trình lập kế hoạch (Plan), TDD và rà soát code nghiêm ngặt. | Nâng cao tư duy kiến trúc của Agent, giảm 90% lỗi logic phát sinh. | [Superpowers.md](02-skills/Superpowers.md) |
| **11** | **UI UX Pro Max** | Cẩm nang thiết kế UI/UX đỉnh cao (VisionOS Glassmorphism). | Hướng dẫn Agent tạo giao diện web tinh tế, hiện đại, chuẩn thẩm mỹ. | [UI-UX-Pro-Max.md](02-skills/UI-UX-Pro-Max.md) |
| **12** | **planning-with-files** | Lưu vết kế hoạch và tiến độ qua các tệp (`TASK_PLAN.md`). | Duy trì tính liên tục của dự án qua nhiều phiên chat khác nhau. | [planning-with-files.md](02-skills/planning-with-files.md) |

---

## 🔮 Nhóm 3. MCP & Kết nối
*Kết nối dữ liệu, công cụ và dịch vụ bên ngoài thông qua Model Context Protocol.*

| STT | MCP Server | Chức năng chính | Cách thức tích hợp | Tài liệu chi tiết |
|:---:|:---|:---|:---|:---:|
| **13** | **Context7** | Tra cứu tài liệu thư viện cập nhật mới nhất. | `npx -y @upstash/context7-mcp` | [Context7.md](03-mcp/Context7.md) |
| **14** | **GitHub MCP** | Đọc/viết issue, PR, duyệt code trực tiếp trên GitHub. | `npx -y @modelcontextprotocol/server-github` | [GitHub-MCP.md](03-mcp/GitHub-MCP.md) |
| **15** | **Playwright MCP** | Kiểm thử trình duyệt tự động (Headless Chrome/Firefox). | `npx -y @executeautomation/playwright-mcp-server` | [Playwright-MCP.md](03-mcp/Playwright-MCP.md) |
| **16** | **Chrome DevTools MCP** | Phân tích lỗi console, DOM inspect và hiệu năng web. | Cài đặt qua Plugin Marketplace Antigravity | [Chrome-DevTools-MCP.md](03-mcp/Chrome-DevTools-MCP.md) |
| **17** | **Firecrawl MCP** | Thu thập nội dung website thành định dạng clean markdown. | `npx -y firecrawl-mcp` | [Firecrawl-MCP.md](03-mcp/Firecrawl-MCP.md) |
| **18** | **Google Knowledge** | Tìm kiếm tài liệu Google chính thức (Gemini SDK, Cloud). | Tích hợp sẵn trong Antigravity runtime | [Google-Knowledge.md](03-mcp/Google-Knowledge.md) |

---

## 🛡️ Nhóm 4. Chất lượng mã nguồn
*Đảm bảo mã nguồn sạch, nhất quán, không lỗi tiềm ẩn và an toàn bảo mật.*

| STT | Công cụ | Chức năng chính | Lệnh cài đặt / Chạy nhanh | Tài liệu chi tiết |
|:---:|:---|:---|:---|:---:|
| **19** | **ESLint** | Phát hiện lỗi và bất thường trong mã JavaScript/TypeScript. | `npm install --save-dev eslint` | [ESLint.md](04-code-quality/ESLint.md) |
| **20** | **Prettier** | Chuẩn hóa định dạng mã nguồn (format-on-save). | `npm install --save-dev prettier` | [Prettier.md](04-code-quality/Prettier.md) |
| **21** | **Ruff** | Linter & Formatter siêu tốc bằng Rust cho Python. | `uv tool install ruff` hoặc `pip install ruff` | [Ruff.md](04-code-quality/Ruff.md) |
| **22** | **pytest** | Framework kiểm thử tự động hàng đầu cho Python. | `uv pip install pytest pytest-cov` | [pytest.md](04-code-quality/pytest.md) |
| **23** | **Vitest** | Kiểm thử dự án JavaScript/TypeScript thế hệ mới siêu nhanh. | `npm install --save-dev vitest` | [Vitest.md](04-code-quality/Vitest.md) |
| **24** | **Gitleaks** | Quét và chặn rò rỉ secrets (API key, mật khẩu) trước commit. | `winget install gitleaks -e` | [Gitleaks.md](04-code-quality/Gitleaks.md) |

---

## 🚀 Nhóm 5. Quan sát & Năng suất
*Tăng hiệu quả làm việc, theo dõi tiến độ và quản lý cơ sở dữ liệu.*

| STT | Công cụ | Chức năng chính | Lệnh cài đặt / Sử dụng | Tài liệu chi tiết |
|:---:|:---|:---|:---|:---:|
| **25** | **Repomix** | Đóng gói toàn bộ repository thành 1 file cho AI đọc. | `npx repomix` | [Repomix.md](05-productivity/Repomix.md) |
| **26** | **Beads** | Lưu lại dấu vết công việc xuyên các phiên làm việc. | Cấu hình file checkpoint task | [Beads.md](05-productivity/Beads.md) |
| **27** | **Postman** | Nền tảng kiểm thử và quản lý REST API chuyên nghiệp. | `winget install Postman.Postman -e` | [Postman.md](05-productivity/Postman.md) |
| **28** | **Bruno** | Kiểm thử API mã nguồn mở, lưu collection trực tiếp trong Git. | `winget install Usebruno.Bruno -e` | [Bruno.md](05-productivity/Bruno.md) |
| **29** | **DBeaver** | Quản trị và truy vấn trực quan CSDL (SQLite, Postgres, MySQL). | `winget install dbeaver.dbeaver -e` | [DBeaver.md](05-productivity/DBeaver.md) |
| **30** | **GitLens** | Extension xem lịch sử Git, blame từng dòng code trong IDE. | Cài từ VS Code / Antigravity Extensions | [GitLens.md](05-productivity/GitLens.md) |

---

*Tài liệu được biên soạn tự động và đồng bộ với cấu trúc `antigravity-setup/`.*
