"""Backward-compatible facade — implementation lives in core.auth.sms_service."""

import sys
from core.auth import sms_service as _impl

sys.modules[__name__] = _impl
