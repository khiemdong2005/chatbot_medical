"""Backward-compatibility alias for ``core.ai.gemini_service``."""

from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module("core.ai.gemini_service")
