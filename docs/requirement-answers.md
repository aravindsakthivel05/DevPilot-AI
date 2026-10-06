# Complete source-grounded answers

The October 6 NetworkX baseline retrieved all frozen source anchors, but covered
only 6/17 required details. The changes below address answer omissions and
validation errors. They do not establish that model output is correct.

## Reading and answering

`backend/rag/obligations.py` derives bounded requirements from the question alone:
requested conditions, results, argument forwarding, error triggers, state changes,
ordering and enumerated cases. Reference answers never enter these requirements.
The generator maps every requirement to zero-based generated-draft claim indices or marks it
missing. These indices refer to the stable original claims in the attempt diagnostics
(`claim_audit.original_claims`), before rejection coalesces missing-detail messages;
they are not indices into the final rendered answer. Duplicate IDs, cross-aspect references and references to rejected claims
cannot establish coverage. Invalid coverage metadata is reported separately and
does not discard otherwise cited answer text.

The generator explains condition → action/call with arguments → result in its
claim text, assisted by the existing source-linked Python syntax tables. This is
structured source reading, not symbolic execution or a full control-flow proof.
The reviewer independently checks requirements, including exact exception
predicates. Error messages do not establish the predicate that caused an error.
The generator prompt distinguishes yielded objects from generator functions,
follows helper results through caller state changes, and keeps explicitly
enumerated valid cases separate from unrelated invalid-input scenarios.
Both coverage assessments remain fallible model judgments. Human/source review
and representative execution scenarios are needed to score actual quality.

`backend/rag/subject_scope.py` distinguishes a conditional subject supplied by the
question (for a MultiDiGraph) from an assertion that the cited function declares
that class, including the conditional plural form (for MultiDiGraphs).
The narrow exemption does not authorize invented class identities,
methods or configuration. All claims still require actual source coordinates and
the normal review policy.

## Reviewed correction

Earlier accepted claims remain fallible. Repair may explicitly replace one using
its previous claim index, a cited replacement in the same aspect, and a reason.
The same reviewer separately checks the correction and must identify valid source
coordinates explaining the mistake. Only a supported replacement with an approved
correction can supersede the retained text. An invalid revision record, unavailable
review or dropped information preserves the original accepted answer when one exists. This is a
bounded correction mechanism, not independent proof of a better answer.

## Efficiency and inspection

- Claim review stores cited line text once; each claim keeps exact line references.
  Other claims' cited lines cannot count as positive support for this claim.
- The reviewer does not receive the generator's completeness flags. When its
  prompt is too large, it first removes duplicate derived syntax tables while
  retaining every cited and enclosing source line, then adapts its output reserve.
  If the actual source and a minimum response reserve still cannot fit, review
  remains unavailable. Budget decisions are recorded; estimates are approximate.
- Generation context is checked against the actual serialized prompt estimate,
  including requirements. Repeated tables and low-priority sources are trimmed
  first. Token estimates are approximate; provider usage reports actual counts.
- Unambiguous exact named implementations use deterministic source ordering.
- A 32-entry process-local cache reuses lexical evidence only when database path,
  snapshot, index revision, database/WAL stamps, query and settings match. It returns
  isolated copies. Writes or setting changes invalidate reuse. Semantic retrieval
  and generated answers are recomputed; provider failures are not cached.
- `stage_timings_ms` reports initial retrieval, source reading, generation, review
  and local validation. Attempt diagnostics retain model usage, failures, correction
  decisions and selected contexts. Missing-detail descriptions are shown in the UI.

## Evaluation and training

The frozen benchmark spans NetworkX, Tenacity, Boltons, AnyIO and Pluggy, with
branching, error precedence, argument forwarding, plugin dispatch, history and
private-runtime guards. Development regressions and fresh holdout runs are labelled
separately in `evaluation/requirements-2026-10-06/`. Source-authored references and
Codex reviews are not independent human labels. Keep failed attempts in scores.

`scripts/compare_local_models.py` compares installed generators and reviewers on
identical frozen contexts and records source/code/model hashes. Use
`scripts/summarize_model_comparison.py` with explicit source reviews to score those
outputs. The comparison does not change the configured model automatically.

The existing local training gate remains in force: reviewed development examples
from multiple repositories and repository-separated validation/holdout data are
required. New review packs include the requirement-aware response contract; older claim-only
packs require separate review before migration. New test runs never update weights. Pending targets and a low training
loss do not justify training-data approval or adapter promotion.
