---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Sample project

A Python package used as a test fixture for the Loom Hatchling build hook.
It contains just enough metadata and source code to produce a valid wheel.

## Building

Build with `--no-isolation` so the locally installed Loom is picked up:

```bash
cd tests/fixtures/sampleproject
python -m build --wheel --no-isolation
```

The resulting wheel will contain `.dist-info/sboms/sbom.spdx3.json` (PEP 770).
