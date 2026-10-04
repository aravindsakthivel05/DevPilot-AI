"""Compatibility import for the custom RAG pipeline; old clients keep working."""

import sys

from .rag import pipeline

sys.modules[__name__] = pipeline
