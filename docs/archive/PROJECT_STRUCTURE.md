# 🏥 MEDIMIND CLINICAL AI — KIẾN TRÚC & CẤU TRÚC THƯ MỤC DỰ ÁN

Tài liệu này hướng dẫn chi tiết cách tổ chức mã nguồn, phân chia module, quy trình làm việc nhóm (Git) và cách deploy lên AWS hoặc Docker VPS thuận tiện nhất.

---

## 📂 Sơ Đồ Cấu Trúc Thư Mục (Directory Tree)

```text
Medical ChatBOT\
│
├── 🌐 GIAO DIỆN & TẦNG FRONTEND
│   ├── templates\                   # Mã nguồn Giao diện HTML (Jinja2 Templates)
│   │   └── index.html               # Web Portal chính (Chatbot, Dashboard, Quản lý tài liệu)
│   └── static\                      # Tài nguyên tĩnh phục vụ trình duyệt
│       ├── css\                     # Stylesheets (Giao diện y tế, dark/light mode, mobile responsive)
│       ├── js\                      # Logic tương tác phía Client (Fetch API, JWT Bearer, DOM rendering)
│       │   └── app.js               # Controller JavaScript chính của Web Portal
│       └── images\                  # Logo, Icon và Atlas minh họa lâm sàng
│
├── ⚙️ TẦNG LOGIC & DỊCH VỤ CỐT LÕI (BACKEND CORE)
│   ├── app.py                       # ⭐ Điểm khởi chạy chính của hệ thống Flask Server & API Routing
│   └── core\                        # Các module dịch vụ độc lập (Clean Architecture)
│       ├── models.py                # Mô hình dữ liệu ORM (SQLAlchemy), Băm mật khẩu scrypt
│       ├── jwt_auth.py              # Xác thực Stateless JWT (Access/Refresh Token, Decorator @jwt_required)
│       ├── security_patch.py        # Tầng phòng thủ OWASP: Magic Bytes check, OTP Lockout, XSS Sanitize
│       ├── gemini_service.py        # Tích hợp Google Gemini Flash API cho suy luận y khoa
│       ├── rag_service.py           # Grounded RAG tra cứu tri thức y khoa từ ChromaDB
│       ├── cache_service.py         # Bộ nhớ đệm Redis & RAM Fallback, Rate Limiting
│       ├── email_service.py         # Gửi email mã OTP xác thực quên mật khẩu (SMTP / SES)
│       ├── observability.py         # Giám sát Prometheus (/metrics) & Cảnh báo Telegram tự động
│       ├── triage.py                # Phân luồng khẩn cấp và cảnh báo dấu hiệu nguy hiểm (Red Flags)
│       └── prompts.py               # System Prompts lâm sàng chuẩn y khoa
│
├── 🚀 TẦNG TRIỂN KHAI & DEVOPS (DEPLOYMENT)
│   ├── Dockerfile                   # Multi-stage Dockerfile tối ưu hóa kích thước & Gunicorn WSGI
│   ├── docker-compose.yml           # Orchestration 4 dịch vụ: Web + Nginx + PostgreSQL + Redis
│   ├── .dockerignore                # Loại bỏ file thừa giúp build Docker siêu tốc & bảo mật
│   └── deploy\                      # Kịch bản tự động hóa máy chủ
│       ├── nginx.conf               # Cấu hình Nginx Reverse Proxy, SSL, Gzip, Security Headers
│       ├── ec2_setup.sh             # Kịch bản 1-click cài đặt toàn bộ môi trường trên AWS Ubuntu
│       └── update.sh                # Kịch bản 15 giây tự động kéo code mới và cập nhật Docker
│
├── 🛠️ CÔNG CỤ & KỊCH BẢN PHỤ TRỢ (SCRIPTS)
│   └── scripts\
│       ├── view_db.py               # Tra cứu nhanh hồ sơ tài khoản trong CSDL từ Terminal
│       ├── ingest.py                # Kịch bản Chunking & nạp dữ liệu y học vào ChromaDB
│       ├── setup_clinical_atlas.py  # Khởi tạo dữ liệu hình ảnh atlas giải phẫu
│       └── fetch_atlas_images.py    # Tải dataset hình ảnh y khoa
│
├── 📦 DỮ LIỆU & STORAGE NỘI BỘ
│   ├── data\                        # Dataset tài liệu y khoa chuẩn hóa (MedlinePlus, Sách Y học)
│   ├── instance\                    # Thư mục chứa SQLite CSDL nội bộ (medimind.db)
│   ├── uploads\                     # Thư mục lưu file tạm khi người dùng tải ảnh xét nghiệm
│   └── medical_vectordb\            # Kho lưu trữ Vector Embeddings của ChromaDB
│
└── 📋 FILE CẤU HÌNH GỐC
    ├── .env.example                 # Mẫu khai báo biến môi trường chuẩn sản xuất
    ├── .gitignore                   # Loại trừ file nhạy cảm và cache khỏi Git
    ├── requirements.txt             # Danh sách thư viện Python
    └── README.md                    # Hướng dẫn tổng quan
```

---

## 👥 Hướng Dẫn Phân Chia Công Việc Trong Nhóm (Collaboration Workflow)

Để anh Tú và bạn cùng phát triển mượt mà mà không bao giờ bị xung đột mã nguồn (Git Conflict):

| Thành viên | Khu vực phụ trách chính | Thư mục chỉnh sửa |
| :--- | :--- | :--- |
| **Thành viên A (Frontend & Giao diện)** | • Thiết kế giao diện, nút bấm, bảng biểu<br>• Xử lý hiệu ứng, CSS responsive<br>• Gọi API qua Fetch/Axios | `templates/`<br>`static/css/`<br>`static/js/` |
| **Thành viên B (Backend & AI Logic)** | • Viết API mới, xử lý dữ liệu DB<br>• Tinh chỉnh prompt AI Gemini, RAG<br>• Bảo mật, JWT, Email OTP | `app.py`<br>`core/` |

---

## ⚡ Quy Trình Deploy & Cập Nhật Lên AWS (Chỉ 2 Bước)

### Bước 1: Thiết lập lần đầu trên máy chủ AWS EC2
Khi vừa tạo máy ảo Ubuntu 24.04 trên AWS:
```bash
git clone <URL_REPO_CỦA_ANH> && cd "Medical ChatBOT"
chmod +x deploy/ec2_setup.sh deploy/update.sh
./deploy/ec2_setup.sh
```

### Bước 2: Mỗi lần có code mới (Cập nhật trong 15 giây)
Mỗi khi anh hoặc bạn push code mới lên GitHub, trên AWS anh chỉ cần gõ đúng 1 lệnh:
```bash
./deploy/update.sh
```
Hệ thống sẽ tự động kéo code, build lại container và cập nhật phiên bản mới mà không làm gián đoạn hay mất dữ liệu CSDL!
