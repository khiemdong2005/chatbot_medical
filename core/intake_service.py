"""Backward-compatible facade — implementation lives in core.chat.intake_service."""

import sys
from core.chat import intake_service as _impl

sys.modules[__name__] = _impl
