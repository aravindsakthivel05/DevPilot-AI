# Current implementation and research follow-up

The approved architecture refactor is implemented as a recommendation-based research prototype. Its actual scope, API/database changes, test results and limitations are in [implementation-2026-10-04.md](implementation-2026-10-04.md).

Remaining research work is distinct from making the prototype runnable:

1. Broader independently reviewed, frozen cross-language holdout questions and candidate issue/fix labels.
2. Stronger semantic resolution for TypeScript/default imports, Go modules, Rust traits, C/C++ macros and C# instance/project types.
3. Measured vector-store scaling and context/latency tradeoffs on much larger corpora.
4. Better control-flow-aware claim support and fewer false abstentions; current syntax/identity/model checks remain fallible.
5. Reviewer-approved training examples and an untouched holdout before optional local tuning. Repositories alone do not train weights.

No Docker verification, automatic patch application or target test execution is required for these core research capabilities. Earlier execution-oriented plans and reports are historical experiments, not the current default workflow.
