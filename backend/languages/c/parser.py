"""Grammar-specific declaration mapping for c."""

from ..tree_parser import TreeAdapter
from .resolver import resolve_relationships

adapter = TreeAdapter(
    "c",
    (".c", ".h"),
    {"function_definition": "function", "struct_specifier": "struct", "enum_specifier": "enum"},
    resolve_relationships,
)
