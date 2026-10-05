"""Run local MLX QLoRA only on a reviewed, repository-separated export.

The adapter is an experimental candidate. This command does not fuse weights,
change the answering model, upload data or treat lower loss as answer accuracy.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

TOKEN_PREFLIGHT = """
import json, sys
from pathlib import Path
from mlx_lm.utils import load_tokenizer
tokenizer = load_tokenizer(Path(sys.argv[1]))
maximum = int(sys.argv[3])
for split in ('train', 'valid', 'test'):
    for line in (Path(sys.argv[2]) / (split + '.jsonl')).read_text().splitlines():
        row = json.loads(line)
        tokens = tokenizer.apply_chat_template(row['messages'], tokenize=True)
        if len(tokens) > maximum:
            raise SystemExit('Reviewed example exceeds sequence limit; do not silently truncate source or target: ' + row['provenance']['id'])
print('All reviewed examples fit the training sequence limit.')
"""


def validate_export(data):
    provenance = json.loads((data / "provenance.json").read_text())
    if (
        provenance.get("training_ready") is not True
        or provenance.get("minimum_examples", 0) < 100
        or provenance.get("ready_examples", 0) < 100
        or provenance.get("development_repositories", 0) < 5
        or provenance.get("holdout_repositories", 0) < 2
    ):
        raise ValueError("Reviewed grounded training readiness gate has not passed.")
    repos = {}
    counts = {}
    for split in ("train", "valid", "test"):
        path = data / f"{split}.jsonl"
        if hashlib.sha256(path.read_bytes()).hexdigest() != provenance.get("file_sha256", {}).get(
            path.name
        ):
            raise ValueError("Training export changed after review.")
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if not rows or len(rows) != provenance.get("counts", {}).get(split):
            raise ValueError("Empty or inconsistent training split.")
        counts[split] = len(rows)
        for row in rows:
            if not row.get("provenance", {}).get("reviewer"):
                raise ValueError("Training example lacks reviewer provenance.")
            repo = row["provenance"]["repository"]
            if repos.setdefault(repo, split) != split:
                raise ValueError("Repository leakage across training splits.")
    if (
        counts["train"] + counts["valid"] < 100
        or sum(split != "test" for split in repos.values()) < 5
        or sum(split == "test" for split in repos.values()) < 2
    ):
        raise ValueError("Actual training splits do not meet the readiness gate.")
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument(
        "--model", type=Path, required=True, help="Existing local quantized checkpoint"
    )
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument(
        "--python", type=Path, default=Path(".devpilot/mlx-training-venv/bin/python")
    )
    parser.add_argument("--iters", type=int, default=80)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    args = parser.parse_args()
    try:
        provenance = validate_export(args.data)
    except (ValueError, OSError) as exc:
        parser.error(f"Reviewed training export is not ready: {exc}")
    if not 512 <= args.max_seq_length <= 8192:
        parser.error("Sequence length must be between 512 and 8192")
    if not 1 <= args.iters <= 1000 or not args.model.is_dir() or args.adapter.exists():
        parser.error("Use a local model, a new adapter path and 1–1000 iterations")
    subprocess.run(
        [
            str(args.python.resolve()),
            "-c",
            TOKEN_PREFLIGHT,
            str(args.model.resolve()),
            str(args.data.resolve()),
            str(args.max_seq_length),
        ],
        check=True,
    )
    args.adapter.mkdir(parents=True)
    command = [
        str(args.python.resolve()),
        "-m",
        "mlx_lm",
        "lora",
        "--model",
        str(args.model.resolve()),
        "--train",
        "--data",
        str(args.data.resolve()),
        "--adapter-path",
        str(args.adapter.resolve()),
        "--num-layers",
        "4",
        "--batch-size",
        "1",
        "--iters",
        str(args.iters),
        "--learning-rate",
        "1e-5",
        "--max-seq-length",
        str(args.max_seq_length),
        "--grad-checkpoint",
        "--mask-prompt",
        "--steps-per-eval",
        "20",
        "--save-every",
        "20",
        "--seed",
        "7",
    ]
    metadata = {
        "status": "running",
        "experimental": True,
        "promoted": False,
        "command": command,
        "data_provenance": provenance,
        "required_next_step": "Source-reviewed base versus adapter evaluation on held-out repositories",
    }
    report = args.adapter / "training-run.json"
    report.write_text(json.dumps(metadata, indent=2) + "\n")
    with (args.adapter / "training.log").open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    metadata.update(
        status="completed" if result.returncode == 0 else "failed", exit_code=result.returncode
    )
    report.write_text(json.dumps(metadata, indent=2) + "\n")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
