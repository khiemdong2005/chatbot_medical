#!/bin/bash
# ==============================================================
# MEDIMIND CLINICAL AI - 1-CLICK QUICK UPDATE SCRIPT
# Tự động kéo code mới nhất từ Git và cập nhật Docker trong 15s
# Sử dụng: ./deploy/update.sh
# ==============================================================

set -e

echo "🔄 [1/3] Đang kéo mã nguồn mới nhất từ GitHub..."
git pull origin main

echo "🏗️ [2/3] Đang biên dịch và cập nhật Docker Containers..."
docker compose up -d --build

echo "🧹 [3/3] Dọn dẹp các Docker image cũ không còn sử dụng..."
docker image prune -f

echo "================================================================"
echo "✅ HỆ THỐNG ĐÃ ĐƯỢC CẬP NHẬT LÊN PHIÊN BẢN MỚI NHẤT THÀNH CÔNG!"
echo "👉 Kiểm tra trạng thái: docker compose ps"
echo "👉 Kiểm tra log:        docker compose logs -f web"
echo "================================================================"
