"""Backward-compatible facade — implementation lives in core.shared.settings."""

import sys
from core.shared import settings as _impl

sys.modules[__name__] = _impl
