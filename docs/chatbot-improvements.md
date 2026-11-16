# Đánh giá và cải thiện chatbot MediMind

## Phạm vi phù hợp

Chatbot hỗ trợ tìm hiểu sức khỏe ban đầu, hỏi thêm thông tin cần thiết và định
hướng tìm trợ giúp. Đây không phải hệ thống bệnh án của bệnh viện, công cụ xác
nhận chẩn đoán hay kê đơn. Không coi điểm số do mô hình sinh ra là xác suất y khoa
đã được kiểm định.

Không cần dựng lại trang bệnh án chính thức để duy trì ngữ cảnh. Bổ sung mục
**Thông tin sức khỏe**, tùy chọn cho từng cuộc trò chuyện: tuổi, giới tính,
thai kỳ/cho con bú, dị ứng, thuốc đang dùng và bệnh nền người dùng tự khai.
Người dùng áp dụng, sửa hoặc xóa thông tin này. Các giá trị chỉ ở bộ nhớ của trang,
không ghi vào tài khoản hay localStorage; chúng được gửi cùng lượt hỏi tới Gemini.
Đổi cuộc chat/tài khoản hoặc tải lại trang sẽ xóa mục bổ sung này.
Xóa mục bổ sung không xóa những nội dung đã được nhắc lại trong câu trả lời hoặc
lịch sử hội thoại; người dùng có thể xóa cả cuộc trò chuyện bằng thao tác riêng.

Hội thoại và dữ kiện intake vẫn có cơ chế lưu nháp hiện tại trên server, với chủ
sở hữu là tài khoản hoặc token khách. Lịch sử hiển thị cũng được lưu trên thiết bị.
Không mô tả cơ chế này là mã hóa đầu cuối. Bản tóm tắt trước khám chỉ được lưu
vào danh sách đã xác nhận khi người dùng đăng nhập, xem lại dữ kiện, đồng ý lưu
và gửi đúng phiên bản. Lời AI không trở thành chẩn đoán trong bệnh án chính thức.

## Vấn đề được sửa

| Trước | Sau |
| --- | --- |
| Gemini chỉ nhận 4 lượt cuối và gợi ý câu hỏi; mất dữ kiện cũ | Tối đa 20 lượt có giới hạn kích thước, kèm dữ kiện intake và mục tự khai riêng |
| Intake lưu câu hỏi nội bộ khác câu bot thực sự nói | Lưu phản hồi thực tế để lời đáp ngắn ở lượt sau được hiểu đúng |
| Thiếu điểm nguy cơ bị đổi thành 25/30 | Giữ `null` và trạng thái chưa đủ thông tin trong API, lưu và mở lại lịch sử |
| Mô hình có thể trả nguồn không có trong dữ liệu truy xuất | Nguồn lấy từ metadata của tài liệu thực sự được tìm thấy |
| AI lỗi nhưng fallback đưa liều thuốc/chẩn đoán mẫu | Báo trạng thái dự phòng; không tự kê liều, suy đoán bệnh hoặc mô tả ảnh chưa xem |
| Câu hỏi intake ghi đè câu trả lời hoặc hướng dẫn khẩn | Câu hỏi là gợi ý tùy chọn; phản hồi khẩn không bị thay bằng câu hỏi thường |
| Mọi lần nhắc kháng sinh đều bị thay thành cảnh báo chung | Giữ giải thích và lời từ chối an toàn; chặn hướng dẫn tự dùng hoặc kê liều |
| Gửi chồng lượt, chuyển chat khi phản hồi chưa về | Khóa gửi chung, hủy request và kiểm tra phiên/tài khoản trước khi gắn phản hồi |
| Chat nổi và chat chính lệch lịch sử/nguồn/cờ đỏ | Dùng chung dữ liệu và metadata hiển thị |
| Xóa bản tóm tắt nhưng bản nháp trong DB/RAM còn | Kiểm tra chủ sở hữu rồi xóa các phần liên quan; phản hồi chậm không tạo lại phiên đã xóa |
| Phiên legacy không có chủ vẫn cho truy cập bằng ID | Từ chối truy cập khi không xác minh được chủ sở hữu |
| Nhận phủ định dị ứng/thuốc thành khẳng định | Giữ phủ định và chỉ ghi dữ kiện dương tính thực sự có trong lời khai |

## Đường xử lý

1. Kiểm tra kiểu, kích thước message/history/ảnh/context trước khi gọi dịch vụ.
2. Kiểm tra dấu hiệu khẩn bằng quy tắc; hỏi rõ nếu lời xác nhận còn mơ hồ.
3. Cập nhật dữ kiện của phiên theo chủ sở hữu.
4. Tìm tài liệu trong kho cục bộ, mặc định bằng BM25; không tải mô hình embedding
   trong đường xử lý chat mặc định. Triệu chứng đã phủ nhận không được ưu tiên
   thành từ khóa tìm tài liệu; vẫn giữ nguyên câu hỏi hiện tại và lời khai gốc
   cho mô hình. Không cache câu hỏi sức khỏe.
5. Gửi dữ liệu có giới hạn tới Gemini theo JSON, tách khỏi chỉ dẫn hệ thống.
   Ngữ cảnh tự khai và tài liệu là dữ liệu không đáng tin, không phải mệnh lệnh.
6. Kiểm tra cấu trúc trả về, nguồn và hậu kiểm câu trả lời. Hiện nguồn và trạng
   thái dự phòng ở cả hai giao diện chat. Không đưa tên/địa chỉ/số bảo hiểm của
   tài khoản vào prompt một cách tự động.

## Cấu hình và kiểm thử

- `GEMINI_CHAT_MODEL`: mặc định `gemini-flash-lite-latest`, có thể cấu hình riêng.
- `GEMINI_CHAT_API_KEY`: khóa riêng nếu cần; hỗ trợ cấu hình Gemini đang có.
  Khóa chỉ ở server và file môi trường được Git bỏ qua.
- Mỗi lần sinh phản hồi giới hạn 25 giây, không lặp vô hạn khi provider lỗi.
- `RAG_VECTOR_SEARCH_ENABLED=true`: tùy chọn cho môi trường đã chuẩn bị mô hình
  embedding. Mặc định dùng tài liệu cục bộ; lỗi vector vẫn giữ kết quả BM25.
- `DELETE /api/intake/session/<conversation_id>`: xóa bản nháp, transcript và bản
  tóm tắt liên quan của đúng chủ sở hữu. Không gọi tự động khi mở chat mới.
- `python -m pytest tests -q`: toàn bộ ca kiểm thử, dùng DB tạm và AI giả lập.
- `node --check static/js/app.js` và `node --check static/js/chat-context.js`.

Các kiểm thử kỹ thuật không chứng nhận độ chính xác lâm sàng. Tài liệu truy xuất,
quy tắc dấu hiệu khẩn và câu trả lời AI vẫn cần đánh giá chuyên môn trên bộ tình
huống được duyệt trước khi dùng làm công cụ quyết định chăm sóc.

Tham chiếu về phạm vi và giới hạn của trợ lý sức khỏe:
[WHO – hướng dẫn AI đa phương thức trong y tế](https://www.who.int/publications/b/70584),
[NHS – cách dịch vụ hỗ trợ triệu chứng hoạt động](https://www.nhs.uk/nhs-services/urgent-and-emergency-care-services/when-to-use-111/how-nhs-111-online-works/).
