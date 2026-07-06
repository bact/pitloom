---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Sample project (dynamic version)

A Python package used as a test fixture for the Pitloom Hatchling build hook's
use of Hatchling's own resolved project metadata. Its version is `dynamic`
and resolved via a `[tool.hatch.version] source = "code"` expression that
Pitloom's own naive `pyproject.toml`-only version extraction cannot evaluate
(it only reads raw source text, never executes it), so this fixture proves
the hook uses `self.metadata.version` -- not a re-parsed guess.

## Building

Build with `--no-isolation` so the locally installed Pitloom is picked up:

```bash
cd tests/fixtures/projects/sampleproject-hatchling-dynver
python -m build --wheel --no-isolation
```

The resulting wheel will contain `.dist-info/sboms/sbom.spdx3.json` (PEP 770)
with `software_packageVersion` set to `1.0.5` (the code-evaluated version).
