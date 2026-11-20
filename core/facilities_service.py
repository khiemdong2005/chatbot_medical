"""Backward-compatible facade — implementation lives in core.facilities.facilities_service."""

import sys
from core.facilities import facilities_service as _impl

sys.modules[__name__] = _impl
