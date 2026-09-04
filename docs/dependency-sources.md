---
Created: 2026-09-04
Last-Modified: 2026-09-05
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

**A direct dependency already in your declared list keeps its declared
range in the SBOM, even when a lock file has resolved it to an exact
version.** For example, if `pyproject.toml` declares `requests>=2.0` and
your lock file resolved it to `2.31.0`, the SBOM still shows
`requests>=2.0` for that entry -- only dependencies *not already
declared* (the ones the lock file alone reveals) get added, as new,
exactly-pinned entries.

## Supported lock formats, and what counts as "resolved"

| Priority | Format | File | What's included |
| :---: | :--- | :--- | :--- |
| 1 (highest) | PEP 751 | `pylock.toml` | Every resolved package the file records. |
| 2 | uv | `uv.lock` | Your project's own main/runtime dependencies (not `optional-dependencies` extras or `dev-dependencies` groups). A dependency pinned to more than one version for different Python versions is skipped, not guessed at -- see below. |
| 3 | Poetry | `poetry.lock` | Packages in the `main` dependency group only (not `[tool.poetry.group.*]` dev/extra groups). |
| 4 | PDM | `pdm.lock` | Packages in the `default` dependency group only. |
| 5 | Pipenv | `Pipfile.lock` | Packages in the `default` section only (not `develop`). A package whose resolved `version` isn't a single exact `==` pin is skipped, not guessed at. |

Support for a fully pinned `requirements.txt` is planned, ranked below
the formats above.

**Only the single highest-priority lock file present is used.** If more
than one lock file exists in the same project directory (uncommon, but
possible after a build-tool migration), Pitloom picks the one highest in
the table above and ignores the rest entirely -- it never merges two
lock files' resolutions together.

**A lock entry that can't be resolved to one exact version is left out,
not guessed.** `uv.lock` in particular can record the same package
pinned to genuinely different versions for different Python versions in
one file; Pitloom doesn't evaluate environment markers to pick one, so
such a dependency is simply omitted from the additional (transitive)
list rather than added with a possibly-wrong version. Check stderr for a
`WARNING:` naming the skipped package if a dependency you expected is
missing.

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

Every SBOM element built from a lock-resolved dependency carries a
provenance annotation naming the file and method Pitloom used, e.g.
`Source: pylock.toml | Method: resolved_lockfile`. If a lower-priority
lock file was present but ignored in favor of a higher-priority one,
the annotation also says so, e.g. `Source: pylock.toml | Method:
resolved_lockfile | Note: supersedes poetry.lock`. See [Metadata
provenance](metadata-provenance.md) for how to read these annotations
in the generated SBOM.

## Configuration and flags

There is currently no setting to change the priority order above,
choose a specific lock file, or turn lock-file reading off -- it's
automatic, based purely on which lock file (if any) is present next to
`pyproject.toml`. If you don't want a lock file's resolved dependencies
included, the only way is to not have that file present when you run
`loom project`/`loom generate`.

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
