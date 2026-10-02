"""Build a Java runner image with dependencies from one pinned indexed snapshot."""

import argparse
import contextlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from backend.config import DATA, SNAPSHOTS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", choices=("petclinic", "commons-lang", "mockito"))
    args = parser.parse_args()
    manifest = json.loads(Path("docs/indexed-reference-repositories.json").read_text())
    info = manifest[args.repository]
    snapshot = SNAPSHOTS / info["id"]
    gradle = args.repository == "mockito"
    if not (snapshot / ("build.gradle.kts" if gradle else "pom.xml")).is_file():
        parser.error("The pinned snapshot lacks its build manifest; refresh the Java references")
    image = f"devpilot-java-{args.repository}:local"
    test_selector = {
        "petclinic": "OwnerControllerTests",
        "commons-lang": "StringUtilsTest",
    }.get(args.repository)
    dockerfile = "Dockerfile.gradle-runner" if gradle else "Dockerfile.maven-runner"
    build_root = DATA / "build-contexts"
    build_root.mkdir(exist_ok=True)
    context_manager = (
        tempfile.TemporaryDirectory(dir=build_root) if gradle else contextlib.nullcontext()
    )
    with context_manager as temp:
        context = Path(temp) / "context" if gradle else snapshot
        if gradle:
            shutil.copytree(snapshot, context)
            (context / "infra").mkdir()
            shutil.copyfile(Path("infra/devpilot-gradle"), context / "infra/devpilot-gradle")
        subprocess.run(
            [
                "docker",
                "build",
                "-f",
                str(Path("infra", dockerfile).resolve()),
                *([] if gradle else ["--build-arg", f"TEST_SELECTOR={test_selector}"]),
                "-t",
                image,
                str(context),
            ],
            check=True,
        )
    print(image)


if __name__ == "__main__":
    main()
