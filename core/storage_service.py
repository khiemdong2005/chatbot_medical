"""Backward-compatible facade — implementation lives in core.ocr.storage_service."""

import sys
from core.ocr import storage_service as _impl

sys.modules[__name__] = _impl
