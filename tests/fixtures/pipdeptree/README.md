---
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# pipdeptree output fixtures

See also: [../real-world-projects/README.md](../real-world-projects/README.md)
(the vendored `requests-2.34.2` sdist installed to produce these);
[`../../extract/test_env.py`](../../extract/test_env.py) and
[`../../core/generator/test_generator_env_pipdeptree.py`](../../core/generator/test_generator_env_pipdeptree.py)
for the tests that use them.

Real, unmodified `pipdeptree` output for `loom env`'s extractor and
assembler tests. Mocks written by hand hid a `--json` vs `--json-tree`
shape mismatch, so the shapes here are captured, not authored.

| File | Command | Used for |
| --- | --- | --- |
| `requests-2.34.2.json` | `pipdeptree --python <venv>/bin/python -o json` | positive: the shape `loom env` runs (`--json`) |
| `requests-2.34.2.json-tree.json` | `pipdeptree --python <venv>/bin/python -o json-tree` | negative: the old, rejected nested shape |

## Method

- Source project: the vendored sdist
  `../real-world-projects/setuptools/requests-2.34.2/requests-2.34.2.tar.gz`.
- Environment: `uv venv` (Python 3.13.12), then
  `uv pip install <that sdist>`. Resolved on 2026-09-30:
  `certifi 2026.7.22`, `charset-normalizer 3.5.1`, `idna 3.20`,
  `requests 2.34.2`, `urllib3 2.8.0`. Only requests is top-level.
- Tool: `pipdeptree 4.2.5`, run from Pitloom's own `.venv` with
  `--python` pointing at the scratch venv, so pipdeptree itself is not
  in the captured environment. `-o json` output is byte-identical to
  `--json`, and `-o json-tree` to `--json-tree --all` (checked).
- Pitloom's floor `pipdeptree>=4.2.3` emits the same `--json` shape
  (checked with 4.2.3).
- Fixtures do not change when their packages release; recapture only if
  pipdeptree's JSON shape changes.
