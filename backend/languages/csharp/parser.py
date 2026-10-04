"""Grammar-specific declaration mapping for csharp."""

from ..tree_parser import TreeAdapter
from .resolver import resolve_relationships

adapter = TreeAdapter(
    "csharp",
    (".cs",),
    {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "struct_declaration": "struct",
        "enum_declaration": "enum",
        "namespace_declaration": "namespace",
        "file_scoped_namespace_declaration": "namespace",
        "method_declaration": "method",
        "constructor_declaration": "constructor",
        "property_declaration": "property",
    },
    resolve_relationships,
)
