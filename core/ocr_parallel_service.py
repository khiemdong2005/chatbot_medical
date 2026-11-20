"""Backward-compatible facade — implementation lives in core.ocr.ocr_parallel_service."""

import sys
from core.ocr import ocr_parallel_service as _impl

sys.modules[__name__] = _impl
