"""Normalized repository entities. Legacy field names remain stable for clients."""

import hashlib
from pathlib import PurePosixPath


def file_id(repo_id, path):
    return hashlib.sha256(f"{repo_id}\0{path}".encode()).hexdigest()[:32]


def file_role(path):
    from .test_links import is_test_path

    name = PurePosixPath(path).name
    if is_test_path(path):
        return "test"
    if name in {
        "setup.py",
        "go.sum",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "pom.xml",
        "go.mod",
        "Cargo.toml",
    } or name.endswith(".csproj"):
        return "dependency_manifest"
    if name in {
        "Makefile",
        "CMakeLists.txt",
        "Dockerfile",
        "build.gradle.kts",
        "settings.gradle.kts",
        "build.gradle",
        "settings.gradle",
        "gradlew",
        "mvnw",
    }:
        return "build"
    if PurePosixPath(path).suffix in {".md", ".rst"}:
        return "documentation"
    if PurePosixPath(path).suffix in {
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".xml",
        ".properties",
    }:
        return "configuration"
    return "source"


def normalize_symbol(symbol, language):
    source = symbol.get("source", "")
    declaration = next(
        (
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("def ", "async def ", "class "))
        ),
        source.splitlines()[0][:500] if source else "",
    )
    return {
        **symbol,
        "language": language,
        "file_id": file_id(symbol["repo_id"], symbol["path"]),
        "signature": symbol.get("signature", declaration[:500]),
        "role": file_role(symbol["path"]),
    }
