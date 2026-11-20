"""Backward-compatible facade — implementation lives in core.nutrition.nutrition_ai."""

import sys
from core.nutrition import nutrition_ai as _impl

sys.modules[__name__] = _impl
