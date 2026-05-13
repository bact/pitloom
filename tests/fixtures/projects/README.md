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
Pitloom's setuptools metadata extraction (`pitloom.extract.setuptools`).
It uses the common transitional layout: `pyproject.toml` for the
`[build-system]` table only, with all project metadata in `setup.cfg`
and a bare `setup.py` shim.
