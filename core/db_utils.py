"""Backward-compatible facade — implementation lives in core.shared.db_utils."""

import sys
from core.shared import db_utils as _impl

sys.modules[__name__] = _impl
