---
Created: 2026-09-13
Last-Modified: 2026-11-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Performance optimisations

Known, non-blocking optimisation opportunities — analysed and deferred,
not rejected. Each entry records the bottleneck, expected impact, what
blocks a fix, and where the relevant code lives.

See also: [roadmap.md](roadmap.md) (feature-oriented plan).

---

## Eager PyPI prefetch ignores locally-filled fields

**Identified:** PR #212 code review (2026-09-13)

**Bottleneck:** `_prefetch_combined_release_info()` in
`_document_locked_deps.py` eagerly fetches PyPI release JSON for *every*
dependency before any per-package enrichment runs. Even when installed
metadata + a lock-file hash fully satisfy a dependency's `originator`,
`license`, and `hash` fields, the PyPI network call for that package was
already made and wasted.

The per-package short-circuit (`if {"originator", "license",
"hash"}.issubset(already_filled): return set()`) in `_enrich_from_pypi()`
prevents wasted *parsing* of the prefetched response, but not the
network call itself.

**Expected impact:** Fewer HTTP requests in online mode for projects
whose installed metadata is already rich (common for well-maintained
packages). The prefetch is concurrent, so wall-clock savings depend on
how many packages can be skipped vs total batch size.

**What blocks it:** The prefetch runs before `_enrich_from_installed()`,
which is what discovers which fields are already filled. Fixing this
requires restructuring the enrichment pipeline to:

1. Run `_enrich_from_installed()` for all dependencies first (collecting
   `filled` sets).
2. Apply lock hashes for all dependencies (updating `filled` sets).
3. Filter out dependencies where all three fields are already covered.
4. Batch-prefetch only the remaining dependencies.

This touches the core assembly loop in `deps.py` and
`_document_locked_deps.py` and changes the execution order of side
effects (provenance writes, package mutations), so it needs careful
design to avoid regressions.

**Where:**

- `_document_locked_deps.py:_prefetch_combined_release_info()`
- `deps.py:_finish_dependency_enrichment()`
- `deps.py:_enrich_from_pypi()`

---

## Rust backend / parallel hashing

**Identified:** roadmap review (moved from [roadmap.md](roadmap.md))

**Bottleneck:** For large projects, two CPU-bound operations dominate
wall-clock time: build log parsing and per-file SHA-256 hashing for
Merkle root computation. Both are embarrassingly parallel and
byte-processing-intensive — good candidates for a compiled backend.

**Expected impact:** Significant for projects with thousands of files
or large build logs. Not blocking any current use case at the private
alpha scale.

**What blocks it:** Requires introducing a Rust build dependency
(via PyO3/maturin) into a pure-Python project. Worth deferring until
profiling shows these are the real bottlenecks at production scale.
