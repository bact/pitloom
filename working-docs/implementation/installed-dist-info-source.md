---
Created: 2026-09-14
Last-Modified: 2026-11-06
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Installed `.dist-info`/`.egg-info` as a metadata source

Status: built (V1, the in-tree editable-install byproduct), shipped in
0.18.0. The site-packages phase is not built:
[installed-dist-info-site-packages.md](../design/installed-dist-info-site-packages.md).

See also: [metadata-sources.md](../design/metadata-sources.md) (the overall
priority-order design this corrects and splits),
[build-backend-improvements.md](../design/build-backend-improvements.md),
[roadmap.md](../design/roadmap.md) (summary bullets, this doc's detail moved
out of there per this repo's roadmap-hygiene rule).

## Two different things are both called "installed `.dist-info`"

Conflating them is dangerous:

1. **In-tree editable-install byproduct** (this doc's implemented slice,
   V1). A build backend's *editable-install* step sometimes leaves its
   metadata **inside the project's own source tree**: setuptools'
   `egg_info` step (run internally by `editable_wheel`) leaves
   `<name>.egg-info/` next to `pyproject.toml` and never cleans it up --
   still common today, `pip install -e .` included. `loom` can find this
   safely because it sits right next to the project it's already
   scanning.
2. **Real installed dist-info** (deferred, not yet built -- see
   ["Deferred"](#deferred-real-installed-dist-info-site-packages) below).
   The *actual* installed record for any `pip install` (editable or not,
   any backend) lives in the **venv's `site-packages`**, a different
   filesystem location `loom` cannot safely guess without being told
   which venv.

## Why the static source stays authoritative

A stale in-tree `.egg-info` is a byproduct of whenever `pip install -e .`
last ran -- not necessarily the current commit. Treating it as
higher-priority than `pyproject.toml`/`setup.cfg`/`setup.py` (as an
earlier draft of `metadata-sources.md` proposed) would let a stale build
artefact silently override a project's own current, hand-edited
declaration.

The rule instead: the static source (`pyproject.toml`/`setup.cfg`/
`setup.py`) stays authoritative on any genuine disagreement; installed
metadata only fills gaps the static source left undeclared (e.g. a
`dynamic = ["version"]` field only the build backend actually resolved
-- static parsing categorically cannot see it). A real disagreement is
recorded as an SPDX G2 conflict Annotation on the main project package,
never silently substituted -- reusing the same `ConflictCandidate`/
`build_conflict_annotation` model already used for dependency-version
conflicts (`deps_installed.py`) and the project's own declared/concluded
licence disagreement (`deps_license.py`).

## Why this slice was built first despite narrow day-to-day payoff

Its main payoff is narrow: setuptools projects using
`setuptools_scm`/dynamic versioning, where static parsing categorically
cannot resolve the real value but the installed metadata already has it
-- and it barely applies to Pitloom's own primary Hatchling target
(Hatchling doesn't run `egg_info`, so it rarely leaves anything in-tree).
It was built anyway as **the foundation for the future backend-agnostic,
site-packages-aware phase** that will apply to every backend and every
`pip install`: the discovery/parsing/reconciliation pieces are written so
that future phase can reuse parsing and reconciliation unchanged,
swapping only discovery.

## Field mapping

`pitloom.extract.project.installed._parse_installed_metadata()` maps
Core Metadata RFC 822 headers, per the [PyPA Core Metadata
spec](https://packaging.python.org/en/latest/specifications/core-metadata/):

| `ProjectMetadata` field | RFC 822 header(s) | Notes |
|---|---|---|
| `name` | `Name` | Identity gate only (see below), never merged |
| `version` | `Version` | Conflict-checked |
| `description` | `Summary` | Gap-fill only; **not** the long `Description` body |
| `requires_python` | `Requires-Python` | Conflict-checked, PEP 440 `SpecifierSet` equality |
| `license_name` | `License-Expression` if present, else legacy `License` | Conflict-checked, SPDX expression equality |
| `keywords` | `Keywords` | Gap-fill only; CSV split via `to_str_list` |
| `urls` | `Project-URL` (+ legacy `Home-page` -> `"Homepage"`) | Gap-fill only; first-comma-only split; **not** `Download-URL` (deliberately narrower than `extract/wheel.py`'s parser, see "Relationship to `extract/wheel.py`'s parser" below) |

Not extracted in V1, each for its own real design reason:

- `License-File` -- no `ProjectMetadata` field to fill: an SBOM lists
  nothing under a distribution's own `.dist-info` (`licenses/` included),
  so `[project.license-files]` is not read on any path either.
- `authors` -- flat `Author`/`Author-email` RFC 822 strings vs. PEP 621's
  structured `project.authors` list; collapsing N structured authors down
  to one flat string (what a build backend does when *writing* METADATA)
  is lossy in a way that can't be cleanly reversed in the general case.
- `dependencies` -- `Requires-Dist` mixes base dependencies and extras
  (marked `; extra == "..."`); filtering extras out needs
  `packaging.requirements.Requirement(...).marker` inspection per entry.

## Name/identity safety gate

The single most important safety property: an in-tree
`.egg-info`/`.dist-info` whose `Name` does not canonically match (PEP
503) the project already being scanned is rejected **entirely** -- not
even used for gap-fill. Realistic trigger: a monorepo, a renamed package
whose old `.egg-info` was never deleted, or a leftover from
`pip install -e .` having been run against a different checkout that
happens to share a directory. Using such a candidate's `version`/
`license`/etc. would silently attribute a completely unrelated package's
facts to the one being described. The check runs in discovery
(`find_installed_metadata_candidate`) **before** the `.dist-info`-vs-
`.egg-info` tie-break, not after -- so a wrong-name `.dist-info` can never
out-rank a correct-name `.egg-info` on format alone.

## Discovery

Bounded, non-recursive glob only (`*.egg-info`, `*.dist-info`,
`src/*.egg-info`, `src/*.dist-info`, `src/*/*.egg-info`,
`src/*/*.dist-info`) -- never `rglob`, to avoid descending into an
accidentally-vendored `node_modules`/`vendor/` tree. The one-path-segment
`src/*.egg-info` pattern is the empirically-verified real shape:
setuptools' own `egg_info` command writes `<name>.egg-info` directly
under `src/` for a `package_dir={"": "src"}` project (verified via a real
`python setup.py egg_info` run against a `src/`-layout project), not
nested inside an extra package-name directory. The two-segment
`src/*/*.egg-info` pattern is kept alongside it defensively, for a
layout/backend not independently verified to use the one-segment shape.
Deterministic tie-break when multiple name-matching candidates survive:
`.dist-info` before `.egg-info` (more modern/structured format), then
alphabetical path.

## Relationship to `extract/wheel.py`'s parser

`extract/wheel.py`'s `_populate_metadata_from_email`/`_parse_metadata_urls`
already parse a wheel's own embedded `.dist-info/METADATA` -- the closest
existing code to this module's `_parse_installed_metadata`/
`_parse_installed_urls`, and the two now duplicate the `Project-URL`
first-comma-only split logic nearly verbatim. Deliberately not unified in
V1: `wheel.py` is a separate, working, tested path (`embed-wheel`'s
wheel-internal-METADATA source, unrelated to this in-tree feature) with
its own known gaps at the time (flattened authors; extras-only
`Requires-Dist` as required), both fixed in #300: authors now come from the
shared `extract/_core_metadata.py` reader, extras-only entries become
`hasOptionalDependency` edges. `wheel.py`'s parser also handles
`Download-URL` (-> `urls["Download"]`); this module's does not -- not an
oversight, just not in this feature's V1 field scope (see the field
mapping table above). Worth unifying into one shared RFC 822
Core-Metadata parser later, once a second caller besides `wheel.py`
actually needs `Download-URL`/author-list correctness, rather than
speculatively generalising now.

## Reuse note (not duplicated by the future phase)

`_parse_installed_metadata()` and `reconcile_installed_metadata()` are
written format-agnostic of *where* the marker file came from. The future
site-packages phase only needs a new discovery function (a sibling of
`find_installed_metadata_candidate`), not a rewrite of parsing or
reconciliation -- a future implementer should reuse them rather than
duplicate.

## Deferred: real installed dist-info (site-packages)

Not built. The design of that phase is in
[installed-dist-info-site-packages.md](../design/installed-dist-info-site-packages.md).
