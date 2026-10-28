import os
import time
import json
import logging
import requests
from typing import Dict, Any, List, Optional
from core.prompts import VIETNAMESE_MEDICAL_SYSTEM_PROMPT

logger = logging.getLogger("GeminiService")

class GeminiMedicalService:
    """
    Dịch vụ giao tiếp với Google Gemini API (Gemini 3.5 Flash / 3.8 Flash).
    Hỗ trợ sinh phản hồi tư vấn lâm sàng tự nhiên và phân tầng Triage có cấu trúc.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
        self.endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )

    def is_configured(self) -> bool:
        """Kiểm tra xem Gemini API Key đã được cấu hình hợp lệ chưa."""
        return bool(
            self.api_key
            and not self.api_key.startswith("YOUR_")
            and len(self.api_key) > 20
        )

    def generate_clinical_response(
        self,
        user_message: str,
        history: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Gọi Google Gemini API để phân tích triệu chứng y tế và trả về kết quả có cấu trúc.
        """
        if not self.is_configured():
            print("[⚠️ GEMINI SERVICE] Chưa cấu hình GEMINI_API_KEY. Kích hoạt Fallback Rule-Based Engine.")
            return None

        print(f"\n{'='*60}")
        print(f"[🚀 GEMINI API CALL] Đang gửi yêu cầu tới Google Gemini...")
        print(f" • Model: {self.model}")
        print(f" • Tin nhắn người bệnh: '{user_message}'")
        print(f"{'='*60}")

        start_time = time.time()

        # Định hình System Prompt tăng cường định dạng JSON phản hồi
        instruction_prompt = (
            f"{VIETNAMESE_MEDICAL_SYSTEM_PROMPT}\n\n"
            "BẠN PHẢI TRẢ VỀ DUY NHẤT MỘT JSON OBJECT theo đúng schema sau:\n"
            "{\n"
            '  "answer": "Nội dung phản hồi tư vấn y tế cho người bệnh (bằng Tiếng Việt, định dạng Markdown gạch đầu dòng rõ ràng, thấu cảm, nhắc nhở an toàn)",\n'
            '  "risk_level": "Thấp (Theo dõi) | Trung bình (Cần thăm khám) | Cao (Cần cấp cứu)",\n'
            '  "risk_score": 35,\n'
            '  "symptoms": ["Triệu chứng 1", "Triệu chứng 2"],\n'
            '  "specialist": "Tên chuyên khoa đề xuất (ví dụ: Tai Mũi Họng, Nội tiêu hóa, Nội tổng quát)",\n'
            '  "medications": [\n'
            "    {\n"
            '      "name": "Tên thuốc hoạt chất (ví dụ: Paracetamol)",\n'
            '      "strength": "Hàm lượng (ví dụ: 500mg)",\n'
            '      "category": "Nhóm dược lý",\n'
            '      "type": "OTC (Không kê đơn)",\n'
            '      "instructions": "Hướng dẫn liều dùng an toàn và liều tối đa trong 24h",\n'
            '      "type_badge": "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"\n'
            "    }\n"
            "  ],\n"
            '  "sources": [\n'
            '    {"title": "MedlinePlus Medical Encyclopedia", "source": "NIH National Library of Medicine", "url": "https://medlineplus.gov"},\n'
            '    {"title": "Hướng dẫn chẩn đoán và điều trị Bộ Y Tế", "source": "Bộ Y Tế Việt Nam", "url": "https://kcb.vn"}\n'
            "  ]\n"
            "}\n"
            "TUYỆT ĐỐI KHÔNG DÙNG MARKDOWN CODE BLOCK (```json). CHỈ TRẢ VỀ DUY NHẤT CHUỖI JSON."
        )

        contents = []
        for msg in history[-4:]:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}]
            })

        contents.append({
            "role": "user",
            "parts": [{"text": f"Bệnh nhân báo triệu chứng: {user_message}"}]
        })

        payload = {
            "system_instruction": {
                "parts": [{"text": instruction_prompt}]
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json"
            }
        }

        try:
            response = requests.post(
                f"{self.endpoint}?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=20
            )

            latency = time.time() - start_time

            if response.status_code != 200:
                print(f"[❌ GEMINI ERROR] HTTP {response.status_code} ({latency:.2f}s): {response.text[:200]}")
                return None

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                print(f"[⚠️ GEMINI WARNING] Không có candidates trong phản hồi ({latency:.2f}s).")
                return None

            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            parsed = self._parse_json(raw_text)

            print(f"[✅ GEMINI SUCCESS] HTTP 200 OK | Thời gian phản hồi: {latency:.2f}s")
            print(f" • Chuyên khoa định tuyến: {parsed.get('specialist')}")
            print(f" • Mức độ rủi ro (Risk Score): {parsed.get('risk_score')}/100")
            print(f" • Số lượng thuốc gợi ý: {len(parsed.get('medications', []))}")
            print(f"{'='*60}\n")

            return parsed

        except Exception as e:
            latency = time.time() - start_time
            print(f"[💥 GEMINI EXCEPTION] Lỗi kết nối sau {latency:.2f}s: {e}")
            return None

    def extract_prescription_json(self, cleaned_text: str) -> Optional[Dict[str, Any]]:
        """
        Bóc tách đơn thuốc bằng Gemini API theo schema yêu cầu.
        """
        if not self.is_configured():
            return None

        print(f"\n[🚀 GEMINI PRESCRIPTION] Bắt đầu bóc tách văn bản đơn thuốc qua {self.model}...")
        start_time = time.time()

        prompt = (
            "Bạn là chuyên gia y tế. Hãy đọc văn bản sau và trả về DUY NHẤT một JSON object có cấu trúc: "
            '{"patient_info": {"name": "", "age": ""}, "medications": [{"name": "", "dosage": "", "frequency": "", "instruction": ""}]}. '
            "Không giải thích gì thêm, không dùng markdown code block."
        )

        payload = {
            "contents": [{
                "parts": [{"text": f"{prompt}\n\nVăn bản đơn thuốc:\n{cleaned_text}"}]
            }],
            "generationConfig": {
                "temperature": 0.0,
                "response_mime_type": "application/json"
            }
        }

        try:
            response = requests.post(
                f"{self.endpoint}?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=25
            )

            latency = time.time() - start_time

            if response.status_code != 200:
                print(f"[❌ GEMINI PRESCRIPTION ERROR] HTTP {response.status_code}: {response.text[:200]}")
                return None

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None

            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            parsed = self._parse_json(raw_text)
            print(f"[✅ GEMINI PRESCRIPTION SUCCESS] Hoàn tất bóc tách trong {latency:.2f}s")
            return parsed
        except Exception as e:
            print(f"[💥 GEMINI PRESCRIPTION EXCEPTION] {e}")
            return None

    def _parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        clean_str = text.strip()
        if clean_str.startswith("```"):
            clean_str = clean_str.split("\n", 1)[-1]
            if clean_str.endswith("```"):
                clean_str = clean_str[:-3]
        clean_str = clean_str.strip()

        try:
            return json.loads(clean_str)
        except Exception:
            return None
