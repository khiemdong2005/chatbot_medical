# ==============================================================
# MEDIMIND CLINICAL AI - SMS OTP GATEWAY SERVICE
# Hỗ trợ cổng SMS Twilio, SpeedSMS (Việt Nam) & Chế độ Dev Simulator
# ==============================================================

import os
import re
from typing import Optional, Dict, Any


class SmsService:
    """Dịch vụ gửi SMS OTP giao dịch y tế."""
    def __init__(self):
        # Twilio Provider
        self.twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from = os.getenv("TWILIO_PHONE_NUMBER", "")

        # SpeedSMS Provider (Việt Nam)
        self.speedsms_token = os.getenv("SPEEDSMS_AUTH_TOKEN", "")

    def is_configured(self) -> bool:
        return bool((self.twilio_sid and self.twilio_token and self.twilio_from) or self.speedsms_token)

    def normalize_phone(self, phone: str) -> str:
        """Chuẩn hóa số điện thoại về định dạng E.164 (+84...)"""
        cleaned = re.sub(r"[^\d+]", "", phone.strip())
        if cleaned.startswith("0") and len(cleaned) == 10:
            cleaned = "+84" + cleaned[1:]
        elif not cleaned.startswith("+") and len(cleaned) >= 9:
            cleaned = "+84" + cleaned
        return cleaned

    def send_otp_sms(self, to_phone: str, otp_code: str, brand_name: str = "MediMind AI") -> bool:
        """
        Gửi mã OTP qua tin nhắn SMS tới số điện thoại người bệnh.
        Nếu chưa cấu hình SMS Gateway bên thứ ba, chạy chế độ Dev Simulator in ra console.
        """
        norm_phone = self.normalize_phone(to_phone)
        message_text = f"[{brand_name}] Ma xac thuc y te (OTP) cua ban la: {otp_code}. Hieu luc trong 5 phut. Tuyet doi khong chia se cho nguoi khac."

        # Chế độ Dev Simulator khi chưa có API Key
        if not self.is_configured():
            print("\n" + "=" * 70)
            print(f"📱 [DEV SMS SIMULATOR] Gửi tới SĐT: {norm_phone}")
            print(f"🔑 Mã OTP 6 số: {otp_code}")
            print(f"💬 Tin nhắn: {message_text}")
            print("=" * 70 + "\n")
            return True

        # Gửi qua Twilio nếu được cấu hình
        if self.twilio_sid and self.twilio_token and self.twilio_from:
            try:
                import urllib.parse
                import urllib.request
                import base64

                url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_sid}/Messages.json"
                auth = base64.b64encode(f"{self.twilio_sid}:{self.twilio_token}".encode("utf-8")).decode("ascii")
                data = urllib.parse.urlencode({
                    "From": self.twilio_from,
                    "To": norm_phone,
                    "Body": message_text
                }).encode("utf-8")

                req = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {auth}"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status in (200, 201):
                        print(f"✅ [Twilio SMS] Đã gửi mã OTP tới {norm_phone}")
                        return True
            except Exception as e:
                print(f"❌ [Twilio SMS Error] Gửi SMS thất bại tới {norm_phone}: {e}")

        # Gửi qua SpeedSMS nếu có Token
        if self.speedsms_token:
            try:
                import json
                import urllib.request
                import base64

                url = "https://api.speedsms.vn/index.php/sms/send"
                auth = base64.b64encode(f"{self.speedsms_token}:x".encode("utf-8")).decode("ascii")
                payload = json.dumps({
                    "to": [norm_phone],
                    "content": message_text,
                    "sms_type": 2
                }).encode("utf-8")

                req = urllib.request.Request(url, data=payload, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {auth}"
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    if res_json.get("status") == "success":
                        print(f"✅ [SpeedSMS] Đã gửi mã OTP tới {norm_phone}")
                        return True
            except Exception as e:
                print(f"❌ [SpeedSMS Error] Gửi SMS thất bại tới {norm_phone}: {e}")

        return False


sms_service = SmsService()
