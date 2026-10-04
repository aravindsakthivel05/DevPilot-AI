"""Tree-sitter java parsing with the existing conservative resolver."""

from ...models import normalize_symbol
from ..base import AnalysisResult
from .resolver import resolve_repository


class Adapter:
    language = "java"
    extensions = (".java",)

    def capabilities(self):
        return {
            "language": self.language,
            "extensions": self.extensions,
            "parser": "Tree-sitter + Java declared receiver/import resolver",
            "relationships": "existing tested static relationships",
            "limitations": ["No runtime dispatch, reflection or complete compiler typing"],
        }

    def analyze(self, repo_id, files):
        symbols, edges, errors, unresolved = resolve_repository(repo_id, files)
        return AnalysisResult(
            [normalize_symbol(s, self.language) for s in symbols], edges, errors, unresolved
        )


adapter = Adapter()
