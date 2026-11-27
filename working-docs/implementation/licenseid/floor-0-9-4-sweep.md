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
fixtures was compared under both versions. Result: **one regression**,
found by a second-opinion review, not by the sweep: under 0.9.4 Pitloom
no longer sees that a licence file holds several texts (#554's rule), so a
later licence file can give the package a licence. Every other answer is
unchanged. The fix is open; see "Several texts" below.

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
   `tests/fixtures/projects/`, `real-world-locks/*/*/` and
   `real-world-extras/*/*/`, the 21 sdists of `real-world-projects/`, the
   manual checks' `demo` project, Pitloom's own tree, and one Hatchling
   project per `tests/fixtures/license-texts/*-LICENSE` (the text as
   `LICENSE`, no declared licence, so LicenseID detects it); `loom wheel` on
   the 13 wheels Hatchling built from the `demo` and licence-text projects
   (the wheel route reads only copyright from them: no licence coverage).
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

Pitloom's own 0.25.0 wheel (built by the release gate) gives the same
SBOM and stderr under both versions. LicenseID alone (`licenseid detect`)
reads numpy's text as `GPL-3.0-only` under 0.9.3 and as nothing under 0.9.4.

No declared, concluded or detected licence and no direct read
(`read_license_text().expression`) changed.

## Several texts: a regression under 0.9.4

The direct-read probe recorded `texts`, an attribute `LicenseTextReading`
does not have, so it never saw `several_texts`. Recorded properly, it flips
from true to false under 0.9.4 for six files: numpy 2.5.5's and 2.2.6's
`LICENSE.txt`, mypy's, exceptiongroup's and librt's `LICENSE`, and
setuptools' `_validate_pyproject/NOTICE`.

Cause: for these texts 0.9.4's `LicenseDetector.detect()` returns no
result, where 0.9.3 returned ranked results that each carried
`texts: [...]`. `_holds_several_texts()` (`_license_text_match.py`) reads
`results[0]["texts"]`, so it cannot fire. 0.9.4 gives the list through
`LicenseDetector.texts()`, which 0.9.3 lacks.

End to end: a project with numpy's text as `LICENSE` and an Apache-2.0 text
as `COPYING`, no declared licence, gets no licence under 0.9.3 (the search
ends) and `Apache-2.0` (`Source: COPYING | Method: licenseid_detection`)
under 0.9.4. The Hugging Face card route (`huggingface_fetch.py`, which
stops on `several_texts`) is exposed the same way. The tests stay green:
the "ends the search" test uses the types-setuptools text, which 0.9.4
still flags, and the numpy test asserts only `None`.

Every fixture project holds one licence file, so a lost refusal looked like
"no licence" there; that is why the SBOM sweep missed it.

`licenseid>=0.9.3` already installs 0.9.4, so this reaches users whatever
the floor. Fix (open, the user's call): ask `texts()` when `detect()` gives
nothing (needs the 0.9.4 floor), with a regression test of a several-texts
file followed by a one-licence file.
