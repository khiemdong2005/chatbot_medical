"""Backward-compatible facade — implementation lives in core.ocr.preprocessing_service."""

import sys
from core.ocr import preprocessing_service as _impl

sys.modules[__name__] = _impl
