---
Created: 2026-09-04
Last-Modified: 2026-09-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Lock/pin format priority cascade -- implementation notes

See also: [poetry-support.md](poetry-support.md)'s "`poetry.lock`
transitive dependencies" section and [pep751-pylock-support.md](pep751-pylock-support.md)
for the two formats this cascade was generalized from;
[lock-files.md](../design/lock-files.md) for the broader multi-format
roadmap; [sbom-lifecycle-stages.md](sbom-lifecycle-stages.md) for the
source/build/deployed staging model that makes every source here
source-stage-only.

## Motivation

`poetry.lock` and `pylock.toml` (PEP 751) each shipped with their own
bespoke "extract, check if a result is already set, override with a
`WARNING:`" wiring (`_try_read_poetry()` for the former,
`_apply_pylock_dependencies()`, since deleted, for the latter). That
pattern doesn't scale to `uv.lock`, `pdm.lock`, `Pipfile.lock`, and
pinned `requirements.txt` landing on top -- five near-identical
bespoke functions is exactly the "pattern hand-copied across 3+ call
sites drifts" problem this repo's own conventions warn about. This
module (`src/pitloom/extract/_locked_dependencies.py`) replaces every
new format's would-be bespoke function with one shared, ordered cascade.

## The cascade

```python
_LockExtractor = Callable[[Path], list[str]]

_LOCK_SOURCES: list[tuple[str, _LockExtractor, str]] = [
    ("pylock.toml", extract_pylock_dependencies, "resolved_lockfile"),
    # uv.lock, pdm.lock, Pipfile.lock, requirements.txt land here as
    # their own extractors ship -- see roadmap.md.
]


def apply_locked_dependencies(metadata: ProjectMetadata, project_dir: Path) -> None:
    ...
```

Each entry pairs a source filename, an extractor (`project_dir -> list[str]`
of exact-pin PEP 508 strings, empty when absent/unusable -- the same
signature convention `_poetry_lock.py`/`_pylock.py` already established),
and a provenance `Method` tag. `apply_locked_dependencies()` tries each
entry in priority order (highest first) and applies the first non-empty
result, in place, onto `metadata.locked_dependencies` and
`metadata.provenance["locked_dependencies"]`.

**`poetry.lock` is not in this table.** It stays exactly where it
shipped, gated inside `_try_read_poetry()`'s `include_locked_dependencies`
build-stage flag, since `poetry.lock` only ever makes sense alongside a
`[tool.poetry]` table -- which requires `pyproject.toml` to exist
regardless, so it needs no `read_project()`-level generalization. The
cascade runs *after* `_try_read_poetry()` in `read_pyproject()`
(indirectly, via `read_project()` -- see below), so a higher-priority
cascade entry can still override an already-set `poetry.lock` result.

## Priority order

Highest to lowest, per `working-docs/design/roadmap.md`'s "Remaining
lock formats" item and `lock-files.md`'s phase reasoning
(build-backend-agnostic and universal beats tool-specific; a real
resolver lock beats a merely-pinned file):

1. `pylock.toml` (PEP 751) -- the interoperability standard.
2. `uv.lock`
3. `poetry.lock` (via `_try_read_poetry()`, not this cascade -- see above)
4. `pdm.lock`
5. `Pipfile.lock`
6. pinned `requirements.txt` -- weakest signal; only usable when every
   line is an exact `==` pin (see that format's own implementation
   notes once it lands).

## Where the cascade is called from -- `read_project()`, not `read_pyproject()`

This is the one deliberate divergence from `pylock.toml`'s original
wiring (which called `_apply_pylock_dependencies()` from inside
`read_pyproject()`'s three exit paths). `pitloom.extract.project.read_project()`
is the single dispatcher deciding between three metadata sources for a
directory: `pyproject.toml` (succeeds), a `pyproject.toml`-with-no-usable-
`[project]`-table fallback to `read_setuptools()`, or `setup.cfg`/`setup.py`
alone with no `pyproject.toml` at all. `Pipfile.lock` and pinned
`requirements.txt` predate PEP 621 almost entirely -- every real-world
project checked while sourcing test fixtures for this cascade
(`requests-html`, `responder` pre-`v3.0.0`) is `setup.py`-only, no
`pyproject.toml` -- so a cascade wired only inside `read_pyproject()`
would never run for the realistic case those two formats actually show
up in.

`apply_locked_dependencies()` is called once, right before each of
`read_project()`'s three directory-based `return` statements (the
sdist-archive branch is skipped -- there's no sibling directory to
check for a lock file against a single archive file), so it runs
uniformly regardless of which metadata source won.

## Provenance recording

`metadata.provenance["locked_dependencies"]` is a single string,
`"Source: <file> | Method: <method>"`, consumed by `document.py`'s
`add_dependencies(dep_provenance=...)` to annotate every locked-transitive
`dependsOn` relationship. Two things beyond the pre-existing pattern:

- **The cascade owns the string format**, built once from `_LOCK_SOURCES`'
  `(source_name, method)` pair, rather than each extractor's call site
  formatting its own copy -- the same "no hand-copied pattern" reasoning
  as the cascade loop itself.
- **An override is recorded in the string, not only logged.** When a
  higher-priority source supersedes an already-set one (from
  `poetry.lock`, or a previous cascade winner -- though only one cascade
  entry ever wins per call), the resulting string gets a trailing
  `| Note: supersedes <name>`, e.g. `"Source: pylock.toml | Method:
  resolved_lockfile | Note: supersedes poetry.lock"`. This means a
  reader of the *generated SBOM* -- not only Pitloom's own stderr at
  generation time -- can see that more than one lock source existed and
  which one Pitloom trusted, per this repo's "no silent deviations"
  principle applied to the artifact itself.

## Document UUID seeding

`compute_doc_uuid()` (`src/pitloom/core/models.py`) folds
`locked_dependencies` (the resolved dependency *content*) into its seed,
but originally not *which source produced it*. With six lock/pin
formats now cascading instead of two, two different formats resolving
to an identical dependency set for a small project became a real,
checkable collision risk: two runs -- one with only `poetry.lock`
present, one with only `pylock.toml` present -- that happen to resolve
to the same exact pins would produce the *same* document UUID despite
the generated document's `provenance["locked_dependencies"]` field (and
any override note) differing, a real content difference the UUID is
meant to guard against. Fixed by adding a
`locked_dependencies_provenance: str | None` parameter, folded into the
seed alongside `locked_dependencies` itself whenever both are non-empty/
given. Omitted (every pre-existing call site) leaves the seed
unaffected -- purely additive.

## Adding a new format to the cascade

1. Write `extract_<format>_dependencies(project_dir: Path) -> list[str]`
   in its own `src/pitloom/extract/_<format>.py`, following
   `_pylock.py`'s shape: exact-pin PEP 508 strings, empty list when
   absent/unusable, `WARNING:` (never a silent drop) for anything
   malformed or non-registry-sourced.
2. Add one entry to `_LOCK_SOURCES` in `_locked_dependencies.py`, at the
   priority position from the table above.
3. No changes needed anywhere else -- `read_project()`'s wiring,
   provenance formatting, the override note, and UUID seeding are all
   already generic across every entry in the table.
