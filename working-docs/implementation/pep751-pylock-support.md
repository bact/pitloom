---
Created: 2026-09-02
Last-Modified: 2026-09-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# PEP 751 (`pylock.toml`) support -- implementation notes

See also: [poetry-support.md](poetry-support.md)'s "`poetry.lock`
transitive dependencies" section -- this feature reuses that shape
almost unchanged; [lock-files.md](../design/lock-files.md) for the
broader multi-format lock-file roadmap this closes Phase 1's headline
item of; [sbom-lifecycle-stages.md](sbom-lifecycle-stages.md) for the
source/build/deployed staging model that makes this source-stage-only;
[lock-file-cascade.md](lock-file-cascade.md) for the shared priority
mechanism this format's wiring was generalized into once `uv.lock`,
`pdm.lock`, `Pipfile.lock`, and pinned `requirements.txt` needed the
same shape -- the "Wiring" and "Priority" sections below describe that
current, generalized mechanism, not this format's original bespoke one.

## Motivation

[PEP 751] standardises `pylock.toml` as a build-backend-agnostic,
fully resolved dependency snapshot -- produced by `uv export --format
pylock.toml`, `pdm lock --format pylock`, `poetry export
--format=pylock.toml`, and similar, consumed only by installers. Per
[lock-files.md](../design/lock-files.md), it's the "universal core" a
Python SBOM generator should support first, since it works for any
project regardless of build backend, unlike the already-shipped
`poetry.lock` support which only applies to Poetry projects.

[PEP 751]: https://peps.python.org/pep-0751/

## Source files

| File | Role |
| :--- | :--- |
| `src/pitloom/extract/_pylock.py` | `pylock.toml` resolved-dependency extraction (source-stage only) |
| `src/pitloom/extract/_locked_dependencies.py` | Cascade wiring `pylock.toml` (and every other lock format) into `read_project()` -- see [lock-file-cascade.md](lock-file-cascade.md) |
| `tests/extract/test_pylock.py` | `pylock.toml` parsing unit and integration tests |
| `tests/extract/test_locked_dependencies.py` | Cascade mechanism tests (priority ordering, override note, `setup.py`-only wiring) |

No changes were needed in `src/pitloom/assemble/spdx3/deps.py` or
`document.py` -- both already operate on the generic
`ProjectMetadata.locked_dependencies` field the `poetry.lock` work
introduced, with no knowledge of which lock format populated it. The
existing `tests/assemble/test_deps_locked_dependencies.py` suite
already covers that layer generically and needed no changes either.

## Extraction function

### `extract_pylock_dependencies(project_dir)`

Reads `pylock.toml` next to `pyproject.toml` and returns its resolved
`[[packages]]` entries as exact-pin `name==version` PEP 508 strings.
Returns `None` when no `pylock.toml` is present or it can't be parsed --
optional enrichment, never a requirement. `None` (as opposed to a
valid-but-empty `[]`) tells the cascade this source doesn't apply here,
so a lower-priority source can still be tried, rather than a genuinely
dependency-free lock file being confused with an absent/unusable one.

Unlike `poetry.lock`, PEP 751 has no `groups`-style per-package
membership tag to filter on: a `pylock.toml` is already the flattened,
fully resolved package set for whichever extras/dependency-groups the
tool that generated it was asked to include (`dependency-groups`/
`default-groups`/`extras` are file-level generation inputs, not a
per-package "which group requested me" marker). So every `[[packages]]`
entry is taken as-is, with no group-based filtering.

A malformed lock (a `packages` key that isn't a list, or an individual
`[[packages]]` entry missing/non-string `name`/`version`) is skipped
with a `WARNING:`, not silently dropped, per this repo's "no silent
deviations" rule -- mirrors `poetry.lock`'s equivalent malformed-entry
handling. The top-level `lock-version` field is validated more strictly
than a bare presence check: it must parse as a `major.minor` pair
(rejecting e.g. `"garbage"` or `"1.0.0"`), and a *major* version other
than the one this Pitloom release understands (`1`) is rejected
outright -- PEP 751 may define an incompatible schema under a future
major version. A newer *minor* version within the known major (e.g.
`"1.5"` when this release only knows `"1.0"`) is still read, per PEP
751's additive-minor-versions policy, but with a `WARNING:` that some
content may go unrecognized.

## Non-registry sources

A package pinned via PEP 751's `vcs`, `directory`, or `archive` source
tables has no meaningful PyPI version pin, so including it as
`name==version` would misrepresent it as an ordinary published release
(wrong PURL, bogus PyPI enrichment lookup downstream). These are
skipped with a `WARNING:` naming the package and source kind --
mirrors `poetry.lock`'s equivalent `directory`/`file`/`git`/`url` skip
in `_poetry_lock.py`. A package sourced via `sdist`/`wheels` (or with no
source table at all) is included whenever it has a version.

## Wiring and priority

`pylock.toml` is one entry (the highest-priority one) in the shared
lock/pin cascade -- see [lock-file-cascade.md](lock-file-cascade.md) for
the mechanism, priority order, provenance recording, and why the
cascade is called from `read_project()` rather than
`read_pyproject()`. Two points specific to `pylock.toml` itself:

- It's build-backend-agnostic -- a plain PEP 621 project with no Poetry
  involvement at all can have one -- unlike `poetry.lock`, which is
  gated behind `[tool.poetry]` detection.
- No `include_locked_dependencies`-style build-stage guard was ever
  needed for it: unlike `poetry.lock` (whose gap-fill helper
  `_try_read_poetry()` is also called directly by the Hatchling build
  hook's `_poetry_fallback_metadata()`, which must pass
  `include_locked_dependencies=False` to avoid leaking a source-stage
  artifact into a build-stage SBOM), `read_project()`'s cascade call is
  never reached from the Hatchling build hook at all -- only from the
  CLI/library source-stage path.

## Known limitations

- **No dependency graph, same as `poetry.lock`.** PEP 751 packages can
  declare a `dependencies` list identifying their own resolved pins
  (useful for reconstructing a full transitive graph), but this
  extractor -- matching `poetry.lock`'s existing flat-list shape --
  only returns the flattened package list, not that graph. Every
  locked package not already a direct dependency gets one additive
  `dependsOn` edge straight from the main package
  (`_locked_transitive_only_dependencies()` in `document.py`), the same
  as `poetry.lock`.
- **No marker evaluation.** A `pylock.toml` entry may carry a `marker`
  (environment marker) restricting when it applies (e.g. a
  platform-specific package). This extractor doesn't evaluate markers
  against any particular environment -- every `[[packages]]` entry is
  included regardless, the same simplification `poetry.lock` parsing
  already makes for direct dependency constraints.
- **`pylock.<name>.toml` named locks are not discovered.** PEP 751
  allows a `pylock.<name>.toml` naming convention (e.g.
  `pylock.dev.toml`) for multiple named locks in one project; only the
  bare `pylock.toml` is read. Extending discovery to named locks would
  need its own priority/selection rule and is left for a future change
  if a real project motivates it.
