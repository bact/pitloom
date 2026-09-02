---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Sample project

A minimal `src/`-layout PDM-backend package used as a test fixture for
Pitloom's PDM metadata extraction (`pitloom.extract._pdm`) and wheel
file discovery (`pitloom.core._models_wheel_pdm`).

`[tool.pdm.build] package-dir = "src"` exercises the `physical_path` vs
`distribution_path` divergence: the package lives at
`src/sampleproject_pdm/` on disk but must be discovered at
`sampleproject_pdm/` inside the wheel.

`version` is a PEP 621 `dynamic` field, resolved via `[tool.pdm.version]
source = "file"` reading `src/sampleproject_pdm/__init__.py`'s
`__version__` assignment -- the gap Pitloom's generic dynamic-version
heuristic (built for Hatchling's `__about__.py`/`__version__.py` file
convention) doesn't cover on its own.
