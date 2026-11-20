"""Backward-compatible facade — implementation lives in core.ai.llm_provider."""

import sys
from core.ai import llm_provider as _impl

sys.modules[__name__] = _impl
