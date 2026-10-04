"""Use the custom RAG engine for optional source-grounded issue investigation."""

from ..retrieval import answer


def explain(repo_id, issue):
    question = f"Why is the source in {issue['file']} at line {issue['line']} flagged as a potential {issue['type']}? {issue['message']}"
    result = answer(repo_id, question)
    return {
        "issue": issue,
        "static_explanation": {
            "candidate_cause": issue["root_cause"],
            "evidence": issue["evidence"],
            "related_symbols": issue["related_symbols"],
            "assumptions": "Indexed static structure only; intentional overrides, runtime injection, generated code or excluded files can affect interpretation.",
        },
        "investigation": result,
        "verified": False,
    }
