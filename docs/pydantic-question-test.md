# Pydantic question test

DevPilot indexed `pydantic/pydantic` at commit
`bb6da4cfbb1f559885ea2fa207ec93853bfeac64` (snapshot
`96e7fe6b9ebf73cf2f4115fc363b36a3b34dfc9d0cb70149ecb2c51c6559a019`). The index
contains 597 files, 14,638 symbols, and 21,841 resolved edges. Embeddings finished successfully.
The scanner skipped 221 files, including unsupported Rust source; this test deliberately asks
about Python code.

The same [source-reviewed questions](../evaluation/pydantic-test-candidates.jsonl) were rerun
through Quick and Deep in hybrid mode with local `qwen2.5-coder:7b`. The latest
[evaluation artifact](../evaluation/pydantic-devpilot-question-run-v14.json) records the pinned
snapshot, top-eight evidence, generated/fallback status, warnings, latency, and citations. It
invokes the backend functions used by the API routes directly; it does not measure HTTP server
behavior.

| Question | Quick recall@8 | Quick answer | Deep recall@8 | Deep answer |
| --- | ---: | --- | ---: | --- |
| Easy: `model_dump` | 1/1 | Correct: names `__pydantic_serializer__.to_python()` and explains `exclude_none` | 1/1 | Same correct answer |
| Medium: `model_json_schema` | 2/3 | Generated, but incorrectly says the mock schema rebuilds itself via `__pydantic_core_schema__.rebuild()` | 2/3 | Generated, but omits the specific mock-schema rebuild behavior |
| Hard: unresolved forward reference | 3/6 | Generated a lifecycle explanation from retrieved source | 6/6 | Generated a lifecycle explanation covering all six expected symbols |

Deep used four retrieval passes for medium and hard. The updated answer contract uses a
schema-constrained response from local Ollama, keeps all six hard-question obligations separate,
checks that each claim relates to its aspect, and selects a matching source line deterministically
from the cited excerpt. All six answers generated in one call without warnings. Quick/Deep times
were 4.8/4.4 seconds for easy, 7.4/9.1 seconds for medium, and 14.4/17.6 seconds for hard.
These are single-run measurements on a warm local model, not a controlled speed comparison. The
full DevPilot suite passed with 94 tests passed and one Docker-dependent test skipped. No Pydantic
project tests or container execution were run.

The generated response must cover each aspect and contain terms that connect it to the aspect and
selected source line. These checks are deterministic relevance checks, not semantic entailment;
they cannot prove that a line fully supports a claim (`citation_check.entailment_checked` remains
false). Medium retrieval still finds two of three expected symbols, although the helper excerpt
contains the final generator call. Hard Quick retrieves three of six expected symbols while Deep
retrieves all six. This three-question check is a narrow diagnostic, not an accuracy estimate.

## Source review and baseline failures

- **Easy:** [`BaseModel.model_dump`](https://github.com/pydantic/pydantic/blob/bb6da4cfbb1f559885ea2fa207ec93853bfeac64/pydantic/main.py#L472)
  calls `self.__pydantic_serializer__.to_python(self, ...)` and forwards `exclude_none` as a
  keyword argument. In the initial run, both model responses instead answered about
  `model_dump_json`, even though the correct `model_dump` symbol appeared in the evidence.
- **Medium:** `BaseModel.model_json_schema` delegates to the
  [`model_json_schema` helper](https://github.com/pydantic/pydantic/blob/bb6da4cfbb1f559885ea2fa207ec93853bfeac64/pydantic/json_schema.py#L2715). That helper
  creates a generator, asks a mock core schema to rebuild if needed, and calls
  `schema_generator_instance.generate(cls.__pydantic_core_schema__, mode=mode)`. Earlier runs
retrieved the helper but did not name that call precisely in earlier runs. In v14 both answers
reached the final generator call, but Quick made an unsupported statement about a mock-schema
`rebuild()` method and Deep omitted the specific rebuilding mechanism.
- **Hard:** Class construction tries `complete_model_class`, which installs mocks if an undefined
  annotation prevents completion. A later `model_validate` access to the mock validator triggers
  `model_rebuild`, which retries completion and installs the real validator when the type resolves.
  If rebuilding still fails, the mock raises `PydanticUserError`. This path is implemented in
  [`_model_construction.py`](https://github.com/pydantic/pydantic/blob/bb6da4cfbb1f559885ea2fa207ec93853bfeac64/pydantic/_internal/_model_construction.py),
  [`_mock_val_ser.py`](https://github.com/pydantic/pydantic/blob/bb6da4cfbb1f559885ea2fa207ec93853bfeac64/pydantic/_internal/_mock_val_ser.py), and
  [`main.py`](https://github.com/pydantic/pydantic/blob/bb6da4cfbb1f559885ea2fa207ec93853bfeac64/pydantic/main.py), and exercised by
  [`test_forward_ref_auto_update_no_model`](https://github.com/pydantic/pydantic/blob/bb6da4cfbb1f559885ea2fa207ec93853bfeac64/tests/test_forward_ref.py#L46).
  Both initial generated answers missed this path and made unsupported repair claims.

In the earlier prompt version, the provider checked that each claim included a quote appearing
exactly in its cited source; the citation checker validated marker placement and numbering. Neither
established that a quote logically supported a claim (`entailment_checked: false`). The initial run
accepted incorrect answers because their citations were syntactically valid. The two initial medium
responses were rejected and replaced with retrieval reports. On this small,
deliberately chosen set, the initial run produced zero correct explanatory answers. The rerun
improved the easy answer but still left the medium and hard explanations incomplete in v6. The
v14 run improves retrieval on the hard question, but the medium explanations remain incomplete or
incorrect and the three-question set remains a diagnostic rather than
an overall accuracy estimate.
