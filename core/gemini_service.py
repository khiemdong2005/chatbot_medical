import os
import time
import json
import logging
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types
from core.prompts import VIETNAMESE_MEDICAL_SYSTEM_PROMPT

logger = logging.getLogger("GeminiService")

class GeminiMedicalService:
    """
    Dịch vụ giao tiếp với Google Gemini API (sử dụng SDK chính thức google-genai).
    Hỗ trợ sinh phản hồi tư vấn lâm sàng tự nhiên và phân tầng Triage có cấu trúc
    kết hợp với cơ chế RAG (Retrieval-Augmented Generation).
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
        self.client = None
        if self.is_configured():
            try:
                self.client = genai.Client(api_key=self.api_key)
                print(f"✅ [GEMINI SERVICE] Đã kết nối thành công Google Gemini SDK (Model: {self.model})")
            except Exception as e:
                print(f"⚠️ [GEMINI SERVICE] Lỗi khởi tạo SDK: {e}")

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
        history: List[Dict[str, Any]],
        rag_docs: Optional[List[Dict[str, Any]]] = None,
        image_bytes: Optional[bytes] = None,
        image_mime_type: str = "image/jpeg"
    ) -> Optional[Dict[str, Any]]:
        """
        Gọi Google Gemini API để phân tích triệu chứng y tế và trả về kết quả có cấu trúc JSON.
        Hỗ trợ Đa phương thức (Multimodal): Phân tích cả văn bản và hình ảnh tổn thương lâm sàng.
        Tích hợp RAG Context từ kho tri thức y khoa để chống ảo giác (Hallucination).
        Tự động fallback sang mô hình Lite nếu mô hình chính tạm thời bận (503).
        """
        if not self.is_configured():
            self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
            if self.is_configured():
                try:
                    self.client = genai.Client(api_key=self.api_key)
                except Exception:
                    pass

        if not self.is_configured() or not self.client:
            print("[⚠️ GEMINI SERVICE] Chưa cấu hình GEMINI_API_KEY. Kích hoạt Fallback Rule-Based Engine.")
            return None

        has_image = bool(image_bytes and len(image_bytes) > 0)
        print(f"\n{'='*60}")
        print(f"[🚀 GEMINI API CALL] Đang gửi yêu cầu tới Google Gemini...")
        print(f" • Model: {self.model}")
        print(f" • Chế độ: {'Multimodal (Kèm ảnh chụp tổn thương)' if has_image else 'Text Only'}")
        print(f" • Tin nhắn người bệnh: '{user_message}'")
        if rag_docs:
            print(f" • Tài liệu RAG đối chiếu: {len(rag_docs)} đoạn trích y khoa")
        print(f"{'='*60}")

        start_time = time.time()

        # Chuẩn bị khối tài liệu RAG nếu có
        rag_context_block = ""
        if rag_docs:
            formatted_chunks = []
            for i, d in enumerate(rag_docs, 1):
                chunk_str = f"--- [Tài liệu {i}: {d.get('title')}] (Nguồn: {d.get('source')}) ---\n{d.get('content')}"
                formatted_chunks.append(chunk_str)
            rag_context_block = (
                "\n\nTÀI LIỆU Y KHOA ĐỐI CHIẾU CHÍNH THỐNG (GROUNDED KNOWLEDGE BASE):\n"
                + "\n\n".join(formatted_chunks)
                + "\n\nBẠN HÃY CĂN CỨ VÀO THÔNG TIN TRONG CÁC TÀI LIỆU TRÊN ĐỂ TƯ VẤN CHO NGƯỜI DÂN MỘT CÁCH CHUẨN XÁC, ẤM ÁP VÀ DỄ HIỂU NHẤT."
            )

        # Định hình System Instruction tăng cường định dạng JSON phản hồi & Thái độ ân cần
        instruction_prompt = (
            f"{VIETNAMESE_MEDICAL_SYSTEM_PROMPT}\n"
            f"{rag_context_block}\n\n"
            "BẠN PHẢI TRẢ VỀ DUY NHẤT MỘT JSON OBJECT theo đúng schema sau:\n"
            "{\n"
            '  "answer": "Nội dung phản hồi tư vấn y tế cho người bệnh (bằng Tiếng Việt, giọng điệu ân cần, đồng cảm, có mở đầu hỏi thăm thấu cảm, các gạch đầu dòng hướng dẫn tại nhà rõ ràng, lưu ý theo dõi và lời chúc mau khỏe ở cuối)",\n'
            '  "visual_findings": ["Đặc điểm thị giác 1 (ví dụ: Dát đỏ ranh giới rõ)", "Đặc điểm 2 (Mụn nước li ti)"],\n'
            '  "differential_diagnosis": ["Tên bệnh lý nghi ngờ 1 (ví dụ: Zona thần kinh)", "Bệnh lý 2 (Viêm da tiếp xúc)"],\n'
            '  "risk_level": "Thấp (Tự chăm sóc & Theo dõi) | Trung bình (Cần thăm khám) | Cao (Cần đi viện)",\n'
            '  "risk_score": 35,\n'
            '  "symptoms": ["Triệu chứng 1", "Triệu chứng 2"],\n'
            '  "specialist": "Tên chuyên khoa đề xuất (ví dụ: Da liễu, Tai Mũi Họng, Nội tiêu hóa, Nội tổng quát)",\n'
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
            '    {"title": "MedlinePlus Medical Encyclopedia", "source": "NIH National Library of Medicine", "url": "https://medlineplus.gov"}\n'
            "  ]\n"
            "}\n"
            "TUYỆT ĐỐI KHÔNG DÙNG MARKDOWN CODE BLOCK (```json). CHỈ TRẢ VỀ DUY NHẤT CHUỖI JSON."
        )

        # Chuẩn bị nội dung hội thoại
        dialogue_text = ""
        for msg in history[-4:]:
            role_label = "Bệnh nhân" if msg.get("role") == "user" else "Trợ lý MediMind"
            dialogue_text += f"{role_label}: {msg.get('content', '')}\n"

        if has_image:
            image_note = "[BỆNH NHÂN GỬI KÈM 1 BỨC ẢNH VÙNG TỔN THƯƠNG / TRIỆU CHỨNG LÂM SÀNG]"
            prompt_content = f"{dialogue_text}Bệnh nhân: {image_note} {user_message}\nTrợ lý MediMind (Quan sát kỹ ảnh, phân tích hình thái học, chẩn đoán phân biệt và trả về JSON có lời hỏi thăm ân cần):"
            try:
                image_part = types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type)
                req_contents = [image_part, prompt_content]
            except Exception as e_part:
                print(f"⚠️ Lỗi tạo image part: {e_part}. Chuyển sang text.")
                req_contents = prompt_content
        else:
            prompt_content = f"{dialogue_text}Bệnh nhân: {user_message}\nTrợ lý MediMind (Trả về JSON có lời hỏi thăm ân cần):"
            req_contents = prompt_content

        try:
            config = types.GenerateContentConfig(
                system_instruction=instruction_prompt,
                temperature=0.3,
                response_mime_type="application/json"
            )

            # Thử gọi model chính, nếu 503 tự động chuyển sang model lite
            try:
                res = self.client.models.generate_content(
                    model=self.model,
                    contents=req_contents,
                    config=config
                )
            except Exception as e_first:
                err_str = str(e_first)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    print(f"[🔄 GEMINI RETRY] {self.model} tạm thời bận, tự động chuyển sang gemini-3.5-flash-lite...")
                    res = self.client.models.generate_content(
                        model="gemini-3.5-flash-lite",
                        contents=req_contents,
                        config=config
                    )
                else:
                    raise e_first

            latency = time.time() - start_time
            raw_text = res.text or ""
            parsed = self._parse_json(raw_text)

            # Cập nhật danh sách nguồn trích dẫn thật từ RAG nếu có
            if rag_docs and parsed:
                parsed["sources"] = [
                    {
                        "title": d.get("title", "MedlinePlus"),
                        "source": d.get("source", "MedlinePlus"),
                        "url": d.get("source_url", "https://medlineplus.gov")
                    }
                    for d in rag_docs
                ]

            print(f"[✅ GEMINI SUCCESS] HTTP 200 OK | Thời gian phản hồi: {latency:.2f}s")
            print(f" • Chuyên khoa định tuyến: {parsed.get('specialist')}")
            print(f" • Mức độ rủi ro (Risk Score): {parsed.get('risk_score')}/100")
            print(f" • Số lượng nguồn trích dẫn: {len(parsed.get('sources', []))}")
            if parsed.get("visual_findings"):
                print(f" • Nhận định thị giác: {parsed.get('visual_findings')}")
            print(f"{'='*60}\n")

            return parsed

        except Exception as e:
            latency = time.time() - start_time
            print(f"[💥 GEMINI EXCEPTION] Lỗi kết nối sau {latency:.2f}s: {e}")
            return None

    def _parse_json(self, raw_text: str) -> Dict[str, Any]:
        """Bóc tách chuỗi JSON trả về phòng thủ (Defensive JSON Parser)."""
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except Exception:
            return {
                "answer": text,
                "risk_level": "Trung bình (Cần thăm khám)",
                "risk_score": 40,
                "symptoms": ["Triệu chứng chung"],
                "specialist": "Nội tổng quát",
                "medications": [],
                "sources": [
                    {
                        "title": "MedlinePlus Medical Encyclopedia",
                        "source": "NIH National Library of Medicine",
                        "url": "https://medlineplus.gov"
                    }
                ]
            }
