"""Backward-compatible facade — implementation lives in core.shared.network_utils."""

import sys
from core.shared import network_utils as _impl

sys.modules[__name__] = _impl
