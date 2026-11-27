---
Created: 2026-11-27
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# LicenseID floor 0.9.4: licence-answer sweep

The 0.25.0 bump raises the floor from `licenseid>=0.9.3,<0.10` to
`>=0.9.4,<0.10`. Before the raise, every licence answer Pitloom gives on its
fixtures was compared under both versions. Result: **no licence answer
differs.**

See also: [README.md](README.md), [adoption-built.md](adoption-built.md)
(the 0.22.1 to 0.23.0 sweep this one follows),
[license-pipeline.md](../license-pipeline.md).

## What 0.9.4 changes upstream

From its release notes (PyPI, 2026-11-27): several texts of one file listed
in file order; more texts recognised when the copyright holder or project
name differs from the SPDX License List's; numpy's `LICENSE.txt` no longer
read as `GPL-3.0-only`; database build 7.

## Method

Two scratch virtual environments on Python 3.10.19, each an exact
`--no-deps` copy of the repo `.venv`'s packages with only `licenseid`
pinned (0.9.3, 0.9.4). Each built its own database
(`licenseid update --source packaged`) under a scratch `HOME`; the shared
`~/.local/share/licenseid/licenses.db` was not touched. Pitloom from the
bump tree (`PYTHONPATH=src`), `SOURCE_DATE_EPOCH=1767225600`, `--offline`.

1. **SBOMs.** `loom project` on 87 targets: every directory under
   `tests/fixtures/projects/`, `real-world-locks/*/` and
   `real-world-extras/*/`, the 21 sdists of `real-world-projects/`, the
   manual checks' `demo` project, Pitloom's own tree, and one Hatchling
   project per `tests/fixtures/license-texts/*-LICENSE` (the text as
   `LICENSE`, no declared licence, so LicenseID detects it); `loom wheel` on
   the 13 wheels Hatchling built from the `demo` and licence-text projects.
   SBOM, stdout, stderr and exit code compared byte for byte, after
   replacing `licenseid==0.9.x` and the output directory.
2. **Direct reads.** `read_license_text()` on 339 licence files (every
   `LICENSE*`, `LICENCE*`, `COPYING*` and `licenses/*` under
   `tests/fixtures/` and the environment's `site-packages`); 250 give an
   answer.

## Result

98 SBOMs were written (2 targets fail the same way under both versions:
the dynamic-version fixture and a `setup.py` with no name; neither is about
licences). 71 hold a declared licence, 50 a concluded one, 48 a LicenseID
detection.

| Difference | Where | Why |
| --- | --- | --- |
| `licenseid` package version 0.9.3 -> 0.9.4 | Pitloom's own SBOM | the installed dependency, as expected |
| `INFO: licenseid: input: variant not stated: GPL-3.0; using GPL-3.0-only` gone | numpy 2.5.5 `LICENSE.txt` (licence-text project) | 0.9.4 no longer reads the file as GPL-3.0; Pitloom already gave no licence (several texts, #554), so the SBOM is unchanged |

No declared, concluded or detected licence, no several-texts refusal and
no direct read changed. No CHANGELOG entry for answers; the floor raise
joins the existing floor entry.
