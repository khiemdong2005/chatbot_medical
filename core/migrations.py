"""Backward-compatible facade — implementation lives in core.shared.migrations."""

import sys
from core.shared import migrations as _impl

sys.modules[__name__] = _impl
