"""Source roles and graph paths for structured, coordinate-preserving context."""


def role(item):
    if item.get("role") == "test":
        return "test_evidence"
    if item.get("role") in ("configuration", "dependency_manifest", "build"):
        return "configuration_evidence"
    paths = item.get("traversal", [])
    if paths:
        return "dependency_evidence"
    return "primary_evidence"
