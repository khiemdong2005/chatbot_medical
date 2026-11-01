# 06. Docker Desktop — Chạy dịch vụ, container thử nghiệm

## 📌 Tổng quan
Docker Desktop trên Windows 11 cho phép đóng gói ứng dụng, chạy thử nghiệm các database cục bộ (PostgreSQL, Redis, ChromaDB), kiểm thử môi trường production AWS ECS / App Runner trước khi triển khai thực tế.

## 🚀 Cài đặt trên Windows 11
```powershell
# Yêu cầu kích hoạt WSL 2 trước
wsl --install

# Cài đặt Docker Desktop
winget install Docker.DockerDesktop -e --source winget
```

## ⚙️ Kiểm tra hoạt động
```powershell
docker --version
docker compose version
docker run hello-world
```

## 💡 Mẹo dùng với Antigravity
* Yêu cầu Antigravity tạo `Dockerfile` chuẩn multi-stage build để giảm dung lượng image:
  `docker build -t medimind-clinical-ai:latest .`
* Chạy thử nghiệm local: `docker run -p 8000:8000 --env-file .env medimind-clinical-ai:latest`.
