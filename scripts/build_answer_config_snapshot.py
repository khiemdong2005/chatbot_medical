import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FILES = [
    "core/chat_service.py",
    "core/gemini_service.py",
    "core/prompts.py",
    "core/rag_service.py",
    "core/triage.py",
    "core/observability.py",
    "evaluation/answer_eval_dataset.json"
]

def file_sha256(rel_path):
    p = ROOT / rel_path
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    hashes = {f: file_sha256(f) for f in FILES}
    
    from core.prompts import VIETNAMESE_MEDICAL_SYSTEM_PROMPT
    prompt_hash = hashlib.sha256(VIETNAMESE_MEDICAL_SYSTEM_PROMPT.encode("utf-8")).hexdigest()

    config = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "2.1 - LLM Answer Quality Evaluation",
        "dataset_version": "v1.0 - 50 curated clinical cases (25 VI, 25 EN)",
        "model": os.getenv("GEMINI_CHAT_MODEL", "gemini-flash-lite-latest"),
        "temperature": 0.25,
        "max_output_tokens": 2400,
        "response_mime_type": "application/json",
        "system_prompt_sha256": prompt_hash,
        "retrieval_config": {
            "retriever": "medical_rag_service.retrieve_context",
            "top_k": 2,
            "max_reference_documents": 4,
            "vector_search_enabled": False,
            "reranker_enabled": False
        },
        "safety_guardrails": {
            "emergency_precheck": "assess_emergency_risk",
            "postcheck": "apply_safety_guardrails",
            "antibiotic_guard": "true",
            "max_history_items": 20,
            "max_message_length": 2000
        },
        "files_sha256": hashes,
        "auth_status": {
            "gemini_api_key_configured": bool(os.getenv("GEMINI_CHAT_API_KEY") or os.getenv("GEMINI_API_KEY")),
            "last_auth_probe": "ClientError 401 UNAUTHENTICATED (ACCESS_TOKEN_TYPE_UNSUPPORTED)"
        },
        "notes": [
            "Generation pipeline is strictly frozen for Phase 2.1 evaluation.",
            "No prompt modifications, model switching, or safety rule loosening are permitted.",
            "If Gemini authentication fails, report BLOCKED_BY_MODEL_AUTHENTICATION and do not fabricate answers."
        ]
    }

    out_path = ROOT / "evaluation" / "answer_phase21_config.json"
    out_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved frozen generation config snapshot to {out_path}")

if __name__ == "__main__":
    main()
