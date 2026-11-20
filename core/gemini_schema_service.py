"""Backward-compatible facade — implementation lives in core.ocr.gemini_schema_service."""

import sys
from core.ocr import gemini_schema_service as _impl

sys.modules[__name__] = _impl
