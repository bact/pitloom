---
Created: 2026-05-07
Last-Modified: 2026-08-31
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Poetry support -- implementation notes

See also: [setuptools-support.md](setuptools-support.md) (the
wheel-file-discovery section below mirrors its shape) and
[hatchling-build-hook.md](hatchling-build-hook.md) (Poetry has no
equivalent build-time hook -- see "Build-time hook: not attempted"
below); [backend-file-discovery-validation.md](backend-file-discovery-validation.md)
for the real-world validation results; `working-docs/design/roadmap.md`'s
"Non-Hatchling file discovery" section for the backend-priority table
this work closes item #2 of.

## Motivation

Pitloom 0.5.1 cannot extract any metadata from projects that use Poetry as
their build backend (e.g. [mistral-inference]) because those projects may have
no `[project]` section in `pyproject.toml`.  Instead they declare everything
under `[tool.poetry]`.  Issue [#64].

[mistral-inference]: https://github.com/mistralai/mistral-inference
[#64]: https://github.com/bact/pitloom/issues/64

## Source files

| File | Role |
| :--- | :--- |
| `src/pitloom/extract/_poetry.py` | Metadata extraction module (renamed from `poetry.py`) |
| `src/pitloom/extract/_poetry_lock.py` | `poetry.lock` transitive-dependency extraction (source-stage only) |
| `src/pitloom/extract/_pyproject.py` | Falls back to / merges Poetry metadata; wires in `poetry.lock` reading |
| `src/pitloom/core/_models_wheel_poetry.py` | Wheel file discovery, delegating to poetry-core's own `WheelBuilder` |
| `src/pitloom/assemble/spdx3/deps.py`, `document.py` | Additive locked-transitive-dependency `dependsOn` edges, `completeness` tagging |
| `tests/extract/test_poetry_parsing.py`, `tests/extract/test_poetry_pyproject.py` | 51 unit and integration tests for metadata extraction (originally `tests/test_poetry.py`, later split into these two files -- see `working-docs/design/cli-test-coverage-roadmap.md`) |
| `tests/extract/test_poetry_lock.py` | `poetry.lock` parsing unit and integration tests |
| `tests/core/test_models_wheel_poetry.py` | Wheel file discovery unit tests |
| `tests/assemble/test_deps_locked_dependencies.py` | Assemble-layer additive-edge/`completeness` tests |
| `tests/fixtures/projects/sampleproject-poetry/` | Real-world metadata fixture (mistral-inference; no `src/` package dir, not usable for file discovery) |
| `tests/fixtures/projects/sampleproject-poetry-src/`, `sampleproject-poetry-include-exclude/` | Synthetic file-discovery fixtures (`src/`-layout, `include`/`exclude` globs) |

## Extraction functions

### `extract_poetry_metadata(data, project_dir)`

The only entry point.  Accepts the pre-parsed TOML dict and returns
`ProjectMetadata`; called by `read_pyproject()`'s `_try_read_poetry()`
fallback so the file is only ever read/parsed once. There is no
standalone "read a poetry pyproject.toml from disk" function -- that
would just duplicate what `read_pyproject()` already does for every
project regardless of build backend.

## Field mapping

| `[tool.poetry]` key | `ProjectMetadata` field |
| :--- | :--- |
| `name` | `name` |
| `version` | `version` |
| `description` | `description` |
| `readme` | `readme` (first element when a list) |
| `authors` | `authors` (parsed from `"Name <email>"` strings) |
| `license` | `license_name` |
| `keywords` | `keywords` |
| `homepage` | `urls["Homepage"]` |
| `repository` | `urls["Repository"]` |
| `documentation` | `urls["Documentation"]` |
| `dependencies.python` | `requires_python` |
| `dependencies` (non-python) | `dependencies` |

## Dependency groups

`[tool.poetry.group.*]` sections (e.g. `[tool.poetry.group.dev.dependencies]`)
are **intentionally excluded** from the SBOM.  These groups are a Poetry
convention for tooling used during development or deployment, equivalent to
`[project.optional-dependencies]` dev extras.  They are not runtime
dependencies of the package and do not belong in an SBOM.

Only `[tool.poetry.dependencies]` (the main, non-grouped table) is included.

## Version specifier conversion

Poetry uses specifiers that are not valid PEP 440/508:

| Poetry form | Meaning | Converted to |
| :--- | :--- | :--- |
| `"^X.Y.Z"` (X > 0) | `>=X.Y.Z,<(X+1).0.0` | `>=X.Y.Z,<X+1.0.0` |
| `"^0.Y.Z"` | `>=0.Y.Z,<0.(Y+1).0` | `>=0.Y.Z,<0.Y+1.0` |
| `"~X.Y.Z"` | `>=X.Y.Z,<X.(Y+1).0` | `>=X.Y.Z,<X.Y+1.0` |
| `"X.Y.Z"` (bare) | exact match | `==X.Y.Z` |
| `"*"` | any | (no constraint) |
| `">=X"` etc. | PEP 440 -- pass-through | unchanged |

Inline-table constraints (`{version = "^1.0", optional = true, …}`) have their
`version` key extracted and converted.  Entries with `path`, `git`, or `url`
sources cannot be expressed as simple PEP 508 specifiers and are skipped.

## Conflict resolution with `[project]`

`read_pyproject()` merges the two sources when both exist.  Priority order
(highest first):

1. `[project]` -- parsed by `pyproject-metadata` (PEP 621)
2. `[tool.poetry]` -- fills any empty/falsy fields not covered by `[project]`

When `[project]` is absent or has no `name`, `[tool.poetry]` is used
as the sole source.

## Wheel file discovery

`_models_wheel_poetry.py`'s `discover()` resolves `[tool.poetry]`'s
`packages`/`include`/`exclude` config the same way
`_models_wheel_hatchling.py` does: **delegate to the real backend
library**, not a hand-rolled reimplementation. Poetry-core is fully
declarative (no `setup.py`-style arbitrary code execution needed to know
what files belong in a wheel), so this is safe the same way the existing
Hatchling delegation is -- unlike setuptools, which had to hand-roll its
own static-config resolution specifically to avoid executing
project-authored `setup.py` code.

Mechanism: `poetry.core.factory.Factory().create_poetry(project_dir)`
builds a `Poetry` object from `pyproject.toml`; `WheelBuilder(poetry_obj)
.find_files_to_add()` (a public method on the base `Builder` class,
inherited unchanged by `WheelBuilder`) returns the resolved file set.
Each `BuildIncludeFile.path` (absolute) becomes `IncludedFile.path`;
`.relative_to_target_root()` becomes `IncludedFile.distribution_path`.
Any exception (not a Poetry project, malformed config) is caught and
logged as a `WARNING:`, returning `None` so the caller falls back
accordingly -- identical error-handling shape to the Hatchling module.

Two poetry-core behaviors worth knowing before extending this:

- **A bare `include`/`exclude` string entry defaults to `format =
  ["sdist"]` only.** To apply to wheel builds too (what `discover()`
  needs), an entry must declare `format` explicitly (e.g. `{path = "...",
  format = ["sdist", "wheel"]}`). A naive glob-only `include` list looks
  like it should work for wheels and silently doesn't -- confirmed via
  poetry-core source and reproduced in the
  `sampleproject-poetry-include-exclude` fixture.
- **A `.git` directory, when present, only *excludes* `.gitignore`-matched
  files** -- it is never required, and never expands the *included* base
  set beyond what `packages`/`include` already declare. This keeps
  discovery deterministic and usable in a git-less checkout (e.g. an
  extracted sdist).

`poetry-core>=2.0.0` was added as a new runtime dependency for this.

## Build-time hook: not attempted

Unlike Hatchling (`pitloom.plugins.hatch`, a `hatchling.build_config`
plugin that fires for every PEP 517 build regardless of caller), Poetry
has no comparable in-build hook mechanism to attach to. poetry-core --
the actual PEP 517 backend invoked by `pip install`, `python -m build`,
and CI -- has no plugin/hook API at all. Only the separate, optional
`poetry` CLI application has a plugin system
(`poetry.plugin.Plugin`/`ApplicationPlugin`), and it only fires for
`poetry build` specifically run through that CLI, not the standard PEP
517 path most tooling actually uses. This puts Poetry at the same tier
as setuptools (also dispatch/library-level only, no in-build hook) --
one tier below Hatchling. Both rely on the GitHub Action as their
"automatic" surface. This was evaluated, not simply left undone: there is
no code path to add here without hooking Poetry's own CLI application, a
materially different and narrower integration point than Hatchling's.

## `poetry.lock` transitive dependencies

`poetry.lock` is produced and consumed entirely by the separate `poetry`
CLI application (`poetry lock`/`add`/`update` write it, `poetry install`
reads it) -- confirmed via poetry-core source (`factory.py` has zero
references to "lock") that poetry-core's build backend (`poetry build`,
`pip install .`, `python -m build`) never touches it. That makes it a
**source-stage-only** artifact per
[sbom-lifecycle-stages.md](sbom-lifecycle-stages.md): appropriate for
`loom project`/`loom generate` (a static file sitting next to
`pyproject.toml`), wrong for `loom wheel`/`embed-wheel` (the real
wheel's own metadata is ground truth and never consulted the lock) and
wrong for `loom env` (live introspection of what's actually installed is
strictly more authoritative than a lock that may be stale relative to
it).

`_poetry_lock.py`'s `extract_poetry_lock_dependencies()` reads
`[[package]]` tables from a sibling `poetry.lock`, keeping only packages
whose `groups` includes `"main"` (excluding dev/other-group-only
packages, the same "not a runtime dependency" policy already applied to
`[tool.poetry.group.*]` above), as exact-pin `name==version` strings.
Wired into `_try_read_poetry()` so both `read_pyproject()` branches
(Poetry-as-sole-source and Poetry-filling-gaps-for-`[project]`) get it
automatically via `merge_project_metadata()`'s generic field iteration.

In the assembled SPDX 3 graph, a locked package already covered by a
direct `[tool.poetry.dependencies]` entry gets no duplicate edge --
only genuinely transitive-only packages get an additive `dependsOn`
relationship, tagged `completeness = complete` (via
`spdx3.RelationshipCompleteness`, previously declared but unused
anywhere in the codebase) to distinguish a lock-resolved edge from an
unresolved direct-constraint one. The document UUID's seed also folds in
`locked_dependencies` (when non-empty) so two documents with identical
direct dependencies but different lock-resolved graphs don't collide on
the same UUID.

## Test fixture

`tests/fixtures/projects/sampleproject-poetry/` contains a verbatim copy of the
[mistral-inference](https://github.com/mistralai/mistral-inference) repository's
`pyproject.toml` and `poetry.lock`.  This project was the original motivating
case for Poetry support (issue [#62]).  It has:

- No `[project]` section
- `[tool.poetry]` with name, version, authors, readme
- Empty `description` field (maps to `None`)
- No `license` field
- `[tool.poetry.dependencies]` with caret and `>=` constraints
- `[tool.poetry.group.dev.dependencies]` (excluded from SBOM)

[#62]: https://github.com/bact/pitloom/issues/62

## Known limitations

- **Dynamic versions -- confirmed out of scope, not a TODO.** Native
  `[tool.poetry].version` has no `{attr = "pkg.__version__"}`-style dynamic
  resolution at all -- that syntax is a Hatchling/setuptools convention, not
  something `[tool.poetry]` accepts. The only way a Poetry project gets a
  dynamic version is the third-party `poetry-dynamic-versioning` plugin,
  which resolves a VCS tag only inside the full `poetry` CLI's own build
  path -- not statically resolvable at all, the same class of limitation as
  `hatch-vcs` for Hatchling (which Pitloom also cannot statically resolve
  for the version *string*, independent of wheel file discovery). This was
  previously written up as an unresolved TODO; it isn't one.
- **Path / git / URL dependencies** -- entries with `path`, `git`, or `url`
  sources are skipped because they cannot be expressed as PEP 508
  specifiers, logging a `WARNING:` naming the dependency and the source
  kind (`_poetry_dep_to_pep508()` in `_poetry.py`).
- **`[tool.poetry.extras]`** -- optional extras are not yet mapped to
  `ProjectMetadata`. This is a schema-wide gap, not Poetry-specific:
  `ProjectMetadata` has no extras/optional-dependencies field for any
  backend (Hatchling and setuptools don't get this either).
