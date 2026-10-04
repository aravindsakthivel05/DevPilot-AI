"""Existing Python AST scope/import resolver, preserved behind the adapter contract."""

from ...analysis import analyse as resolve_repository

__all__ = ["resolve_repository"]
