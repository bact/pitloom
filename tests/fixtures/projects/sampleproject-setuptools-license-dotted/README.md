---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Sample project

A minimal setuptools package used as a test fixture for Pitloom's
handling of PEP 621's TOML dotted-key license form, `license.text =
"..."` -- as opposed to the more common inline-table form, `license =
{text = "..."}`. Modeled on
[apple/tree-sitter-pkl](https://github.com/apple/tree-sitter-pkl)'s real
`pyproject.toml`, which uses this exact style (not published on PyPI, so
vendored as a small synthetic fixture here rather than a real sdist --
see `tests/fixtures/real-world-projects/README.md`).

Both forms parse to an identical Python dict once read by any TOML
library (`{"license": {"text": "Apache-2.0"}}`) -- dotted keys are just
TOML's syntax for building up a nested table inline. This fixture exists
to document that equivalence explicitly, not because Pitloom's
`_pyproject.py`/`_models_wheel_setuptools.py` need separate code paths
for it.
