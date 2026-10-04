"""Evidence sufficiency signals are exposed, never presented as proof."""


def sufficiency(result):
    statuses = result.get("aspect_statuses", [])
    supported = sum(s["status"] == "supported" for s in statuses)
    return {
        "supported_aspects": supported,
        "requested_aspects": len(statuses),
        "all_aspects_supported": bool(statuses) and supported == len(statuses),
        "confidence": "insufficient"
        if result.get("abstained") or not result.get("generated")
        else "partial"
        if result.get("partial")
        else "model_supported",
        "factual_correctness_proven": False,
    }
