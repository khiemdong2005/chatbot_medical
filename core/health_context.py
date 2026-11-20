"""Backward-compatible facade — implementation lives in core.chat.health_context."""

import sys
from core.chat import health_context as _impl

sys.modules[__name__] = _impl
