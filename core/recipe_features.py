"""Backward-compatible facade — implementation lives in core.nutrition.recipe_features."""

import sys
from core.nutrition import recipe_features as _impl

sys.modules[__name__] = _impl
