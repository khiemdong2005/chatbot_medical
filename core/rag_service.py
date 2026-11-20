"""Backward-compatible facade — implementation lives in core.chat.rag_service."""

import sys
from core.chat import rag_service as _impl

sys.modules[__name__] = _impl
