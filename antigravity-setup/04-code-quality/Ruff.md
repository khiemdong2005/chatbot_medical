# 21. Ruff — Lint và format Python siêu nhanh

## 📌 Tổng quan
Ruff được viết bằng Rust, thay thế cùng lúc `flake8`, `black`, `isort`, `pylint`. Tốc độ nhanh hơn black/flake8 từ **10x đến 100x**. Là tiêu chuẩn vàng cho dự án Python năm 2024–2026.

## 🚀 Cài đặt trên Windows 11
```powershell
# Cài đặt qua uv hoặc pip
uv tool install ruff
# Hoặc: uv pip install ruff
```

## ⚙️ Lệnh thực thi
```powershell
# Kiểm tra lỗi lint
ruff check .

# Tự động sửa lỗi có thể fix
ruff check --fix .

# Tự động format code theo chuẩn PEP 8
ruff format .
```

## 💡 Mẹo dùng với Antigravity
* Cấu hình file `ruff.toml` ở thư mục gốc để kích hoạt các rule kiểm tra type hints và docstrings.
