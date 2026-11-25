"""Backward-compatibility alias for ``core.shared.api_errors``."""

from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module("core.shared.api_errors")
