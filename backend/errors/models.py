"""Issue identity and provenance tied to an immutable repository snapshot."""

import hashlib


def issue(
    repo_id,
    snapshot,
    kind,
    path,
    line,
    message,
    root_cause,
    fix,
    severity="warning",
    confidence="medium",
    end_line=None,
):
    identity = hashlib.sha256(
        f"{repo_id}\0{snapshot}\0{kind}\0{path}\0{line}\0{message}".encode()
    ).hexdigest()[:32]
    return {
        "id": identity,
        "repository_id": repo_id,
        "snapshot": snapshot,
        "type": kind,
        "severity": severity,
        "confidence": confidence,
        "file": path,
        "line": line,
        "end_line": end_line or line,
        "symbol": None,
        "message": message,
        "evidence": [{"file": path, "start_line": line, "end_line": end_line or line}],
        "related_symbols": [],
        "root_cause": root_cause,
        "suggested_fix": fix,
        "suggested_test": {
            "syntax_error": "Add a parse/compile check using the project’s configured language toolchain after correcting the indicated syntax.",
            "signature_mismatch": "Add a regression case calling the function with its intended argument count and asserting the expected result.",
            "unreachable_statement": "Exercise the enclosing function’s exit path and assert the intended return value or exception.",
            "undefined_symbol": "Exercise the branch that reads this name and assert the intended result after establishing the binding.",
        }.get(
            kind,
            "Add a focused regression case exercising this condition and its intended behavior using the repository’s existing test conventions.",
        ),
        "status": "static_candidate",
        "verified": False,
    }
