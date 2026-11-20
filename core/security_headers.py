"""Backward-compatible facade — implementation lives in core.auth.security_headers."""

import sys
from core.auth import security_headers as _impl

sys.modules[__name__] = _impl
