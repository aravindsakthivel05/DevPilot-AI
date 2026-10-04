"""Compatibility import for optional legacy agent_repair."""

import sys

from .legacy import agent_repair

sys.modules[__name__] = agent_repair
