# 🩺 MediMind AI — Clinical Assistant & Symptom Triage Platform
> **Nền tảng Trợ lý AI Y tế Lâm sàng & Sàng lọc Triệu chứng End-to-End**  
> Kết hợp giữa **Clinical Triage Protocol**, **Medical Safety Guardrails** và **Kiến trúc Điện toán Đám mây AWS**.

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Framework-Flask%203.1.0-emerald.svg)](https://flask.palletsprojects.com/)
[![Cloud Ready](https://img.shields.io/badge/Cloud-AWS%20S3%20%7C%20ECR%20%7C%20App%20Runner-orange.svg)](https://aws.amazon.com/)
[![Medical Protocol](https://img.shields.io/badge/Protocol-Clinical%20Triage%20Guidelines-red.svg)](#-nguyên-tắc-an-toàn-y-tế)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#)

---

## 📖 1. Giới thiệu Tổng quan (Overview)

**MediMind AI** là hệ thống trợ lý y tế số thông minh hỗ trợ người bệnh sàng lọc triệu chứng ban đầu, đánh giá mức độ nguy cơ lâm sàng, cảnh báo cờ đỏ cấp cứu và kết xuất hồ sơ tóm tắt tiền khám (*Pre-Consultation Summary*) gửi trực tiếp cho bác sĩ chuyên khoa trong vòng 30 giây.

Hệ thống được thiết kế theo tiêu chuẩn an toàn y tế nghiêm ngặt, tuân thủ hướng dẫn điều trị của **Bộ Y Tế** và các tài liệu chuẩn quốc tế như **MedlinePlus**, giúp giảm tải áp lực tiếp đón bệnh nhân tại khoa khám bệnh và tối ưu hóa thời gian hội chẩn lâm sàng.

---

## 🌟 2. Tính năng Cốt lõi (Key Features)

* 🚨 **AI Clinical Triage & Red Flag Detection**:
  * Phát hiện tức thời dấu hiệu cấp cứu đe dọa tính mạng (*đau thắt ngực, đột quỵ, co giật, khó thở dữ dội, sốc phản vệ, nôn/ho ra máu...*).
  * Kích hoạt quy trình khẩn cấp hướng dẫn người bệnh gọi **Cấp cứu 115** hoặc di chuyển khẩn đến cơ sở y tế gần nhất.
  * Phân tầng nguy cơ 3 cấp độ: **Xanh (Nhẹ / Theo dõi)** $\rightarrow$ **Vàng (Cần khám chuyên khoa)** $\rightarrow$ **Đỏ (Khẩn cấp 115)**.
* 🛡️ **Medical Safety Guardrails (Rào chắn an toàn)**:
  * Tuyệt đối **không chẩn đoán khẳng định** ("Triệu chứng có thể liên quan..." thay vì kết luận áp đặt).
  * Tuyệt đối **không tự ý kê đơn kháng sinh** hoặc thuốc đặc trị.
  * Tự động kiểm tra tiền sử dị ứng và chống chỉ định (ví dụ: dị ứng Penicillin / NSAIDs / Paracetamol).
* 📚 **Grounded Citations (Đối chiếu chuẩn y khoa)**:
  * Mọi thông tin phản hồi đều đính kèm nguồn trích dẫn đối soát chính thống (*Cục Quản lý Khám chữa bệnh - kcb.vn*, *MedlinePlus*).
* 🧪 **Multimodal Lab Scanner (Phân tích sinh hóa máu)**:
  * Bóc tách và so sánh các chỉ số sinh hóa máu quan trọng (*Glucose đói, Cholesterol toàn phần, Men gan SGOT/AST, Creatinine thận*) với dải tham chiếu chuẩn.
  * Cảnh báo nguy cơ bất thường (tiền tiểu đường, rối loạn lipid máu, suy giảm chức năng gan/thận).
* 📋 **Pre-Consultation Summary (Bản tóm tắt bệnh án cho Bác sĩ)**:
  * Kết xuất bệnh sử hiện tại (*HPI - History of Present Illness*), danh sách dị ứng, chẩn đoán phân biệt sơ bộ (*Differential Diagnosis*) kèm độ tin cậy và đề xuất cận lâm sàng (*Suggested Lab Orders*).

---

## 🏗️ 3. Kiến trúc Hệ thống (System Architecture)

```text
[ Người Bệnh / Web UI (Single Page Application) ]
                         │
                         ├──► [ POST /api/chat ]
                         │            │
                         │            ▼
                         │   [ assess_emergency_risk ]
                         │            │
                         │    ┌───────┴───────┐
                         │    ▼               ▼
                         │ [CỜ ĐỎ CẤP CỨU]  [TRIỆU CHỨNG THƯỜNG]
                         │    │               │
                         │    ▼               ▼
                         │ [Bypass 115]   [analyze_symptoms]
                         │                    │
                         │                    ├── Tính Risk Score (0 - 100)
                         │                    ├── Định tuyến Chuyên khoa
                         │                    ├── Khuyến nghị OTC & Cảnh báo
                         │                    └── Trích xuất Grounded Sources
                         │
                         ├──► [ POST /api/upload-lab ] ──► Bóc tách chỉ số xét nghiệm & Amazon S3
                         │
                         └──► [ GET /api/clinical-summary ] ──► Xuất tóm tắt bệnh sử cho Bác sĩ
```

---

## 📂 4. Cấu trúc Thư mục Dự án (Project Structure)

```text
Medical ChatBOT/
├── app.py                      # Flask Application Server & Định tuyến 4 APIs
├── requirements.txt            # Danh sách dependencies (Flask, Boto3, Pydantic, Requests)
├── .env.example                # Cấu hình môi trường (Port, API Keys, AWS S3)
├── README.md                   # Tài liệu kỹ thuật dự án
│
├── core/                       # Lõi Xử lý Nghiệp vụ Lâm sàng
│   ├── __init__.py
│   ├── prompts.py              # Medical Safety Prompts & Guardrails Tiếng Việt
│   └── triage.py               # Thuật toán Triage, Red Flags, Risk Scoring & Routing
│
├── templates/
│   └── index.html              # Giao diện Web lâm sàng thời gian thực (SPA)
│
└── static/
    ├── css/                    # Giao diện y khoa hiện đại, responsive
    └── js/                     # Xử lý tương tác AJAX, render markdown, upload file
```

---

## 🔌 5. Đặc tả API Endpoints (API Specification)

| Phương thức | Endpoint | Chức năng | Dữ liệu đầu vào | Dữ liệu đầu ra |
|:---:|:---|:---|:---|:---|
| `GET` | `/` | Tải giao diện Web SPA | Không | HTML/CSS/JS Application |
| `POST` | `/api/chat` | Phân tích triệu chứng & Phân tầng Triage | `{"message": "string", "history": []}` | `answer`, `risk_level`, `risk_score`, `specialist`, `medications`, `sources` |
| `POST` | `/api/upload-lab` | Tiếp nhận và phân tích phiếu xét nghiệm máu | `multipart/form-data` (file ảnh) | `extracted_metrics`, `ai_summary`, `s3_url` |
| `GET` | `/api/clinical-summary` | Kết xuất tóm tắt bệnh án sơ bộ cho bác sĩ | Không | `chief_complaint`, `hpi`, `differential_diagnosis`, `suggested_orders`, `contraindications` |

---

## 🚀 6. Hướng dẫn Cài đặt & Vận hành (Local Setup)

### Yêu cầu tiên quyết
* **Python**: Phiên bản 3.10 trở lên.
* **Git**: Đã cài đặt trên máy.

### Bước 1: Clone kho mã nguồn
```bash
git clone https://github.com/khiemdong2005/chatbot_medical.git
cd chatbot_medical
```

### Bước 2: Tạo môi trường ảo và cài đặt thư viện
```bash
# Khởi tạo môi trường ảo Python
python -m venv venv

# Kích hoạt môi trường (Windows PowerShell / CMD)
.\venv\Scripts\activate
# Hoặc trên Linux/macOS:
# source venv/bin/activate

# Cài đặt toàn bộ dependencies
pip install -r requirements.txt
```

### Bước 3: Cấu hình biến môi trường
Tạo file `.env` từ file mẫu:
```bash
cp .env.example .env
```
*(Tùy chỉnh các tham số cấu hình `PORT`, `AWS_ACCESS_KEY_ID`, `S3_BUCKET_NAME` nếu cần).*

### Bước 4: Khởi chạy Server
```bash
python app.py
```
Mở trình duyệt web và truy cập: **`http://localhost:8000`** hoặc **`http://127.0.0.1:8000`**.

---

## ☁️ 7. Triển khai Đám mây AWS (AWS Cloud Deployment)

Hệ thống sẵn sàng tích hợp 3 dịch vụ điện toán đám mây cốt lõi của AWS:
1. **Amazon S3**: Lưu trữ an toàn, phân quyền bảo mật cho ảnh chụp phiếu kết quả xét nghiệm và hồ sơ bệnh nhân.
2. **Amazon ECR (Elastic Container Registry)**: Đóng gói ứng dụng thành Docker Container siêu nhẹ:
   ```dockerfile
   FROM python:3.12-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   EXPOSE 8000
   CMD ["python", "app.py"]
   ```
3. **AWS App Runner**: Kết nối trực tiếp với ECR Image, tự động cấp phát chứng chỉ HTTPS/SSL, cấu hình Auto-scaling dựa theo tải truy cập người bệnh thực tế.

---

## ⚖️ 8. Tuyên bố Miễn trừ Trách nhiệm Y tế (Medical Disclaimer)

> **CẢNH BÁO QUAN TRỌNG:**  
> MediMind AI là hệ thống hỗ trợ tham khảo và sàng lọc thông tin y tế ban đầu, **hoàn toàn không thay thế** cho việc chẩn đoán, thăm khám, kê đơn hoặc điều trị trực tiếp từ các bác sĩ chuyên khoa hoặc nhân viên y tế có chứng chỉ hành nghề.  
> Trong trường hợp xuất hiện các triệu chứng nguy kịch đe dọa tính mạng, người bệnh hoặc người nhà cần gọi ngay **Cấp cứu 115** hoặc di chuyển khẩn cấp tới cơ sở y tế gần nhất.
