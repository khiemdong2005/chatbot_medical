"""Compare two OpenRouter vision models through the MediMind chat pipeline."""

import argparse
import base64
import json
import os
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Original image to send to both models")
    parser.add_argument("--question", default="Đây có thể là tình trạng gì?")
    parser.add_argument("--models", nargs=2, default=[
        "nvidia/nemotron-3.5-super-vl:free", "google/gemini-2.5-flash",
    ])
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    os.environ["AI_PROVIDER"] = "openrouter"
    from core.llm_provider import llm_provider

    key = llm_provider.resolve_api_key(profile="chat")
    if not key.startswith("sk-or-"):
        parser.error("Set OPENROUTER_CHAT_API_KEY or OPENROUTER_API_KEY before running the comparison.")

    from core.chat_service import process_clinical_chat
    from core.gemini_service import GeminiMedicalService
    from core.storage_service import decode_and_validate_base64_image

    try:
        encoded = base64.b64encode(args.image.read_bytes()).decode("ascii")
    except OSError as error:
        parser.error(str(error))
    mime_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                 ".webp": "image/webp"}.get(args.image.suffix.lower(), "application/octet-stream")
    image, mime_type, error = decode_and_validate_base64_image(f"data:{mime_type};base64,{encoded}")
    if error:
        parser.error(error)

    class ComparisonService(GeminiMedicalService):
        first_response = None
        first_attempt_finished = False

        def generate_clinical_response(self, *args, **kwargs):
            response = super().generate_clinical_response(*args, **kwargs)
            if not self.first_attempt_finished:
                self.first_response = response
                self.first_attempt_finished = True
            return response

    results = []
    for model in args.models:
        service = ComparisonService(api_key=key)
        with patch.dict(os.environ, {"OPENROUTER_CHAT_VISION_MODEL": model}):
            result = process_clinical_chat(
                args.question, image_bytes=image, image_mime_type=mime_type,
                gemini_service=service, lang="vi", consultation_mode="informational",
            )
        results.append({
            "model": model,
            "before_rag": service.first_response,
            "final": {field: result.get(field) for field in (
                "answer", "sources", "grounding_status", "degraded", "ai_error_code",
            )},
        })
    print(json.dumps(results, ensure_ascii=True, indent=2))
    return int(any(item["final"]["degraded"] for item in results))


if __name__ == "__main__":
    raise SystemExit(main())
