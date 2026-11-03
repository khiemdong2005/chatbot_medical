# ==============================================================
# MEDIMIND CLINICAL AI - PRODUCTION MULTI-STAGE DOCKERFILE
# ==============================================================

FROM python:3.12-slim as base

# Cài đặt các thư viện hệ thống cần thiết
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Sao chép và cài đặt các dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Sao chép mã nguồn ứng dụng
COPY . .

# Tạo thư mục lưu trữ dataset scan và instance CSDL
RUN mkdir -p /app/uploads /app/instance

# Thiết lập biến môi trường
ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    FLASK_ENV=production

EXPOSE 8000

# Khởi chạy ứng dụng bằng Gunicorn WSGI Server chịu tải cao
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2", "--timeout", "120", "app:app"]
