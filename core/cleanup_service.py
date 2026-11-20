"""Backward-compatible facade — implementation lives in core.shared.cleanup_service."""

import sys
from core.shared import cleanup_service as _impl

sys.modules[__name__] = _impl
