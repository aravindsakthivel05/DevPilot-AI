"""Grammar-specific declaration mapping for go."""

from ..tree_parser import TreeAdapter
from .resolver import resolve_relationships

adapter = TreeAdapter(
    "go",
    (".go",),
    {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_spec": "type",
        "var_spec": "variable",
        "const_spec": "constant",
    },
    resolve_relationships,
)
