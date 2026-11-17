# BÁO CÁO ĐỀ XUẤT GIẢI PHÁP VÀ THIẾT KẾ KIẾN TRÚC WORKSHOP (PROPOSAL)
## DỰ ÁN: NỀN TẢNG TRỢ LÝ Y TẾ LÂM SÀNG & ĐỐI SOÁT ĐƠN THUỐC THÔNG MINH (MEDIMIND CLINICAL AI)
**Học phần:** Thực tập Tốt nghiệp / Workshop Chuyên môn  
**Hệ thống điện toán đám mây mục tiêu:** Amazon Web Services (AWS)  
**Tiêu chuẩn kiến trúc:** AWS Well-Architected Framework & Chuẩn An toàn Y tế (HIPAA / MedlinePlus)

---

## MỤC LỤC CHI TIẾT
1. [2.3.1. Tổng quan Bài toán và Giải pháp (Executive Summary)](#231-tổng-quan-bài-toán-và-giải-pháp)
2. [2.3.2. Mục tiêu & Phạm vi Dự án (Objectives & Scope)](#232-mục-tiêu--phạm-vi-dự-án)
3. [2.3.3. Vấn đề Thực tiễn Cần Giải quyết (Problem Statement)](#233-vấn-đề-thực-tiễn-cần-giải-quyết)
4. [2.3.4. Thiết kế Kiến trúc Hệ thống Chuẩn AWS (System Architecture)](#234-thiết-kế-kiến-trúc-hệ-thống-chuẩn-aws)
   - 4.1. Sơ đồ Luồng Kiến trúc Tổng thể (High-Level Architecture)
   - 4.2. Danh mục Dịch vụ AWS Chính thức Sử dụng
   - 4.3. Phân tích Chi tiết 5 Trụ cột AWS Well-Architected Framework
   - 4.4. Hướng dẫn Vẽ & Trình bày Diagram chuẩn AWS Icon
5. [2.3.5. Kế hoạch & Timeline Thực hiện Dự án (Implementation Roadmap)](#235-kế-hoạch--timeline-thực-hiện-dự-án)
6. [2.3.6. Bảng Dự toán Ngân sách & Tối ưu Chi phí (Cost Estimation & Optimization)](#236-bảng-dự-toán-ngân-sách--tối-ưu-chi-phí)
   - 6.1. Chi tiết Bảng giá AWS Pricing Calculator (Singapore ap-southeast-1)
   - 6.2. Kịch bản Giai đoạn Thử nghiệm (Development / PoC)
   - 6.3. Kịch bản Vận hành Thực tế (Production 10.000 người dùng/tháng)
   - 6.4. Chiến lược Tối ưu hóa Chi phí AWS (Cost Optimization Techniques)
7. [2.3.7. Quản trị Rủi ro & Phương án Giảm thiểu (Risk Management)](#237-quản-trị-rủi-ro--phương-án-giảm-thiểu)
8. [2.3.8. Kịch bản Kiểm chứng Sản phẩm Chạy Thực tế (Live Demo Verification)](#238-kịch-bản-kiểm-chứng-sản-phẩm-chạy-thực-tế)

---

<a name="231-tổng-quan-bài-toán-và-giải-pháp"></a>
### 2.3.1. Tổng quan Bài toán và Giải pháp (Executive Summary)

Trong bối cảnh hệ thống y tế công cộng tuyến đầu tại Việt Nam thường xuyên chịu áp lực quá tải từ 150% – 200% công suất tiếp nhận, việc bệnh nhân tự ý mua thuốc điều trị hoặc không tuân thủ chỉ dẫn đơn thuốc viết tay đang là nguyên nhân trực tiếp dẫn đến các biến cố y khoa nghiêm trọng như sốc phản vệ, kháng kháng sinh (AMR), loét dạ dày xuất huyết và suy gan/thận do tương tác thuốc.

**MediMind Clinical AI** là giải pháp nền tảng y tế số ứng dụng trí tuệ nhân tạo đa phương thức (Multimodal Generative AI) kết hợp cơ chế truy xuất dữ liệu tăng cường (**RAG - Retrieval-Augmented Generation**) và thuật toán phân loại lâm sàng (**Clinical Triage Algorithm**). Hệ thống được đóng gói container hóa hiện đại, triển khai trên hạ tầng điện toán đám mây **Amazon Web Services (AWS)** tuân thủ nghiêm ngặt **AWS Well-Architected Framework** và các tiêu chuẩn bảo mật y tế **HIPAA**.

Nền tảng cung cấp bộ 4 trụ cột nghiệp vụ cốt lõi:
1. **Sàng lọc triệu chứng thông minh & Phát hiện cờ đỏ cấp cứu (Emergency Red Flag Bypass)**: Phân tầng người bệnh theo 3 thang nguy cơ (Xanh - Vàng - Đỏ), tự động kích hoạt cảnh báo gọi Cấp cứu 115 khi phát hiện dấu hiệu nguy kịch đe dọa tính mạng.
2. **Bóc tách thị giác & Số hóa đơn thuốc / Phiếu xét nghiệm (Multimodal OCR & Vision)**: Chuyển đổi ảnh chụp đơn thuốc viết tay và phiếu sinh hóa máu thành lộ trình uống thuốc trực quan theo thời gian thực (Sáng - Trưa - Chiều - Tối; Trước/Sau ăn).
3. **Tra cứu & Đối soát Dược thư Chuẩn y khoa (Grounded Medical RAG)**: Liên kết trực tiếp kho tri thức lâm sàng chính thống (Dược thư Quốc gia Việt Nam, MedlinePlus, Cục Quản lý Khám chữa bệnh - kcb.vn) với cơ chế trích dẫn có căn cứ (Grounded Citations), tuyệt đối không bịa đặt thông tin.
4. **Hồ sơ Tóm tắt Tiền khám Bệnh án Điện tử (Pre-Consultation EMR Summary)**: Tự động tổng hợp lý do vào viện, bệnh sử hiện tại (HPI), tiền sử dị ứng và đề xuất cận lâm sàng giúp bác sĩ nắm bắt tình trạng ca bệnh chỉ trong **30 giây**.

---

<a name="232-mục-tiêu--phạm-vi-dự-án"></a>
### 2.3.2. Mục tiêu & Phạm vi Dự án (Objectives & Scope)

#### A. Mục tiêu Dự án (SMART Objectives)
* **Tính Chính xác & An toàn Lâm sàng (Clinical Safety)**: Đạt độ nhạy 100% trong việc nhận diện 10 nhóm triệu chứng cờ đỏ cấp cứu đe dọa tính mạng; tuân thủ 100% rào chắn an toàn (không tự ý chẩn đoán áp đặt, không kê đơn kháng sinh bừa bãi).
* **Hiệu năng & Tốc độ Phản hồi (Performance)**: Thời gian phản hồi phân tầng triệu chứng qua Chatbot < 2.5 giây; thời gian bóc tách và phân tích đơn thuốc qua OCR < 4.0 giây.
* **Độ sẵn sàng Hệ thống (High Availability)**: Thiết kế đạt mức Uptime $\ge 99.9\%$ trên hạ tầng đám mây AWS với cơ chế Multi-AZ và Auto-scaling tự động co giãn theo lưu lượng.
* **Bảo mật Dữ liệu Y tế (Security Compliance)**: Mã hóa 100% dữ liệu nhạy cảm của người bệnh cả khi lưu trữ (At-Rest qua AWS KMS), khi truyền (In-Transit qua TLS 1.3), và áp dụng cơ chế Ẩn danh Dữ liệu (Data Anonymization) trước khi gọi LLM.
* **Tối ưu Chi phí Vận hành (Cost Efficiency)**: Tối ưu ngân sách giai đoạn thử nghiệm/workshop trong hạn mức Free Tier ($\approx \$0 - \$25/\text{tháng}$) và mô hình Production không vượt quá $\$0.005$ trên mỗi lượt phiên khám bệnh.

#### B. Phạm vi Dự án (Project Scope)
* **Trong phạm vi (In-Scope)**:
  - Xây dựng Web Single Page Application (SPA) chuẩn Spatial Glassmorphism (VisionOS UI) hỗ trợ người dân và bác sĩ.
  - Xây dựng Backend Microservices bằng Python (Flask/FastAPI) xử lý nghiệp vụ Triage, RAG, OCR và Quản lý Bệnh án.
  - Sử dụng **Amazon OpenSearch Serverless** làm Vector Database lưu trữ các vector embeddings tài liệu y khoa.
  - Thiết kế và triển khai kiến trúc Serverless/Container nội bộ AWS: Amazon S3, **Amazon ECS Fargate**, Application Load Balancer, Amazon ECR, AWS WAF, **Amazon Bedrock**.
  - Xây dựng bộ kịch bản kiểm thử lâm sàng (4 ca bệnh mẫu thực nghiệm: Đau thần kinh tọa, Viêm dạ dày cấp, Viêm amidan cấp, Phiếu sinh hóa máu).
* **Ngoài phạm vi (Out-of-Scope)**:
  - Hệ thống không thực hiện chức năng ký số văn bản pháp lý thay thế con dấu của bệnh viện.
  - Không thay thế bác sĩ thực hiện phẫu thuật hoặc can thiệp y khoa xâm lấn.

---

<a name="233-vấn-đề-thực-tiễn-cần-giải-quyết"></a>
### 2.3.3. Vấn đề Thực tiễn Cần Giải quyết (Problem Statement)

Dự án tập trung giải quyết 4 điểm nghẽn (Pain Points) nhức nhối trong chu trình khám chữa bệnh hiện nay:

| STT | Điểm nghẽn Thực tiễn | Thực trạng Hiện nay | Giải pháp Đột phá của MediMind AI |
|:---:|:---|:---|:---|
| **1** | **Quá tải tiếp đón & Phân loại sai tuyến** | Người bệnh đổ dồn về bệnh viện tuyến trung ương ngay cả với các bệnh lý thông thường, gây ùn tắc phòng cấp cứu và lãng phí thời gian chờ đợi trung bình từ 2 – 4 tiếng. | Thuật toán **Clinical Triage** phân tầng nguy cơ 3 cấp độ, tự động định tuyến đúng chuyên khoa và cơ sở y tế phù hợp theo vị trí GPS thực tế. |
| **2** | **Nguy cơ bỏ sót "Giờ Vàng" Cấp cứu** | Người bệnh không nhận thức được mức độ nguy kịch của các dấu hiệu sớm (đột quỵ, thiếu máu cơ tim, sốc nhiễm trùng), tự điều trị tại nhà làm mất cơ hội can thiệp kịp thời. | Cơ chế **Emergency Red Flag Bypass** quét nhận diện các từ khóa và ngữ cảnh nguy kịch, lập tức kích hoạt chỉ dẫn gọi 115 và sơ cứu trong 1 giây. |
| **3** | **Đơn thuốc viết tay khó đọc & Sai sót dùng thuốc** | Đơn thuốc viết tay bác sĩ khó luận chữ, bệnh nhân quên giờ uống, uống nhầm thuốc trước/sau ăn hoặc phối hợp các thuốc tương tác đối kháng gây loét dạ dày/ngộ độc. | **Multimodal OCR & Vision Service** bóc tách tên thuốc, chuyển thành thời khóa biểu thông minh kèm hướng dẫn kiêng khem và hệ thống nhắc cữ thuốc tự động. |
| **4** | **Ảo giác Thông tin Y tế từ AI trôi nổi** | Người dân tra cứu triệu chứng trên mạng hoặc AI thông thường nhận về các kết luận sai lệch, bịa đặt (hallucination) gây hoang mang hoặc điều trị sai phác đồ. | **Grounded RAG Pipeline** giới hạn phạm vi sinh ngôn ngữ trong kho tri thức y khoa đã thẩm định, đối soát chéo và cung cấp nguồn trích dẫn rõ ràng. |

---

<a name="234-thiết-kế-kiến-trúc-hệ-thống-chuẩn-aws"></a>
### 2.3.4. Thiết kế Kiến trúc Hệ thống Chuẩn AWS (System Architecture)

> [!IMPORTANT]
> **Tuân thủ Tuyệt đối Quy chuẩn AWS**: Toàn bộ kiến trúc dưới đây sử dụng 100% định danh dịch vụ chính thức từ hệ sinh thái Amazon Web Services, bảo đảm dữ liệu y tế không bao giờ rời khỏi hạ tầng mạng của AWS (AWS Network Backbone), tuân thủ triệt để nguyên tắc Zero Trust và tiêu chuẩn HIPAA.

#### 4.1. Sơ đồ Luồng Kiến trúc Tổng thể (High-Level AWS Architecture)

![Sơ đồ Kiến trúc AWS Chuẩn MediMind AI](c:\Users\vule0\FPT\WORKSHOP_PROPOSAL.png)

#### 4.2. Danh mục Dịch vụ AWS Chính thức Sử dụng

1. **Amazon Route 53 & AWS WAF & Amazon CloudFront**: Bộ ba dịch vụ biên (Edge) tiếp nhận lưu lượng, bảo vệ chống DDoS (Layer 7), chặn SQL Injection và phân phối nội dung tĩnh (CDN) với độ trễ siêu thấp.
2. **Application Load Balancer (ALB)**: Tiếp nhận lưu lượng HTTPS, xác thực chứng chỉ số (ACM) và cân bằng tải an toàn vào Private Subnet.
3. **Amazon ECS on AWS Fargate**: Môi trường thực thi container ứng dụng hoàn toàn Serverless. Hoạt động độc lập trong Private Subnet, tự động co giãn theo lưu lượng bệnh nhân và loại bỏ gánh nặng quản lý máy chủ.
4. **Amazon Bedrock (Claude 3.5 Sonnet)**: Trái tim AI của hệ thống. Đóng vai trò phân tích hình ảnh đa phương thức (Vision) cho OCR đơn thuốc và suy luận LLM cho RAG. Việc sử dụng Bedrock giúp toàn bộ dữ liệu y tế được xử lý nội bộ trong AWS, không vi phạm chính sách bảo mật như khi gọi API ra ngoài Internet.
5. **Amazon OpenSearch Serverless**: Hoạt động như một Vector Database Serverless hiệu năng cao, lưu trữ các embeddings của 414+ tài liệu MedlinePlus phục vụ cho cơ chế tra cứu RAG (Retrieval-Augmented Generation).
6. **Amazon S3, AWS KMS, AWS Secrets Manager, CloudWatch & ECR**: Quản lý lưu trữ bảo mật (S3 mã hóa KMS), biến môi trường (Secrets Manager), giám sát hệ thống (CloudWatch) và phân phối mã nguồn (ECR).

#### 4.3. Phân tích Chi tiết 5 Trụ cột AWS Well-Architected Framework

##### Trụ cột 1: Bảo mật (Security) — Trọng tâm Đánh giá Nghiêm ngặt Nhất
* **Tuân thủ HIPAA & Bảo mật Dữ liệu Y tế**:
  - **Mã hóa Toàn diện**: Mã hóa At-Rest qua AWS KMS (SSE-KMS) cho S3 và OpenSearch; mã hóa In-Transit qua giao thức TLS 1.3.
  - **Cơ chế Ẩn danh (Data Anonymization)**: Container Backend tự động quét và che giấu các thông tin định danh cá nhân (PII) như Tên, Số điện thoại bệnh nhân trước khi đưa dữ liệu vào Amazon Bedrock suy luận.
  - **Mạng Cô lập (Network Isolation)**: Gọi API tới S3, OpenSearch và Bedrock hoàn toàn thông qua **AWS PrivateLink / VPC Endpoints**, đảm bảo luồng dữ liệu không bao giờ truyền qua public internet.

##### Trụ cột 2: Độ tin cậy (Reliability)
* Triển khai ứng dụng trên kiến trúc đa vùng khả dụng (**Multi-AZ Deployment**) trong Region `ap-southeast-1` (Singapore), đảm bảo hệ thống duy trì hoạt động ngay cả khi một Data Center của AWS gặp sự cố.
* Cơ chế tự phục hồi (Self-Healing): Container Fargate gặp sự cố sẽ tự động bị tiêu hủy và thay thế bằng task mới thông qua Health Checks của ALB.

##### Trụ cột 3: Hiệu năng Vận hành (Performance Efficiency)
* Giảm tải máy chủ Backend bằng cách đẩy toàn bộ tài nguyên tĩnh lên bộ đệm Amazon CloudFront.
* Tối ưu hóa tải container: Sử dụng Docker Base Image siêu nhẹ `python:3.12-slim` kết hợp Multi-stage Build, tăng tốc độ khởi động (Cold Start) của Fargate task.

##### Trụ cột 4: Tối ưu Chi phí (Cost Optimization)
* Áp dụng nguyên lý "Pay-as-you-go" của ECS Fargate và Bedrock (tính phí theo token thực dùng, không tốn phí duy trì GPU).
* Cấu hình **Amazon S3 Lifecycle Rule**: Tự động chuyển các ảnh chụp đơn thuốc sau 30 ngày sang **S3 Standard-Infrequent Access (S3 Standard-IA)**, và sau 90 ngày sang **S3 Glacier Instant Retrieval** để giảm chi phí lưu trữ nhưng vẫn đảm bảo truy xuất tính bằng mili-giây khi có ca cấp cứu khẩn cấp.

##### Trụ cột 5: Vận hành Xuất sắc (Operational Excellence)
* Quản lý hạ tầng bằng mã (**Infrastructure as Code**) qua AWS CloudFormation.
* Giám sát thời gian thực: Cấu hình Amazon CloudWatch theo dõi chỉ số P95/P99 Latency và tự động gửi cảnh báo (Alarms) qua Amazon SNS khi phát sinh lỗi.

---

<a name="235-kế-hoạch--timeline-thực-hiện-dự-án"></a>
### 2.3.5. Kế hoạch & Timeline Thực hiện Dự án (Implementation Roadmap)

Dự án được phân bổ thực hiện theo mô hình Agile/Scrum qua 5 giai đoạn trọng tâm. Dưới đây là bảng tiến độ thực hiện:

| Giai đoạn | Hạng mục Công việc Trọng tâm | Thời gian dự kiến | Trạng thái |
| :--- | :--- | :--- | :---: |
| **1. Khảo sát & Thiết kế** | • Khảo sát bài toán & Thu thập phác đồ y tế<br>• Thiết kế Kiến trúc AWS Well-Architected & API Spec | 01/09 – 14/09/2026 | ✅ Hoàn thành |
| **2. Phát triển Cốt lõi** | • Xây dựng Triage & RAG Engine (OpenSearch)<br>• Phát triển Multimodal OCR & Phân tích Đơn thuốc | 15/09 – 12/10/2026 | ✅ Hoàn thành |
| **3. Frontend & Tích hợp** | • Xây dựng UI Spatial Glassmorphism (VisionOS)<br>• Tích hợp End-to-End Chatbot & EMR Export | 13/10 – 29/10/2026 | ✅ Hoàn thành |
| **4. Đóng gói & Triển khai AWS** | • Container hóa Docker & Thiết lập Amazon ECR<br>• Cấu hình ECS Fargate, S3 SSE-KMS, ALB & Bedrock | 30/10 – 10/11/2026 | ✅ Hoàn thành |
| **5. Kiểm thử & Workshop** | • Kiểm thử Tải (Load Testing) & Rà soát Bảo mật<br>• Hoàn thiện Báo cáo, Video Minh chứng & Workshop | 11/11 – 23/11/2026 | 🚀 Đang thực hiện |

---

<a name="236-bảng-dự-toán-ngân-sách--tối-ưu-chi-phí"></a>
### 2.3.6. Bảng Dự toán Ngân sách & Tối ưu Chi phí (Cost Estimation & Optimization)

> [!CAUTION]
> **Quy định Điểm Liệt Mục Trình Bày**: Báo cáo bắt buộc phải có đầy đủ số liệu tính toán chi phí minh bạch từ công cụ **AWS Pricing Calculator**, thể hiện rõ kịch bản thử nghiệm (Free Tier/Dev) và kịch bản mở rộng (Production Scale) có bao gồm các dịch vụ Network như ALB và NAT.

#### 6.1. Chi tiết Bảng giá AWS Pricing Calculator (Khu vực: Singapore - ap-southeast-1)

#### 6.2. Kịch bản Giai đoạn Thử nghiệm & Chấm thi Workshop (Dev / PoC Environment)
*Chiến lược: Để tiết kiệm chi phí, môi trường Dev sẽ chạy ECS Fargate trong Public Subnet (không dùng NAT Gateway) và kết nối trực tiếp không qua ALB, gọi API AWS qua VPC Endpoints miễn phí.*

| Dịch vụ AWS (Service) | Cấu hình & Mức sử dụng Dự tính | Chi phí Tháng (USD) | Ghi chú Tối ưu Hạn mức Dev |
|:---|:---|:---:|:---|
| **Amazon ECS (Fargate)** | 1 Task (1 vCPU, 2 GB RAM) - Chạy ngắt quãng phục vụ Test (~100 giờ/tháng) | **\$5.80** | Đặt trong Public Subnet để tiết kiệm phí NAT Gateway. Tắt task khi không chấm điểm. |
| **Amazon Bedrock** | Claude 3.5 Sonnet (~200.000 input tokens, 50.000 output tokens) | **\$1.35** | Tính phí theo token thực dùng (Pay-as-you-go). Rất tiết kiệm. |
| **Amazon OpenSearch** | Serverless Vector Search (Chạy rải rác test RAG) | **\$8.00** | Cấu hình OCU tối thiểu, tự tắt khi rảnh rỗi. |
| **Amazon S3 & KMS** | Lưu 500 ảnh, KMS ~2.000 requests | **\$1.06** | Miễn phí S3 5GB đầu. Tính phí mã hóa KMS. |
| **AWS Secrets Manager**| 2 Secrets (`JWT_SECRET`, v.v.) | **\$0.80** | Bảo vệ cấu hình nhạy cảm. |
| **Amazon CloudFront** | 10 GB Data Transfer Out | **\$0.00** | Miễn phí trong hạn mức 1TB Always-Free. |
| **AWS WAF & CloudWatch**| WAF (Bật lúc test), CloudWatch cơ bản | **\$6.80** | Miễn phí 5GB Logs. Tốn phí rule WAF cơ bản. |
| **TỔNG CỘNG (DEV/POC)**| *Môi trường thử nghiệm & đánh giá chấm thi* | **\$23.81 / tháng** | **Kiểm soát chặt chẽ trong mức sinh viên.** |

#### 6.3. Kịch bản Vận hành Mở rộng Thực tế (Production Environment: 10.000 Người Dùng/Tháng)
*Quy mô giả định: Hạ tầng bảo mật chuẩn VPC (có ALB, NAT Gateway), 10.000 người bệnh/tháng, 25.000 phiên hội chẩn, 8.000 ảnh bóc tách, hoạt động 24/7.*

| Hạng mục Dịch vụ | Tài nguyên Dự toán | Chi phí Ước tính / Tháng |
|:---|:---|:---:|
| **Compute & Network (ECS, ALB, NAT)** | 2 Fargate Tasks liên tục, 1 ALB, 1 NAT Gateway xử lý outbound | **\$98.50** |
| **AI & Search (Bedrock, OpenSearch)** | Claude 3.5 Sonnet (3M Tokens), OpenSearch Serverless (0.5 OCU) | **\$45.00** |
| **Storage (S3 Standard & Glacier Instant)**| 35 GB ảnh đơn thuốc mới + Lifecycle lưu trữ dài hạn | **\$1.50** |
| **Security (WAF, KMS)** | 1 Web ACL, 5 Rules OWASP, KMS requests | **\$11.30** |
| **Management (Secrets, CloudWatch)** | 3 Secrets, 15 GB Logs, Dashboards | **\$7.50** |
| **Data Transfer & CDN** | 150 GB DTO (CloudFront Cache 80%) | **\$5.20** |
| **TỔNG CHI PHÍ PRODUCTION** | **Phục vụ 10.000 người bệnh / 25.000 lượt hội chẩn** | **\$169.00 / tháng** |

> [!TIP]
> **Chỉ số Hiệu quả Chi phí (Unit Economics)**:
> Mặc dù chi phí tổng tăng để đảm bảo an ninh mạng doanh nghiệp, chi phí trên mỗi phiên khám vẫn cực kỳ tối ưu:
> $\text{Chi phí trên mỗi phiên khám} = \frac{\$169.00}{25.000\text{ lượt}} \approx \mathbf{\$0.0067\text{ USD}}\ (\approx \mathbf{167\text{ VNĐ}}/\text{lượt})$.

#### 6.4. Chiến lược Tối ưu hóa Chi phí (Cost Optimization Techniques)
1. **Kiến trúc Dev linh hoạt**: Ở môi trường Test, bỏ qua ALB và NAT Gateway (đặt container trực tiếp ở Public Subnet có Security Group chặt chẽ) để cắt giảm \$50 chi phí mạng cố định.
2. **S3 Lifecycle Transitions**: Chuyển ảnh đơn thuốc sang `S3 Glacier Instant Retrieval` sau 90 ngày. Đảm bảo giảm 60% chi phí lưu trữ mà bác sĩ vẫn có thể truy xuất hồ sơ bệnh án cũ trong vài mili-giây lúc cấp cứu (thay vì phải đợi 1-5 tiếng như Glacier Flexible thông thường).
3. **AWS Budgets**: Thiết lập giới hạn ngân sách tự động cảnh báo qua email khi chi phí Dev chạm ngưỡng \$20.

---

<a name="237-quản-trị-rủi-ro--phương-án-giảm-thiểu"></a>
### 2.3.7. Quản trị Rủi ro & Phương án Giảm thiểu (Risk Management)

| Nhóm Rủi ro | Nguy cơ Cụ thể | Mức độ | Phương án Kiểm soát & Giảm thiểu của Dự án |
|:---|:---|:---:|:---|
| **Rủi ro Pháp lý & Y khoa** | Người bệnh coi câu trả lời của AI là phán quyết cuối cùng dẫn đến việc chậm trễ đi khám. | **Cao** | • Hiển thị cảnh báo **Medical Disclaimer** bắt buộc.<br>• AI chỉ đóng vai trò phân loại, tuyệt đối không chẩn đoán. |
| **Rủi ro Rò rỉ Dữ liệu (Privacy Leak)** | Lộ lọt hình ảnh hồ sơ bệnh án có chứa thông tin cá nhân (PII) khi đẩy vào LLM. | **Cao** | • **Data Anonymization**: Tiền xử lý ẩn danh tên/SDT bệnh nhân trước khi gọi Bedrock.<br>• 100% tệp trên S3 được phân quyền Private và mã hóa KMS. |
| **Rủi ro Ảo giác Mô hình (Hallucination)** | AI bịa đặt tên thuốc hoặc tư vấn sai cách dùng thuốc. | **Trung bình** | • Áp dụng **RAG Pipeline** với Amazon OpenSearch.<br>• Bắt buộc trích xuất chính xác từ Dược thư MedlinePlus đã nhúng vector. |
| **Rủi ro Quá tải Chi phí Cloud** | Người dùng hoặc bot gửi request liên tục làm phát sinh chi phí AWS ngoài dự tính. | **Trung bình** | • Bật **AWS WAF Rate-Limiting** chặn IP spam.<br>• Thiết lập **AWS Budgets Alarm** báo động chi phí. |

---

<a name="238-kịch-bản-kiểm-chứng-sản-phẩm-chạy-thực-tế"></a>
### 2.3.8. Kịch bản Kiểm chứng Sản phẩm Chạy Thực tế (Live Demo Verification)

Hệ thống đã được lập trình hoàn chỉnh, kiểm thử thực tế và sẵn sàng cho phiên **Live Demo chấm điểm** với 4 tình huống kiểm chứng lâm sàng:

```text
[BƯỚC 1: TRUY CẬP HỆ THỐNG]
URL Production / Localhost: http://127.0.0.1:8000
Giao diện: Spatial Glassmorphism (VisionOS v2.5).

[BƯỚC 2: DEMO PHÂN TẦNG LÂM SÀNG & BẢO VỆ AN TOÀN]
• Ca 1: Triệu chứng cờ đỏ cấp cứu (Emergency Bypass)
  Nhập: "Tôi đau thắt ngực dữ dội, vã mồ hôi và khó thở lan ra tay trái"
  Kết quả: Kích hoạt Red Flag cấp cứu ngay lập tức, hiển thị hotline 115.

[BƯỚC 3: DEMO BÓC TÁCH ĐƠN THUỐC THỊ GIÁC VÀ ẨN DANH PII]
• Tải lên ảnh đơn thuốc mẫu BN. Nguyễn Thị Lợi (60 tuổi):
  Kết quả:
  - Hệ thống Anonymization: Đổi tên thành "BN: N*** T*** L***" trước khi phân tích.
  - Bóc tách tự động: Seotolac 200mg, Độc hoạt, Đại tần giao...
  - Sắp xếp lộ trình: Cữ Sáng (06:30) | Cữ Trưa | Cữ Tối (19:30).

[BƯỚC 4: DEMO HỒ SƠ BỆNH ÁN ĐIỆN TỬ (EMR SUMMARY)]
• Chuyển sang Tab "Hồ sơ Bác sĩ (EMR)":
  Kết quả: Tự động tổng hợp bản tóm tắt 30 giây (Lý do khám, bệnh sử HPI, 
  cảnh báo tiền sử dị ứng).
```

---

## KẾT LUẬN & KIẾN NGHỊ

Bản đề xuất giải pháp **MediMind Clinical AI** đáp ứng toàn diện và chặt chẽ mọi tiêu chí khắt khe của học phần Thực tập / Workshop Chuyên môn:
1. **Kiến trúc Hệ thống (Architecture)**: Thiết kế chuẩn **AWS Well-Architected**, bảo đảm 100% tài nguyên và luồng dữ liệu (S3, OpenSearch, Bedrock) được cô lập an toàn trong hệ sinh thái AWS, tuân thủ tiêu chuẩn HIPAA.
2. **Dự toán Ngân sách & Tối ưu Chi phí (Cost Estimation)**: Cung cấp đầy đủ bảng tính giá chi tiết, thực tế. Kịch bản DEV được tối ưu lược bỏ hạ tầng mạng đắt đỏ (\$23.81), trong khi kịch bản Production (\$169.00) phản ánh đúng tính chất an ninh cấp doanh nghiệp (có ALB, NAT).
3. **Minh chứng Sản phẩm Chạy Thực tế (Live Demo)**: Ứng dụng sẵn sàng trình diễn toàn bộ các luồng nghiệp vụ lâm sàng trước hội đồng đánh giá.
