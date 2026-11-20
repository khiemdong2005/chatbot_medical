"""Backward-compatible facade — implementation lives in core.ai.interpretation_service."""

import sys
from core.ai import interpretation_service as _impl

sys.modules[__name__] = _impl
