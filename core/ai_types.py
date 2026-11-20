"""Backward-compatible facade — implementation lives in core.ai.ai_types."""

import sys
from core.ai import ai_types as _impl

sys.modules[__name__] = _impl
