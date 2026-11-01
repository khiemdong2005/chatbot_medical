# 01. Git — Quản lý phiên bản và lịch sử thay đổi

## 📌 Tổng quan
Git là hệ thống quản lý phiên bản phân tán (VCS) tiêu chuẩn cho mọi lập trình viên và AI Agent. Giúp Antigravity theo dõi các thay đổi code, tạo commit an toàn và đồng bộ với GitHub/GitLab.

## 🚀 Cài đặt trên Windows 11
```powershell
# Cài đặt qua winget
winget install --id Git.Git -e --source winget
```

## ⚙️ Cấu hình ban đầu
```powershell
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
git config --global core.autocrlf true
git config --global init.defaultBranch main
```

## 💡 Mẹo dùng với Antigravity
* Yêu cầu Agent tạo commit thường xuyên sau mỗi tính năng thành công: `git commit -m "feat(module): description"`.
* Dùng `git status` và `git diff` để kiểm tra thay đổi trước khi ra lệnh commit.
