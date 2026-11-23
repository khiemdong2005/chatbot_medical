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

# Cài đặt các gói hệ thống nhẹ cần thiết (curl cho healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Tạo người dùng non-root (appuser) để tuân thủ tiêu chuẩn an toàn container
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -s /bin/bash -m appuser

WORKDIR /app

# 1. Tận dụng Docker layer caching cho dependencies
COPY requirements.txt requirements-reranker.txt ./

# Cả hai bộ OCR chạy trên CPU. Cài PyTorch bản CPU trước để tránh kéo thư viện CUDA.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.12.0 torchvision==0.27.0 && \
    pip install --no-cache-dir -r requirements.txt

# VietOCR chỉ dùng để suy luận. Bỏ các gói huấn luyện và bản Pillow cũ trong metadata.
RUN pip install --no-cache-dir --no-deps vietocr==0.3.13 einops==0.2.0 gdown==4.4.0

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

# Tải trọng số OCR trong lúc build để lần quét đầu tiên chạy cục bộ.
USER appuser
RUN python -c "import easyocr; easyocr.Reader(['vi', 'en'], gpu=False, verbose=False)"
RUN mkdir -p /app/models/vietocr && cd /app/models/vietocr && \
    curl -fSL --retry 2 -o base.yml https://vocr.vn/data/vietocr/config/base.yml && \
    curl -fSL --retry 2 -o vgg-seq2seq.yml https://vocr.vn/data/vietocr/config/vgg-seq2seq.yml && \
    curl -fSL --retry 2 -o vgg_seq2seq.pth https://vocr.vn/data/vietocr/vgg_seq2seq.pth && \
    printf '%s\n' \
        '9c8283fadb950f06f5d3400475f80d5355700ff315c9c48b7875e6ea66647d1c  base.yml' \
        '0160ba8d442ae96f4c6095b92ac3521c59b83ce6eda9fd5459e8628a5586c3e8  vgg-seq2seq.yml' \
        '0921503a41375a0584268e23ef3d414ea478a8fe8777865c7745d38f2d0bc5db  vgg_seq2seq.pth' \
        | sha256sum --check && \
    python -c "from vietocr.tool.predictor import Predictor"

# 4. Sao chép toàn bộ mã nguồn ứng dụng (Đã loại trừ qua .dockerignore)
COPY --chown=appuser:appuser . .

EXPOSE 8000

# Kiểm tra sức khỏe tiến trình định kỳ bằng /health endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Khởi chạy FastAPI Gateway bằng Uvicorn
CMD ["uvicorn", "core.main_fastapi:app", "--host", "0.0.0.0", "--port", "8000"]

