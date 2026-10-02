"""Build an inspectable, tree-only QLoRA dataset for transferable repo-structure reasoning."""

import json
import random
from collections import Counter
from pathlib import Path

from backend import db

ROOT = Path(__file__).resolve().parents[1]
TRAINING_MANIFEST = ROOT / "evaluation/training-repository-snapshots.json"
HOLDOUT_MANIFESTS = (
    ROOT / "evaluation/clean-holdout-snapshots.json",
    ROOT / "evaluation/final-holdout-snapshots.json",
)
OUTPUT = ROOT / "evaluation/transfer-training"
SYSTEM = (
    "You teach transferable software-repository analysis. Use only the supplied tree evidence. "
    "Separate observed facts from likely conventions. Never invent runtime call paths, test results, "
    "or architecture layers from names alone. For an unfamiliar repository, say what source and "
    "tests to inspect next."
)
ANALYSIS_QUESTIONS = (
    "Read this repository tree sketch. What structural pattern is visible, and how would you trace a feature safely?",
    "Given only these paths and counts, separate direct observations from useful hypotheses and name the next files to inspect.",
    "Explain how an engineer should orient themselves in this repository before changing code. Ground each point in the tree.",
    "How can an engineer find the relevant implementation, its tests, and the command used to run those tests from this tree? State what the tree cannot prove.",
)

PATTERN_GROUPS = (
    {
        "repos": ("requests", "flask"),
        "claim": "Both layouts place implementation under a src/<package>/ path and tests under a separate top-level tests/ tree.",
        "transfer": "In an unfamiliar Python project, check whether src/ separates importable code from repository tooling, then pair a module with tests by name or feature.",
    },
    {
        "repos": ("commons-lang", "spring-data-elasticsearch"),
        "claim": "Both Java projects expose src/main/java and src/test/java roots.",
        "transfer": "Treat main and test roots as a common Maven-style convention, then inspect the build file and nearest test before inferring how a feature is verified.",
    },
    {
        "repos": ("numpy", "scikit-learn"),
        "claim": "Both Python package trees include tests beneath package subdirectories, such as numpy/_core/tests and sklearn/_loss/tests.",
        "transfer": "Test code may live beside or below the package area rather than in one central tests/ directory; search by package and test filename.",
    },
    {
        "repos": ("requests", "httpx"),
        "claim": "Both HTTP-client repositories expose a client/session implementation area and test modules for client behavior, authentication, or cookies.",
        "transfer": "For a client behavior, trace from the public API or Client/Session implementation into request policy and transport code, then compare with focused tests. Verify call order in source.",
    },
    {
        "repos": ("fastapi", "django"),
        "claim": "Both framework snapshots contain many distinct package areas, documentation or examples, and test-related paths rather than one small application module.",
        "transfer": "Large frameworks often need a subsystem-first reading strategy: identify the public entry point, narrow to one component, and follow its tests and configuration instead of reading the tree linearly.",
    },
    {
        "repos": ("mockito",),
        "claim": "The Java test-library repository is split into named modules such as mockito-core, mockito-integration-tests, and mockito-extensions, with Gradle build files.",
        "transfer": "In a multi-module repository, determine which module owns the behavior and inspect its module build file; root-level names alone do not establish dependency direction.",
    },
    {
        "repos": ("numpy", "scikit-learn", "pytorch"),
        "claim": "These scientific-computing repositories contain broad, domain-oriented package trees and extensive test, example, or documentation areas.",
        "transfer": "Large scientific libraries are easier to inspect by following one public operation into its owning subsystem and focused tests; directory breadth does not by itself reveal native-code or runtime execution paths.",
    },
    {
        "repos": ("petclinic", "spring-data-elasticsearch"),
        "claim": "Both Java/Spring snapshots use src/main/java and src/test/java, while the sample application and data-access library have different domain scopes.",
        "transfer": "Separate framework conventions from application-specific layers. Confirm controllers, services, repositories, and model relationships from source instead of assuming every Spring project uses every layer.",
    },
)

TEST_PARTS = {"test", "tests", "spec", "specs", "testing"}
DOC_PARTS = {"doc", "docs", "documentation"}
CONFIG_NAMES = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "tox.ini",
    "pytest.ini",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "meson.build",
    "package.json",
    "makefile",
    "makefile.am",
}


def _top_dirs(paths):
    counts = Counter(path.split("/", 1)[0] for path in paths if "/" in path)
    return [f"{name}/ ({count} indexed files)" for name, count in counts.most_common(10)]


def _is_test_source(path):
    parts = path.split("/")
    excluded = DOC_PARTS | {"example", "examples", "benchmark", "benchmarks"}
    if any(part.lower() in excluded for part in parts[:-1]):
        return False
    if not any(part.lower() in TEST_PARTS for part in parts[:-1]):
        return False
    file_path = Path(path)
    if file_path.suffix.lower() not in {".py", ".java", ".js", ".jsx", ".ts", ".tsx"}:
        return False
    stem = file_path.stem.lower()
    return (
        stem.startswith(("test_", "test."))
        or stem.endswith(("_test", ".test", ".spec", "_spec"))
        or stem in {"conftest", "test", "tests"}
        or (file_path.suffix.lower() == ".java" and ("test" in stem or "tests" in stem))
    )


def _is_project_config(path):
    parts = path.split("/")
    excluded = TEST_PARTS | DOC_PARTS | {"example", "examples", "benchmark", "benchmarks"}
    if len(parts) > 3 or any(part.lower() in excluded for part in parts[:-1]):
        return False
    return Path(path).name.lower() in CONFIG_NAMES


def inventory(name, info):
    with db.connection() as connection:
        rows = connection.execute(
            "SELECT path FROM files WHERE repo_id=? ORDER BY path", (info["id"],)
        ).fetchall()
    paths = [row["path"] for row in rows]
    if not paths:
        raise ValueError(f"No indexed paths found for {name}")
    tests = [path for path in paths if _is_test_source(path)]
    docs = [path for path in paths if any(part.lower() in DOC_PARTS for part in path.split("/"))]
    configs = [path for path in paths if _is_project_config(path)]
    ext_counts = Counter(Path(path).suffix.lower() or "[no extension]" for path in paths)
    root_files = [path for path in paths if "/" not in path]
    separate_tests = any(path.split("/")[0].lower() in TEST_PARTS for path in tests)
    nested_tests = any(
        any(part.lower() in TEST_PARTS for part in path.split("/")[:-1])
        and path.split("/")[0].lower() not in TEST_PARTS
        for path in tests
    )
    return {
        "name": name,
        "file_count": len(paths),
        "top_dirs": _top_dirs(paths),
        "root_files": root_files[:8],
        "test_samples": tests[:8],
        "doc_samples": docs[:5],
        "build_and_test_config": configs[:8],
        "extensions": [f"{suffix}: {count}" for suffix, count in ext_counts.most_common(6)],
        "test_layout": "both top-level and nested test paths"
        if separate_tests and nested_tests
        else "top-level test paths are present"
        if separate_tests
        else "tests/specs are nested under package directories"
        if nested_tests
        else "no test directory appeared in the indexed paths",
    }


def _tree_text(item):
    return "\n".join(
        (
            f"Indexed file count: {item['file_count']}",
            "Top-level directories: " + (", ".join(item["top_dirs"]) or "none"),
            "Root files: " + (", ".join(item["root_files"]) or "none"),
            "Test-path examples: " + (", ".join(item["test_samples"]) or "none"),
            "Documentation examples: " + (", ".join(item["doc_samples"]) or "none"),
            "Build/test configuration: "
            + (", ".join(item["build_and_test_config"]) or "none identified"),
            "Indexed file extensions: " + ", ".join(item["extensions"]),
        )
    )


def _answer(item):
    dirs = ", ".join(item["top_dirs"][:4]) or "no top-level directories"
    tests = ", ".join(item["test_samples"][:3]) or "no indexed test-path examples"
    configs = ", ".join(item["build_and_test_config"][:4]) or "no recognized build/test manifest"
    docs = ", ".join(item["doc_samples"][:2]) or "no indexed documentation-path examples"
    return (
        f"**Observed:** The indexed snapshot has {item['file_count']} files. Its largest visible "
        f"directory groups are {dirs}. The test layout is {item['test_layout']}; examples include "
        f"{tests}. Recognized build or test configuration includes {configs}, and documentation "
        f"examples include {docs}.\n\n"
        "**Useful hypothesis:** This layout can help separate implementation, tests, project "
        "configuration, and documentation. Directory names show organization, but they do not "
        "prove runtime call order, dependency injection, or test coverage.\n\n"
        "**Safe trace:** Find the public entry point for the behavior, follow imports and calls in "
        "the implementation, locate the closest relevant test, and check the project configuration "
        "for the supported test command. Confirm each relationship in source before describing it."
    )


def _task_answer(item, task_index):
    if task_index == 0:
        return _answer(item)
    tests = ", ".join(item["test_samples"][:5]) or "no test paths were indexed"
    configs = (
        ", ".join(item["build_and_test_config"][:5])
        or "no recognized build/test manifest was indexed"
    )
    if task_index == 1:
        return (
            f"**Evidence:** The tree lists test files at {tests}; the recognized build/test files are {configs}. "
            f"The largest directory groups are {', '.join(item['top_dirs'][:5])}.\n\n"
            "**Next:** Identify the behavior's owning implementation module, search for its closest test, "
            "then inspect the manifest and test configuration to determine the actual command. A directory "
            "name alone does not establish coverage or execution order."
        )
    if task_index == 2:
        return (
            f"**Direct observations:** {item['test_layout']}; test-path examples are {tests}. "
            f"Configuration paths include {configs}.\n\n"
            "**Hypothesis:** The path layout can narrow where implementation and tests are maintained. "
            "To trace one behavior, match its public symbol or feature to a source module, inspect imports "
            "and calls, then read the closest test. The tree does not prove runtime behavior, test quality, "
            "or which checks pass."
        )
    return (
        f"Start with the behavior's owning source package, then follow imports and calls. Search the "
        f"indexed test paths, for example {tests}. Inspect {configs} to learn the supported test command. "
        "The tree reveals organization, not the call graph, coverage, or test outcome; verify those in source "
        "and by running the relevant test."
    )


def _pattern_examples(inventories):
    result = []
    question_forms = (
        "Compare these anonymized repository layouts. What repeated structure is useful when approaching a new project?",
        "What transferable repository-organization pattern do these tree sketches support, and what should an analyst verify next?",
    )
    for pattern in PATTERN_GROUPS:
        items = [inventories[name] for name in pattern["repos"]]
        evidence = "\n\n".join(
            f"Example {index}:\n{_tree_text(item)}" for index, item in enumerate(items, 1)
        )
        for question in question_forms:
            answer = (
                f"**Observed pattern:** {pattern['claim']}\n\n"
                f"**Transfer:** {pattern['transfer']}\n\n"
                "Treat this as a search strategy, not a guarantee about an unfamiliar repository. "
                "Confirm the owning modules and relationships in source, and use the closest tests "
                "to verify the behavior."
            )
            result.append(_chat(f"{evidence}\n\nTask: {question}", answer))
    return result


def _chat(question, answer):
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    }


def _load_manifest(path):
    rows = json.loads(path.read_text())
    return {name: info for name, info in rows.items()}


def build():
    train_manifest = _load_manifest(TRAINING_MANIFEST)
    train_examples = []
    inventory_manifest = {}
    inventories = {}
    for name, info in train_manifest.items():
        item = inventory(name, info)
        inventories[name] = item
        inventory_manifest[name] = {
            "id": info["id"],
            "commit": info["commit"],
            "fingerprint": info["fingerprint"],
            "index_scope": info["index_scope"],
            "inventory": item,
        }
        evidence = _tree_text(item)
        for index, question in enumerate(ANALYSIS_QUESTIONS):
            train_examples.append(
                _chat(
                    f"Repository tree sketch:\n{evidence}\n\nTask: {question}",
                    _task_answer(item, index),
                )
            )
    train_examples.extend(_pattern_examples(inventories))

    valid_examples = []
    # Hold back a prompt wording per repository for validation loss. The independent repository
    # transfer set below is not part of MLX training or validation.
    for name, info in train_manifest.items():
        item = inventory_manifest[name]["inventory"]
        valid_examples.append(
            _chat(
                f"Unlabeled repository layout:\n{_tree_text(item)}\n\n"
                "What can this layout establish, and what must be checked in source before claiming a runtime architecture?",
                _answer(item),
            )
        )

    holdout = {}
    for manifest_path in HOLDOUT_MANIFESTS:
        for name, info in _load_manifest(manifest_path).items():
            if name in train_manifest:
                raise ValueError(f"Repository leakage between training and holdout: {name}")
            item = inventory(name, info)
            holdout[name] = {
                "id": info["id"],
                "commit": info["commit"],
                "fingerprint": info["fingerprint"],
                "inventory": item,
            }

    random.Random(214).shuffle(train_examples)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for split, examples in (
        ("train", train_examples),
        ("valid", valid_examples),
        (
            "test",
            [
                _chat(
                    f"Repository tree sketch:\n{_tree_text(info['inventory'])}\n\n"
                    "What structure is directly visible, what pattern is plausible, and what should be inspected next?",
                    _answer(info["inventory"]),
                )
                for info in holdout.values()
            ],
        ),
    ):
        (OUTPUT / f"{split}.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in examples)
        )
    (OUTPUT / "provenance.json").write_text(
        json.dumps(
            {
                "objective": "Transfer repository-tree interpretation and source-first analysis habits; not repo-specific factual memory.",
                "training_source": str(TRAINING_MANIFEST.relative_to(ROOT)),
                "training_examples": len(train_examples),
                "validation_examples": len(valid_examples),
                "independent_holdout_examples": len(holdout),
                "content_policy": "Relative paths, indexed-file counts, extension counts, and configuration filenames only; no source code bodies or generated model answers.",
                "training_snapshots": inventory_manifest,
                "independent_holdout_snapshots": holdout,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "train": len(train_examples),
                "valid": len(valid_examples),
                "test": len(holdout),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    build()
