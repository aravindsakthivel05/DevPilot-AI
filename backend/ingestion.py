import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from . import db
from .config import (
    IGNORE,
    MAX_COVERAGE_ENTRIES,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    SNAPSHOTS,
    SUFFIXES,
    TEXT_FILENAMES,
)
from .config_links import configuration_edges
from .languages.registry import analyze_repository, detect_language
from .models import file_id, file_role
from .structure import enrich


def supported_text_path(path):
    item = Path(path)
    return (
        item.suffix.lower() in SUFFIXES
        or item.name in TEXT_FILENAMES
        or ("mockito-extensions" in item.parts and item.name.startswith("org.mockito.plugins."))
    )


def collect_files(root, with_coverage=False):
    root = Path(root).resolve()
    result = {}
    coverage = []
    reasons = Counter()
    extensions = Counter()
    skipped_files = 0
    ignored_directories = 0
    coverage_capped = False
    total = 0

    def record(path, kind, status, reason=None, size=None):
        nonlocal skipped_files, ignored_directories, coverage_capped
        extension = Path(path).suffix.lower() or "[none]"
        if status == "skipped":
            reasons[reason] += 1
            if kind == "file":
                skipped_files += 1
            else:
                ignored_directories += 1
        else:
            extensions[extension] += 1
        if len(coverage) < MAX_COVERAGE_ENTRIES:
            coverage.append(
                {
                    "path": path,
                    "kind": kind,
                    "status": status,
                    "reason": reason,
                    "size": size,
                    "extension": extension if kind == "file" else None,
                }
            )
        else:
            coverage_capped = True

    for directory, dirs, names in os.walk(root, followlinks=False):
        kept = []
        for name in sorted(dirs):
            path = Path(directory) / name
            reason = (
                "ignored_directory"
                if name in IGNORE
                else "symlink_directory"
                if path.is_symlink()
                else "hidden_directory"
                if name.startswith(".") and name != ".github"
                else None
            )
            if reason:
                record(path.relative_to(root).as_posix() + "/", "directory", "skipped", reason)
            else:
                kept.append(name)
        dirs[:] = kept
        for name in sorted(names):
            p = Path(directory) / name
            path = p.relative_to(root).as_posix()
            reason = (
                "symlink_file"
                if p.is_symlink()
                else "secret_file"
                if name.startswith(".env")
                else "lockfile"
                if name in ("package-lock.json", "poetry.lock", "uv.lock")
                else "unsupported_extension"
                if not supported_text_path(path)
                else None
            )
            if reason:
                record(path, "file", "skipped", reason)
                continue
            try:
                size = p.stat().st_size
            except OSError:
                record(path, "file", "skipped", "unreadable")
                continue
            if size > MAX_FILE_BYTES:
                record(path, "file", "skipped", "file_too_large", size)
                continue
            if len(result) >= MAX_FILES:
                raise ValueError(
                    f"Repository exceeds {MAX_FILES} supported files. Select a smaller directory."
                )
            try:
                content = p.read_bytes()
            except OSError:
                record(path, "file", "skipped", "unreadable", size)
                continue
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                record(path, "file", "skipped", "non_utf8", size)
                continue
            if "\0" in text:
                record(path, "file", "skipped", "nul_byte", size)
                continue
            total += len(content)
            if total > MAX_TOTAL_BYTES:
                raise ValueError("Repository exceeds the 40 MB indexing limit.")
            result[path] = text
            record(path, "file", "indexed", size=size)
    if not result:
        raise ValueError("No supported source or text files found.")
    summary = {
        "indexed_files": len(result),
        "skipped_files": skipped_files,
        "ignored_directories": ignored_directories,
        "reason_counts": dict(sorted(reasons.items())),
        "indexed_extensions": dict(sorted(extensions.items())),
        "recorded_entries": len(coverage),
        "entries_capped": coverage_capped,
        "ignored_directory_contents_scanned": False,
    }
    return (result, coverage, summary) if with_coverage else (result, skipped_files)


def git_commit(root):
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def ingest(repo_id, source):
    checkout = None
    try:
        db.update_repository(repo_id, status="indexing", progress="Reading repository files")
        if source.startswith("https://"):
            if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", source):
                raise ValueError("Use a public https://github.com/owner/repository URL.")
            checkout = tempfile.TemporaryDirectory(prefix="devpilot-clone-")
            root = Path(checkout.name) / "repo"
            run = subprocess.run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "clone",
                    "--depth",
                    "1",
                    "--",
                    source,
                    str(root),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if run.returncode:
                raise ValueError("Clone failed: " + run.stderr[-1500:])
        else:
            root = Path(source).expanduser().resolve()
            if not root.is_dir():
                raise ValueError("Local repository directory does not exist.")
        from time import perf_counter

        started = perf_counter()
        files, coverage, coverage_summary = collect_files(root, with_coverage=True)
        commit = git_commit(root)
        fingerprint = hashlib.sha256(
            "".join(
                p + "\0" + hashlib.sha256(t.encode()).hexdigest() for p, t in sorted(files.items())
            ).encode()
        ).hexdigest()
        dest = SNAPSHOTS / repo_id
        dest.mkdir(parents=True, exist_ok=True)
        for path, content in files.items():
            target = dest / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        db.update_repository(
            repo_id,
            progress="Extracting symbols and dependency relationships",
            commit_id=commit,
            fingerprint=fingerprint,
        )
        files_done = perf_counter()
        analysis = analyze_repository(repo_id, files)
        symbols, edges, errors, unresolved = (
            analysis.symbols,
            analysis.relationships,
            analysis.errors,
            analysis.unresolved,
        )
        edges.extend(configuration_edges(repo_id, files, symbols))
        extra_symbols, extra_edges = enrich(repo_id, files, symbols, edges)
        symbols.extend(extra_symbols)
        edges.extend(extra_edges)
        graph_done = perf_counter()
        from .rag.chunking import repository_chunks

        chunks = repository_chunks(symbols, edges)
        with db.connection() as c:
            c.executemany(
                "INSERT INTO coverage VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        repo_id,
                        entry["path"],
                        entry["kind"],
                        entry["status"],
                        entry["reason"],
                        entry["size"],
                        entry["extension"],
                    )
                    for entry in coverage
                ],
            )
            c.executemany(
                "INSERT INTO files(repo_id,path,content,language,file_id,role) VALUES (?,?,?,?,?,?)",
                [
                    (
                        repo_id,
                        p,
                        t,
                        detect_language(p),
                        file_id(repo_id, p),
                        file_role(p),
                    )
                    for p, t in files.items()
                ],
            )
            c.executemany(
                "INSERT INTO symbols(id,repo_id,path,name,qualified,kind,start_line,end_line,source,docstring,parent_id,file_id,language,signature,role) VALUES (:id,:repo_id,:path,:name,:qualified,:kind,:start_line,:end_line,:source,:docstring,:parent_id,:file_id,:language,:signature,:role)",
                symbols,
            )
            c.executemany(
                "INSERT INTO chunks VALUES (?,?,?,?,?,?)",
                [
                    (
                        s["id"],
                        repo_id,
                        s["file_id"],
                        s["language"],
                        s["kind"],
                        json.dumps(chunks[s["id"]]),
                    )
                    for s in symbols
                ],
            )
            c.executemany(
                "INSERT OR IGNORE INTO edges VALUES (:repo_id,:source,:target,:kind,:line,:confidence,:label)",
                edges,
            )
            c.executemany(
                "INSERT INTO unresolved_references VALUES (?,?)",
                [(repo_id, json.dumps(item)) for item in unresolved],
            )
        stored_done = perf_counter()
        stats = dict(
            files=len(files),
            python_files=sum(p.endswith(".py") for p in files),
            java_files=sum(p.endswith(".java") for p in files),
            languages=dict(Counter(detect_language(p) for p in files)),
            symbols=len(symbols),
            edges=len(edges),
            parse_errors=errors,
            unresolved_count=len(unresolved),
            unresolved=unresolved[:100],
            skipped_files=coverage_summary["skipped_files"],
            coverage=coverage_summary,
            embedding_status="not_configured",
            index_version="2026-10-04-language-adapters-v1",
            timings_ms={
                "read_and_snapshot": round((files_done - started) * 1000, 3),
                "analysis_and_graph": round((graph_done - files_done) * 1000, 3),
                "chunks_and_storage": round((stored_done - graph_done) * 1000, 3),
            },
        )
        from .providers import index_embeddings

        db.update_repository(repo_id, progress="Preparing search index")
        try:
            stats["embedding_status"] = index_embeddings(symbols)
        except Exception as e:
            stats["embedding_status"] = "failed"
            stats["embedding_error"] = str(e)[:300]
        stats["timings_ms"].update(
            embeddings=round((perf_counter() - stored_done) * 1000, 3),
            total_index=round((perf_counter() - started) * 1000, 3),
        )
        db.update_repository(
            repo_id, status="ready", progress="Ready for investigation", stats=json.dumps(stats)
        )
    except Exception as e:
        db.update_repository(
            repo_id, status="failed", progress="Indexing failed", error=str(e)[:2000]
        )
    finally:
        if checkout:
            checkout.cleanup()
