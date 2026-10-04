"""Original-file citation provenance; validity is not factual entailment."""

from ..evidence import source_lines


def evidence_reference(item, start, end):
    available = source_lines(item)
    if start > end or any(n not in available for n in range(start, end + 1)):
        raise ValueError("Citation contains unavailable lines")
    return {
        "file": item["path"],
        "symbol": item["qualified"],
        "start_line": start,
        "end_line": end,
        "relationship": item.get("traversal", []),
        "text": "\n".join(available[n] for n in range(start, end + 1)),
        "entailment_proven": False,
    }
