"""Generate local base/adapter answers from the identical held-out export.

Reference targets are withheld from generation. Scores remain pending source
review. This script cannot promote an adapter or upload examples.
Run with the local MLX virtual environment after unloading Ollama models.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path


def main():
    from mlx_lm import generate, load

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.model.is_dir():
        parser.error("Use an existing local model and a new output file")
    test = args.data / "test.jsonl"
    provenance = json.loads((args.data / "provenance.json").read_text())
    sha = hashlib.sha256(test.read_bytes()).hexdigest()
    if sha != provenance.get("file_sha256", {}).get("test.jsonl"):
        parser.error("Held-out examples changed after review")
    model, tokenizer = load(
        str(args.model), adapter_path=str(args.adapter) if args.adapter else None
    )
    report = {
        "dataset_sha256": sha,
        "adapter": str(args.adapter) if args.adapter else None,
        "model": str(args.model),
        "promoted": False,
        "results": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for line in test.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        messages = row["messages"]
        if messages[-1]["role"] != "assistant":
            raise ValueError("Expected a withheld reviewed target")
        prompt = tokenizer.apply_chat_template(
            messages[:-1], tokenize=False, add_generation_prompt=True
        )
        started = time.perf_counter()
        answer = generate(model, tokenizer, prompt, max_tokens=2048)
        report["results"].append(
            {
                "provenance": row["provenance"],
                "answer": answer,
                "expected_answer": messages[-1]["content"],
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "review": {"correct": None, "complete": None, "unsupported_claims": None},
            }
        )
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
