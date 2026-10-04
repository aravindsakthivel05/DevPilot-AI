"""Grammar-specific declaration mapping for javascript."""

from ..tree_parser import TreeAdapter
from .resolver import resolve_relationships

adapter = TreeAdapter(
    "javascript",
    (".js", ".jsx", ".mjs", ".cjs"),
    {
        "class_declaration": "class",
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "method_definition": "method",
        "variable_declarator": "variable",
    },
    resolve_relationships,
)
