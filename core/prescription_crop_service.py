"""Backward-compatible facade — implementation lives in core.ocr.prescription_crop_service."""

import sys
from core.ocr import prescription_crop_service as _impl

sys.modules[__name__] = _impl
