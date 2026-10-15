---
Created: 2026-09-04
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Lock/pin format priority cascade -- implementation notes

This is implementation reference for maintainers -- what the code does
and why. For the user-facing behaviour (what shows up in a generated
SBOM, which lock file wins, which commands use lock files at all), see
[docs/dependency-sources.md](../../docs/dependency-sources.md) instead;
this page assumes that one as background and doesn't restate it.

See also: [poetry-support.md](poetry-support.md)'s "`poetry.lock`
transitive dependencies" section and [pep751-pylock-support.md](pep751-pylock-support.md)
for the two formats this cascade was generalized from;
[lock-files.md](../design/lock-files.md) for the broader multi-format
roadmap; [sbom-lifecycle-stages.md](sbom-lifecycle-stages.md) for the
source/build/deployed staging model that makes every source here
source-stage-only.

Split into three files: this page (the cascade, its wiring and provenance),
[lock-file-cascade-formats.md](lock-file-cascade-formats.md) (per-format
extraction notes and the shared `_common.py` code) and
[lock-file-cascade-opt-out.md](lock-file-cascade-opt-out.md) (the
`--no-use-lockfile` opt-out).

## Motivation

`poetry.lock` and `pylock.toml` (PEP 751) each shipped with their own
bespoke "extract, check if a result is already set, override with a
`WARNING:`" wiring (`_try_read_poetry()` for the former,
`_apply_pylock_dependencies()`, since deleted, for the latter). That
pattern doesn't scale to `uv.lock`, `pdm.lock`, `Pipfile.lock`, and
pinned `requirements.txt` landing on top -- five near-identical
bespoke functions would have been exactly the "pattern hand-copied
across 3+ call sites drifts" problem this repo's own conventions warn
about. This module (`src/pitloom/extract/lock/cascade.py`)
replaces every new format's would-be bespoke function with one shared,
ordered cascade -- all six formats now registered in it.

## The cascade

```python
_LockExtractor = Callable[[Path, str | None], list[str] | None]
_LockHashExtractor = Callable[[Path, list[str]], dict[str, str] | None]

_LOCK_SOURCES: list[tuple[str, _LockExtractor, _LockHashExtractor | None, str]] = [
    (
        "pylock.toml",
        _ignore_expected_name(extract_pylock_dependencies),
        extract_pylock_hashes,
        "resolved_lockfile",
    ),
    (
        "uv.lock",
        extract_uv_lock_dependencies,
        extract_uv_lock_hashes,
        "resolved_lockfile",
    ),
    (
        "poetry.lock",
        _ignore_expected_name(extract_poetry_lock_dependencies),
        extract_poetry_lock_hashes,
        "resolved_lockfile",
    ),
    (
        "pdm.lock",
        _ignore_expected_name(extract_pdm_lock_dependencies),
        extract_pdm_lock_hashes,
        "resolved_lockfile",
    ),
    (
        "Pipfile.lock",
        _ignore_expected_name(extract_pipfile_lock_dependencies),
        extract_pipfile_hashes,
        "resolved_lockfile",
    ),
    (
        "requirements.txt",
        _ignore_expected_name(extract_pinned_requirements_dependencies),
        None,
        "pinned_requirements",
    ),
]


def apply_locked_dependencies(metadata: ProjectMetadata, project_dir: Path) -> None: ...
```

Each entry pairs a source name, an extractor matching the uniform
`_LockExtractor` shape (`(project_dir, expected_name) -> list[str] | None`
of exact-pin PEP 508 strings), and a provenance `Method` tag. Only
`uv.lock`'s own extractor uses *expected_name* (to disambiguate a shared
workspace lock's multiple local package entries without re-reading
`pyproject.toml` a second time); `pylock.toml`'s, `poetry.lock`'s, `pdm.lock`'s,
and `Pipfile.lock`'s extractors keep their simpler, single-`project_dir`
signature and are wrapped with `_ignore_expected_name()` when registered
in `_LOCK_SOURCES` above, rather than widening every format's own
signature for a need only one of them has. `apply_locked_dependencies()`
tries each extractor-bearing entry in priority order (highest first) and
applies the first result that isn't `None`, in place, onto
`metadata.locked_dependencies` and `metadata.provenance["locked_dependencies"]`.

**`None` and `[]` mean different things, and the distinction matters.**
`None` means this source doesn't apply here at all (absent, unparseable,
or otherwise unusable) -- try the next source in priority order. `[]`
means this source *does* apply, and is a real, authoritative answer: a
successfully-parsed lock that genuinely resolves to zero runtime
dependencies. The cascade treats `[]` as a win like any other -- it stops
and does *not* fall through to a lower-priority source, since that would
let a lower-priority, less-authoritative source add dependencies the
winning lock says don't exist. Every extractor in `_LOCK_SOURCES`
(and `poetry.lock`'s own `_try_read_poetry()` gate) follows this same
contract.

Every entry's `Method` tag is `"resolved_lockfile"` except
`requirements.txt`'s own `"pinned_requirements"` -- it's not a real
lock file (no resolver metadata, no hashes guaranteed), so its
provenance string reads differently on purpose, letting a reader of the
generated SBOM tell "a resolver actually produced this" from "this
merely happened to already be a fully pinned list" -- see
[docs/dependency-sources.md](../../docs/dependency-sources.md).

**`poetry.lock` is registered with an extractor in the cascade table.**
When `pyproject.toml` is a Poetry 1.x project, `_try_read_poetry()` extracts
it earlier during project parsing; when the cascade runs, the deduplication
guard recognises that `poetry.lock` was already extracted and avoids re-parsing
it. For standard PEP 621 or non-Poetry projects accompanied by a `poetry.lock`,
the cascade's registered extractor parses it directly.

## Priority order

Same order [docs/dependency-sources.md](../../docs/dependency-sources.md)
documents for users, restated here as the exact rank list
`_LOCK_SOURCES` must match. Highest to lowest, per
`working-docs/implementation/roadmap-completed.md`'s "Lock/pin formats" item and
`lock-files.md`'s phase reasoning (build-backend-agnostic and universal
beats tool-specific; a real resolver lock beats a merely-pinned file):

1. `pylock.toml` (PEP 751) -- the interoperability standard.
2. `uv.lock`
3. `poetry.lock`
4. `pdm.lock`
5. `Pipfile.lock` -- JSON, not TOML; see its own notes in
   [lock-file-cascade-formats.md](lock-file-cascade-formats.md).
6. pinned `requirements.txt` -- weakest signal, lowest rank; not a real
   lock file at all, only usable when every line is already an exact
   `==` pin. See its own notes in
   [lock-file-cascade-formats.md](lock-file-cascade-formats.md).

## Why `poetry.lock` needs a fixed rank, not just "runs first"

Caught while adding `pdm.lock` (rank 4, below `poetry.lock` at rank 3):
the original cascade loop applied the *first* extractor-bearing entry
that returned non-empty data, full stop -- correct as long as every
entry in `_LOCK_SOURCES` outranks `poetry.lock` (true for `pylock.toml`
and `uv.lock`, ranks 1-2), but silently wrong the moment an entry ranks
*below* it. Without a fix, a project with both `poetry.lock` and
`pdm.lock` present would have `pdm.lock` unconditionally clobber
`poetry.lock`'s already-applied result, even though `pdm.lock` is
supposed to lose that comparison.

The fix: `poetry.lock` is a real entry in `_LOCK_SOURCES`, so its rank is
looked up the same way as everything else instead of being assumed.
`apply_locked_dependencies()` first resolves the rank of whatever source
(if any) already populated `metadata.provenance["locked_dependencies"]`
(such as `poetry.lock` via `_try_read_poetry()` for Poetry 1.x projects),
then only tries the entries strictly above that rank
(`sources_to_try = _LOCK_SOURCES[:previous_rank]`) -- nothing at or
below the already-set source's rank could legitimately win, so it's
never even called. `tests/extract/lock/test_pdm.py::test_read_project_pdm_lock_never_overrides_poetry_lock`
is the regression test for this; `test_read_project_uv_lock_still_overrides_pdm_lock`
confirms the higher-ranked entries' behaviour didn't change.

**Any format ranked below `poetry.lock` needs no extra code for this**
-- the same generic rank check covers it once it's added to
`_LOCK_SOURCES` at its documented position; `pdm.lock`, `Pipfile.lock`,
and pinned `requirements.txt` (rank 6, lowest) all confirmed this when
they landed. Only a format that would need to be inserted *around* an
existing entry (unlikely, given the order above is already settled)
would need to re-verify this logic.

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
up in. Confirmed once both landed:
`tests/extract/lock/test_pipfile.py::test_read_project_populates_locked_dependencies_from_setup_py_only`
and `tests/extract/lock/test_requirements.py::test_read_project_populates_locked_dependencies_from_setup_py_only`
each exercise this path against a `setup.py`-only project directory.

`apply_locked_dependencies()` is called once, at the single point where
`read_project()`'s three directory-based branches (`pyproject.toml`,
the `setup.cfg`/`setup.py` fallback, and `setup.cfg`/`setup.py` alone)
have already converged onto one shared `metadata`/`pitloom_config`
before its one `return` statement -- the sdist-archive branch returns
separately, earlier, and is skipped entirely (there's no sibling
directory to check for a lock file against a single archive file). One
call site covers every directory-based metadata source uniformly,
rather than one call per branch.

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
  resolved_lockfile | Note: supersedes poetry.lock"` -- per this repo's
  "no silent deviations" principle applied to the artifact itself, not
  only to the run that produced it. See
  [docs/dependency-sources.md](../../docs/dependency-sources.md#how-to-tell-which-source-was-used)
  for how a user reads this in a generated SBOM.

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

1. Write `extract_<format>_dependencies(project_dir: Path) -> list[str] | None`
   in its own `src/pitloom/extract/lock/<format>.py`, following
   `pylock.py`'s shape: exact-pin PEP 508 strings, `None` when
   absent/unusable (as opposed to a valid-but-empty `[]` -- see the
   "`None` and `[]` mean different things" note above), `WARNING:`
   (never a silent drop) for anything
   malformed or non-registry-sourced. Use `_common.load_lock_toml()`
   to load the file (or `_common.load_lock_json()` for a JSON-format
   lock file -- `pipfile.py` is the precedent), and (if the format
   can resolve the same name more than once, the way `uv.lock`/`pdm.lock`/
   `requirements.txt` can) `_common.index_packages_by_name()` (full
   `[[package]]`-style entries) or `_common.group_versions_by_canonical_name()`
   (bare `(name, version)` pairs) to group entries before deciding
   whether that's ambiguous. Only add a second parameter to the
   extractor itself if it genuinely needs `expected_name` for
   disambiguation the way `uv.lock` does (see the cascade code block
   above) -- otherwise keep the simpler single-`project_dir` signature
   and let `_ignore_expected_name()` wrap it when registered.
2. Add one entry to `_LOCK_SOURCES` in `cascade.py`, at the
   priority position from the table above -- **including if it ranks
   below `poetry.lock`** (pinned `requirements.txt`, rank 6, does).
   No extra code is needed for that case: `apply_locked_dependencies()`
   slices `_LOCK_SOURCES` down to whatever rank is already resolved
   (`sources_to_try = _LOCK_SOURCES[:previous_rank]`), so every entry --
   `poetry.lock` included -- is treated uniformly regardless of where
   it sits in the table.
3. No changes needed anywhere else -- `read_project()`'s wiring,
   provenance formatting, the override note, and UUID seeding are all
   already generic across every entry in the table.
