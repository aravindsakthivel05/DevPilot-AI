# DevPilot source fixture

A deliberately small, mixed-language source repository for integration checks. It is **not** a production application or a representative complex repository benchmark. Do not install dependencies or execute `python/static_candidates.py`; two intentional diagnostic candidates are included. The declared `example-library` dependency is synthetic fixture data, not a recommended package.

Index this folder in DevPilot, then ask:

- In the Python pricing module, how does a shipping quote handle a nonpositive weight?
- How does the TypeScript API delegate quote computation to pricing?
- What is the current production deployment state? (The snapshot cannot establish this.)

The expected retrieval and error labels are in `evaluation/implementation-2026-10-04/research-cases.json`. These are authored development fixtures, not held-out evidence of generalization.
