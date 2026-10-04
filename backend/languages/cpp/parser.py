"""Grammar-specific declaration mapping for cpp."""

from ..tree_parser import TreeAdapter
from .resolver import resolve_relationships

adapter = TreeAdapter(
    "cpp",
    (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"),
    {
        "function_definition": "function",
        "class_specifier": "class",
        "struct_specifier": "struct",
        "enum_specifier": "enum",
        "namespace_definition": "namespace",
    },
    resolve_relationships,
)
