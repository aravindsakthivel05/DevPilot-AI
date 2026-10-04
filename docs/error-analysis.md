# Static error analysis and suggestions

`backend/errors/` separates static candidate detection from model reasoning. The core never runs target repository code.

Implemented candidates:

- Parser syntax diagnostics for nine languages; Python AST syntax errors are stronger than grammar-recovery diagnostics.
- Invalid `package.json` JSON; JSONC `tsconfig.json` is not incorrectly treated as strict JSON.
- Python duplicate unconditional top-level definitions (replacement may be intentional).
- Explicit missing Python relative modules in the indexed snapshot (files may be generated/excluded).
- Straight-line unreachable siblings after `return`, `raise`, `break` or `continue`.
- Too many positional arguments to a direct undecorated, unreassigned top-level Python definition; starred/dynamic calls are excluded.
- Selected undefined names in simple undecorated top-level Python function scopes, with parameters/imports/builtins/exception and match bindings recognized. Dynamic injection, nested scopes and comprehensions are excluded conservatively.
- Import cycles through established graph edges, labelled informational because cycles are not necessarily failures.

Every candidate has snapshot/repository identity, type, severity, confidence, file/line, source evidence, candidate cause, suggested action and test guidance. Localisation finds the enclosing source entity and bounded static neighbors. It does not claim execution confirmation. An unresolved call, external library, ambiguous overload or unknown framework receiver is not automatically an error. Missing implementations, complete unused-code detection, general API/type mismatches and whole-program dependency correctness are not reliably supported.

Cause investigation retains the static candidate explanation and optionally asks custom hybrid RAG for a source-backed explanation. If the model fails validation, the UI shows static evidence and the failed/insufficient model investigation; it does not invent a successful explanation.

Fix/test generation retrieves source definitions and related tests/manifests, uses existing repository conventions where available, and requests minimal source replacements plus new test files. Paths must be safe and indexed edits must match exact old text. Edits become a unified diff and undergo `git apply --check` against the stored snapshot. This checks applicability **without applying the patch**. New tests undergo grammar/AST syntax checks; Python test framework imports receive selected checks. Test-only requests reject implementation patches/edits and may retry once.

These checks do not validate behavior, all imports, build configuration, test effectiveness or completeness. The draft includes `status=draft_unverified` and `verified=false`, evidence and missing information. Suggested code is never auto-applied and suggested tests are never run by the core. A reviewer must assess cause, contract, framework conventions, edge cases, patch relevance and regressions before manual application.
