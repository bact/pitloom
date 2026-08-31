---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Sample project

A minimal Poetry package used as a test fixture for Pitloom's Poetry wheel
file discovery (`pitloom.core._models_wheel_poetry`), exercising explicit
`include`/`exclude` glob lists.

- `extra_data/included.txt` sits outside the auto-discovered package
  directory and is only picked up because of `include`.
- `sampleproject_poetry_include_exclude/data.json` sits inside the package
  directory (would be picked up by default) but is dropped via `exclude`.
- `notes/scratch.md` is outside the package directory, not listed in
  `include`, and additionally matched by `exclude` -- never included.
