"""Shared parser contract and per-language capabilities."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class AnalysisResult:
    symbols: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    unresolved: list[dict] = field(default_factory=list)


class LanguageAdapter(Protocol):
    language: str
    extensions: tuple[str, ...]

    def analyze(self, repo_id: str, files: dict[str, str]) -> AnalysisResult: ...

    def capabilities(self) -> dict: ...
