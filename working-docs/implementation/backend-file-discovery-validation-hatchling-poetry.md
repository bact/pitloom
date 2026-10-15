---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Backend file discovery validation: Hatchling and Poetry rounds

See also:

- [Overview][main] (policy and method)
- [Setuptools rounds][set] (setuptools, license-form diversity, pipenv)
- [Flit-core and PDM-backend round][fp] (Flit-core, PDM-backend)
- [allow-build validation][ab] (`--allow-build` rounds)

[main]: backend-file-discovery-validation.md
[set]: backend-file-discovery-validation-setuptools.md
[fp]: backend-file-discovery-validation-flit-pdm.md
[ab]: allow-build-validation.md

## Hatchling (10 packages, 2026-08-28)

First systematic real-world validation of `_models_wheel_hatchling.py`'s
`discover()` (previously covered only by synthetic fixtures and by
being the pre-existing default for every project).

| Package | Version (tag) | Config style | Result |
| :--- | :--- | :--- | :--- |
| attrs | 26.1.0 | `hatch-vcs` dynamic version, `hatch-fancy-pypi-readme`, community org (python-attrs) | Perfect match |
| Pygments | 2.21.0 | Dynamic version, package_data-heavy (343 files, lexer/style modules), community org | Perfect match |
| redis-py | 8.1.0 | Dynamic version, PEP 639 SPDX-string `license` + legacy `License ::` classifier | Perfect match after fix -- see Findings |
| colorama | 0.4.6 | Static (non-dynamic) version, tiny/simple, PEP 639 SPDX-string `license` + legacy classifier | Perfect match after fix -- see Findings |
| wcwidth | 0.8.2 | Static version, solo maintainer, simplest case in the set | Perfect match |
| platformdirs | 4.11.4 | `hatch-vcs` dynamic version, tox-dev org, PEP 639 + legacy classifier | Perfect match after fix -- see Findings |
| Twisted | 26.4.0 | `hatch-fancy-pypi-readme`, ~20-year-old codebase, largest set here (889 files) | Perfect match |
| black | 26.5.1 | `hatch-vcs` dynamic version, PSF org, mypyc-compiled extensions | Perfect match (compiled `.so`s and VCS-generated `_black_version.py` correctly outside static scope) |
| httpx | 0.28.1 | `hatch-fancy-pypi-readme`, encode org, PEP 639 + legacy classifier | Perfect match after fix -- see Findings |
| virtualenv | 21.7.5 | `hatch-vcs` dynamic version, PyPA org, PEP 639 + legacy classifier | Perfect match after fix -- see Findings |

### Findings

- **File discovery itself: 5/5 perfect** on every package that got far
  enough to compare (attrs, Pygments, wcwidth, Twisted, black).
  - `_models_wheel_hatchling.py`'s pre-existing logic needed no changes.
- **`loom project` hard-crashed on 5/10** (colorama, platformdirs,
  httpx, virtualenv, redis-py).
  - Error: `Failed to parse project metadata: Setting "project.license"
    to an SPDX license expression is not compatible with 'License ::'
    classifiers`.
  - Source: [pyproject-metadata](https://github.com/pypa/pyproject-metadata)'s
    own strict PEP 639 validation in the shared, backend-agnostic
    metadata path (`src/pitloom/extract/project/pyproject.py`) -- not specific
    to Hatchling, and not something any of the setuptools packages
    in [the setuptools round](backend-file-discovery-validation-setuptools.md)
    happened to trigger.
  - Why it's common: real projects mid-PEP-639-migration routinely
    keep both the new SPDX `license` string and the legacy `License ::`
    classifier rather than deleting the classifier the same release.
    That turned out to be the *majority* case in this sample, not an
    edge case.
  - **Fixed**: `read_pyproject()` now catches this one specific, narrow
    validation error (`ConfigurationError` with `key ==
    "project.license"` and `"License ::"` in the message), logs a
    `WARNING:`, drops the redundant classifiers, and retries -- keeping
    the SPDX expression as authoritative (the newer, more specific PEP
    639 source). Any other `project.license` failure still raises
    unchanged.
  - See `_is_license_classifier_conflict()` and
    `_drop_redundant_license_classifiers()` in `project/pyproject.py`.
- **Environment gap, not a code issue**: httpx additionally failed
  Hatchling's own wheel-file discovery.
  - Error: `Unknown metadata hook: fancy-pypi-readme`, until the
    optional `hatch-fancy-pypi-readme` plugin was installed in the
    validation venv.
  - attrs and Twisted also declare the plugin but don't actually invoke
    the hook for file discovery, so they didn't surface the gap.
  - Already degraded gracefully (a `WARNING:` and an empty file list,
    not a crash) before the plugin was installed -- no code change
    needed, same shape as the `setuptools>=70` dev-venv gotcha in
    [setuptools-support.md](setuptools-support.md).

## Poetry (11 packages, 2026-08-31)

First systematic real-world validation of `_models_wheel_poetry.py`'s
`discover()` (previously covered only by synthetic fixtures). Candidate
packages were confirmed to actually declare
`build-backend = "poetry.core.masonry.api"` by downloading each sdist
(`pip download --no-deps --no-binary=:all:`) and reading its
`[build-system]` table directly -- several plausible-looking candidates
(httpie, trino, pendulum, typer, arrow, loguru, cattrs, dependency-injector,
copier, pyinfra, towncrier) were ruled out this way before cloning, because
they'd actually moved to setuptools, Hatchling, flit, pdm, uv-build, or
maturin.

| Package | Version (tag) | Config style | Result |
| :--- | :--- | :--- | :--- |
| cleo | 2.1.0 | `src/`-layout `packages = [{include="cleo", from="src"}]`, python-poetry org (Poetry's own CLI-framework dependency) | Perfect match |
| crashtest | 0.4.1 | Implicit auto-discovery (no `packages`/`include`/`exclude` at all), solo maintainer (sdispater, Poetry's original author), simplest/tiniest case (13 files) | Perfect match |
| poetry-core | 2.4.1 | Explicit `packages = [...]` list + `include` + `exclude`, python-poetry org -- the library this very module delegates to | Perfect match |
| tomlkit | 0.15.1 | Implicit auto-discovery + `include` for extra non-code files, python-poetry org | Perfect match |
| poethepoet | 0.48.0 | Implicit auto-discovery, zero `packages`/`include`/`exclude` config, solo maintainer (nat-n), console-script entry point | Perfect match |
| questionary | 2.1.1 | Implicit auto-discovery, small team (tmbo + maintainer), ships a `NOTICE` file alongside `LICENSE` | Perfect match |
| returns | 0.26.0 | Implicit auto-discovery, dry-python org, largest module count in the set that still uses implicit discovery (117 files) | Perfect match |
| rich | 15.0.0 | Implicit auto-discovery + explicit `include = ["rich/py.typed"]`, Textualize org, mature/widely-used | Perfect match |
| textual | 8.2.8 | Implicit auto-discovery + `include`/`exclude` (snapshot-test directory excluded), Textualize org, largest set overall (264 files) | Perfect match |
| hvac | 2.4.0 | Explicit `packages = [...]` list, community/org-backed (HashiCorp Vault Python client) | Perfect match |
| poetry-plugin-export | 1.10.0 | Explicit `packages` + `include` + `exclude`, python-poetry org's own official plugin, smallest set (5 files) | Perfect match |

### Findings

- **11/11 perfect matches, no code changes needed.**
  - Every config style in the diversity matrix resolved to exactly the
    wheel's real file set: implicit auto-discovery, explicit `packages
    = [...]` lists, `src/`-layout `{include=..., from=...}`, and
    explicit `include`/`exclude`.
  - `wheel - project` was dist-info files only in every case;
    `project - wheel` was empty in every case.
  - No `WARNING:` about discovery failing or falling back ever fired
    across all 22 `loom` invocations (11 `project` + 11 `wheel`),
    confirming the dispatch-table registration in `_models_wheel.py`
    and poetry-core delegation both worked cleanly for every sample.
- **poethepoet tripped the same PEP 639 `license`/`License ::`
  classifier conflict** documented under Hatchling above.
  - `WARNING:` logged, redundant classifiers dropped, SPDX expression
    kept.
  - This is the pre-existing, backend-agnostic `read_pyproject()` fix
    from that earlier round doing its job again -- not a new gap, and
    not specific to Poetry.
- **rich's `pyproject.toml` triggered poetry-core's own deprecation
  notice**: `The "poetry.dev-dependencies" section is deprecated...`,
  printed directly by poetry-core during `Factory().create_poetry()`.
  - Harmless and expected: `discover()` only reads
    `find_files_to_add()` output, never `dev-dependencies`, so this
    doesn't affect the file list and needed no handling.
- **No environment gaps encountered** -- unlike Hatchling's optional
  metadata-hook plugins, none of the 11 packages required anything
  beyond `poetry-core` itself (already the sole runtime dependency this
  module needs) to resolve correctly.
- **Conclusion**: `_models_wheel_poetry.py` is production-ready as
  written; this validation round required no changes to it.
