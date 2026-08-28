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

`sampleproject-poetry/` is a minimal Python package that exercises
Pitloom's Poetry metadata extraction (`pitloom.extract.poetry`).
It uses  metadata under ``[tool.poetry]`` and optionally
``[tool.poetry.dependencies]`` in `pyproject.toml`.

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
