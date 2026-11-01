# 05. GitHub CLI (`gh`) — Quản lý repository, issue và PR

## 📌 Tổng quan
GitHub CLI đưa toàn bộ sức mạnh của GitHub vào Command Line / PowerShell. Cho phép Antigravity clone repo, tạo Pull Request, review code, quản lý GitHub Issues và secrets mà không cần mở trình duyệt.

## 🚀 Cài đặt trên Windows 11
```powershell
winget install --id GitHub.cli -e --source winget
```

## ⚙️ Đăng nhập xác thực
```powershell
gh auth login
# Chọn: GitHub.com -> HTTPS -> Yes (Authenticate Git with your GitHub credentials) -> Login with a web browser
```

## 💡 Mẹo dùng với Antigravity
* Tạo PR tự động: `gh pr create --title "feat: add clinical triage" --body "Automated PR by Antigravity"`.
* Xem danh sách issue: `gh issue list`.
* Xem trạng thái CI/CD GitHub Actions: `gh run list`.
