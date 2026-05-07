---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Poetry support — implementation notes

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
| `src/pitloom/extract/poetry.py` | New extraction module |
| `src/pitloom/extract/pyproject.py` | Updated to fall back to / merge Poetry data |
| `tests/test_poetry.py` | 51 unit and integration tests |
| `tests/fixtures/sampleproject-poetry/` | Real-world fixture (mistral-inference) |

## Extraction functions

### `read_poetry(pyproject_path)`

Public entry point.  Reads `pyproject.toml` from disk, extracts metadata from
`[tool.poetry]`, and returns `(ProjectMetadata, PitloomConfig)`.
`[tool.pitloom]` is still honoured for Pitloom-specific settings.

### `extract_poetry_metadata(data, project_dir)`

Internal helper called by `read_pyproject()` to avoid reading the file twice.
Accepts the pre-parsed TOML dict and returns only `ProjectMetadata`.

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
| `">=X"` etc. | PEP 440 — pass-through | unchanged |

Inline-table constraints (`{version = "^1.0", optional = true, …}`) have their
`version` key extracted and converted.  Entries with `path`, `git`, or `url`
sources cannot be expressed as simple PEP 508 specifiers and are skipped.

## Conflict resolution with `[project]`

`read_pyproject()` merges the two sources when both exist.  Priority order
(highest first):

1. `[project]` — parsed by `pyproject-metadata` (PEP 621)
2. `[tool.poetry]` — fills any empty/falsy fields not covered by `[project]`

When `[project]` is absent or has no `name`, `[tool.poetry]` is used
as the sole source.

## Test fixture

`tests/fixtures/sampleproject-poetry/` contains a verbatim copy of the
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

- **Dynamic versions** — Poetry supports `version = {attr = "pkg.__version__"}`
  style dynamic versions.  These are not resolved; the literal string is
  returned as-is.
- **Path / git / URL dependencies** — entries with `path`, `git`, or `url`
  sources are silently skipped because they cannot be expressed as PEP 508
  specifiers.
- **`poetry.lock`** — the lock file is present as a fixture for future work
  but is not yet read.  Resolving the full transitive dependency graph from
  `poetry.lock` is a planned enhancement.
- **`[tool.poetry.extras]`** — optional extras are not yet mapped to
  `ProjectMetadata`.
