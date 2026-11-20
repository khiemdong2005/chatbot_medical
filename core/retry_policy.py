"""Backward-compatible facade — implementation lives in core.ai.retry_policy."""

import sys
from core.ai import retry_policy as _impl

sys.modules[__name__] = _impl
