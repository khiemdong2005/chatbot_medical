"""Backward-compatible facade — implementation lives in core.auth.otp_service."""

import sys
from core.auth import otp_service as _impl

sys.modules[__name__] = _impl
