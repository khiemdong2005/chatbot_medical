# 04. uv — Quản lý môi trường Python siêu nhanh

## 📌 Tổng quan
`uv` là công cụ quản lý package và project Python thế hệ mới được viết bằng Rust bởi Astral (nhà phát triển Ruff). Nhanh hơn `pip` từ **10x đến 100x**, giải quyết dependency song song và tích hợp sẵn virtualenv manager.

## 🚀 Cài đặt trên Windows 11
```powershell
# Cài đặt qua PowerShell chính thức
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Hoặc cài qua winget
winget install astral-sh.uv -e --source winget
```

## ⚙️ Lệnh cơ bản thường dùng
```powershell
# Tạo môi trường ảo siêu tốc (<1 giây)
uv venv

# Kích hoạt môi trường ảo
.venv\Scripts\activate

# Cài đặt thư viện với tốc độ tên lửa
uv pip install -r requirements.txt
uv pip install flask google-genai opencv-python

# Chạy script trực tiếp với uv
uv run app.py
```

## 💡 Mẹo dùng với Antigravity
* Khi Antigravity cần cài đặt package nặng (Torch, OpenCV, Transformers), dùng `uv pip install` để hoàn thành chỉ trong vài giây thay vì chờ đợi lâu.
