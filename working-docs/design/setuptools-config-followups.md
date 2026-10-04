---
Created: 2026-10-04
Last-Modified: 2026-10-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# setuptools config reading: follow-ups

See also: [license-typing.md](../implementation/license-typing.md) (the
`file:` directive rules built in PR #276),
[roadmap.md](roadmap.md#near-term).

Found in the PR #276 review rounds (R8), outside that PR's scope. All in
`src/pitloom/extract/project/_setup_cfg_directives.py` unless noted.

- **`version = attr:` crashes on a non-UTF-8 module.** `_read_version_attr`
  does not catch `UnicodeDecodeError`/`ValueError`; `loom project` ends with
  `ERROR: SBOM generation failed`. Give it the `file:` treatment: one
  `WARNING:`, version unset.
- **`file:` paths are not confined to the project.** setuptools refuses a
  path outside the project root (`_assert_local`); Pitloom reads `../x`.
  Only `License ::` lines of such a file reach the SBOM, and sdists never
  resolve `file:`. Decide: refuse with one `WARNING:` as setuptools does.
- **setuptools' own `SetuptoolsWarning` lines reach stderr untagged**
  during file discovery (`core/_models_wheel_setuptools.py` drives
  `setuptools.config`). Capture them and re-emit as one `WARNING:` each,
  or silence the ones Pitloom already reports itself.
- **Directory as a `file:` target warns; setuptools skips it silently.**
  Kept on purpose (an existing path that cannot be read is a real failure,
  not absence). Revisit only if it proves noisy.
- **Found in R10 (compared with setuptools 84 on 56 projects):**
  - a `version` file with a BOM: `setup.cfg` records `"\ufeff1.2.3"`, the
    pyproject path ends the run with `ERROR:` (invalid PEP 440); one policy
    for both (e.g. `utf-8-sig`);
  - an invalid single-line version file (`1.2.3 # rel`) is recorded
    unchecked on the `setup.cfg` path, refused on the pyproject path;
  - `description = file: X` is not resolved (records `file: X`);
  - pyproject `dynamic = ["version"]` without `tool.setuptools.dynamic`
    does not fall back to `setup.cfg [metadata] version` as a real build
    does; dynamic `classifiers`/`readme` `{file = ...}` are not read (a
    licence classifier file is lost);
  - `attr:` gaps: `package_dir` other than `src`, tuple versions,
    annotated/multi-target assignments, a constant inside a `def` picked by
    `ast.walk` (setuptools reads top level, then executes);
  - `pyproject` `{file = ..., attr = ...}` together: setuptools refuses,
    Pitloom uses `attr`;
  - `warn_once` is per process: a second `generate_project_sbom` call in
    one process logs the `FILE=` warning at DEBUG only;
  - a setuptools-backend project with a `License ::` classifier prints
    setuptools' untagged 13-line deprecation banner on stderr.
