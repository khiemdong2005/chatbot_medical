"""Backward-compatible facade — implementation lives in core.shared.api_errors."""

import sys
from core.shared import api_errors as _impl

sys.modules[__name__] = _impl
