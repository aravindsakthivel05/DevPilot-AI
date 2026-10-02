"""Run an MLX checkpoint on the unseen repository-tree transfer set."""

import argparse
import json
import time
from pathlib import Path

from mlx_lm import generate, load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    model, tokenizer = load(
        str(args.model), adapter_path=str(args.adapter) if args.adapter else None
    )
    cases = [
        json.loads(line)
        for line in Path("evaluation/transfer-training/test.jsonl").read_text().splitlines()
    ]
    provenance = json.loads(Path("evaluation/transfer-training/provenance.json").read_text())
    holdout_names = list(provenance["independent_holdout_snapshots"])
    if len(cases) != len(holdout_names):
        raise ValueError("Holdout cases and pinned repository manifest differ in length.")
    if args.limit:
        cases = cases[: args.limit]
        holdout_names = holdout_names[: args.limit]

    results = []
    for name, case in zip(holdout_names, cases):
        messages = case["messages"]
        prompt = tokenizer.apply_chat_template(
            messages[:-1], tokenize=False, add_generation_prompt=True
        )
        started = time.perf_counter()
        # MLX-LM's default sampler is greedy; generate() no longer accepts the CLI-only --temp flag.
        response = generate(model, tokenizer, prompt, max_tokens=512)
        results.append(
            {
                "repository": name,
                "commit": provenance["independent_holdout_snapshots"][name]["commit"],
                "fingerprint": provenance["independent_holdout_snapshots"][name]["fingerprint"],
                "response": response,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(args.output), "runs": len(results)}, indent=2))


if __name__ == "__main__":
    main()
