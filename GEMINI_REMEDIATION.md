# Yêu cầu Gemini khắc phục kiến trúc MediMind

Bạn là kỹ sư phụ trách sửa repository này. Hãy trực tiếp đọc mã, thực hiện thay đổi và kiểm thử; không chỉ đưa ra kế hoạch. Các phát hiện bên dưới cần được xác minh lại trên phiên bản hiện tại.

## Phạm vi và nguyên tắc

- Giữ giao diện và các chức năng đang hoạt động. Chọn Flask làm backend chính theo README; không duy trì hai bản nghiệp vụ riêng. Nếu giữ FastAPI, dùng chung application services và kiểm thử tính tương đương. Nếu ngừng hỗ trợ, ghi rõ và loại bỏ entrypoint gây hiểu nhầm một cách có chủ đích.
- Giữ kiến trúc monolith có module; chưa tách microservices hay triển khai cloud.
- Kiểm tra git status trước khi sửa. Không ghi đè thay đổi có sẵn, không xóa dữ liệu, không reset repository, không commit/push/deploy tự động.
- Không đọc/in khóa trong .env, không gửi dữ liệu bệnh nhân hoặc tài liệu uploads tới dịch vụ ngoài khi kiểm thử. Mock Gemini, OCR và vector store trong test.
- Không chỉnh sửa trực tiếp SQLite, uploads hoặc medical_vectordb thật. Dùng thư mục tạm và database test.

## 1. Sửa quyền truy cập và upload trước

- app.py auth_update_profile: bỏ fallback lấy user_id từ JSON khi không có session. Trả 401 nếu chưa đăng nhập; chỉ cho sửa hồ sơ của người đã xác thực.
- Đăng ký công khai luôn tạo patient; không chấp nhận tự cấp role doctor/admin từ client. Chuẩn hóa role trong response.
- Bảo vệ API liệt kê, xóa và truy cập tài liệu bằng xác thực và kiểm tra owner_id. Bổ sung model tài liệu và migration. File cũ không có owner không được tự động công khai hay gán tùy tiện cho người dùng.
- Dùng ID/tên lưu ngẫu nhiên, kiểm tra đường dẫn nằm trong uploads, loại file thực tế và dung lượng. Không tin filename/MIME client; không ghi đè file trùng tên. Áp dụng cho mọi đường upload, kể cả ảnh base64.
- main_fastapi.py hiện ghép trực tiếp filename vào UPLOAD_FOLDER: xử lý nguy cơ path traversal nếu còn giữ entrypoint này.
- Bỏ secret mặc định trong mã ở production. Demo accounts chỉ seed khi bật cấu hình demo rõ ràng. Tắt debug/reload production; bổ sung cấu hình cookie và bảo vệ request thay đổi trạng thái phù hợp với session auth.

## 2. Không trả dữ liệu mẫu như kết quả thật

- core/prescription_service.py: khi OCR và Gemini thất bại, không trả get_preset_data theo tên file. Trả trạng thái failed/needs_review, mã lỗi và hướng dẫn thử lại; không bịa kết quả, thuốc hoặc chỉ số.
- Preset chỉ hoạt động ở chế độ demo rõ ràng, response và UI đều hiển thị is_demo.
- clinical-summary phải lấy dữ liệu thuộc người dùng và hội thoại được chọn. Nếu chưa có dữ liệu, trả trạng thái thiếu dữ liệu thay vì bệnh án hardcode.
- Đồng bộ frontend để xử lý lỗi, kết quả cần xác nhận và trạng thái demo.

## 3. Thống nhất hợp đồng và chính sách AI

- Tách điều phối chat/scan khỏi route thành services dùng chung, không sao chép giữa Flask/FastAPI.
- Định nghĩa schema đầu vào/đầu ra: giới hạn message/history/image, enum ngôn ngữ/risk, risk_score 0..100, danh sách nguồn, trạng thái degraded và lỗi.
- Nếu giữ FastAPI, bổ sung trường lang còn thiếu trong ChatMessageRequest; bỏ auth giả lập và /me luôn authenticated=true.
- Kiểm chứng JSON Gemini bằng schema; JSON sai hoặc thiếu trường không được mặc định thành kết quả hợp lệ/nguy cơ thấp.
- core/triage.py apply_safety_guardrails hiện chỉ nối cảnh báo. Thay bằng chính sách từ chối/thay thế nội dung vi phạm, không giữ nguyên hướng dẫn bị cấm. Áp dụng cho cả AI và fallback và các trường có nội dung tư vấn.
- Thống nhất chính sách không tự kê thuốc/liều giữa prompt và fallback. Không suy diễn phát hiện hình ảnh khi không có xử lý ảnh thành công. Không coi bộ quy tắc đơn giản là kiểm định y khoa.
- Duy trì đánh giá khẩn cấp nhất quán; không ghi cứng is_emergency=false nếu kết quả đã xác định cần xử lý khẩn. Trường hợp thiếu bằng chứng cần được biểu diễn rõ.

## 4. RAG và vận hành

- Không coi 1-distance là xác suất tin cậy. Ghi rõ distance metric, bổ sung tiêu chí chấp nhận tài liệu có thể cấu hình và đánh giá bằng tập truy vấn; không khẳng định ngưỡng chưa đo là đã đáng tin.
- Nguồn trả về phải tham chiếu tài liệu/chunk truy xuất thực tế. Không tự gán nguồn trang chủ như bằng chứng cho mọi câu trả lời.
- ingest.py: kiểm tra dữ liệu trước, nạp collection có phiên bản mới, xác minh hoàn tất rồi chuyển active version; giữ bản cũ để rollback. Không xóa collection đang phục vụ trước khi nạp xong.
- Đưa thay đổi schema DB sang migration có phiên bản thay cho ALTER TABLE và nuốt exception khi import.
- Cấu hình timeout và giới hạn thử lại cho LLM. Nếu giữ async FastAPI, không chạy OCR/LLM đồng bộ trực tiếp trên event loop; dùng cơ chế offload phù hợp.
- Thêm logging có request_id, latency, failure/degraded status; không log nguyên văn thông tin sức khỏe cá nhân.
- Hoàn thiện dependencies thực sự cần cho backend đã chọn và OCR; cập nhật README, .env.example, hướng dẫn migration và chế độ demo/production. Không cài thêm hạ tầng không cần thiết.

## Kiểm thử bắt buộc

1. Không đăng nhập không sửa được hồ sơ, liệt kê/xóa tài liệu riêng tư.
2. User A không sửa/xóa tài liệu của user B; client không tự cấp doctor/admin.
3. Filename traversal, file quá lớn, sai định dạng và tên trùng được xử lý an toàn.
4. OCR/LLM thất bại không trả preset hoặc thành công giả.
5. Schema Gemini sai, thiếu trường, risk_score ngoài khoảng và nguồn không hợp lệ được xử lý.
6. Chính sách an toàn áp dụng cho cả AI/fallback; kiểm thử tiền kiểm, phủ định và lịch sử hội thoại có liên quan.
7. Ingestion thất bại không phá phiên bản tri thức đang hoạt động.
8. Smoke test backend chính và các luồng frontend liên quan; nếu giữ hai backend, kiểm thử contract tương đương.

## Báo cáo bàn giao

Nêu các file đã thay đổi, lỗi đã khắc phục, lệnh kiểm thử và kết quả thực tế, migration/cấu hình cần áp dụng, các phần còn chưa làm hoặc cần kiểm định chuyên môn. Không tuyên bố production-ready chỉ vì test kỹ thuật đã pass.
