"""Backward-compatible facade — implementation lives in core.shared.cache_service."""

import sys
from core.shared import cache_service as _impl

sys.modules[__name__] = _impl
