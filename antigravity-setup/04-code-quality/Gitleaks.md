# 24. Gitleaks — Quét secrets trước khi commit

## 📌 Tổng quan
Gitleaks là công cụ bảo mật quét tự động mã nguồn và lịch sử Git để phát hiện các thông tin nhạy cảm vô tình bị bỏ quên (AWS Access Keys, `GEMINI_API_KEY`, Private Keys, JWT Secrets, Passwords).

## 🚀 Cài đặt trên Windows 11
```powershell
winget install gitleaks -e --source winget
```

## ⚙️ Lệnh quét an ninh
```powershell
# Quét toàn bộ repository
gitleaks detect -v

# Bảo vệ trước khi commit (Pre-commit hook)
gitleaks protect -v --staged
```

## 💡 Mẹo dùng với Antigravity
* Chạy `gitleaks detect` trước mỗi lần nộp bài hoặc push code lên GitHub để đảm bảo tuyệt đối không bị lộ API key.
