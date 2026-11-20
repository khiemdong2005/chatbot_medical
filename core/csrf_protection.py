"""Backward-compatible facade — implementation lives in core.auth.csrf_protection."""

import sys
from core.auth import csrf_protection as _impl

sys.modules[__name__] = _impl
