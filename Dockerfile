# ==============================================================================
# 🩺 MEDIMIND CLINICAL AI - DOCKERFILE (LOCAL PACKAGING)
# ==============================================================================
# Multi-stage / Layered Slim Image for FastAPI + RAG + Local Observability
# ==============================================================================

FROM python:3.11-slim

# Ngăn Python tạo bytecode .pyc và bật unbuffered output để log hiển thị tức thì
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HF_HOME=/home/appuser/.cache/huggingface

# Cài đặt các gói hệ thống nhẹ cần thiết (curl cho healthcheck, libglib/libgomp cho OpenCV)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Tạo người dùng non-root (appuser) để tuân thủ tiêu chuẩn an toàn container
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -s /bin/bash -m appuser

WORKDIR /app

# 1. Tận dụng Docker layer caching cho dependencies
COPY requirements.txt requirements-reranker.txt ./

# Cài đặt dependencies chính
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 2. Build arg tùy chọn cho BGE Reranker (Mặc định: false để image nhẹ và build nhanh)
ARG INSTALL_RERANKER=false
RUN if [ "$INSTALL_RERANKER" = "true" ] ; then \
        echo "Installing optional BGE Reranker dependencies (sentence-transformers)..." && \
        pip install --no-cache-dir -r requirements-reranker.txt ; \
    else \
        echo "Skipping optional BGE Reranker installation (INSTALL_RERANKER=false)..." ; \
    fi

# 3. Tạo sẵn các thư mục lưu trữ dữ liệu bền vững và cấp quyền cho appuser
RUN mkdir -p /app/medical_vectordb /app/instance /app/uploads /home/appuser/.cache/huggingface && \
    chown -R appuser:appuser /app /home/appuser/.cache

# 4. Sao chép toàn bộ mã nguồn ứng dụng (Đã loại trừ qua .dockerignore)
COPY --chown=appuser:appuser . .

# Chuyển sang quyền appuser non-root
USER appuser

EXPOSE 8000

# Kiểm tra sức khỏe tiến trình định kỳ bằng /health endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Khởi chạy FastAPI Gateway bằng Uvicorn (nhận X-Forwarded-Proto/For từ CloudFront/ALB)
CMD ["uvicorn", "core.main_fastapi:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]

