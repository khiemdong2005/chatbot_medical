"""Backward-compatibility alias for ``core.nutrition.recipe_features``."""

from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module("core.nutrition.recipe_features")
