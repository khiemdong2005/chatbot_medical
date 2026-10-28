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
        image_mime_type: str = "image/jpeg",
        lang: str = "vi"
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
        is_en = (lang == "en")
        lang_directive = (
            "LANGUAGE REQUIREMENT:\n"
            "- YOU MUST RESPOND COMPLETELY IN ENGLISH.\n"
            "- All values in the JSON (answer, visual_findings, differential_diagnosis, specialist, home_care_tips) MUST BE IN ENGLISH.\n\n"
            if is_en else ""
        )
        answer_desc = (
            "Medical consultation response for patient (in fluent English, warm, empathetic tone, beginning with supportive acknowledgment, bulleted evidence-based non-pharmacological home care guidance, monitoring instructions, and well wishes at the end)"
            if is_en else
            "Nội dung phản hồi tư vấn y tế cho người bệnh (bằng Tiếng Việt, giọng điệu ân cần, đồng cảm, có mở đầu hỏi thăm thấu cảm, các gạch đầu dòng hướng dẫn chăm sóc tại nhà an toàn không dùng thuốc, lưu ý theo dõi và lời chúc mau khỏe ở cuối)"
        )

        instruction_prompt = (
            f"{VIETNAMESE_MEDICAL_SYSTEM_PROMPT}\n"
            f"{rag_context_block}\n\n"
            f"{lang_directive}"
            "NGUYÊN TẮC Y ĐỨC BẮT BUỘC / MEDICAL ETHICS:\n"
            "- DO NOT PRESCRIBE MEDICATIONS or specific dosages. Recommend safe non-pharmacological care (hydration, rest, cooling compresses, hygiene).\n"
            "- Advise patient to consult a licensed physician or pharmacist if symptoms persist.\n\n"
            "RETURN ONLY A SINGLE JSON OBJECT strictly matching this schema:\n"
            "{\n"
            f'  "answer": "{answer_desc}",\n'
            '  "visual_findings": ["Visual observation 1", "Visual observation 2"],\n'
            '  "differential_diagnosis": ["Suspected condition 1", "Condition 2"],\n'
            '  "risk_level": "Low (Self-care & Monitor) | Medium (Doctor visit recommended) | High (Hospital visit)",\n'
            '  "risk_score": 35,\n'
            '  "symptoms": ["Symptom 1", "Symptom 2"],\n'
            '  "specialist": "Recommended clinical specialty (e.g. Dermatology, ENT, Internal Medicine)",\n'
            '  "home_care_tips": ["Safe home care tip 1", "Tip 2"],\n'
            '  "sources": [\n'
            '    {"title": "MedlinePlus Medical Encyclopedia", "source": "NIH National Library of Medicine", "url": "https://medlineplus.gov"}\n'
            '  ]\n'
            "}\n"
            "DO NOT WRAP IN MARKDOWN CODE BLOCKS. RETURN RAW JSON ONLY."
        )

        # Chuẩn bị nội dung hội thoại
        dialogue_text = ""
        p_label = "Patient" if is_en else "Bệnh nhân"
        a_label = "MediMind Assistant" if is_en else "Trợ lý MediMind"
        for msg in history[-4:]:
            role_label = p_label if msg.get("role") == "user" else a_label
            dialogue_text += f"{role_label}: {msg.get('content', '')}\n"

        if has_image:
            image_note = "[PATIENT ATTACHED 1 CLINICAL LESION IMAGE]" if is_en else "[BỆNH NHÂN GỬI KÈM 1 BỨC ẢNH VÙNG TỔN THƯƠNG / TRIỆU CHỨNG LÂM SÀNG]"
            prompt_suffix = "Carefully examine lesion, morphological features, differential diagnosis and return JSON in English with empathetic tone" if is_en else "Quan sát kỹ ảnh, phân tích hình thái học, chẩn đoán phân biệt và trả về JSON có lời hỏi thăm ân cần"
            prompt_content = f"{dialogue_text}{p_label}: {image_note} {user_message}\n{a_label} ({prompt_suffix}):"
            try:
                image_part = types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type)
                req_contents = [image_part, prompt_content]
            except Exception as e_part:
                print(f"⚠️ Lỗi tạo image part: {e_part}. Chuyển sang text.")
                req_contents = prompt_content
        else:
            prompt_suffix = "Return JSON in English with empathetic guidance" if is_en else "Trả về JSON có lời hỏi thăm ân cần"
            prompt_content = f"{dialogue_text}{p_label}: {user_message}\n{a_label} ({prompt_suffix}):"
            req_contents = prompt_content

        try:
            config = types.GenerateContentConfig(
                system_instruction=instruction_prompt,
                temperature=0.3,
                response_mime_type="application/json"
            )

            # Thử gọi model chính; nếu gặp 429 (hết quota), 503 hoặc 404 thì tự động chuyển sang model dự phòng
            candidate_models = [self.model, "gemini-flash-latest", "gemini-3.8-flash", "gemini-3.7-flash"]
            models_to_try = []
            for m in candidate_models:
                if m and m not in models_to_try:
                    models_to_try.append(m)

            res = None
            last_err = None
            for model_name in models_to_try:
                try:
                    res = self.client.models.generate_content(
                        model=model_name,
                        contents=req_contents,
                        config=config
                    )
                    if res and res.text:
                        break
                except Exception as m_err:
                    last_err = m_err
                    print(f"[🔄 GEMINI FALLBACK] Model {model_name} không khả dụng ({type(m_err).__name__}). Đang thử model tiếp theo...")

            if not res or not res.text:
                raise last_err or RuntimeError("Không thể nhận phản hồi từ bất kỳ mô hình Gemini nào.")

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
