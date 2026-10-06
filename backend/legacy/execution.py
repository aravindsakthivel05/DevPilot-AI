"""Execute only in disposable Docker containers, never the host interpreter."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from .. import db
from ..config import ROOT, SNAPSHOTS
from ..test_results import clear_reports, collect_reports, regression_transition


def docker_status():
    if not shutil.which("docker"):
        return {"available": False, "reason": "Docker CLI is not installed."}
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return {
            "available": result.returncode == 0,
            "reason": None if result.returncode == 0 else "Docker engine is not running.",
        }
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "reason": "Docker engine did not respond."}


def validate_runner_settings(image, target, runner):
    """Reject invalid runner inputs before an expensive proposal or container run."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{0,180}", image):
        raise ValueError("Invalid container image.")
    if runner not in ("python", "maven", "gradle"):
        raise ValueError("Unsupported test runner.")
    if (
        target.startswith("-")
        or ".." in Path(target.split("::")[0]).parts
        or Path(target).is_absolute()
    ):
        raise ValueError("Test target must be a relative path within the repository.")
    if (
        runner != "python"
        and target not in ("", "tests")
        and not re.fullmatch(r"[A-Za-z0-9_.$*#-]{1,200}", target)
    ):
        raise ValueError("Java test target must be a class or test pattern.")


def execute(
    repo_id,
    image,
    target,
    timeout,
    patch=None,
    extra_tests=None,
    runner="python",
    scenario_isolation=False,
):
    validate_runner_settings(image, target, runner)
    if scenario_isolation and (
        runner != "python" or not extra_tests or not target.startswith("tests/devpilot_scenarios/")
    ):
        raise ValueError(
            "Scenario isolation requires supplied Python tests in the dedicated scenario directory."
        )
    status = docker_status()
    if not status["available"]:
        raise ValueError(status["reason"])
    container = "devpilot-" + uuid.uuid4().hex[:12]
    # Colima shares the user's project directory, but not macOS's private temp mount.
    runs = ROOT / ".devpilot" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="devpilot-run-", dir=runs) as temp:
        work = Path(temp) / "work"
        shutil.copytree(SNAPSHOTS / repo_id, work)
        if extra_tests:
            for path, content in extra_tests.items():
                dest = (work / path).resolve()
                valid_path = (
                    path.startswith("tests/") and path.endswith(".py")
                    if runner == "python"
                    else "/src/test/java/" in "/" + path and path.endswith(".java")
                )
                if not dest.is_relative_to(work.resolve()) or not valid_path or dest.exists():
                    raise ValueError("Generated tests must be new files in the runner's test tree.")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content)
        if runner == "gradle":
            (work / ".devpilot-test-init.gradle").write_text(
                "gradle.beforeProject { project ->\n"
                "  project.tasks.withType(org.gradle.api.tasks.testing.Test).configureEach {\n"
                "    outputs.cacheIf { false }\n"
                "    outputs.upToDateWhen { false }\n"
                "  }\n"
                "}\n"
            )
        if patch:
            patchfile = Path(temp) / "change.patch"
            patchfile.write_text(patch)
            # The temporary checkout sits inside our project. Stop Git from walking up
            # to the project's .git directory, so the patch edits only this copy.
            apply_env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(work.parent)}
            applied = subprocess.run(
                ["git", "apply", "--check", str(patchfile)],
                cwd=work,
                env=apply_env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if applied.returncode:
                raise ValueError("Patch cannot be applied: " + applied.stderr[-1000:])
            subprocess.run(
                ["git", "apply", str(patchfile)],
                cwd=work,
                env=apply_env,
                check=True,
                capture_output=True,
                timeout=10,
            )
        clear_reports(work, runner)
        # Caller supplies an already-built image with repository dependencies and pytest installed.
        # A read-only root plus a single disposable writable mount keeps snapshots immutable.
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            container,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "512" if runner == "gradle" else "128",
            "--memory",
            "4g" if runner == "gradle" else "1g",
            "--cpus",
            "2",
            "--user",
            "65534:65534",
            "--tmpfs",
            "/tmp:rw,exec,nosuid,size=2g"
            if runner == "gradle"
            else "/tmp:rw,exec,nosuid,size=256m",
            "-v",
            f"{work}:/workspace:rw",
            "-w",
            "/workspace",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-e",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            "-e",
            "PYTHONPATH=/workspace:/workspace/src",
        ]
        if runner == "python":
            cmd += [
                "--entrypoint",
                "python",
                image,
                "-m",
                "pytest",
                target,
                "-q",
                "-p",
                "no:cacheprovider",
                "--tb=short",
                "--junitxml=/workspace/.devpilot-test-results.xml",
            ]
            if scenario_isolation:
                # Supplied source scenarios use controlled fixtures; loading a
                # repository's suite conftest/addopts would change their scope.
                cmd += ["-c", "/dev/null", "--confcutdir=/workspace/tests/devpilot_scenarios"]
        elif runner == "maven":
            if not (work / "pom.xml").is_file():
                raise ValueError("Maven runner requires pom.xml in the indexed snapshot.")
            cmd += [
                "--entrypoint",
                "mvn",
                image,
                "-o",
                "-B",
                "-q",
                "-Dmaven.repo.local=/opt/maven-cache",
            ]
            if target not in ("", "tests"):
                cmd.append(f"-Dtest={target}")
            cmd.append("test")
        else:
            if not ((work / "build.gradle").is_file() or (work / "build.gradle.kts").is_file()):
                raise ValueError("Gradle runner requires a build.gradle file in the snapshot.")
            cmd += [
                "--entrypoint",
                "/usr/local/bin/devpilot-gradle",
                image,
                "--offline",
                "--no-daemon",
                "--no-scan",
                "--init-script",
                ".devpilot-test-init.gradle",
                ":mockito-core:test",
            ]
            if target not in ("", "tests"):
                cmd += ["--tests", target]
        for directory, dirs, files in os.walk(work):
            os.chmod(directory, 0o777)
            for name in files:
                os.chmod(Path(directory) / name, 0o666)
        started = time.perf_counter()
        timed_out = False
        with tempfile.TemporaryFile() as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                proc.wait()
                code = -1
            finally:
                subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=15)
            log.seek(0, 2)
            size = log.tell()
            log.seek(max(0, size - 50000))
            output = log.read().decode(errors="replace")
        report = collect_reports(work, runner)
        verified_pass = (
            code == 0
            and report.get("available")
            and report.get("passed", 0) > 0
            and not report.get("failures")
            and not report.get("errors")
        )
        return dict(
            exit_code=code,
            status="timeout"
            if timed_out
            else "passed"
            if verified_pass
            else "unverified"
            if code == 0
            else "failed",
            test_report=report,
            output=output,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            image=image,
            target=target,
            output_truncated=size > 50000,
            snapshot=db.repository(repo_id)["fingerprint"],
            network="disabled",
            patch_applied=bool(patch),
            runner=runner,
        )


def run_job(run_id, repo_id, image, target, timeout, patch, extra_tests, runner="python"):
    try:
        before = execute(repo_id, image, target, timeout, extra_tests=extra_tests, runner=runner)
        after = (
            execute(
                repo_id, image, target, timeout, patch=patch, extra_tests=extra_tests, runner=runner
            )
            if patch
            else None
        )
        result = {
            "baseline": before,
            "patched": after,
            "regression_demonstrated": regression_transition(before, after),
            "existing_suite_verified": False,
            "verification_scope": "supplied target only; guided repair checks existing tests separately",
        }
        state = "complete"
    except Exception as e:
        result = {"error": str(e)}
        state = "failed"
    with db.connection() as c:
        c.execute(
            "UPDATE executions SET status=?,result=? WHERE id=?",
            (state, json.dumps(result), run_id),
        )
