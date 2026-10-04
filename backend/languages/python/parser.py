"""Tree-sitter python parsing with the existing conservative resolver."""

from ...models import normalize_symbol
from ..base import AnalysisResult
from ..tree_parser import parser_for
from .resolver import resolve_repository


class Adapter:
    language = "python"
    extensions = (".py",)

    def capabilities(self):
        return {
            "language": self.language,
            "extensions": self.extensions,
            "parser": "Tree-sitter + Python AST scope/import resolver",
            "relationships": "existing tested static relationships",
            "limitations": ["No runtime dispatch, reflection or complete compiler typing"],
        }

    def analyze(self, repo_id, files):
        symbols, edges, errors, unresolved = resolve_repository(repo_id, files)
        if self.language == "python":
            # AST retains existing scope resolution; Tree-sitter also exposes
            # recovery diagnostics and supplies the shared parsing contract.
            for path, source in files.items():
                root = parser_for(self.language, path).parse(source.encode()).root_node
                if root.has_error and not any(e["path"] == path for e in errors):
                    errors.append(
                        {
                            "path": path,
                            "line": 1,
                            "error": "Tree-sitter syntax recovery error",
                            "language": self.language,
                        }
                    )
        return AnalysisResult(
            [normalize_symbol(s, self.language) for s in symbols], edges, errors, unresolved
        )


adapter = Adapter()
