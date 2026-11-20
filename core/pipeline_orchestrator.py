"""Backward-compatible facade — implementation lives in core.ocr.pipeline_orchestrator."""

import sys
from core.ocr import pipeline_orchestrator as _impl

sys.modules[__name__] = _impl
