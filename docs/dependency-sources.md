---
Created: 2026-09-04
Last-Modified: 2026-09-12
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Dependency sources and precedence

> **Note:** Background reading -- useful for understanding what shows up
> in a generated Source SBOM's dependency list and why, not needed to
> just generate one.

## Two kinds of dependency information

Every Source SBOM (`loom project`/`loom generate`) always includes your
project's **declared dependencies** -- the version ranges listed in
`pyproject.toml`'s `[project.dependencies]` (or `[tool.poetry.dependencies]`
for a Poetry project), e.g. `requests>=2.0`. These are read directly and
always present, with or without a lock file.

If a **lock file** is also present next to `pyproject.toml`, Pitloom
additionally reads its exact resolved versions and adds any dependency
they introduce that your declared list doesn't already name -- your
project's *transitive* dependencies, pinned exactly (e.g. `idna==3.7`).

**When a direct dependency is declared with a version range and a lock
file is present, Pitloom uses the lock file's exact resolved version
for the emitted SBOM package.** For example, if `pyproject.toml`
declares `requests>=2.0` and your lock file resolved it to `2.31.0`, the
package's `software_packageVersion` and PyPI PURL become `2.31.0` (with
enrichment fetching metadata for that exact release), while the
original declared range is preserved in the element's
`declared_constraint` provenance annotation. Transitive dependencies
revealed only by the lock file (e.g. `idna==3.7`) are added as new,
additive entries.

## Supported lock formats, and what counts as "resolved"

| Priority | Format | File | What's included |
| :---: | :--- | :--- | :--- |
| 1 (highest) | PEP 751 | `pylock.toml` | Every resolved package the file records for its declared `default-groups` (a package needed only for a non-default dependency-group/extra, per its own `marker` field, is excluded). |
| 2 | uv | `uv.lock` | Your project's own main/runtime dependencies, walked transitively (dependencies of dependencies, and so on), including any extra a real dependency requests on another package (e.g. `uvicorn[standard]` pulls in `uvicorn`'s own `standard` extra). Your project's *own* `optional-dependencies`/`dev-dependencies` groups (the ones a user would have to opt into, e.g. `pip install yourpkg[dev]`) are not included. A dependency pinned to more than one version for different Python versions is skipped, not guessed at, and nothing depending only on it is walked into either -- see below. |
| 3 | Poetry | `poetry.lock` | Packages in the `main` dependency group only (not `[tool.poetry.group.*]` dev/extra groups). |
| 4 | PDM | `pdm.lock` | Packages in the `default` dependency group only. |
| 5 | Pipenv | `Pipfile.lock` | Packages in the `default` section only (not `develop`). A package whose resolved `version` isn't a single exact `==`/`===` pin is skipped, not guessed at. |
| 6 (lowest) | -- | pinned `requirements.txt` | Not a real lock file -- only used when *every* line in the file is already a single exact `==`/`===` pin. If even one line is unpinned, ranged, a pip option (`-e`, `-r`, `--hash`, ...), a URL-based requirement (even one that looks like it points at a tagged release), or one package name is pinned to two conflicting versions, the **whole file** is skipped, not just that line -- see below. |

`requirements.txt`'s entry is tagged `Method: pinned_requirements` in
its provenance annotation (see "How to tell which source was used"
below), not `Method: resolved_lockfile` like every format above it --
it's the one source here that isn't a real lock file, just a list of
lines that happen to already be fully pinned.

**A URL-based `requirements.txt` line is never treated as a version
pin, even when the URL looks like it points at a tagged release** (e.g.
`name @ https://github.com/org/repo/archive/refs/tags/v2.31.0.zip`). A
git tag or release filename is an arbitrary string with no guaranteed
relationship to the package's real, normalised version -- Pitloom
doesn't fetch the URL to check, so a line like that disqualifies the
whole file the same as an unpinned or ranged one would.

**Only the single highest-priority *usable* lock file present is used.**
If more than one lock file exists in the same project directory
(uncommon, but possible after a build-tool migration), Pitloom picks the
highest-ranked one in the table above that it can actually read and
parse, and ignores every other one entirely -- it never merges two lock
files' resolutions together. "Usable" matters: a higher-priority lock
file that's absent, unparseable, or otherwise not a genuine file of its
claimed format doesn't win by merely being *present* -- Pitloom moves on
to the next-highest-priority source instead, the same as if that file
weren't there at all. This holds even when the winning lock resolves to
*zero* dependencies: a real, successfully-parsed lock file that
legitimately has nothing to add is still a definitive answer, and a
lower-priority lock present alongside it is still ignored, not used to
fill in what looks like a gap.

**A lock entry that can't be resolved to one exact version is left out,
not guessed.** `uv.lock` in particular can record the same package
pinned to genuinely different versions for different Python versions in
one file; Pitloom doesn't evaluate environment markers to pick one, so
such a dependency is simply omitted from the additional (transitive)
list rather than added with a possibly-wrong version. Check stderr for a
`WARNING:` naming the skipped package if a dependency you expected is
missing.

## Version comparison: PEP 440, not SemVer

**Pitloom compares dependency versions using [PEP 440][pep-440] equality,
not SemVer.** "Same version" means the two version strings normalise to
the identical release under PEP 440 -- trailing-zero components are
padded and compared, so `1.0`, `1.0.0`, and `1.0.0.0` are all the same
version. It does **not** mean "the latest release compatible with 1.0"
or any other range/caret-style resolution: `1.0` and `1.0.1` are
different versions under this comparison, exactly as they'd differ under
strict string equality, even though a SemVer-style `^1.0.0` range would
consider `1.0.1` compatible.

This comparison is what decides whether two version strings for the same
package are treated as agreeing or genuinely conflicting. It shows up in
two places:

- **A lock file's own duplicate entries.** If one lock file records the
  same package name more than once (e.g. a platform-specific variant),
  entries that normalise to the same PEP 440 release are silently
  collapsed into one; entries that don't get a `WARNING:` naming both
  versions, and that package is left out of the transitive list
  entirely rather than guessed at.
- **A declared range vs. the lock file's resolved version.** When a
  direct dependency is unpinned or declared as a range, the lock file's
  resolved version is used (see above); when it's already pinned
  exactly (e.g. `requests==2.31.0`) and the lock file separately
  resolved it to a version that doesn't normalise the same way (e.g.
  `2.31.1`), Pitloom logs a `WARNING:` but keeps the *declared* pin --
  the lock's differing value never silently overrides an exact pin the
  project itself declared. Either direction, a genuine disagreement also
  adds a `conflict` Annotation (`field: "dependency_version"`) to the
  generated SBOM, not just a stderr `WARNING:` -- see [Metadata
  provenance](metadata-provenance.md#how-a-dependency-version-source-is-chosen).

[pep-440]: https://peps.python.org/pep-0440/

## Which commands use lock files at all

Lock-file resolution only ever applies to a **Source SBOM**
(`loom project`, `loom generate`, and the equivalent
[Python API](python-api.md) call) -- describing your project as
declared in source, before a build happens.

It's never consulted by:

- `loom wheel`, `loom embed-wheel`, `loom verify-wheel`/`validate-wheel`
  -- a built wheel's own installed metadata is the ground truth for an
  **Analyzed SBOM**; a lock file (which describes what a *future* build
  might resolve to) is beside the point once a real wheel exists.
- `loom env` -- describing what's actually installed in an environment
  is more authoritative than a lock file that may be stale relative to
  it.
- The [Hatchling build hook](hatchling-build-hook.md) -- SBOMs it embeds
  during `hatch build`/`pip install .` describe the build artifact
  itself, the same "real build, not a lock's prediction" reasoning as
  `loom wheel` above.

So it's normal for `loom project`'s SBOM to list more transitive
dependencies than an SBOM embedded by the Hatchling build hook for the
same project -- they're describing different things (a hypothetical
resolution vs. what a real build actually installed), not a bug in
either.

## How to tell which source was used

Every transitive SBOM package introduced by a lock file carries a
provenance annotation naming the file and method Pitloom used, e.g.
`Source: pylock.toml | Method: resolved_lockfile`. Direct dependencies
retain their declared source (e.g. `Source: pyproject.toml`), with
`Version resolved: Project lock file` noting when a declared range was
resolved to an exact version by the lock file. The cascade stops at
the first usable source it tries, so it doesn't itself check whether a
still-lower-priority lock file is *also* present on disk -- the one
case it does detect and annotate is `poetry.lock`, since that one is
resolved earlier, before the cascade runs, and the cascade can see its
already-set result: if a higher-priority format then wins over it, the
annotation adds a note, e.g. `Source: pylock.toml | Method:
resolved_lockfile | Note: supersedes poetry.lock`. Two lock files that
are both tried by the cascade itself (e.g. `pdm.lock` and `Pipfile.lock`
both present) never produce this note -- only the single winning
source's own annotation appears. See [Metadata
provenance](metadata-provenance.md) for how to read these annotations
in the generated SBOM.

## Configuration and flags

There is currently no setting to change the priority order above or
choose a specific lock file -- which one wins is automatic, based purely
on which lock file (if any) is present next to `pyproject.toml`.

To turn lock-file reading off entirely -- falling back to direct
dependencies plus environment introspection only -- pass
`--no-use-lockfile` on `loom project`, `loom generate`, or `loom enrich`
(the last only together with `--project-dir` -- no project metadata is
read at all on a bare `loom enrich <model>`, so the flag has no effect
without it), or set `[tool.pitloom] use-lockfile = false` in
`pyproject.toml`. On by default (an explicit CLI flag always wins over
the config value); see [Configuration](configuration.md).

`loom enrich --project-dir DIR` computes the fragment's target document
identity from that same setting: pass `--use-lockfile`/`--no-use-lockfile`
explicitly to match whatever produced the base SBOM, or omit it to
auto-match *DIR*'s own `[tool.pitloom] use-lockfile` config. A mismatch here
silently produces a fragment referencing the wrong document identity.

`--use-lockfile`/`--no-use-lockfile` has no effect for an sdist archive
target (`loom project`/`loom generate` on a `.tar.gz`/`.zip`): no lock/pin
cascade support exists for archives yet, so a real lock file in the
archive's *own* build environment was never read into it in the first
place. An explicit flag passed for an archive target logs a `WARNING:`
and is otherwise ignored.

`--offline` (also settable via `[tool.pitloom] offline` --
see [Configuration](configuration.md)) is unrelated to lock-file
reading: it only controls whether Pitloom's own PyPI JSON API lookups
(used to fill in a dependency package's supplier/license/copyright gaps)
are attempted. A lock file is always read from disk regardless of this
setting -- there's no network involved in reading it.

## See also

- [Command line](cli.md) and [Python API](python-api.md) for how to run
  a Source SBOM generation that reads lock files this way.
- [Metadata provenance](metadata-provenance.md) for the general
  provenance-annotation mechanism this page's "how to tell which source
  was used" section relies on.
- [Configuration](configuration.md) for `--offline` and every other
  `[tool.pitloom]` setting.
