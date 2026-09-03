---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Project fixtures

## Hatchling

`sampleproject-hatchling/` is a minimal Python package used to test the
Pitloom Hatchling build hook (`pitloom.plugins.hatch`).  See
[sampleproject-hatchling/README.md](sampleproject-hatchling/README.md) for
build instructions.

## Poetry

`sampleproject-poetry/` is a verbatim copy of a real project's
(mistral-inference) `pyproject.toml`/`poetry.lock`, used to exercise
Pitloom's Poetry metadata extraction (`pitloom.extract._poetry`). It has
no `src/` package directory on disk -- metadata-only, not usable for wheel
file discovery.

`sampleproject-poetry-src/` is a minimal, complete `src/`-layout Poetry
package that exercises Pitloom's Poetry wheel file discovery
(`pitloom.core._models_wheel_poetry`) via an explicit
`packages = [{include = ..., from = "src"}]` entry -- the
`physical_path`/`distribution_path` divergence every backend's discovery
module must get right.

`sampleproject-poetry-include-exclude/` exercises the same discovery
module's `include`/`exclude` glob handling: a file outside the
auto-discovered package directory only appears because of `include`, and
a file inside the package directory that would be included by default is
dropped via `exclude`.

## Setuptools

`sampleproject-setuptools/` is a minimal Python package that exercises
Pitloom's setuptools metadata extraction (`pitloom.extract.setuptools`)
and wheel file discovery (`pitloom.core._models_wheel_setuptools`). It
uses the common transitional layout: `pyproject.toml` for the
`[build-system]` table only, with all project metadata in `setup.cfg`
and a bare `setup.py` shim -- `[options.packages.find] where = src`
specifically, the layout that regresses if the `where=` source
directory leaks into distribution paths.

`sampleproject-setuptools-data/` exercises the same wheel file
discovery module's manifest-analysis path: `package_data` (explicit
glob) and `include_package_data` + `MANIFEST.in` together, plus the
no-disk-mutation guarantee (discovery must never leave an `.egg-info`
artifact behind). Same transitional `pyproject.toml`/`setup.cfg` split
as `sampleproject-setuptools/`.

`sampleproject-setuptools-zeroconfig/` is a bare PEP 621 project --
`pyproject.toml` declares only `[project] name`/`version`, no
`[tool.setuptools]` table at all. Exercises setuptools' own zero-config
auto-discovery (`Distribution.set_defaults()`/`ConfigDiscovery`),
distinct from `apply_configuration()`'s explicit-config path used by
the two fixtures above -- a project shaped this way resolves to an
empty file list, not a build-backend-not-yet-supported `None`, if
auto-discovery is never triggered.

`sampleproject-setuptools-merged/` has `[tool.setuptools.package-data]`
in `pyproject.toml` and `packages`/`package_dir` in `setup.cfg` --
proves both files are consulted together (not mutually exclusive) for
wheel file discovery, matching how a real setuptools build treats them.

`sampleproject-setuptools-license-dotted/` exercises PEP 621's TOML
dotted-key license form (`license.text = "..."`, as seen in
apple/tree-sitter-pkl's real `pyproject.toml` -- not published on PyPI,
so vendored here as a small synthetic fixture instead of a real sdist,
see `tests/fixtures/real-world-projects/README.md`), confirming it
parses identically to the more common inline-table form (`license =
{text = "..."}`).

## Flit

`sampleproject-flit/` is a minimal `src/`-layout Flit-core package that
exercises Pitloom's Flit metadata extraction (`pitloom.extract._flit`)
and wheel file discovery (`pitloom.core._models_wheel_flit`):
`version`/`description` are PEP 621 `dynamic` fields resolved from the
module's `__version__` assignment and docstring (flit-core's own
convention), and the `src/` layout exercises the same
`physical_path`/`distribution_path` divergence Poetry's `-src` fixture
does.

## PDM

`sampleproject-pdm/` is a minimal `src/`-layout PDM-backend package that
exercises Pitloom's PDM metadata extraction (`pitloom.extract._pdm`) and
wheel file discovery (`pitloom.core._models_wheel_pdm`): `version` is a
PEP 621 `dynamic` field resolved via `[tool.pdm.version] source =
"file"`, and `[tool.pdm.build] package-dir = "src"` exercises the same
`physical_path`/`distribution_path` divergence as the Flit/Poetry `-src`
fixtures.
