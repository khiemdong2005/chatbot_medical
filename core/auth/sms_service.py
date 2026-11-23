# ==============================================================
# MEDIMIND CLINICAL AI - SMS OTP GATEWAY SERVICE
# Hỗ trợ cổng SMS SpeedSMS (Việt Nam) & Chế độ Dev Simulator
# ĐÃ LOẠI BỎ HOÀN TOÀN TWILIO SMS API (CỔNG QUỐC TẾ) - CHỈ HỖ TRỢ NỘI ĐỊA
# ==============================================================

import os
import re
import logging
from typing import Optional, Dict, Any
from core.settings import is_configured_secret

logger = logging.getLogger("SmsService")


class SmsService:
    """Dịch vụ gửi SMS OTP giao dịch y tế nội địa Việt Nam."""
    def __init__(self):
        # SpeedSMS Provider (Cổng SMS Việt Nam)
        self.speedsms_token = os.getenv("SPEEDSMS_AUTH_TOKEN", "").strip()
        self.speedsms_sms_type = int(os.getenv("SPEEDSMS_SMS_TYPE", "2"))
        self.speedsms_sender = os.getenv("SPEEDSMS_SENDER", "").strip()

    def is_configured(self) -> bool:
        """Kiểm tra cấu hình cổng SMS nội địa (loại trừ giá trị placeholder mẫu)."""
        return is_configured_secret(self.speedsms_token)

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

        allow_sim = (
            os.getenv("ALLOW_DEV_OTP_SIMULATOR", "").lower() in ("1", "true", "yes")
            or os.getenv("TESTING", "").lower() in ("1", "true", "yes")
        )
        # Chế độ Simulator chỉ kích hoạt khi TESTING hoặc ALLOW_DEV_OTP_SIMULATOR=1 (không in plaintext OTP mặc định)
        if not self.is_configured():
            if allow_sim:
                logger.info("[SMS Service] Test/simulator mode active; SMS OTP delivery simulated.")
                return True
            logger.warning("[SMS Service] SpeedSMS chưa được cấu hình (CONFIGURATION REQUIRED: SPEEDSMS_AUTH_TOKEN).")
            return False

        # Gửi qua SpeedSMS nếu có Token (Cổng SMS Việt Nam)
        if self.speedsms_token:
            if self.speedsms_sms_type != 2 and not self.speedsms_sender:
                logger.warning(
                    "[SMS Service] CONFIGURATION REQUIRED: SPEEDSMS_SENDER is required when SPEEDSMS_SMS_TYPE=%s.",
                    self.speedsms_sms_type,
                )
                return False
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
                        logger.info("[SpeedSMS] Sent SMS OTP | tranId=%s | totalSMS=%s | totalPrice=%s", tran_id, total_sms, total_price)
                        return True
                    logger.warning("[SpeedSMS Error] Delivery rejected (status=%s).", res_json.get("status"))
            except Exception as e:
                logger.warning("[SpeedSMS Error] Gửi SMS thất bại (%s).", type(e).__name__)

        return False


sms_service = SmsService()
