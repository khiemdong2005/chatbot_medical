# 🩺 MediMind AI — Nền tảng Trợ lý AI Y tế Lâm sàng & Sàng lọc Triệu chứng End-to-End

Dự án Trợ lý AI Y tế được phát triển bởi **AI Engineer**, kết hợp giữa **Clinical Triage Protocol**, **Grounded RAG** và **Kiến trúc Điện toán Đám mây AWS**.

---

## 🚀 Tính năng Nổi bật
* **AI Clinical Triage:** Phân tầng rủi ro lâm sàng thời gian thực (Xanh - Nhẹ $\rightarrow$ Vàng - Theo dõi $\rightarrow$ Đỏ - Cấp cứu 115).
* **Medical Safety Guardrails:** Tuân thủ hướng dẫn điều trị Bộ Y Tế, tuyệt đối không chẩn đoán bừa bãi và không kê đơn kháng sinh tự do.
* **Grounded Citations:** Mọi thông tin đều đi kèm nguồn đối chiếu chuẩn y khoa (MedlinePlus / Bộ Y Tế).
* **Multimodal Scanner:** Quét và phân tích chỉ số sinh hóa máu từ ảnh chụp phiếu xét nghiệm.
* **Bản tóm tắt bệnh án cho Bác sĩ (Pre-Consultation Summary):** Xuất báo cáo lâm sàng 1 trang giúp bác sĩ nắm bắt bệnh sử trong 30 giây.
* **Hạ tầng AWS Cloud (3 Dịch vụ):**
  * **Amazon S3:** Lưu trữ bảo mật tài liệu y khoa PDF và ảnh xét nghiệm của bệnh nhân.
  * **Amazon ECR:** Đăng ký và lưu trữ Docker Image siêu nhẹ (< 150MB).
  * **AWS App Runner:** Chạy ứng dụng web container với chứng chỉ bảo mật HTTPS tự động và Auto-scaling.

---

## 🛠️ Cài đặt & Chạy Thử nghiệm

### 1. Cài đặt môi trường
```bash
cd "D:\Ki_6\Vide code\chatbot_medical"
pip install -r requirements.txt
```

### 2. Khởi chạy Server
```bash
python app.py
```

Mở trình duyệt tại: **http://localhost:8000**
