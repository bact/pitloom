---
Created: 2026-09-04
Last-Modified: 2026-09-04
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
_LockExtractor = Callable[[Path, str | None], list[str]]

_LOCK_SOURCES: list[tuple[str, _LockExtractor | None, str | None]] = [
    ("pylock.toml", extract_pylock_dependencies, "resolved_lockfile"),
    ("uv.lock", extract_uv_lock_dependencies, "resolved_lockfile"),
    ("poetry.lock", None, None),
    ("pdm.lock", extract_pdm_lock_dependencies, "resolved_lockfile"),
    # Pipfile.lock, requirements.txt land here as their own extractors
    # ship -- see roadmap.md.
]


def apply_locked_dependencies(metadata: ProjectMetadata, project_dir: Path) -> None:
    ...
```

Each entry pairs a source name, an extractor matching the uniform
`_LockExtractor` shape (`(project_dir, expected_name) -> list[str]` of
exact-pin PEP 508 strings, empty when absent/unusable), and a
provenance `Method` tag. Only `uv.lock`'s own extractor uses
*expected_name* (to disambiguate a shared workspace lock's multiple
local package entries without re-reading `pyproject.toml` a second
time); `pylock.toml`'s and `pdm.lock`'s extractors keep their simpler,
single-`project_dir` signature and are wrapped with
`_ignore_expected_name()` when registered in `_LOCK_SOURCES` below,
rather than widening every format's own signature for a need only one
of them has,
and a provenance `Method` tag. `apply_locked_dependencies()` tries each
extractor-bearing entry in priority order (highest first) and applies
the first non-empty result, in place, onto `metadata.locked_dependencies`
and `metadata.provenance["locked_dependencies"]`.

**`poetry.lock` has no extractor here (`None`, `None`), but it *is* in
the table.** It's still applied earlier, gated inside
`_try_read_poetry()`'s `include_locked_dependencies` build-stage flag,
since `poetry.lock` only ever makes sense alongside a `[tool.poetry]`
table -- which requires `pyproject.toml` to exist regardless, so it
needs no `read_project()`-level generalization of its own. What changed
once a format *below* `poetry.lock` in the priority order (`pdm.lock`)
joined the cascade: `poetry.lock` needed a fixed rank in the *same*
list, not just an informal "runs before this cascade" note -- see the
next section for why.

## Priority order

Same order [docs/dependency-sources.md](../../docs/dependency-sources.md)
documents for users, restated here as the exact rank list
`_LOCK_SOURCES` must match. Highest to lowest, per
`working-docs/design/roadmap.md`'s "Remaining lock formats" item and
`lock-files.md`'s phase reasoning (build-backend-agnostic and universal
beats tool-specific; a real resolver lock beats a merely-pinned file):

1. `pylock.toml` (PEP 751) -- the interoperability standard.
2. `uv.lock`
3. `poetry.lock` (via `_try_read_poetry()`, not this cascade -- see above)
4. `pdm.lock`
5. `Pipfile.lock`
6. pinned `requirements.txt` -- weakest signal; only usable when every
   line is an exact `==` pin (see that format's own implementation
   notes once it lands).

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

The fix: `poetry.lock` is a real entry in `_LOCK_SOURCES` (extractor
`None`, since it's applied elsewhere), so its rank is looked up the same
way as everything else instead of being assumed. `apply_locked_dependencies()`
first resolves the rank of whatever source (if any) already populated
`metadata.provenance["locked_dependencies"]` -- today that can only be
`poetry.lock`, via `_try_read_poetry()`, which runs before this cascade
-- then, walking `_LOCK_SOURCES` in order, stops (`break`) the moment it
reaches an entry ranked *below* that already-set source, since nothing
from there on could legitimately win. `tests/extract/test_pdm_lock.py::test_read_project_pdm_lock_never_overrides_poetry_lock`
is the regression test for this; `test_read_project_uv_lock_still_overrides_pdm_lock`
confirms the higher-ranked entries' behaviour didn't change.

**Any future format ranked below `poetry.lock` (`Pipfile.lock`, pinned
`requirements.txt`) needs no extra code for this** -- the same generic
rank check covers them once they're added to `_LOCK_SOURCES` at their
documented position. Only a format that would need to be inserted
*around* an existing entry (unlikely, given the order above is already
settled) would need to re-verify this logic.

## Per-format extraction notes

Most formats' extractors are a simple flat scan (`_pylock.py`,
`_poetry_lock.py`): every locked entry is either included or excluded,
independently of the others. `_uv_lock.py` is the one exception so far,
because `uv.lock` resolves *every* Python-version/platform combination
its `resolution-markers` cover in one file -- its top-level `[[package]]`
table is a flat union across all of them, so the same package name can
legitimately appear more than once, at different versions, restricted
to different marker conditions (e.g. one entry for
`python_full_version < '3.10'`, another for `>= '3.10'`). Since this
cascade (like every sibling extractor) doesn't evaluate markers against
a real environment, `_uv_lock.py`:

1. Identifies the project's own package entry (via a `source.editable`/
   `source.virtual` marker -- how uv distinguishes "this is the local
   project" from a PyPI download) instead of scanning every
   `[[package]]` entry directly.
2. Reads only that entry's own `dependencies` list (main/runtime --
   `optional-dependencies`/`dev-dependencies` are extras and dev
   groups, excluded the same way `poetry.lock`'s non-`main` groups are).
3. Resolves each referenced name against the flat table only when
   exactly one candidate exists for that name; an ambiguous
   (multiple-version) or marker-conditional (inline `version` on the
   dependency reference itself) name is skipped with a `WARNING:`, not
   guessed. See `tests/fixtures/real-world-locks/README.md`'s `flask`
   entry for a real fixture exercising this (its `click` dependency is
   deliberately absent from `locked_dependencies`).

A future format that shares this same "multiple resolutions in one
file" shape should follow this same pattern rather than inventing a new
one.

`_pdm_lock.py` hits a *milder* version of the same "same name, more than
one entry" shape, but for a different, harmless reason: PDM records a
separate `[[package]]` entry per requested extra variant of a package
(e.g. a bare `httpx` entry alongside one with `extras = ["socks"]`),
always agreeing on `version` -- unlike `uv.lock`'s genuinely conflicting
duplicates. It reuses `index_packages_by_name()` (see the next section)
to group entries by name, then only treats a name as ambiguous (skip,
`WARNING:`) when its entries actually *disagree* on `version`; entries
that agree are collapsed to one `name==version`, not two.

## Sharing code across formats (`_lock_common.py`)

Two steps turned out to be identical across every extractor, not just
similar in spirit:

- **Loading the lock file.** "Try to read/parse it; absent -> empty
  result, silently; malformed -> empty result, with a `WARNING:`" was
  copy-pasted verbatim into `_poetry_lock.py`, `_pylock.py`, and
  `_uv_lock.py` before being factored into
  `pitloom.extract._lock_common.load_lock_toml()`, which all four
  extractors (including `_pdm_lock.py`) now call instead.
- **Grouping a flat package list by name.** First written for
  `_uv_lock.py`'s ambiguity check, then reused as-is by `_pdm_lock.py`'s
  own (milder) version of the same check -- see above. Lives as
  `pitloom.extract._lock_common.index_packages_by_name()`.

What's deliberately **not** shared: the per-entry validation shape
(what counts as "malformed", which keys mark a non-registry source,
what the `groups`/`dependencies` filtering looks like). Each format's
own field names and conventions differ enough (`poetry.lock`'s
`source.type` vs `pylock.toml`'s top-level `vcs`/`directory`/`archive`
keys vs `uv.lock`'s nested `source.{key}` vs `pdm.lock`'s flat
`git`/`path` keys) that forcing one shared function across all of them
would hurt clarity more than it would save -- consistent *wording*
across their `WARNING:` messages matters more here than a single shared
implementation, per this repo's message-style convention.

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

1. Write `extract_<format>_dependencies(project_dir: Path) -> list[str]`
   in its own `src/pitloom/extract/_<format>.py`, following
   `_pylock.py`'s shape: exact-pin PEP 508 strings, empty list when
   absent/unusable, `WARNING:` (never a silent drop) for anything
   malformed or non-registry-sourced. Use
   `_lock_common.load_lock_toml()` to load the file, and (if the format
   can resolve the same name more than once, the way `uv.lock`/`pdm.lock`
   can) `_lock_common.index_packages_by_name()` to group entries before
   deciding whether that's ambiguous.
2. Add one entry to `_LOCK_SOURCES` in `_locked_dependencies.py`, at the
   priority position from the table above -- **including if it ranks
   below `poetry.lock`** (`Pipfile.lock` and pinned `requirements.txt`
   both do). No extra code is needed for that case: the rank check in
   `apply_locked_dependencies()` already treats every entry in
   `_LOCK_SOURCES` (poetry.lock's placeholder included) uniformly.
3. No changes needed anywhere else -- `read_project()`'s wiring,
   provenance formatting, the override note, and UUID seeding are all
   already generic across every entry in the table.
