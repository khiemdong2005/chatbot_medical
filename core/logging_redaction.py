"""Backward-compatible facade — implementation lives in core.shared.logging_redaction."""

import sys
from core.shared import logging_redaction as _impl

sys.modules[__name__] = _impl
