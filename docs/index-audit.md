# Indexed-file audit

The eight pinned reference snapshots have path-level coverage records in
[`reference-coverage.json`](reference-coverage.json). None hit the file or coverage-entry caps.
Ignored directories are reported as boundaries; their contents were not scanned. Most skipped
files are images, fonts, binary fixtures, or repository metadata.

The scanner update now includes selected text files at the same pinned commits:

- pytest's eight `.pyi` files are now indexed as text. They are test fixtures, and Python-stub
  structural analysis remains a separate task because it could duplicate definitions from `.py`.
- Mockito's `mockito-extensions/org.mockito.plugins.*` files are indexed, with conservative links
  to 15 plugin interfaces and seven indexed implementation classes. Unresolved aliases remain
  visible as text rather than invented graph edges.
- CSS/SCSS and common JavaScript/TypeScript suffixes are indexed as text for UI questions. Their
  imports and selectors are not yet structurally analyzed.
- Makefile, Dockerfile, MANIFEST.in, gradlew, and mvnw are allowed by filename. Arbitrary
  extensionless files and binaries remain excluded.

The old manifests and coverage report were preserved as `reference-snapshots-v1.json`,
`clean-holdout-snapshots-v1.json`, and `reference-coverage-v1.json`. The current manifests point
to reindexed snapshots at unchanged commits. [The comparison](indexing-v2-comparison.json)
records old and new file counts and fingerprints. The 48-case development regression and
12-case Click/JUnit4 holdout retained their prior scores after reindexing. The added files are
available for new question types, but have not yet produced a measured retrieval gain.
