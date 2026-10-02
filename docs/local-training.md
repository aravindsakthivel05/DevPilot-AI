# Local transferable-pattern training

## Goal and boundary

This experiment trains Qwen to apply repository-structure analysis habits to an unfamiliar tree.
It does not teach Qwen the source code or behavior of the 15 training repositories, and it does
not replace indexing the repository being investigated. The training input contains relative
paths, indexed-file counts, extension counts, and selected build/test configuration filenames;
it contains no source-code bodies. DevPilot's existing Ollama model remains unchanged and does
not load this experimental adapter.

## Data and reproducibility

[`evaluation/transfer-training/`](../evaluation/transfer-training/) contains the generated
`train.jsonl` (76 examples), `valid.jsonl` (15 examples), `test.jsonl` (4 examples), and
`provenance.json`. The 15 indexed training snapshots and their commit/fingerprint records are
listed in `provenance.json`. The four transfer cases use Click, JUnit 4, urllib3, and Apache
Commons Collections; they were held out from adapter training. Repository-specific data used
for this exercise is structural metadata only. The previously prepared 175 candidate cards
remain pending human review and were not treated as truth labels.

The corpus builder is `scripts/build_transfer_training_data.py`. It excludes documentation and
example trees from test-code samples and only lists recognized project-level manifests. To
regenerate the corpus, run `python -m scripts.build_transfer_training_data` from the project
root. Inspect the resulting examples before any later training run.

## Local run

The local MLX-LM environment is under the ignored `.devpilot/mlx-training-venv/`; the 4-bit
MLX Qwen2.5-Coder-7B-Instruct checkpoint is under `.devpilot/models/`. Training ran on this
Mac's Metal GPU with LoRA, four trainable transformer layers, batch size 1, sequence length
1024, gradient checkpointing, prompt masking, learning rate `1e-5`, and 80 iterations. About
2.9 million adapter parameters were trainable and reported peak memory was 6.03 GB. Validation
loss declined from 2.764 at the initial evaluation to 0.733 at step 80. A small number of
sequences exceeded the 1024-token limit and were truncated.

The final adapter and step checkpoints are stored in the ignored path
`.devpilot/adapters/repo-structure-v1/`. To rerun the same training command:

```sh
.devpilot/mlx-training-venv/bin/mlx_lm.lora \
  --model .devpilot/models/Qwen2.5-Coder-7B-Instruct-4bit \
  --train --data evaluation/transfer-training \
  --adapter-path .devpilot/adapters/repo-structure-v1 \
  --fine-tune-type lora --num-layers 4 --batch-size 1 --iters 80 \
  --learning-rate 0.00001 --max-seq-length 1024 \
  --grad-checkpoint --mask-prompt --val-batches -1 \
  --steps-per-eval 20 --steps-per-report 10 --save-every 20
```

`scripts/evaluate_transfer_adapter.py` runs the same four transfer prompts against the base
checkpoint and an adapter. The saved outputs are `baseline-holdout.json` and
`adapter-holdout.json` in the transfer-training directory.

## Result and decision

This first training run did **not** improve transfer quality. On all four unseen repository
trees, the adapter produced vague, repetitive answers, omitted specific observed paths, and
sometimes emitted malformed end-of-turn tokens. The base model gave more repository-specific
answers, although it also overstated what directory counts prove (for example, calling tests
“comprehensive”). The adapter's validation loss improved on examples generated from the same
training repositories, but this did not transfer to the independent tree prompts. This is a
clear example of why training loss alone is not a quality measure.

Do not use this adapter for normal DevPilot answers. The measured run is retained as an
experimental artifact to make the outcome inspectable. No weights were merged into Qwen, no
runtime default was changed, and nothing was uploaded to a cloud service.

The next useful improvement is to replace the repetitive templated targets with a larger,
independently reviewed set of concise structure-analysis examples, add a held-out set with
diverse prompt styles and programming languages, and compare multiple checkpoints using a
fixed human rubric for evidence accuracy, unsupported claims, omissions, and answer clarity.
Only a later adapter that beats the unchanged base on that unseen set should be considered for
optional local use. Repository-specific facts still need per-repository indexing and retrieval.
