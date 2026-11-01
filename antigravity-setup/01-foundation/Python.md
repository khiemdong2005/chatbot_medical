# 03. Python — Runtime cho script và AI tool

## 📌 Tổng quan
Python là ngôn ngữ số 1 cho AI, Data Science, Machine Learning, backend Flask/FastAPI và automation scripts. Cung cấp môi trường thực thi cho các thư viện xử lý ảnh (OpenCV), OCR (EasyOCR), RAG (ChromaDB), và LLM SDK (google-genai).

## 🚀 Cài đặt trên Windows 11
```powershell
# Cài đặt Python 3.11 hoặc 3.12 (khuyên dùng Python 3.11 cho tương thích tối đa)
winget install Python.Python.3.11 -e --source winget
```

## ⚙️ Kiểm tra và thiết lập môi trường
```powershell
python --version
python -m pip install --upgrade pip
```

## 💡 Mẹo dùng với Antigravity
* Luôn chạy dự án trong môi trường ảo (`venv` hoặc `uv venv`) để tránh xung đột dependency hệ thống.
* Sử dụng `py` launcher trên Windows để chuyển đổi phiên bản linh hoạt (`py -3.11 -m venv .venv`).
