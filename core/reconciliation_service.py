"""Backward-compatible facade — implementation lives in core.ocr.reconciliation_service."""

import sys
from core.ocr import reconciliation_service as _impl

sys.modules[__name__] = _impl
