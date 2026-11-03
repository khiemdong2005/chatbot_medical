#!/bin/bash
# ==============================================================
# MEDIMIND CLINICAL AI - AWS EC2 (UBUNTU 24.04) AUTO SETUP SCRIPT
# Khởi tạo toàn bộ môi trường Docker, Git, UFW Firewall trong 1 lệnh
# Sử dụng: chmod +x deploy/ec2_setup.sh && ./deploy/ec2_setup.sh
# ==============================================================

set -e

echo "🚀 [1/5] Cập nhật danh mục gói hệ thống..."
sudo apt-get update && sudo apt-get upgrade -y

echo "📦 [2/5] Cài đặt các công cụ bổ trợ (Git, Curl, UFW, CA-Certificates)..."
sudo apt-get install -y ca-certificates curl gnupg lsb-release git ufw

echo "🐳 [3/5] Cài đặt Docker Engine & Docker Compose chính chủ từ Docker Repository..."
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "👤 [4/5] Cấp quyền chạy Docker không cần sudo cho user hiện tại ($USER)..."
sudo usermod -aG docker "$USER"

echo "🛡️ [5/5] Cấu hình Firewall UFW bảo mật (Mở SSH:22, HTTP:80, HTTPS:443)..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "================================================================"
echo "✅ HOÀN TẤT THIẾT LẬP MÁY CHỦ EC2 THÀNH CÔNG!"
echo "👉 Anh hãy đăng xuất và SSH lại một lần để nhận quyền Docker:"
echo "   docker compose up -d --build"
echo "================================================================"
