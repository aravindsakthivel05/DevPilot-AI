"""Bounded review feedback; never promote a draft or reviewer to source truth."""

import json
import os


def feedback(metrics):
    if os.environ.get("DEVPILOT_REPAIR_REJECTED_CLAIMS", "1").lower() not in ("1", "true", "yes"):
        return None
    claims = metrics.get("claims", [])
    if not any(c["status"] == "supported" for c in claims):
        return None
    audit = metrics.get("claim_audit", {})
    reasons = [f["reason"] for f in metrics.get("claim_validation_failures", [])]
    if audit.get("status") == "completed":
        reasons += [d["reason"] for d in audit.get("decisions", []) if d["verdict"] != "supported"]
        reasons += [
            detail
            for c in audit.get("coverage", [])
            if c["status"] in ("partial", "unknown")
            for detail in c["missing_details"]
        ]
    reasons += [
        r["detail"]
        for r in metrics.get("requirement_coverage", {}).get("items", [])
        if r["status"] == "missing"
    ]
    if not reasons:
        return None
    return json.dumps(
        {
            "instruction": "Repair rejected or missing details using supplied source. Preserve sound information; an earlier accepted claim is fallible. To correct it, return an explicit revision referencing its claim_index, a cited replacement and a source-based reason. Unreviewed replacements will not supersede retained claims. Do not guess.",
            "retained_claims": [
                {"claim_index": i, **c} for i, c in enumerate(claims) if c["status"] == "supported"
            ],
            "review_reasons": [r[:160] for r in reasons[:6]],
            "missing_aspects": sorted(
                {c["aspect_id"] for c in claims if c["status"] != "supported"}
            ),
        }
    )


def revision_requests(declared, previous, revised):
    """Bind replacements to actual previous claims; new claims were validated."""
    if not isinstance(declared, list) or len(declared) > len(previous):
        raise ValueError("Invalid correction records.")
    lookup = {c["claim_index"]: c for c in previous}
    rows, seen = [], set()
    for row in declared:
        if not isinstance(row, dict) or set(row) != {
            "previous_claim_index",
            "replacement_claim_index",
            "reason",
        }:
            raise ValueError("Invalid correction record shape.")
        old, new, reason = (
            row[k] for k in ("previous_claim_index", "replacement_claim_index", "reason")
        )
        if (
            type(old) is not int
            or old not in lookup
            or old in seen
            or type(new) is not int
            or not 0 <= new < len(revised)
            or not isinstance(reason, str)
            or not 8 <= len(reason) <= 200
        ):
            raise ValueError("Invalid correction indices or reason.")
        before, after = lookup[old], revised[new]
        if before["aspect_id"] != after["aspect_id"] or after["status"] != "supported":
            raise ValueError("A correction must be a cited supported claim in the same aspect.")
        rows.append(
            {
                **row,
                "previous_text": before["text"],
                "replacement_text": after["text"],
                "citations": after["citations"],
            }
        )
        seen.add(old)
    return rows


def preserves(previous, revised, revisions=None):
    """A failed repair must not silently drop an already retained explanation."""
    old = {c["text"] for c in previous if c["status"] == "supported"}
    new = {c["text"] for c in revised if c["status"] == "supported"}
    corrected = {
        r["previous_text"]
        for r in (revisions or [])
        if r.get("review_status") == "supported"
        and r.get("basis")
        and r.get("replacement_text") in new
    }
    return old <= new | corrected


def quality(statuses):
    """Prefer more completely supported aspects, not additional redundant claims."""
    return (
        sum(s.get("coverage_status") == "complete" for s in statuses),
        sum(s.get("requirements_covered", 0) for s in statuses),
        sum(s["status"] == "supported" for s in statuses),
        sum(s["status"] in ("supported", "partial") for s in statuses),
    )
