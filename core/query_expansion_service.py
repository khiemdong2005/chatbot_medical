"""Backward-compatible facade — implementation lives in core.chat.query_expansion_service."""

import sys
from core.chat import query_expansion_service as _impl

sys.modules[__name__] = _impl
