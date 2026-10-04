# Local model comparison

On 25 September 2026, DevPilot compared locally installed `llama3.2:latest` and
`qwen2.5-coder:7b` through Ollama's localhost API. The first question from each of Flask,
Requests, HTTPX, and pytest was given the same eight retrieved source locations. Raw answers,
timings, and citation checks are in [`evaluation/model-comparison.json`](../evaluation/model-comparison.json).

| Model | Answers with numbered citations | Mean time per answer |
| --- | ---: | ---: |
| Llama 3.2 | 0/4 | 16.5 s |
| Qwen 2.5 Coder 7B | 2/4 | 33.0 s |

The initial prompt asked for citations but did not define their exact format strongly enough.
After requiring `[1]`, `[2]`, etc. in every substantive paragraph, a repeat on Flask and Requests
produced citations in 2/2 Llama answers and 1/2 Qwen answers. See
[`evaluation/model-comparison-citation-prompt.json`](../evaluation/model-comparison-citation-prompt.json).
DevPilot now falls back to its source-location report if a model response has no valid numbered
citations. Citation syntax only checks the reference number range; it does not establish that a
claim is supported by the cited source.

Four questions and two prompt-repeat questions are insufficient to rank answer accuracy, select
a final model, or justify fine-tuning. Review the answers against source and expand the labelled
set before making those choices. No training was performed, and no cloud model was used.

On the demo proposal smoke test, Llama returned no usable test or patch, while Qwen returned a
valid unverified draft. `make api-local` therefore uses Llama for answers and Qwen for proposals;
`DEVPILOT_PROPOSAL_MODEL` can override that choice. A valid draft alone does not establish patch
correctness. See [`model-validation.json`](model-validation.json) and
[`model-validation-qwen.json`](model-validation-qwen.json).

For a more specific demo request to permit zero-weight domestic parcels at the minimum quote,
the coding model produced one regression test and an exact source edit. DevPilot generated the
unified diff, checked it against the indexed snapshot, and ran the draft in Docker. The generated
test failed before the patch (exit 1) and passed after it (exit 0). This is one verified demo
change, not a real-repository repair benchmark.

## October 3 accuracy comparison

Qwen2.5-Coder 14B is now installed locally and was compared with 7B using identical frozen source
excerpts on new Jinja/Gson snapshots. On six answerable cases, source review found one correct and
complete 7B answer versus three for 14B; strict exact-citation support reduced those counts to one
and two. Median single-attempt latency was 23.1 seconds and 81.3 seconds. Both models still made
errors that their own model audits accepted. Both declined two explicit live/private questions
without a provider call. This single-repeat sample is too small for a general model-quality claim.

The setup script retains 7B for lower latency. 14B is an available slower accuracy option:

```sh
DEVPILOT_LLM_MODEL=qwen2.5-coder:14b ./setup_and_run.sh
```

It ran entirely on the GPU at an 8192-token context on the 18 GiB Mac during this check. Increasing
context further can consume more memory; inspect the actual loaded model in Environment & providers.
These are generation evaluations, not fine-tuning. The [full checkpoint](accuracy-2026-10-03.md)
links raw answers, exact source judgments, timing and remaining limitations.
