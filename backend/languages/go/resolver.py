"""go resolution policy; ambiguous/runtime references stay unresolved."""

from ..resolution import resolve


def resolve_relationships(repo_id, files, symbols, calls, language):
    if language != "go":
        raise ValueError("Resolver received the wrong language")
    return resolve(repo_id, files, symbols, calls, language)
