"""Backward-compatible facade — implementation lives in core.chat.grounding_service."""

import sys
from core.chat import grounding_service as _impl

sys.modules[__name__] = _impl
