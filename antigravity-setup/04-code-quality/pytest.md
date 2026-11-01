# 22. pytest — Kiểm thử tự động cho Python

## 📌 Tổng quan
pytest là framework kiểm thử tự động số 1 cho Python. Hỗ trợ test fixtures, parameterized testing, mocking và báo cáo chi tiết độ bao phủ (code coverage).

## 🚀 Cài đặt trên Windows 11
```powershell
uv pip install pytest pytest-cov
```

## ⚙️ Chạy kiểm thử
```powershell
# Chạy toàn bộ test cases
pytest -v

# Chạy kèm báo cáo độ bao phủ
pytest --cov=core tests/
```

## 💡 Mẹo dùng với Antigravity
* Áp dụng quy tắc: Mỗi khi viết một module mới (như `triage.py`), yêu cầu Agent viết song song file `tests/test_triage.py` và chạy pytest xác nhận 100% test pass.
