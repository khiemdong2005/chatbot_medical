# ==============================================================
# MEDIMIND CLINICAL AI - SMTP TRANSACTIONAL EMAIL SERVICE
# Hỗ trợ gửi Email giao dịch, mã OTP bảo mật 2 lớp & Xác thực tài khoản
# ==============================================================

import os
import html
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, Tuple


class EmailService:
    """Dịch vụ gửi Email giao dịch (OTP 2FA, Khôi phục mật khẩu, Chào mừng)."""

    def __init__(self):
        self._refresh_config()

    def _refresh_config(self) -> None:
        self.server = os.getenv("SMTP_SERVER", "").strip()
        self.port = int(os.getenv("SMTP_PORT", "587") or 587)
        self.username = os.getenv("SMTP_USERNAME", "").strip()
        # Tự động loại bỏ khoảng trắng phòng trường hợp copy mã App Password có dấu cách
        raw_pwd = os.getenv("SMTP_PASSWORD", "").strip()
        self.password = raw_pwd.replace(" ", "") if raw_pwd else ""
        self.use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() == "true"
        self.sender_name = os.getenv("SMTP_SENDER_NAME", "MediMind Clinical AI").strip().strip('"')
        self.sender_email = self.username or "no-reply@medimind.ai"

    @staticmethod
    def _is_production() -> bool:
        env_val = (os.getenv("ENV") or os.getenv("FLASK_ENV") or "").strip().lower()
        return env_val in ("production", "prod")

    def is_configured(self) -> bool:
        self._refresh_config()
        return bool(self.server and self.username and self.password)

    def send_email(self, to_email: str, subject: str, html_body: str, text_body: Optional[str] = None) -> bool:
        """Gửi thư điện tử qua giao thức SMTP. Fail-closed khi ENV=production; local dev in ra terminal."""
        if not isinstance(to_email, str) or "\r" in to_email or "\n" in to_email or "@" not in to_email:
            return False
        to_email = to_email.strip()
        subject = str(subject or "").replace("\r", " ").replace("\n", " ").strip()
        if not self.is_configured():
            if self._is_production():
                print("❌ [Email Service] Production mode: SMTP chưa được cấu hình. Đã chặn Dev Simulator (fail-closed).")
                return False
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
                s.ehlo()
                if self.use_tls:
                    s.starttls()
                    s.ehlo()
                s.login(self.username, self.password)
                s.sendmail(self.sender_email, [to_email], msg.as_string())

            print(f"✅ [Email Service] Đã gửi thư thành công tới: {to_email}")
            return True
        except Exception as e:
            print(f"❌ [Email Service] Gửi thư qua SMTP thất bại ({type(e).__name__}): {e}")
            if self._is_production():
                print("❌ [Email Service] Production mode: không dùng Dev Simulator khi SMTP lỗi (fail-closed).")
                return False
            # Dự phòng Dev Simulator ở Local Development: in mã ra console để không làm nghẽn thử nghiệm
            print("\n" + "=" * 70)
            print(f"📧 [FALLBACK DEV EMAIL SIMULATOR] Gửi tới: {to_email}")
            print(f"📌 Tiêu đề: {subject}")
            print(f"📝 Nội dung:\n{text_body or html_body}")
            print("=" * 70 + "\n")
            if os.getenv("FLASK_DEBUG", "false").lower() in ("true", "1") or os.getenv("ENV", "").lower() == "development":
                print("⚠️ [Email Service] Đang ở chế độ Development -> Cho phép dùng mã trên Terminal để tiếp tục.")
                return True
            return False

    def send_verification_otp(
        self,
        to_email: str,
        otp_code: str,
        full_name: Optional[str] = None,
        purpose: str = "register",
        ttl_seconds: int = 120,
    ) -> bool:
        """Gửi mã OTP 6 số xác thực tài khoản / Đăng nhập 2FA / Đặt lại mật khẩu qua Email."""
        raw_name = full_name or "Quý bệnh nhân"
        name = html.escape(str(raw_name), quote=True)
        purpose_titles = {
            "register": "Xác thực tài khoản mới",
            "login_2fa": "Đăng nhập thiết bị mới (2FA)",
            "reset_pwd": "Đặt lại mật khẩu",
        }
        purpose_title = purpose_titles.get(purpose, "Xác nhận danh tính y tế")
        subject = f"[{otp_code}] Mã xác thực {purpose_title} - MediMind Clinical AI"

        ttl_sec = max(30, int(ttl_seconds or 120))
        ttl_min = max(1, ttl_sec // 60)
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
                <div class="otp-exp">⏱️ Mã có hiệu lực trong vòng {ttl_min} phút ({ttl_sec} giây)</div>
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
        text = f"Kính chào {name},\nMã xác thực {purpose_title} của bạn là: {otp_code}.\nMã có hiệu lực trong {ttl_min} phút ({ttl_sec} giây). Tuyệt đối không chia sẻ mã này cho ai."
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

    @staticmethod
    def _extract_previsit_summary_sections(
        pre_visit_summary: Optional[Dict[str, Any]],
    ) -> Tuple[list, list]:
        """Trích xuất các dòng (nhãn, giá trị) cho Phần A và Phần B từ pre_visit_summary."""
        if not isinstance(pre_visit_summary, dict):
            return [], []

        empty_values = {
            "--",
            "Chưa rõ",
            "Chưa ghi nhận cụ thể",
            "Chưa ghi nhận lý do khám",
            "Chưa rõ các chỉ số tự đo",
            "Chưa rõ tiền sử dị ứng",
            "Chưa rõ thuốc đang dùng",
            "Không có tệp hình ảnh đính kèm",
        }

        def _known(val: Any) -> str:
            if not isinstance(val, str):
                return ""
            s = val.strip()
            return "" if (not s or s in empty_values) else s

        def _join_list(vals: Any) -> str:
            if not isinstance(vals, list):
                return ""
            return ", ".join(filter(None, (_known(v) for v in vals)))

        part_a = pre_visit_summary.get("part_a_patient_facts") or {}
        part_b = pre_visit_summary.get("part_b_system_assessment") or {}
        if not isinstance(part_a, dict):
            part_a = {}
        if not isinstance(part_b, dict):
            part_b = {}

        history = part_a.get("patient_reported_history") or {}
        if not isinstance(history, dict):
            history = {}

        def _history_val(field: str, fallback: Any = None) -> str:
            item = history.get(field) if isinstance(history.get(field), dict) else {}
            text = _known(item.get("text")) or _known(fallback)
            status = item.get("status")
            if status == "skipped":
                return "Đã bỏ qua"
            if status == "unknown":
                return "Chưa rõ theo lời người bệnh"
            if status == "denied" and field != "medications":
                return f"Không có · {text}" if text else "Người bệnh cho biết không có"
            return text

        pain = part_a.get("pain") if isinstance(part_a.get("pain"), dict) else {}
        part_a_candidates = [
            ("Lý do khám", _known(part_a.get("chief_complaint"))),
            ("Thời điểm bắt đầu", _known(part_a.get("duration"))),
            ("Vị trí đau", _known(pain.get("location"))),
            ("Tính chất đau", _known(pain.get("quality"))),
            ("Mức độ đau", _known(pain.get("severity"))),
            ("Tần suất đau", _known(part_a.get("pain_frequency"))),
            ("Triệu chứng ghi nhận", _join_list(part_a.get("symptoms_present"))),
            ("Triệu chứng không có", _join_list(part_a.get("symptoms_denied"))),
            ("Ảnh hưởng sinh hoạt", _known(part_a.get("activity_impact"))),
            ("Dị ứng", _history_val("allergies", part_a.get("allergies"))),
            ("Thuốc đang/đã dùng", _history_val("medications", part_a.get("current_medications"))),
            ("Tiền sử bệnh nền", _history_val("conditions")),
            ("Chỉ số tự đo", _known(part_a.get("vitals"))),
            ("Ảnh đính kèm", _known(part_a.get("attachments_and_observations"))),
        ]
        ctx_answers = part_a.get("contextual_answers")
        if isinstance(ctx_answers, list):
            for item in ctx_answers:
                if isinstance(item, dict):
                    q = _known(item.get("question"))
                    a = _known(item.get("answer"))
                    if q and a:
                        part_a_candidates.append((q, a))

        part_a_rows = [(k, v) for k, v in part_a_candidates if v]

        part_b_rows = []
        if part_b.get("triage_badge") in ("assessed", "emergency"):
            for lbl, val in (
                ("Phân luồng", _known(part_b.get("triage_status"))),
                ("Chuyên khoa gợi ý", _known(part_b.get("recommended_specialist"))),
                ("Hướng chăm sóc", _known(part_b.get("care_approach"))),
            ):
                if val:
                    part_b_rows.append((lbl, val))

        return part_a_rows, part_b_rows

    def send_appointment_confirmation(self, to_email: str, appointment: Dict[str, Any]) -> bool:
        """Gửi email xác nhận đặt lịch khám bệnh tới Gmail / Email đăng ký của bệnh nhân."""
        clean_email = (to_email or "").strip()
        if not clean_email or "@" not in clean_email or clean_email.lower().endswith("@phone.medimind"):
            return False

        appt_id = appointment.get("id") or ""
        appt_code = f"#LH-{appt_id}" if appt_id else "#LH-MEDIMIND"
        raw_facility = str(appointment.get("facility_name") or "Cơ sở Y tế").strip()
        raw_address = str(appointment.get("facility_address") or "").strip()
        raw_specialty = str(appointment.get("specialty") or "Đa khoa").strip()
        raw_date = str(appointment.get("appointment_date") or "").strip()
        raw_time = str(appointment.get("appointment_time") or "").strip()
        raw_patient = str(appointment.get("patient_name") or "Quý bệnh nhân").strip()
        raw_phone = str(appointment.get("patient_phone") or "").strip()
        raw_note = str(appointment.get("note") or "").strip()
        pre_visit_summary = appointment.get("pre_visit_summary")
        part_a_rows, part_b_rows = self._extract_previsit_summary_sections(pre_visit_summary)
        has_previsit = bool(pre_visit_summary)

        display_date = raw_date
        if len(raw_date) == 10 and raw_date[4] == "-" and raw_date[7] == "-":
            parts = raw_date.split("-")
            display_date = f"{parts[2]}/{parts[1]}/{parts[0]}"

        safe_code = html.escape(appt_code, quote=True)
        safe_facility = html.escape(raw_facility, quote=True)
        safe_address = html.escape(raw_address, quote=True)
        safe_specialty = html.escape(raw_specialty, quote=True)
        safe_date = html.escape(display_date, quote=True)
        safe_time = html.escape(raw_time, quote=True)
        safe_patient = html.escape(raw_patient, quote=True)
        safe_phone = html.escape(raw_phone, quote=True)
        safe_note = html.escape(raw_note, quote=True)

        subject = f"[MediMind] Xác nhận đặt lịch khám {appt_code} - {raw_facility}"

        address_row = (
            f'<tr><td style="padding:8px 0;color:#64748b;width:140px;">Địa chỉ</td>'
            f'<td style="padding:8px 0;color:#0f172a;font-weight:600;">{safe_address}</td></tr>'
            if safe_address
            else ""
        )
        note_row = (
            f'<tr><td style="padding:8px 0;color:#64748b;">Ghi chú</td>'
            f'<td style="padding:8px 0;color:#0f172a;">{safe_note}</td></tr>'
            if safe_note
            else ""
        )

        previsit_html_block = ""
        previsit_text_lines = []
        if has_previsit:
            def _render_rows_html(rows):
                return "".join(
                    f'<tr><td style="padding:7px 10px;border-bottom:1px solid #d1fae5;color:#065f46;font-weight:600;width:165px;vertical-align:top;">'
                    f'{html.escape(label, quote=True)}</td>'
                    f'<td style="padding:7px 10px;border-bottom:1px solid #d1fae5;color:#0f172a;vertical-align:top;">'
                    f'{html.escape(val, quote=True)}</td></tr>'
                    for label, val in rows
                )

            table_sections = ""
            if part_a_rows:
                table_sections += (
                    '<div style="font-size:12px;font-weight:800;color:#065f46;text-transform:uppercase;letter-spacing:0.4px;margin:8px 0 6px;">'
                    'Thông tin bệnh nhân cung cấp</div>'
                    '<table style="width:100%;border-collapse:collapse;font-size:12.5px;background:#ffffff;border:1px solid #a7f3d0;border-radius:10px;overflow:hidden;">'
                    + _render_rows_html(part_a_rows)
                    + "</table>"
                )
                previsit_text_lines.append("\n--- BẢNG TÓM TẮT TRƯỚC KHÁM ---")
                for lbl, val in part_a_rows:
                    previsit_text_lines.append(f"- {lbl}: {val}")
            if part_b_rows:
                table_sections += (
                    '<div style="font-size:12px;font-weight:800;color:#0369a1;text-transform:uppercase;letter-spacing:0.4px;margin:12px 0 6px;">'
                    'Đánh giá sơ bộ của hệ thống</div>'
                    '<table style="width:100%;border-collapse:collapse;font-size:12.5px;background:#ffffff;border:1px solid #bae6fd;border-radius:10px;overflow:hidden;">'
                    + _render_rows_html(part_b_rows)
                    + "</table>"
                )
                previsit_text_lines.append("\n--- ĐÁNH GIÁ SƠ BỘ ---")
                for lbl, val in part_b_rows:
                    previsit_text_lines.append(f"- {lbl}: {val}")

            previsit_html_block = (
                '<div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:14px;padding:16px 18px;margin:18px 0;">'
                '<div style="font-size:13px;font-weight:800;color:#065f46;margin-bottom:6px;">'
                '📋 Bảng Tóm Tắt Thông Tin Trước Khám (Đính kèm)</div>'
                + (
                    table_sections
                    if table_sections
                    else '<div style="font-size:12px;color:#065f46;">✅ Đã đính kèm bản tóm tắt tiền khám đã xác nhận.</div>'
                )
                + "</div>"
            )

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
        </head>
        <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background-color:#f8fafc;margin:0;padding:20px;">
          <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 10px 25px rgba(15,23,42,0.08);border:1px solid #e2e8f0;">
            <div style="background:linear-gradient(135deg,#0284c7 0%,#2563eb 100%);padding:28px 24px;text-align:center;color:#ffffff;">
              <h1 style="margin:0;font-size:21px;font-weight:800;letter-spacing:-0.3px;">🏥 Xác Nhận Đặt Lịch Khám</h1>
              <p style="margin:6px 0 0;font-size:13px;opacity:0.92;">MediMind Clinical AI • Mã phiếu hẹn {safe_code}</p>
            </div>
            <div style="padding:28px 24px;color:#334155;line-height:1.6;font-size:14px;">
              <p style="margin-top:0;">Kính chào <strong>{safe_patient}</strong>,</p>
              <p>Lịch hẹn khám của bạn đã được ghi nhận thành công trên hệ thống <strong>MediMind Clinical AI</strong>. Dưới đây là thông tin chi tiết phiếu hẹn:</p>

              <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:14px;padding:16px 18px;margin:18px 0;">
                <table style="width:100%;border-collapse:collapse;font-size:13px;">
                  <tr><td style="padding:8px 0;color:#64748b;width:140px;">Mã phiếu hẹn</td><td style="padding:8px 0;color:#0284c7;font-weight:800;">{safe_code}</td></tr>
                  <tr><td style="padding:8px 0;color:#64748b;">Cơ sở y tế</td><td style="padding:8px 0;color:#0f172a;font-weight:700;">{safe_facility}</td></tr>
                  {address_row}
                  <tr><td style="padding:8px 0;color:#64748b;">Chuyên khoa</td><td style="padding:8px 0;color:#0369a1;font-weight:700;">{safe_specialty}</td></tr>
                  <tr><td style="padding:8px 0;color:#64748b;">Ngày khám</td><td style="padding:8px 0;color:#0f172a;font-weight:700;">{safe_date}</td></tr>
                  <tr><td style="padding:8px 0;color:#64748b;">Khung giờ</td><td style="padding:8px 0;color:#b45309;font-weight:700;">{safe_time}</td></tr>
                  <tr><td style="padding:8px 0;color:#64748b;">Bệnh nhân</td><td style="padding:8px 0;color:#0f172a;font-weight:600;">{safe_patient}</td></tr>
                  <tr><td style="padding:8px 0;color:#64748b;">Số điện thoại</td><td style="padding:8px 0;color:#0f172a;font-weight:600;">{safe_phone}</td></tr>
                  {note_row}
                </table>
              </div>

              {previsit_html_block}

              <div style="background:#fffbeb;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:8px;font-size:12px;color:#92400e;margin:18px 0;">
                <strong>⏰ Lưu ý khi đi khám:</strong> Vui lòng có mặt trước giờ hẹn 15 phút và mang theo CCCD/BHYT cùng các đơn thuốc, kết quả xét nghiệm gần nhất (nếu có).
              </div>

              <p style="font-size:12px;color:#64748b;margin-bottom:0;">Bạn có thể xem lại hoặc hủy phiếu hẹn bất cứ lúc nào trong mục <strong>Lịch hẹn của tôi</strong> trên MediMind.</p>
            </div>
            <div style="background:#f8fafc;padding:18px 24px;text-align:center;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;">
              <p style="margin:0;">© 2026 MediMind Clinical AI. Thư xác nhận tự động, vui lòng không trả lời trực tiếp email này.</p>
            </div>
          </div>
        </body>
        </html>
        """

        text = (
            f"Kính chào {raw_patient},\n"
            f"Lịch hẹn khám của bạn đã được xác nhận trên MediMind Clinical AI.\n"
            f"- Mã phiếu hẹn: {appt_code}\n"
            f"- Cơ sở y tế: {raw_facility}\n"
            + (f"- Địa chỉ: {raw_address}\n" if raw_address else "")
            + f"- Chuyên khoa: {raw_specialty}\n"
            f"- Thời gian: {raw_time} ngày {display_date}\n"
            f"- Số điện thoại: {raw_phone}\n"
            + (f"- Ghi chú: {raw_note}\n" if raw_note else "")
            + ("\n".join(previsit_text_lines) + "\n" if previsit_text_lines else "")
            + "\nVui lòng đến sớm 15 phút và mang theo CCCD/BHYT khi đi khám."
        )
        return self.send_email(clean_email, subject, html_body, text)


email_service = EmailService()
