"""Backward-compatible facade — implementation lives in core.ai.prompts."""

import sys
from core.ai import prompts as _impl

sys.modules[__name__] = _impl
