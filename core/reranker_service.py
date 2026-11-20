"""Backward-compatible facade — implementation lives in core.chat.reranker_service."""

import sys
from core.chat import reranker_service as _impl

sys.modules[__name__] = _impl
