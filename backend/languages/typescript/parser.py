"""Grammar-specific declaration mapping for typescript."""

from ..tree_parser import TreeAdapter
from .resolver import resolve_relationships

adapter = TreeAdapter(
    "typescript",
    (".ts", ".tsx"),
    {
        "class_declaration": "class",
        "abstract_class_declaration": "class",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
        "function_declaration": "function",
        "method_definition": "method",
        "method_signature": "method",
        "variable_declarator": "variable",
        "type_alias_declaration": "type",
    },
    resolve_relationships,
)
