---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Sample project

A minimal `src/`-layout Poetry package used as a test fixture for Pitloom's
Poetry wheel file discovery (`pitloom.core._models_wheel_poetry`).

`[tool.poetry].packages` uses an explicit `{include = ..., from = "src"}`
entry, exercising the `physical_path` vs `distribution_path` divergence:
the package lives at `src/sampleproject_poetry_src/` on disk but must be
discovered at `sampleproject_poetry_src/` inside the wheel.
