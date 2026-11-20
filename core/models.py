"""Backward-compatible facade — implementation lives in core.shared.models."""

import sys
from core.shared import models as _impl

sys.modules[__name__] = _impl
