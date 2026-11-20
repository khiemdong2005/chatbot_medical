"""Backward-compatible facade — implementation lives in core.ocr.image_preprocessor."""

import sys
from core.ocr import image_preprocessor as _impl

sys.modules[__name__] = _impl
