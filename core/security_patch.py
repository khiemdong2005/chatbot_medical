"""Backward-compatible facade — implementation lives in core.auth.security_patch."""

import sys
from core.auth import security_patch as _impl

sys.modules[__name__] = _impl
