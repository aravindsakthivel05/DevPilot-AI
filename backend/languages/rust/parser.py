"""Grammar-specific declaration mapping for rust."""

from ..tree_parser import TreeAdapter
from .resolver import resolve_relationships

adapter = TreeAdapter(
    "rust",
    (".rs",),
    {
        "function_item": "function",
        "struct_item": "struct",
        "enum_item": "enum",
        "trait_item": "interface",
        "mod_item": "module",
        "const_item": "constant",
        "static_item": "variable",
    },
    resolve_relationships,
)
