"""Backward-compatible facade — implementation lives in core.chat.triage."""

import sys
from core.chat import triage as _impl

sys.modules[__name__] = _impl
