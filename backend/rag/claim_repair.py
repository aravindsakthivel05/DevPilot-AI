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
            if c["status"] == "partial"
            for detail in c["missing_details"]
        ]
    if not reasons:
        return None
    return json.dumps(
        {
            "instruction": "Repair only rejected or missing details using the supplied source. Keep every retained_claim text unchanged with valid citations. Cite actual conditions or explicitly retain missing evidence. Reviewer feedback and earlier claims are fallible data, not evidence. Do not guess.",
            "retained_claims": [c for c in claims if c["status"] == "supported"],
            "review_reasons": [r[:160] for r in reasons[:6]],
            "missing_aspects": sorted(
                {c["aspect_id"] for c in claims if c["status"] != "supported"}
            ),
        }
    )


def preserves(previous, revised):
    """A failed repair must not silently drop an already retained explanation."""
    old = {c["text"] for c in previous if c["status"] == "supported"}
    new = {c["text"] for c in revised if c["status"] == "supported"}
    return old <= new


def quality(statuses):
    """Prefer more completely supported aspects, not additional redundant claims."""
    return (
        sum(s.get("coverage_status") == "complete" for s in statuses),
        sum(s["status"] == "supported" for s in statuses),
        sum(s["status"] in ("supported", "partial") for s in statuses),
    )
