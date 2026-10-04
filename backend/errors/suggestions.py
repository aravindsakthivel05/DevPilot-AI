"""Evidence-scoped candidate fixes and regression tests for manual review."""

from ..proposals import propose


def suggest(repo_id, issue, test_only=False):
    return propose(
        repo_id,
        f"Suggest a minimal fix and regression test for the static candidate at {issue['file']}:{issue['line']}. {issue['message']} Candidate cause: {issue['root_cause']} Do not assume the candidate is confirmed. Cite evidence and identify uncertainties.",
        test_only=test_only,
    )
