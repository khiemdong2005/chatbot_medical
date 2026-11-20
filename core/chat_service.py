"""Backward-compatible facade — implementation lives in core.chat.chat_service."""

import sys
from core.chat import chat_service as _impl

sys.modules[__name__] = _impl
