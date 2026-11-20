"""Backward-compatible facade — implementation lives in core.chat.document_chunker."""

import sys
from core.chat import document_chunker as _impl

sys.modules[__name__] = _impl
