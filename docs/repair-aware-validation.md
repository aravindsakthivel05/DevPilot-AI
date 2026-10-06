# Repair-aware answer validation

DevPilot expands source citations before rejecting individual claims, distinguishes executable completeness from removed documentation, and keeps model-review judgments separate from source facts.

## Flow

1. Read bounded implementations and reserve complete, relevant short branches. Preserve original file coordinates.
2. Generate structured claims. Keep the original draft in `generation_diagnostics.attempts[].draft_claims`.
3. Expand valid citations only within source already supplied to the model. Python AST structure supplies enclosing conditions, handlers and return sites. A complete small Python body can establish an implicit return; an incomplete declaration cannot.
4. Check coordinates, source identity and necessary support. Unknown configuration identifiers still fail; terminology casing such as WebSocket/websocket is accepted.
5. Run a separate, fallible model review of individual claims and coverage of the requested behaviors. A reviewer contradiction verdict needs bounded, available source coordinates; without them it becomes uncertainty. This is not proof that a contradiction exists.
6. Preserve supported claims. Unverified model prose is replaced by neutral uncertainty in the answer, while drafts, reasons and original claims remain diagnostic data.
7. If concrete rejection or missing-coverage feedback exists and accepted details remain, allow one correction. Read additional source candidates, provide retained claims, reserve context space for that feedback, and keep the total generation-attempt limit at two.
8. Select a correction only if it preserves accepted text, or explicitly replaces a mistaken claim through the separate source-reviewed correction protocol, and has at least as good reviewed coverage. Preserve the original answer, source context and citation provenance on failure or dropped details.

## Completeness and uncertainty

`truncated` still describes omitted original lines. `executable_complete` describes whether executable lines were retained; missing comments/docstrings alone do not make behavior incomplete. These are source-coverage signals, not runtime execution or general semantic proofs.

`aspect_statuses[].status` describes claim support. `coverage_status` is a separate reviewer judgment (`complete`, `partial`, or `unknown`). One accepted claim is not a completeness guarantee. The UI states when requested details are missing or completeness is unknown. Coverage can still be judged incorrectly by the same model.

The repair loop preserves accepted information to prevent silent omissions. From October 6, a mistaken accepted claim can be superseded by an explicit cited correction in the same aspect, with separately reviewed source coordinates explaining the mistake. Unreviewed revisions and dropped information preserve the original fallback. A supported correction remains a fallible reviewer judgment, not ground truth. See [complete source-grounded answers](requirement-answers.md).

## Configuration

- `DEVPILOT_VERIFY_CLAIMS=1`: enable fallible claim and coverage review.
- `DEVPILOT_REPAIR_REJECTED_CLAIMS=1`: default; permit one bounded correction after concrete feedback. Set to `0` to avoid the additional generation/review latency. Existing explicit environment values take precedence over setup defaults.
- `DEVPILOT_MODEL_SOURCE_SELECTION=1`: retain bounded model source selection.

No model weights are changed by these checks or by the regression run.

## Verification

`tests/test_repair_aware_validation.py` pairs acceptance cases (implicit returns, assigned return values, complete executable bodies, terminology, retained claims) with rejection cases (incomplete declarations, non-None implicit-return claims, missing identifiers, unsupported reviewer assertions and lost repair details). It also checks restoration of the original citation context after a failed correction and source-budget reduction when repair feedback needs space.

The frozen aiohttp/Werkzeug regression rerun and its raw diagnostic evidence are in `evaluation/checks-repair-2026-10-05/`. These questions informed development and are not an unseen accuracy benchmark.
