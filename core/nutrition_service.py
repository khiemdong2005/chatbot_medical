"""Backward-compatible facade — implementation lives in core.nutrition.nutrition_service."""

import sys
from core.nutrition import nutrition_service as _impl

sys.modules[__name__] = _impl
