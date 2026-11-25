"""Backward-compatibility alias for ``core.shared.cache_service``."""

from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module("core.shared.cache_service")
