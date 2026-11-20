"""Backward-compatible facade — implementation lives in core.nutrition.nutrition_rules."""

import sys
from core.nutrition import nutrition_rules as _impl

sys.modules[__name__] = _impl
