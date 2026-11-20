"""Backward-compatible facade — implementation lives in core.ocr.prescription_service."""

import sys
from core.ocr import prescription_service as _impl

sys.modules[__name__] = _impl
