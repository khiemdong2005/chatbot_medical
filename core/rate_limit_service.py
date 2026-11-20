"""Backward-compatible facade — implementation lives in core.auth.rate_limit_service."""

import sys
from core.auth import rate_limit_service as _impl

sys.modules[__name__] = _impl
