---
Created: 2026-08-28
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Backend file discovery: real-world validation

See also: [setuptools-support.md](setuptools-support.md) and
[hatchling-build-hook.md](hatchling-build-hook.md) for the discovery
modules themselves; [sbom-lifecycle-stages.md](sbom-lifecycle-stages.md)
for why discovery stays a static-config read, never a build, for every
backend; [../design/roadmap.md](../design/roadmap.md)'s "Non-Hatchling
file discovery" section for the backends still to come; the per-backend
results are listed under [Rounds](#rounds) below.

## Policy

Every build backend's wheel-file `discover()` -- the current ones
(`_models_wheel_setuptools.py`, `_models_wheel_hatchling.py`,
`_models_wheel_poetry.py`, `_models_wheel_flit.py`,
`_models_wheel_pdm.py`) and any future one -- gets checked against
**at least 10 diverse real PyPI packages** before being considered
production-ready, not just the synthetic fixtures under
`tests/fixtures/projects/`. Synthetic fixtures
are precise (they isolate one config style at a time, and drive the
unit/regression test suite) but they can't substitute for real
packages: real maintainers combine config styles in ways a fixture
author wouldn't think to construct, and only real PyPI wheels give an
independent ground truth to diff against.

Starting with the
[Flit-core/PDM-backend round](backend-file-discovery-validation-flit-pdm.md),
these real-world packages are vendored (as sdist archives) under
`tests/fixtures/real-world-projects/` and checked on every test run via
`tests/core/models_wheel/test_models_wheel_real_world.py`, rather than
cloned fresh and discarded per validation pass -- see that directory's
own README for the fixture format. The [Setuptools](backend-file-discovery-validation-setuptools.md)/
[Hatchling and Poetry](backend-file-discovery-validation-hatchling-poetry.md)
rounds predate that and are recorded here as a point-in-time
result only.

"Diverse" means spread across:

- **Config style**: `packages.find` (`where=`/`include=`), explicit
  `packages = [...]` lists, zero-config auto-discovery, legacy
  `setup.cfg`, dynamic version directives (`attr:`, `file:`, VCS-based).
- **Maturity**: brand-new through 15-20+ years old.
- **Authorship**: solo maintainers, small teams, corporate-backed
  (AWS, Redis Inc.), and foundation/official (PSF, PyPA).

## Method

For each package: shallow-clone the source at the git tag matching a
specific PyPI release, download that release's published wheel with
`pip`, run both `loom project` (source SBOM) and `loom wheel` (built-wheel
SBOM, ground truth), then diff the `software_File` entries (`name` field,
where `software_fileKind == "file"`) between the two.

```bash
git clone --quiet --depth 1 --branch <tag> <repo-url> <dir>
pip download --no-deps --only-binary=:all: -d <wheels-dir> <pkg>==<version>
loom project <dir> -o project.json
loom wheel <wheels-dir>/<file>.whl -o wheel.json
```

A perfect result is: `wheel - project == {dist-info files only}` (the
source tree has no `.dist-info`) and `project - wheel == {}`. A
build-time-generated file (VCS-derived `_version.py`, a compiled
extension) legitimately appearing only in the wheel is not a defect --
it's outside what static analysis can ever see; see
[sbom-lifecycle-stages.md](sbom-lifecycle-stages.md).

**Variant for `--allow-build`**: the same "diff against ground truth"
method, applied one level differently -- `loom project` run *twice*
(with and without `--allow-build`) against the same project, rather
than `project` vs. `wheel` once. This answers three questions the
plain method above doesn't: (1) does a registered backend's real build
ever run when its own static discovery already succeeded (it must
not); (2) for a backend with no static module, how does the
Hatchling-heuristic fallback's file list actually differ from a real
build's (extra files, missing files, or both); (3) does `--allow-build`
reproduce a real published wheel's file list exactly, when one is
available to check against (`tests/fixtures/real-world-projects/*/*/
expected.json`). Automated as
[`scripts/compare_allow_build.py`](../../scripts/compare_allow_build.py)
-- run it by hand against a project directory, an sdist archive, or a
vendored fixture (`--fixture BACKEND/NAME`) whenever
`--allow-build`/`--no-build-isolation` or backend dispatch changes; see
its own docstring for usage. See the uv_build round below for a worked
result.

## Rounds

Results are split by backend, one file per group of rounds; the Policy
and Method above apply to all of them:

- [Setuptools rounds][set] -- setuptools (10 packages, 2026-08-28),
  setuptools license-form diversity (6 packages, 2026-09-03) and pipenv
  (1 package, 2026-09-03).
- [Hatchling and Poetry rounds][hp] -- Hatchling (10 packages,
  2026-08-28) and Poetry (11 packages, 2026-08-31).
- [Flit-core and PDM-backend round][fp] -- Flit-core and PDM-backend
  (8 packages, 2026-09-02).
- [allow-build validation][ab] -- the `--allow-build` rounds (summary
  below).

[set]: backend-file-discovery-validation-setuptools.md
[hp]: backend-file-discovery-validation-hatchling-poetry.md
[fp]: backend-file-discovery-validation-flit-pdm.md
[ab]: allow-build-validation.md

## `--allow-build` build-and-read validation (2026-09-15)

11 real `uv_build` packages plus one fixture per registered backend,
validated with `scripts/compare_allow_build.py`: `--allow-build`
reproduced the real published wheel exactly in every case tested; the
"never build when static discovery already succeeded" invariant held
for all four registered backends. Found and fixed one warning-wording
gap (`has_uv_build_backend_overrides()`) and one new failure shape
(a `module-name` override causing Hatchling's fallback to return zero
files, not just imprecise ones). See
[allow-build-validation.md](allow-build-validation.md) for the full
two rounds -- split into its own file once it pushed this document past
its size limit.
