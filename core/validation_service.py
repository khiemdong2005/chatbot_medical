"""Backward-compatible facade — implementation lives in core.shared.validation_service."""

import sys
from core.shared import validation_service as _impl

sys.modules[__name__] = _impl
