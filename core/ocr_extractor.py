"""Backward-compatible facade — implementation lives in core.ocr.ocr_extractor."""

import sys
from core.ocr import ocr_extractor as _impl

sys.modules[__name__] = _impl
