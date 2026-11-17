# ==============================================================
# MEDIMIND CLINICAL AI - SMS OTP GATEWAY SERVICE
# Hỗ trợ cổng SMS SpeedSMS (Việt Nam) & Chế độ Dev Simulator
# ĐÃ LOẠI BỎ HOÀN TOÀN TWILIO SMS API (CỔNG QUỐC TẾ) - CHỈ HỖ TRỢ NỘI ĐỊA
# ==============================================================

import os
import re
from typing import Optional, Dict, Any


class SmsService:
    """Dịch vụ gửi SMS OTP giao dịch y tế nội địa Việt Nam."""
    def __init__(self):
        # SpeedSMS Provider (Cổng SMS Việt Nam)
        self.speedsms_token = os.getenv("SPEEDSMS_AUTH_TOKEN", "")

    def is_configured(self) -> bool:
        """Kiểm tra cấu hình cổng SMS nội địa."""
        return bool(self.speedsms_token)

    def normalize_phone(self, phone: str) -> Optional[str]:
        """
        Chuẩn hóa số điện thoại về định dạng E.164 Việt Nam (+84...).
        CHỈ HỖ TRỢ ĐẦU SỐ VIỆT NAM (03, 05, 07, 08, 09 hoặc +84).
        Chặn toàn bộ số điện thoại quốc tế.
        """
        cleaned = re.sub(r"[^\d+]", "", phone.strip())
        if cleaned.startswith("+84"):
            digits = cleaned[3:]
        elif cleaned.startswith("84") and len(cleaned) in (11, 12):
            digits = cleaned[2:]
        elif cleaned.startswith("0"):
            digits = cleaned[1:]
        else:
            digits = cleaned

        # Kiểm tra 9 chữ số thuê bao di động VN hợp lệ (bắt đầu bằng 3, 5, 7, 8, 9)
        if len(digits) == 9 and digits[0] in "35789":
            return f"+84{digits}"

        return None

    def send_otp_sms(self, to_phone: str, otp_code: str, brand_name: str = "MediMind AI") -> bool:
        """
        Gửi mã OTP qua tin nhắn SMS tới số điện thoại nội địa Việt Nam.
        Chặn toàn bộ số quốc tế và đã loại bỏ hoàn toàn cổng Twilio SMS quốc tế.
        Nếu chưa cấu hình SpeedSMS token, chạy chế độ Dev Simulator in ra console.
        """
        norm_phone = self.normalize_phone(to_phone)
        if not norm_phone:
            print(f"⚠️ [SMS Service] Từ chối gửi SMS: Số '{to_phone}' không phải số di động Việt Nam (+84). Hệ thống đã chặn gửi OTP quốc tế.")
            return False

        message_text = f"[{brand_name}] Ma xac thuc y te (OTP) cua ban la: {otp_code}. Hieu luc trong 5 phut. Tuyet doi khong chia se cho nguoi khac."

        # Chế độ Dev Simulator khi chưa có API Key
        if not self.is_configured():
            print("\n" + "=" * 70)
            print(f"📱 [DEV SMS SIMULATOR - VN ONLY] Gửi tới SĐT: {norm_phone}")
            print(f"🔑 Mã OTP 6 số: {otp_code}")
            print(f"💬 Tin nhắn: {message_text}")
            print("=" * 70 + "\n")
            return True

        # Gửi qua SpeedSMS nếu có Token (Cổng SMS Việt Nam)
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
                    else:
                        print(f"❌ [SpeedSMS Error] Phản hồi lỗi: {res_json}")
            except Exception as e:
                print(f"❌ [SpeedSMS Error] Gửi SMS thất bại tới {norm_phone}: {e}")

        return False


sms_service = SmsService()
