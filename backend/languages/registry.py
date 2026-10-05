"""Extensible language registry, automatic detection and repository analysis."""

import importlib
import re
from collections import defaultdict
from pathlib import PurePosixPath

from ..analysis import analyse
from ..models import normalize_symbol
from .base import AnalysisResult

LANGUAGES = ("python", "java", "javascript", "typescript", "c", "cpp", "go", "rust", "csharp")


def adapters():
    return [
        importlib.import_module(f"backend.languages.{name}.parser").adapter for name in LANGUAGES
    ]


def detect_language(path, content=None):
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".h" and content:
        # A .h suffix is shared by C and C++. Ignore comments and ordinary string
        # literals so examples in prose cannot change the selected grammar.
        code = re.sub(r"/\*.*?\*/|//[^\n]*", "", content, flags=re.S)
        code = re.sub(r'"(?:\\.|[^"\\])*"', '""', code)
        if re.search(
            r"\b(?:namespace|template|typename|constexpr|consteval)\b|\bstd::|\bclass\s+\w+", code
        ):
            return "cpp"
    for adapter in adapters():
        if suffix in adapter.extensions:
            return adapter.language
    return "text"


def capabilities():
    return [adapter.capabilities() for adapter in adapters()]


def analyze_repository(repo_id, files):
    groups = defaultdict(dict)
    for path, content in files.items():
        groups[detect_language(path, content)][path] = content
    result = AnalysisResult()
    for adapter in adapters():
        if groups[adapter.language]:
            current = adapter.analyze(repo_id, groups[adapter.language])
            for field in ("symbols", "relationships", "errors", "unresolved"):
                getattr(result, field).extend(getattr(current, field))
    if groups["text"]:
        symbols, edges, errors, unresolved = analyse(repo_id, groups["text"])
        result.symbols.extend(normalize_symbol(s, "text") for s in symbols)
        result.relationships.extend(edges)
        result.errors.extend(errors)
        result.unresolved.extend(unresolved)
    return result
