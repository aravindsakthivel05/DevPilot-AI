# Two-repository holdout run — October 4, 2026

Questions and source labels for ItsDangerous and Zod were frozen before these outputs. Source labels and expected answers were withheld from retrieval, reading and generation. The raw results have unchanged backend hashes within this run.

Both repositories indexed successfully, and required source-anchor context recall was 1.0 across four answerable questions. **Strict source review found no fully complete and grounded answers: three were incomplete, and one contained an explicit false cache-reuse claim.** Both live-state questions correctly abstained. Median answerable-case latency was 78.0985 seconds.

The compression answer explains the important threshold and dot/base64 marker correctly, but the strict frozen reference also includes the serialization step. The timestamp answer misses negative-age expiry. The safe-parse comparison misses the synchronous Promise error and exact success/failure shape. The failure helper answer incorrectly says the cached error is not reused.

See `questions.json`, `snapshots.json`, `results.json`, `source-review.json`, and `summary.json` for full evidence. Reviews were authored by Codex, not an independent human evaluator. Project tests and retrieved-source coverage do not certify answer correctness.

After inspecting the Zod failure, a general captured-getter cache guard was developed and checked separately in `../quality-2026-10-04/final-guard-validation/`. **Zod is now a development repository for future comparisons.** The original holdout result above remains unchanged; the new guard check is not presented as untouched holdout performance.
