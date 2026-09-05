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
membership *field*: a `pylock.toml` can bundle more than one
dependency-group's packages in a single flattened `[[packages]]` list,
distinguished only by an optional per-package `marker` string
referencing the pseudo-environment variables `extras`/
`dependency_groups` (e.g. `"'dev' in dependency_groups"`). This
extractor filters to the file's own declared `default-groups` (no
extras) the same way `poetry.lock`/`pdm.lock` filter to their
`main`/`default` group: `_default_group_environment()` builds a
`{"dependency_groups": frozenset(default-groups), "extras":
frozenset()}` environment, and `_group_marker_excludes()` evaluates
each package's `marker` against it with 3-valued logic -- a clause
testing `extras`/`dependency_groups` membership gets a real
`True`/`False`, every other PEP 508 marker variable (`python_version`,
`sys_platform`, etc.) evaluates to "unknown" rather than a real
environment reading (see "Known limitations" below), and a package is
excluded only when the tree provably evaluates `False` from the known
group/extras clauses alone.

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

## Single-use vs multi-use lockfiles

PEP 751 explicitly supports two shapes of `pylock.toml`, and this
extractor handles both without needing to detect which one it's
looking at:

- **Single-use** -- like `requirements.txt`, one file serves one fixed
  purpose (e.g. a production-only or dev-only export). No package
  carries a group/extras-referencing `marker`, since there's no second
  configuration to distinguish from; every `[[packages]]` entry is
  simply included, `default-groups` filtering is a no-op (nothing to
  filter), and `_group_marker_excludes()` never has anything to
  evaluate. `tests/fixtures/real-world-locks/pylock/snowflake-cli-3.26.0/`
  is this shape in practice: its packages' own `marker` fields are
  ordinary `python_version`/`sys_platform` conditions only, never
  `dependency_groups`/`extras`.
- **Multi-use** -- one file bundles more than one installable
  configuration (e.g. base + a `dev` dependency-group) to avoid
  duplicating packages shared between them, distinguishing membership
  per package via a `marker` referencing the `dependency_groups`/
  `extras` pseudo-environment variables (e.g. `"'dev' in
  dependency_groups"`, `"'security' in extras"`). This extractor
  resolves *both* variables against a fixed "no extras, only the file's
  own `default-groups`" environment (see above) -- Pitloom's SBOM
  always represents the base/default install, the same policy already
  applied to `poetry.lock`'s `main`-only group, `pdm.lock`'s
  `default`-only group, and `uv.lock`'s runtime-only (non-optional)
  dependencies. `tests/fixtures/real-world-locks/pylock/pipenv-2026.8.0/`
  is this shape: `dependency-groups = ["dev"]`, `default-groups =
  ["default"]`, and its `dev`-only packages (`alabaster`, `arpeggio`,
  etc.) are correctly excluded from `locked_dependencies`.

Both shapes are covered by dedicated tests in `tests/extract/test_pylock.py`
(`test_non_default_group_package_excluded`,
`test_extras_gated_package_excluded_by_default`,
`test_package_with_no_marker_included_regardless_of_default_groups`),
not just incidentally by the two real-world fixtures.

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
- **No non-group marker evaluation.** A `pylock.toml` entry's `marker`
  can also carry ordinary PEP 508 conditions (`python_version`,
  `sys_platform`, etc.) alongside or instead of a group/extras clause.
  Only the `extras`/`dependency_groups` portion is evaluated (see
  above, for group filtering); every other variable is treated as
  unknown and never evaluated against a real environment -- a
  platform-specific package's marker still lets it through regardless
  of platform, the same simplification `poetry.lock` parsing already
  makes for direct dependency constraints. Evaluating those against
  Pitloom's own running interpreter/platform would make the SBOM's
  contents depend on which machine generated it, which this repo's
  determinism requirement rules out.
- **`pylock.<name>.toml` named locks are not discovered.** PEP 751
  allows a `pylock.<name>.toml` naming convention (e.g.
  `pylock.dev.toml`) for multiple named locks in one project; only the
  bare `pylock.toml` is read. Extending discovery to named locks would
  need its own priority/selection rule and is left for a future change
  if a real project motivates it.
