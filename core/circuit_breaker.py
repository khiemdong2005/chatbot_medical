"""Backward-compatible facade — implementation lives in core.ai.circuit_breaker."""

import sys
from core.ai import circuit_breaker as _impl

sys.modules[__name__] = _impl
