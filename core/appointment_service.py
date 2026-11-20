"""Backward-compatible facade — implementation lives in core.facilities.appointment_service."""

import sys
from core.facilities import appointment_service as _impl

sys.modules[__name__] = _impl
