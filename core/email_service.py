"""Backward-compatible facade — implementation lives in core.auth.email_service."""

import sys
from core.auth import email_service as _impl

sys.modules[__name__] = _impl
