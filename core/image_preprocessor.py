"""Backward-compatibility alias for ``core.ocr.image_preprocessor``."""

from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module("core.ocr.image_preprocessor")
