# ==============================================================
# MEDIMIND CLINICAL AI - SMTP TRANSACTIONAL EMAIL SERVICE
# Hỗ trợ gửi Email giao dịch, mã OTP bảo mật 2 lớp & Xác thực tài khoản
# ==============================================================

import os
import html
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any


class EmailService:
    """Dịch vụ gửi Email giao dịch (OTP 2FA, Khôi phục mật khẩu, Chào mừng)."""
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

    def send_verification_otp(self, to_email: str, otp_code: str, full_name: Optional[str] = None, purpose: str = "register") -> bool:
        """Gửi mã OTP 6 số xác thực 2 lớp / Đăng ký qua Email với giao diện y tế cao cấp."""
        raw_name = full_name or "Quý bệnh nhân"
        name = html.escape(str(raw_name), quote=True)
        purpose_title = "Xác thực tài khoản mới" if purpose == "register" else ("Đăng nhập thiết bị mới (2FA)" if purpose == "login_2fa" else "Xác nhận danh tính y tế")
        subject = f"[{otp_code}] Mã xác thực {purpose_title} - MediMind Clinical AI"

        formatted_otp = " ".join(list(otp_code))

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }}
            .card {{ max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px rgba(15, 23, 42, 0.08); border: 1px solid #e2e8f0; }}
            .header {{ background: linear-gradient(135deg, #0284c7 0%, #4f46e5 100%); padding: 32px 24px; text-align: center; color: #ffffff; }}
            .header h1 {{ margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }}
            .header p {{ margin: 6px 0 0; font-size: 13px; opacity: 0.9; }}
            .content {{ padding: 32px 24px; color: #334155; line-height: 1.6; font-size: 14px; }}
            .otp-box {{ background: #f0f9ff; border: 2px dashed #38bdf8; border-radius: 16px; padding: 20px; text-align: center; margin: 24px 0; }}
            .otp-code {{ font-size: 32px; font-weight: 900; letter-spacing: 8px; color: #0284c7; font-family: 'Courier New', monospace; display: block; }}
            .otp-exp {{ font-size: 12px; color: #64748b; margin-top: 8px; font-weight: 600; }}
            .warning {{ background: #fffbeb; border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 8px; font-size: 12px; color: #92400e; margin: 20px 0; }}
            .footer {{ background: #f8fafc; padding: 20px 24px; text-align: center; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="header">
              <h1>🏥 MediMind Clinical AI</h1>
              <p>Hệ thống Trợ lý Y tế & Phân tầng Lâm sàng An toàn</p>
            </div>
            <div class="content">
              <p>Kính chào <strong>{name}</strong>,</p>
              <p>Hệ thống vừa nhận được yêu cầu <strong>{purpose_title.lower()}</strong> cho tài khoản của bạn. Vui lòng nhập mã bảo mật một lần (OTP) dưới đây để hoàn tất:</p>
              
              <div class="otp-box">
                <span class="otp-code">{formatted_otp}</span>
                <div class="otp-exp">⏱️ Mã có hiệu lực trong vòng 5 phút (300 giây)</div>
              </div>

              <div class="warning">
                <strong>🔒 Lưu ý bảo mật HIPAA:</strong> Tuyệt đối không chia sẻ mã này cho bất kỳ ai. Nhân viên MediMind không bao giờ chủ động gọi điện để hỏi mã xác thực của bạn.
              </div>

              <p style="font-size: 12px; color: #64748b;">Nếu bạn không thực hiện yêu cầu này, vui lòng bỏ qua thư hoặc đổi mật khẩu ngay để bảo vệ hồ sơ bệnh án cá nhân.</p>
            </div>
            <div class="footer">
              <p>© 2026 MediMind Clinical AI. Bảo mật dữ liệu cá nhân cục bộ chuẩn y khoa.</p>
            </div>
          </div>
        </body>
        </html>
        """
        text = f"Kính chào {name},\nMã xác thực {purpose_title} của bạn là: {otp_code}.\nMã có hiệu lực trong 5 phút. Tuyệt đối không chia sẻ mã này cho ai."
        return self.send_email(to_email, subject, html_body, text)

    def send_welcome_email(self, to_email: str, full_name: str) -> bool:
        safe_name = html.escape(str(full_name or "Quý bệnh nhân"), quote=True)
        subject = "Chào mừng bạn đến với MediMind Clinical AI"
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 16px;">
            <div style="background-color: #0284C7; padding: 20px; text-align: center; border-radius: 12px; color: white;">
                <h2 style="margin: 0;">MediMind Clinical AI</h2>
                <p style="margin: 5px 0 0 0; font-size: 13px;">Trợ lý Y tế Sàng lọc Thông minh</p>
            </div>
            <div style="padding: 24px 0; color: #334155; line-height: 1.6;">
                <p>Xin chào <strong>{safe_name}</strong>,</p>
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
        return self.send_email(to_email, subject, html_body, text)

    def send_password_reset_otp(self, to_email: str, otp_code: str) -> bool:
        return self.send_verification_otp(to_email, otp_code, purpose="reset_pwd")


email_service = EmailService()
