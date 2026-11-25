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
        self._refresh_config()

    def _refresh_config(self) -> None:
        # SpeedSMS Provider (Cổng SMS Việt Nam)
        self.speedsms_token = os.getenv("SPEEDSMS_AUTH_TOKEN", "").strip()
        self.speedsms_sms_type = int(os.getenv("SPEEDSMS_SMS_TYPE", "2") or 2)
        self.speedsms_sender = os.getenv("SPEEDSMS_SENDER", "").strip()

    @staticmethod
    def _is_production() -> bool:
        env_val = (os.getenv("ENV") or os.getenv("FLASK_ENV") or "").strip().lower()
        return env_val in ("production", "prod")

    def is_configured(self) -> bool:
        """Kiểm tra cấu hình cổng SMS nội địa."""
        self._refresh_config()
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

    def send_otp_sms(
        self,
        to_phone: str,
        otp_code: str,
        brand_name: str = "MediMind AI",
        ttl_seconds: int = 120,
    ) -> bool:
        """
        Gửi mã OTP qua tin nhắn SMS tới số điện thoại nội địa Việt Nam.
        Chặn toàn bộ số quốc tế và fail-closed khi ENV=production mà chưa cấu hình SpeedSMS.
        Ở local dev khi chưa có API Key, in mã OTP ra terminal.
        """
        norm_phone = self.normalize_phone(to_phone)
        if not norm_phone:
            print(f"⚠️ [SMS Service] Từ chối gửi SMS: Số '{to_phone}' không phải số di động Việt Nam (+84). Hệ thống đã chặn gửi OTP quốc tế.")
            return False

        ttl_min = max(1, int(ttl_seconds or 120) // 60)
        message_text = f"[{brand_name}] Ma xac thuc y te (OTP) cua ban la: {otp_code}. Hieu luc trong {ttl_min} phut. Tuyet doi khong chia se cho nguoi khac."

        # Chế độ Dev Simulator khi chưa có API Key (chặn ở Production)
        if not self.is_configured():
            if self._is_production():
                print("❌ [SMS Service] Production mode: SpeedSMS chưa được cấu hình. Đã chặn Dev Simulator (fail-closed).")
                return False
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
                effective_sender = "" if self.speedsms_sms_type == 2 else self.speedsms_sender
                payload_dict: Dict[str, Any] = {
                    "to": [norm_phone.lstrip("+")],
                    "content": message_text,
                    "sms_type": self.speedsms_sms_type,
                    "sender": effective_sender
                }
                payload = json.dumps(payload_dict).encode("utf-8")

                req = urllib.request.Request(url, data=payload, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {auth}"
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    if res_json.get("status") == "success":
                        data_info = res_json.get("data") or {}
                        tran_id = data_info.get("tranId")
                        total_sms = data_info.get("totalSMS")
                        total_price = data_info.get("totalPrice")
                        print(f"✅ [SpeedSMS] Đã gửi mã OTP tới {norm_phone} | tranId={tran_id} | totalSMS={total_sms} | totalPrice={total_price}")
                        return True
                    else:
                        print(f"❌ [SpeedSMS Error] Phản hồi lỗi: {res_json}")
            except Exception as e:
                print(f"❌ [SpeedSMS Error] Gửi SMS thất bại tới {norm_phone}: {e}")

        return False


sms_service = SmsService()
