"""Backward-compatible facade — implementation lives in core.nutrition.nutrition_options."""

import sys
from core.nutrition import nutrition_options as _impl

sys.modules[__name__] = _impl
