import os
import time
import json
import uuid
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
                logger.info(f"✅ [GEMINI SERVICE] Kết nối thành công Gemini SDK (Model: {self.model})")
            except Exception as e:
                logger.warning(f"⚠️ [GEMINI SERVICE] Lỗi khởi tạo SDK: {e}")

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
        lang: str = "vi",
        request_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Gọi Google Gemini API để phân tích triệu chứng y tế và trả về kết quả có cấu trúc JSON.
        - Không log thông tin sức khỏe cá nhân (PHI) của người bệnh.
        - Kiểm chứng schema JSON chặt chẽ; JSON hỏng/thiếu trường bắt buộc sẽ trả None để kích hoạt fallback.
        """
        req_id = request_id or uuid.uuid4().hex[:8]
        if not self.is_configured():
            self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
            if self.is_configured():
                try:
                    self.client = genai.Client(api_key=self.api_key)
                except Exception:
                    pass

        if not self.is_configured() or not self.client:
            logger.info(f"[REQ-{req_id}] GEMINI_API_KEY chưa cấu hình hoặc không sẵn sàng. Chuyển Fallback.")
            return None

        has_image = bool(image_bytes and len(image_bytes) > 0)
        start_time = time.time()
        logger.info(f"[REQ-{req_id}] Gửi yêu cầu Gemini | Model: {self.model} | Multimodal: {has_image} | Lang: {lang}")

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
                logger.warning(f"[REQ-{req_id}] Lỗi tạo image part: {e_part}. Chuyển sang text.")
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
                    logger.warning(f"[REQ-{req_id}] Model {model_name} không khả dụng ({type(m_err).__name__}). Đang thử model tiếp theo...")

            if not res or not res.text:
                raise last_err or RuntimeError("Không thể nhận phản hồi từ mô hình Gemini.")

            latency = time.time() - start_time
            raw_text = res.text or ""
            parsed = self._validate_and_parse_json(raw_text)

            if parsed is None:
                logger.warning(f"[REQ-{req_id}] Phản hồi từ Gemini không vượt qua schema validation. Chuyển Fallback.")
                return None

            # Cập nhật danh sách nguồn trích dẫn thật từ RAG nếu có
            if rag_docs:
                parsed["sources"] = [
                    {
                        "title": d.get("title", "MedlinePlus"),
                        "source": d.get("source", "MedlinePlus"),
                        "url": d.get("source_url", "https://medlineplus.gov")
                    }
                    for d in rag_docs
                ]

            # Đảm bảo không bịa visual_findings nếu không có ảnh
            if not has_image:
                parsed["visual_findings"] = []

            logger.info(f"[REQ-{req_id}] Gemini thành công | Latency: {latency:.2f}s | Specialist: {parsed.get('specialist')}")
            return parsed

        except Exception as e:
            latency = time.time() - start_time
            logger.warning(f"[REQ-{req_id}] Gemini lỗi sau {latency:.2f}s: {e}")
            return None

    def _validate_and_parse_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        Kiểm chứng cấu trúc JSON theo Schema chuẩn y tế.
        - Trả về None nếu JSON hỏng hoặc thiếu trường bắt buộc 'answer'.
        - Chuẩn hóa và giới hạn risk_score trong khoảng 0..100.
        - Không mặc định thành kết quả nguy cơ thấp nếu dữ liệu không hợp lệ.
        """
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        # Trường bắt buộc phải có và không rỗng
        answer = data.get("answer")
        if not answer or not isinstance(answer, str) or not answer.strip():
            return None

        # Chuẩn hóa risk_score: phải nằm trong 0..100
        raw_score = data.get("risk_score")
        try:
            score = int(raw_score)
            clamped_score = max(0, min(100, score))
        except (ValueError, TypeError):
            clamped_score = 30
        data["risk_score"] = clamped_score

        # Chuẩn hóa các trường danh sách
        for list_field in ["visual_findings", "differential_diagnosis", "symptoms", "home_care_tips"]:
            if not isinstance(data.get(list_field), list):
                data[list_field] = []

        if not isinstance(data.get("sources"), list):
            data["sources"] = []

        return data
