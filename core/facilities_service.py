"""Backward-compatibility alias for ``core.facilities.facilities_service``."""

from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module("core.facilities.facilities_service")
