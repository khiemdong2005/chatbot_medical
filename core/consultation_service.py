"""Backward-compatible facade — implementation lives in core.chat.consultation_service."""

import sys
from core.chat import consultation_service as _impl

sys.modules[__name__] = _impl
