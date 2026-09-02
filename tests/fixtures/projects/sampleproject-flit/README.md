---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Sample project

A minimal `src/`-layout Flit-core package used as a test fixture for
Pitloom's Flit metadata extraction (`pitloom.extract._flit`) and wheel
file discovery (`pitloom.core._models_wheel_flit`).

`version`/`description` are PEP 621 `dynamic` fields, resolved from
`src/sampleproject_flit/__init__.py`'s `__version__` assignment and
module docstring -- the same convention a real Flit build uses, and the
gap Pitloom's generic dynamic-version heuristic (built for Hatchling's
`__about__.py`/`__version__.py` file convention) doesn't cover on its
own.
