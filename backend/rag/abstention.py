"""Evidence sufficiency signals are exposed, never presented as proof."""


def sufficiency(result):
    statuses = result.get("aspect_statuses", [])
    supported = sum(s["status"] == "supported" for s in statuses)
    complete = sum(s.get("coverage_status") == "complete" for s in statuses)
    return {
        "supported_aspects": supported,
        "partially_supported_aspects": sum(s["status"] == "partial" for s in statuses),
        "requested_aspects": len(statuses),
        "all_aspects_supported": bool(statuses)
        and supported == len(statuses)
        and complete == len(statuses),
        "reviewed_complete_aspects": complete,
        "coverage_reviewed": bool(statuses)
        and all(s.get("coverage_status", "unknown") != "unknown" for s in statuses),
        "confidence": "insufficient"
        if result.get("abstained") or not result.get("generated")
        else "partial"
        if result.get("partial")
        else "model_supported",
        "factual_correctness_proven": False,
    }
