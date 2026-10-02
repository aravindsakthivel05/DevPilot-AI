# First local transfer-training result

The base and adapter runs used the same four held-out tree prompts and the same local 4-bit
Qwen2.5-Coder-7B-Instruct checkpoint. The tree data is pinned in `provenance.json`. Raw model
outputs and per-answer latency are preserved in `baseline-holdout.json`, `adapter-step20-holdout.json`,
and `adapter-holdout.json`.

| Held-out repository | 20-step adapter checkpoint |
| --- | --- |
| Click | Echoed visible file counts and the `src/`, `tests/`, `docs/` layout, but labelled the layout “typical” and inferred roles from counts. |
| JUnit 4 | Named the Maven layout and `pom.xml`; described the convention as “standard” without source verification. |
| urllib3 | Named visible `src/`, `test/`, `docs/`, and manifest evidence; still inferred pytest from `conftest.py`. |
| Apache Commons Collections | Named Java file totals and Maven, but incorrectly characterized the visible source/test layout as `src/` instead of the more specific `src/main/java` and `src/test/java`. |

| Held-out repository | Base model | Trained adapter |
| --- | --- | --- |
| Click | Named the observed tests, docs, source, and `pyproject.toml`; overclaimed that counts implied a “comprehensive” suite. | Replaced paths with generic claims, repeated its caveats, and emitted malformed end markers. |
| JUnit 4 | Identified Java, nested tests, and Maven from visible paths/config; some claims about test framework are inferred. | Did not state concrete paths or manifest; repeated caveats and malformed end markers. |
| urllib3 | Named `test/`, `src/`, docs, and Python config files; still treated directory counts as evidence of scale. | Repeated directory metadata instead of analyzing the layout, with substantial boilerplate repetition. |
| Apache Commons Collections | Identified nested Java tests and Maven; some project identity and test claims were inferred. | Gave generic statements, omitted observed paths, and emitted malformed end markers. |

Neither adapter checkpoint consistently improved on the base. The 20-step checkpoint was more
specific than step 80, but it still made unsupported inferences and missed precise Java paths.
The final adapter generated more boilerplate and was about 1.2 seconds slower on average
(19.44 s vs. 18.27 s). The base was also imperfect, so these four cases are a diagnostic, not a
general accuracy estimate. Keep both checkpoints unused until a new dataset and a larger,
untouched, reviewed evaluation show a clear improvement.
