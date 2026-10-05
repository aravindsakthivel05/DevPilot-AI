"""Compact dense candidates; exact facts still come from full indexed source."""

KINDS = (
    "function",
    "method",
    "constructor",
    "class",
    "struct",
    "interface",
    "enum",
    "namespace",
    "module",
    "document",
    "macro",
)
SQL_KINDS = ",".join("'" + kind + "'" for kind in KINDS)


def eligible(symbol):
    return symbol["kind"] in KINDS


def document(symbol):
    source = symbol["source"]
    body = source if len(source) <= 1000 else source[:650] + "\n…\n" + source[-350:]
    return "\n".join(
        (
            symbol["qualified"][:200],
            symbol.get("signature", "")[:160],
            symbol.get("docstring", "")[:400],
            body,
        )
    )
