"""Lightweight, safe health-check for Gemini API connectivity and authentication.

Classifies results into:
  - AUTH_OK
  - INVALID_API_KEY
  - UNSUPPORTED_AUTH_METHOD
  - SDK_INCOMPATIBILITY
  - MODEL_NOT_FOUND
  - PERMISSION_DENIED
  - NETWORK_ERROR
  - UNKNOWN_ERROR

Never logs or prints API keys or tokens.
"""
import os
import re
import sys
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def validate_credential_format(key: Optional[str]) -> Tuple[bool, str, str]:
    """Basic format sanity check without exposing secret.
    
    Accepts any format (including modern AQ-prefixed authorization keys or legacy AIza keys).
    Only rejects missing, placeholder, or obviously malformed keys.
    """
    if not key or not str(key).strip():
        return False, "MISSING_KEY", "GEMINI_API_KEY is missing or empty."
    clean = str(key).strip()
    if clean.startswith("YOUR_") or clean == "your_google_gemini_api_key_here":
        return False, "PLACEHOLDER_KEY", "GEMINI_API_KEY is an unfilled template placeholder."
    if any(c.isspace() for c in clean):
        return False, "MALFORMED_KEY", "GEMINI_API_KEY contains invalid whitespace."
    if not clean.isascii():
        return False, "MALFORMED_KEY", "GEMINI_API_KEY contains non-ASCII characters."
    if len(clean) < 10:
        return False, "MALFORMED_KEY", "GEMINI_API_KEY is too short to be a valid API key."
    return True, "VALID_FORMAT", "Use a Gemini API key / Authentication Key issued by Google AI Studio."


def classify_gemini_error(exc: Exception) -> Tuple[str, str]:
    """Classify error into distinct diagnostic categories without leaking secret data."""
    err_type = type(exc).__name__
    err_msg = str(exc)

    if isinstance(exc, (ImportError, AttributeError)):
        return "SDK_INCOMPATIBILITY", f"SDK import or module incompatibility: {err_type}"

    if "ACCESS_TOKEN_TYPE_UNSUPPORTED" in err_msg:
        return "UNSUPPORTED_AUTH_METHOD", (
            "Gemini Developer API rejected credential: ACCESS_TOKEN_TYPE_UNSUPPORTED. "
            "The authorization key was passed to generativelanguage.googleapis.com but the endpoint "
            "reported an unsupported token type."
        )

    if "API_KEY_SERVICE_BLOCKED" in err_msg:
        return "UNSUPPORTED_AUTH_METHOD", (
            "Gemini Developer API rejected credential: API_KEY_SERVICE_BLOCKED. "
            "The credential may be restricted or blocked for this service."
        )

    if "404" in err_msg or "NOT_FOUND" in err_msg or "is not found" in err_msg or "models/" in err_msg and "not found" in err_msg.lower():
        return "MODEL_NOT_FOUND", f"Model not found on current API path ({err_type})."

    if "403" in err_msg or "PERMISSION_DENIED" in err_msg:
        return "PERMISSION_DENIED", f"Permission denied for this key or project ({err_type}: 403)."

    if "401" in err_msg or "UNAUTHENTICATED" in err_msg or "API key not valid" in err_msg:
        return "INVALID_API_KEY", f"Gemini API authentication failed (401 UNAUTHENTICATED): {err_type}."

    if any(term in err_type for term in ("Timeout", "Connect", "Network")) or any(term in err_msg for term in ("DNS", "NameResolution", "Connection refused")):
        return "NETWORK_ERROR", f"Network connectivity error reaching Google Gemini API ({err_type})."

    return "UNKNOWN_ERROR", f"Unexpected error during Gemini API request ({err_type})."


def probe_single_client(client, target_model: str) -> Tuple[str, str, Optional[str]]:
    """Test harmless generation. Returns (status, message, text_or_none)."""
    try:
        res = client.models.generate_content(
            model=target_model,
            contents="Return exactly OK."
        )
        if res and res.text:
            return "AUTH_OK", "Success", res.text.strip()
        return "UNKNOWN_ERROR", "Received empty response from Gemini API.", None
    except Exception as exc:
        status, msg = classify_gemini_error(exc)
        return status, msg, None


def check_gemini_connection(model: Optional[str] = None) -> Dict[str, Any]:
    """Execute diagnostic probe covering explicit key vs default env and model availability."""
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    target_model = (model or os.getenv("GEMINI_CHAT_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-flash-lite-latest").strip()

    valid, code, reason = validate_credential_format(key)
    if not valid:
        return {
            "status": "INVALID_API_KEY" if code == "PLACEHOLDER_KEY" else "AUTH_FAILED",
            "classification": code,
            "model": target_model,
            "model_status": "UNKNOWN",
            "message": f"Gemini API authentication check failed: {reason}",
            "auth_ok": False,
            "explicit_client_result": "NOT_RUN",
            "default_env_client_result": "NOT_RUN",
            "credential_present": bool(key)
        }

    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        status, msg = classify_gemini_error(e)
        return {
            "status": status,
            "classification": status,
            "model": target_model,
            "model_status": "UNKNOWN",
            "message": msg,
            "auth_ok": False,
            "explicit_client_result": "SDK_ERROR",
            "default_env_client_result": "SDK_ERROR",
            "credential_present": True
        }

    # Test Mode A: Explicit client initialization
    http_opts = types.HttpOptions(timeout=10000, retry_options=types.HttpRetryOptions(attempts=1))
    try:
        explicit_client = genai.Client(api_key=key, http_options=http_opts)
        status_a, msg_a, text_a = probe_single_client(explicit_client, target_model)
    except Exception as exc:
        status_a, msg_a = classify_gemini_error(exc)
        text_a = None

    # Test Mode B: SDK default environment loading
    try:
        default_client = genai.Client(http_options=http_opts)
        status_b, msg_b, text_b = probe_single_client(default_client, target_model)
    except Exception as exc:
        status_b, msg_b = classify_gemini_error(exc)
        text_b = None

    # Separate authentication check from model availability
    if status_a == "MODEL_NOT_FOUND":
        # Diagnostic check: attempt harmless model or list to verify if auth actually succeeded
        try:
            # Diagnostic fallback model check
            diag_model = "gemini-1.5-flash"
            res_diag = explicit_client.models.generate_content(model=diag_model, contents="Return exactly OK.")
            if res_diag and res_diag.text:
                return {
                    "status": "AUTH_OK",
                    "classification": "AUTH_OK",
                    "model": target_model,
                    "model_status": "MODEL_NOT_AVAILABLE",
                    "message": f"Authentication succeeded, but production model '{target_model}' is not available. (Diagnostic model '{diag_model}' succeeded).",
                    "auth_ok": True,
                    "explicit_client_result": f"AUTH_OK (MODEL_NOT_AVAILABLE on {target_model})",
                    "default_env_client_result": status_b,
                    "credential_present": True
                }
        except Exception:
            pass

    overall_status = status_a
    auth_ok = (overall_status == "AUTH_OK")

    return {
        "status": overall_status,
        "classification": overall_status,
        "model": target_model,
        "model_status": "MODEL_OK" if auth_ok else ("MODEL_NOT_AVAILABLE" if overall_status == "MODEL_NOT_FOUND" else "UNKNOWN"),
        "message": msg_a,
        "auth_ok": auth_ok,
        "explicit_client_result": status_a,
        "default_env_client_result": status_b,
        "credential_present": True
    }


def main():
    res = check_gemini_connection()
    print("==================================================")
    print("  GEMINI API AUTHENTICATION & CONNECTIVITY PROBE")
    print("==================================================")
    print(f"  Classification:        {res['classification']}")
    print(f"  Model:                 {res['model']} (Status: {res['model_status']})")
    print(f"  Explicit Client Auth:  {res['explicit_client_result']}")
    print(f"  Default Env Auth:      {res['default_env_client_result']}")
    print(f"  Detail:                {res['message']}")
    print("==================================================")

    if res["auth_ok"]:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
