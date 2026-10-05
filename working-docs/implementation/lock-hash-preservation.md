---
Created: 2026-09-12
Last-Modified: 2026-10-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Lock-file hash preservation

See also: [roadmap.md](../design/roadmap.md), [lock-file-cascade.md](lock-file-cascade.md)
(the pin-extraction cascade this feature builds on top of, unchanged by
this work).

**Status (2026-09-14):** shipped on `main` via PR
[#212](https://github.com/bact/pitloom/pull/212) (merge commit `5c649a7`).
`src/pitloom/extract/` was reorganized into subpackages (`lock/`,
`ai_model/`, `project/`, `dataset/`) as part of this work -- every path
below is current as of this doc's own Last-Modified date; if this doc is
old, re-check with
`find src/pitloom/extract -iname "*hash*"` before trusting a path.

## Problem

`verifiedUsing` (a dependency package's SPDX 3 integrity checksum) was
only ever populated via a PyPI JSON API lookup
(`pitloom.assemble.spdx3.deps_pypi._extract_release_hash`), which is
skipped entirely in `--offline` mode. An offline SBOM therefore carried
no dependency-package hash at all, even though every lock format this
repo already parses (`pylock.toml`, `uv.lock`, `poetry.lock`, `pdm.lock`,
`Pipfile.lock`) records the SHA-256 digest of the exact resolved artifact
right there in the file -- unread by any of the five pin extractors
before this change.

## Scope

SHA-256 only. No lock format and no PyPI JSON API response carries
SHA-512 (a BSI TR-03183-2 requirement) -- getting one would mean
downloading the actual artifact and hashing it, a materially different
feature (real network I/O even in offline mode, streaming-hash handling)
tracked separately in `roadmap.md`. SPDX 3's `Element.verifiedUsing` has
0..* cardinality, so that future work can simply append an additional
`Hash` to the list this feature already populates -- no restructuring
needed here.

## Design decisions

- **Lock-file hash always wins over a PyPI-looked-up hash**, even
  online. The lock file names the exact artifact that was actually
  resolved; a PyPI lookup may resolve to a different release build.
  PyPI's hash lookup is the fallback only when no lock hash exists for
  that canonical package name.
- **Tie-break for multiple hashes on one package**: prefer a wheel
  artifact over any other (sdist), then sort by filename, then sort by
  digest -- shared by every format and the PyPI path via
  `pitloom.extract.lock._hash_selection.select_sha256_hash`. A source with no
  filename at all (`Pipfile.lock`'s bare `hashes` list) falls back to
  sorting the raw digest strings; the artifact this picks is genuinely
  arbitrary by construction for that one format, not wheel-preferring.
  **Important subtlety, fixed after an initial miss:** a URL-only artifact
  (`uv.lock`, `pylock.toml`) must be reduced to its clean basename
  (`pitloom.extract._extract_utils.filename_from_url`, via `urlparse().path`
  + `PureWindowsPath(...).name`) *before* the tie-break sees it -- sorting
  on the raw URL instead sorts by PyPI's content-addressable hash-directory
  prefix (`/32/34/...`), not the artifact filename, making the selected
  hash depend on an ordering this repo has no contract with. A pathless
  URL (`https://example.com`) correctly resolves to `None`, not the
  domain name.

## Data model

`ProjectMetadata.locked_dependency_hashes: dict[str, str]`
(`src/pitloom/core/project.py`) -- PEP 503-canonicalized package name to
bare hex SHA-256 digest. Additive: `locked_dependencies: list[str]` and
every consumer of it are unchanged.

## Per-format extraction

Each format gets a sibling `<format>_hash.py` module in `src/pitloom/extract/lock/`
(kept out of the already-large `<format>.py` pin-extractor modules for this repo's
file-size discipline): `pylock_hash.py`, `uv_hash.py`, `poetry_hash.py`,
`pdm_hash.py`, `pipfile_hash.py`.

Every one of them takes the pin extractor's own **already-resolved**
winning `locked_dependencies` list as input, re-parses each
`name==version` (or `name<op>version`) string via the shared
`pitloom.extract.lock._common.canonical_name_and_pinned_version`, and
looks that `(canonical_name, version)` pair back up in a fresh index of
the raw lock data. This deliberately never re-derives which packages
qualify (group membership, marker evaluation, non-registry-source
exclusion, conflicting-version exclusion) -- that logic stays exactly
once, in each format's existing pin extractor. Hash extraction can
therefore never disagree with pin extraction about what's in scope.

Per-format hash location, confirmed against this repo's own
`tests/fixtures/real-world-locks/` fixtures (not assumed from spec
reading -- see the "verify docs against actual code" rule in the root
`CLAUDE.md`):

- **`pylock.toml`** (PEP 751): `pkg["sdist"]["hashes"]["sha256"]` and
  each `pkg["wheels"][i]["hashes"]["sha256"]` -- each artifact's
  `hashes` is independently a multi-algorithm table, so an artifact with
  only e.g. `blake2b` simply contributes no candidate, not an error; a
  sibling artifact on the same package may still have `sha256`.
- **`uv.lock`**: `pkg["sdist"]["hash"]` / `pkg["wheels"][i]["hash"]`, a
  single `"sha256:<hex>"`-prefixed string per artifact.
- **`poetry.lock`**: **not uniform across lock versions.** Lock-version
  2.0 and later write a per-package `files` array directly on the
  `[[package]]` entry, but a 1.x lock instead lists hashes in one
  *separate*, top-level `[metadata.files]` table keyed by literal package
  name.
  Confirmed by diffing two real fixtures
  (`pastel-0.2.1/poetry.lock`, lock-version 1.1, uses `[metadata.files]`;
  `pendulum-3.2.0/poetry.lock`, lock-version 2.1, uses per-package
  `files`) -- both shapes are checked, per-package first.
- **`pdm.lock`**: per-package `files = [{file, hash}, ...]`, same shape
  as modern `poetry.lock`.
- **`Pipfile.lock`**: per-package `hashes: ["sha256:<hex>", ...]` -- no
  filenames at all, hence the tie-break's arbitrary fallback above.

## Cascade integration

`apply_locked_dependencies()` (`src/pitloom/extract/lock/cascade.py`) calls the
winning source's hash extractor immediately after computing its pin
list, storing the result on `metadata.locked_dependency_hashes`.

`poetry.lock` has a **second** write path that bypasses this cascade
entirely: `_try_read_poetry()` (`src/pitloom/extract/project/pyproject.py`) applies
`poetry.lock`-resolved dependencies directly during `pyproject.toml`
reading, before the cascade ever runs, and the cascade's own priority
logic (`sources_to_try = _LOCK_SOURCES[:previous_rank]`) means the
cascade loop body never executes for a project where poetry already
won. `_try_read_poetry()` therefore calls
`extract_poetry_lock_hashes()` itself, right next to its own call to
`extract_poetry_lock_dependencies()`.

## Assembly integration

`deps.py`:

- `_enrich_from_pypi()`'s hash-fill block is now guarded by
  `if "hash" not in already_filled:`, matching its `originator`/`license`
  sibling blocks -- without this guard a PyPI-reachable online run would
  silently overwrite a lock-derived hash, the opposite of the priority
  decision above.
- `_finish_dependency_enrichment()` takes a new `locked_hashes` parameter
  and fills `verifiedUsing` from it (looked up by
  `packaging.utils.canonicalize_name(dep_name)`) *before* the
  `if not offline:` PyPI branch runs, so it applies in both online and
  offline mode.
- **Version-conflict guard**: for the *direct*-dependency call, a lock
  hash is only trusted when the resolved `dep_version` PEP 440-equals
  the `locked_versions` entry for that canonical name (`locked_versions`
  is also new, threaded down alongside `locked_hashes`) -- otherwise a
  declared exact pin that overrides a conflicting locked version (see
  lock-file-cascade.md's "explicit pin beats lock" rule) would apply a
  hash describing a *different* artifact than the one the package claims
  to be. The lock-resolved-transitive-only call passes no
  `locked_versions` and trusts its hash unconditionally, since its own
  dependency strings already carry the lock's version verbatim by
  construction.
- **Efficiency**: `_enrich_from_pypi()` returns early (`return set()`,
  no network call) when `{"originator", "license", "hash"}` are already
  all filled by local-environment introspection plus the lock hash --
  the common case for a project with both an installed environment and
  a lock file present.
- `add_dependencies()` threads `locked_hashes` down; `document.py` passes
  `metadata.locked_dependency_hashes` at both of its `add_dependencies()`
  call sites (direct dependencies, and lock-resolved transitive-only
  dependencies).
