"""Compatibility import for optional legacy execution."""

import sys

from .legacy import execution

sys.modules[__name__] = execution
