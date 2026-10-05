"""Find source-referenced and name-associated tests without claiming runtime coverage."""

from pathlib import PurePosixPath

from . import db


def is_test_path(path):
    parts = PurePosixPath(path).parts
    name = parts[-1]
    return (
        any(
            part.lower() in ("test", "tests", "testing", "spec", "specs", "benchmarks")
            or any(segment in ("tests", "test") for segment in part.lower().split("."))
            for part in parts[:-1]
        )
        or name.startswith("test_")
        or name.endswith(("_test.py", "Test.java", "Tests.java"))
        or name.endswith(
            ("_test.go", ".test.js", ".spec.js", ".test.ts", ".spec.ts", "Tests.cs", "Test.cs")
        )
        or name.startswith("test_")
        and name.endswith((".cpp", ".c", ".rs"))
    )


def test_stem(path):
    stem = PurePosixPath(path).stem
    if stem.startswith("test_"):
        return stem.removeprefix("test_").lower()
    if stem.endswith("Tests"):
        return stem.removesuffix("Tests").lower()
    if stem.endswith("Test"):
        return stem.removesuffix("Test").lower()
    if stem.endswith("_test"):
        return stem.removesuffix("_test").lower()
    return ""


def related_tests(repo_id, source_path):
    with db.connection() as connection:
        indexed = connection.execute(
            "SELECT 1 FROM files WHERE repo_id=? AND path=?", (repo_id, source_path)
        ).fetchone()
        if not indexed:
            raise ValueError("Source file is not in this snapshot.")
        rows = connection.execute(
            "SELECT DISTINCT s.path AS test_path,e.kind,s.qualified AS caller,"
            "t.qualified AS target FROM edges e "
            "JOIN symbols s ON s.id=e.source JOIN symbols t ON t.id=e.target "
            "WHERE e.repo_id=? AND t.path=? AND e.kind IN ('calls','imports')",
            (repo_id, source_path),
        ).fetchall()
        files = [
            row["path"]
            for row in connection.execute("SELECT path FROM files WHERE repo_id=?", (repo_id,))
        ]
    found = {}
    for row in rows:
        path = row["test_path"]
        if not is_test_path(path) or path == source_path:
            continue
        item = found.setdefault(path, {"path": path, "signals": [], "confidence": "static"})
        signal = {
            "kind": row["kind"],
            "caller": row["caller"],
            "target": row["target"],
        }
        if signal not in item["signals"] and len(item["signals"]) < 8:
            item["signals"].append(signal)
    target_stem = PurePosixPath(source_path).stem.lower()
    for path in files:
        if is_test_path(path) and test_stem(path) == target_stem and path not in found:
            found[path] = {
                "path": path,
                "signals": [{"kind": "name_match"}],
                "confidence": "heuristic",
            }
    return sorted(
        found.values(),
        key=lambda item: (
            test_stem(item["path"]) != target_stem,
            item["confidence"] != "static",
            item["path"],
        ),
    )
