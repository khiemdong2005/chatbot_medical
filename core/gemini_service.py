"""Backward-compatible facade — implementation lives in core.chat.gemini_service."""

import sys
from core.chat import gemini_service as _impl

sys.modules[__name__] = _impl
