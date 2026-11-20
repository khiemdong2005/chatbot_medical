"""Backward-compatible facade — implementation lives in core.nutrition.recipe_catalog."""

import sys
from core.nutrition import recipe_catalog as _impl

sys.modules[__name__] = _impl
