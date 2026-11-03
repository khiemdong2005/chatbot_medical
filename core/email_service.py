# ==============================================================
# MEDIMIND CLINICAL AI - SMTP TRANSACTIONAL EMAIL SERVICE
# ==============================================================

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any


class EmailService:
    """Dịch vụ gửi Email giao dịch (OTP, Khôi phục mật khẩu, Chào mừng)."""
    def __init__(self):
        self.server = os.getenv("SMTP_SERVER", "")
        self.port = int(os.getenv("SMTP_PORT", 587))
        self.username = os.getenv("SMTP_USERNAME", "")
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        self.sender_name = os.getenv("SMTP_SENDER_NAME", "MediMind Clinical AI")
        self.sender_email = self.username or "no-reply@medimind.ai"

    def is_configured(self) -> bool:
        return bool(self.server and self.username and self.password)

    def send_email(self, to_email: str, subject: str, html_body: str, text_body: Optional[str] = None) -> bool:
        """Gửi thư điện tử qua giao thức SMTP. Nếu chưa cấu hình, in ra terminal để test."""
        if not self.is_configured():
            print("\n" + "=" * 70)
            print(f"📧 [DEV EMAIL SIMULATOR] Gửi tới: {to_email}")
            print(f"📌 Tiêu đề: {subject}")
            print(f"📝 Nội dung:\n{text_body or html_body}")
            print("=" * 70 + "\n")
            return True

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.sender_name} <{self.sender_email}>"
            msg["To"] = to_email

            if text_body:
                msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            with smtplib.SMTP(self.server, self.port, timeout=10) as s:
                if self.use_tls:
                    s.starttls()
                s.login(self.username, self.password)
                s.sendmail(self.sender_email, [to_email], msg.as_string())

            print(f"✅ [Email Service] Đã gửi thư thành công tới: {to_email}")
            return True
        except Exception as e:
            print(f"❌ [Email Service] Lỗi khi gửi thư tới {to_email}: {e}")
            return False

    def send_welcome_email(self, to_email: str, full_name: str) -> bool:
        subject = "Chào mừng bạn đến với MediMind Clinical AI"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; rounded: 16px;">
            <div style="background-color: #0284C7; padding: 20px; text-align: center; border-radius: 12px; color: white;">
                <h2 style="margin: 0;">MediMind Clinical AI</h2>
                <p style="margin: 5px 0 0 0; font-size: 13px;">Trợ lý Y tế Sàng lọc Thông minh</p>
            </div>
            <div style="padding: 24px 0; color: #334155; line-height: 1.6;">
                <p>Xin chào <strong>{full_name}</strong>,</p>
                <p>Tài khoản hồ sơ sức khỏe của bạn đã được khởi tạo thành công trên hệ thống <strong>MediMind</strong>.</p>
                <p>Bạn có thể sử dụng các tính năng:</p>
                <ul>
                    <li>Sàng lọc và phân tầng triệu chứng y khoa tức thời qua AI.</li>
                    <li>Nạp và quản lý dữ liệu đơn thuốc, kết quả xét nghiệm.</li>
                    <li>Theo dõi hồ sơ bệnh án cá nhân chuẩn hóa.</li>
                </ul>
                <p style="margin-top: 24px; font-size: 12px; color: #94a3b8;">Lưu ý: Hệ thống chỉ mang tính chất tham khảo, không thay thế chẩn đoán chuyên môn của bác sĩ.</p>
            </div>
        </div>
        """
        text = f"Xin chào {full_name},\nTài khoản của bạn đã được khởi tạo thành công trên MediMind Clinical AI."
        return self.send_email(to_email, subject, html, text)

    def send_password_reset_otp(self, to_email: str, otp_code: str) -> bool:
        subject = f"[{otp_code}] Mã xác nhận đặt lại mật khẩu - MediMind"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 16px;">
            <div style="text-align: center; margin-bottom: 20px;">
                <h3 style="color: #0284C7; margin: 0;">Đặt lại mật khẩu tài khoản</h3>
                <p style="color: #64748b; font-size: 13px;">Mã xác thực y tế một lần (OTP)</p>
            </div>
            <div style="background-color: #f0f9ff; border: 1px dashed #0284C7; padding: 18px; text-align: center; border-radius: 12px;">
                <span style="font-size: 28px; font-weight: bold; letter-spacing: 6px; color: #0369a1;">{otp_code}</span>
            </div>
            <p style="font-size: 12px; color: #64748b; margin-top: 20px; line-height: 1.5;">
                Mã này có hiệu lực trong vòng <strong>5 phút</strong>. Tuyệt đối không chia sẻ mã này cho bất kỳ ai để đảm bảo an toàn cho hồ sơ sức khỏe của bạn.
            </p>
        </div>
        """
        text = f"Mã xác nhận đặt lại mật khẩu MediMind của bạn là: {otp_code}. Mã có hiệu lực trong 5 phút."
        return self.send_email(to_email, subject, html, text)


email_service = EmailService()
