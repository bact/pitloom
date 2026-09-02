---
Created: 2026-08-28
Last-Modified: 2026-09-03
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
file discovery" section for the backends still to come.

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

Starting with the Flit-core/PDM-backend round below, these real-world
packages are vendored (as sdist archives) under
`tests/fixtures/real-world-projects/` and checked on every test run via
`tests/core/models_wheel/test_models_wheel_real_world.py`, rather than
cloned fresh and discarded per validation pass -- see that directory's
own README for the fixture format. The Setuptools/Hatchling/Poetry
rounds below predate that and are recorded here as a point-in-time
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

## Setuptools (10 packages, 2026-08-28)

| Package | Version (tag) | Config style | Result |
| :--- | :--- | :--- | :--- |
| six | 1.17.0 | No `pyproject.toml`, imperative `setup.py` only | Correctly out of scope |
| certifi | 2026.7.22 | `pyproject.toml` with `[build-system]` only, imperative `setup.py` | Correctly out of scope |
| requests | 2.34.2 | Modern PEP 621, `[tool.setuptools.packages.find] where=["src"]`, no `setup.cfg` | Perfect match |
| python-dateutil | 2.9.0.post0 | `setup.cfg`-primary + `[tool.setuptools.dynamic]` merge, `setuptools_scm` | Correct -- gaps are `setuptools_scm`/custom-build-generated files only |
| Django | 6.1 | PEP 621, `packages.find include=["django*"]`, PEP 639 SPDX-string `license` | Perfect match (3686/3686 files) |
| boto3 | 1.43.81 | No `pyproject.toml`; `setup.cfg` present but empty of packaging config; imperative `setup.py` (`find_packages()`, `package_data={...}` as Python literals) | Partial result, now warned -- see Findings |
| PyYAML | 6.0.3 | Custom `build-backend = "_pyyaml_pep517"` wrapper (not a recognized alias); imperative `setup.py` | Correctly out of scope (conservative, exact-match backend detection) |
| cffi | 2.1.1 | Modern PEP 621, `setuptools>=77.0.3` floor, no `[tool.setuptools]` at all (zero-config), `src/cffi` + `src/c` (C sources, no `__init__.py`) | Over-inclusion, now warned -- see Findings |
| Markdown | 3.10.3 | Modern PEP 621, explicit `[tool.setuptools] packages = ['markdown', 'markdown.extensions']` list (not `find:`), PEP 639 SPDX-string `license` | Perfect match |
| tzdata | 2026.3 | Legacy `setup.cfg` (`[options] packages = tzdata`, `package_dir = src`), `version = file: VERSION`, `include_package_data = True`, PSF org, package_data-heavy (627 files) | Perfect match |

### Findings

- **`setuptools<70` gives materially different (wrong) results** than
  this project's own `pyproject.toml` floor (`setuptools>=70`).
  - Confirmed by bisecting in scratch venvs.
  - Under 65.5.0, requests silently lost its `py.typed` marker (the
    implicit `include_package_data=True` PEP 621 default resolves
    differently).
  - Under 65.5.0, Django's PEP 639 string-form `license` was rejected
    outright (pre-70's config schema only accepted
    `{file=...}`/`{text=...}` dicts).
  - Takeaway: `discover()`'s results are only as good as the
    `setuptools` version actually installed at runtime.
- **Doomed-Hatchling-attempt skip was too narrow** (certifi).
  - Old check: "no `pyproject.toml` file at all".
  - Missed case: `pyproject.toml` exists but has no `[project]` table.
  - Both are guaranteed to fail Hatchling's own discovery the same way.
  - **Fixed**: widened the check in `_models_wheel.py`'s
    `_discover_included_files()` to `pyproject_data is None or
    "project" not in pyproject_data`.
- **boto3 -- silent partial result.**
  - A project can have a `setup.cfg` that exists but declares no
    packaging config (only `[options.extras_require]`, say), while the
    real packages/package_data live in an imperative `setup.py` call.
  - Because *some* `setup.cfg` makes `_load_distribution()` treat the
    project as "resolvable", zero-config auto-discovery correctly finds
    the `.py` modules.
  - But the imperative `package_data` dict is invisible to static
    analysis.
  - For boto3 specifically this drops all ~23 `boto3/data/**/*.json`
    files (the AWS API resource definitions -- most of the package's
    actual content).
- **cffi -- over-inclusion.**
  - Zero-config auto-discovery treats `src/c` (a directory of C
    sources with no `__init__.py`, used only to compile
    `_cffi_backend`) as an implicit namespace package, because it
    contains one stray `.py` file.
  - Static analysis reports 10 spurious `.c`/`.h` files that never
    reach the real wheel.
  - Why: cffi's actual `setup.py` explicitly overrides
    `packages=['cffi']` only -- code we don't execute.
- **Both fixed the same way.**
  - Neither case is reliably resolvable without executing `setup.py`
    (out of scope by design -- see
    [sbom-lifecycle-stages.md](sbom-lifecycle-stages.md)).
  - Rather than two special-case heuristics, `discover()` now
    AST-scans `setup.py` (when present) for any of `packages`,
    `py_modules`, `package_dir`, `package_data`,
    `include_package_data`, `exclude_package_data`, `data_files`
    passed to the `setup()` call -- regardless of whether the value
    itself is a resolvable literal (`find_packages()` calls included).
  - If any are found, `discover()` still returns its
    statically-resolved file list (often still correct for the `.py`
    modules, and strictly better than returning nothing), but with a
    `WARNING:` that it may be incomplete or wrong.
  - See `_setup_py_packaging_kwargs()` /
    `_warn_if_setup_py_overrides_packaging()` in
    `_models_wheel_setuptools.py`.
  - Verified against all 10 packages in the table above: fires only
    for boto3 and cffi, silent for the other 8 (including
    python-dateutil and requests, whose `setup.py` files exist but pass
    no packaging-relevant arguments).

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
    metadata path (`src/pitloom/extract/_pyproject.py`) -- not specific
    to Hatchling, and not something any of the setuptools packages
    above happened to trigger.
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
    `_drop_redundant_license_classifiers()` in `_pyproject.py`.
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

## Flit-core and PDM-backend (8 packages, 2026-09-02)

First systematic real-world validation of `_models_wheel_flit.py`'s and
`_models_wheel_pdm.py`'s `discover()`, alongside their metadata-side
siblings `pitloom.extract._flit`/`pitloom.extract._pdm`. Vendored as
persistent fixtures (see the Policy section above) rather than cloned
and discarded -- see
[`tests/fixtures/real-world-projects/README.md`](../../tests/fixtures/real-world-projects/README.md)
for the fixture table, method, and per-fixture `known_gaps`.

| Package | Version | Backend | Config style | Result |
| :--- | :--- | :--- | :--- | :--- |
| tiangolo/typer | 0.27.2 | PDM | PEP 621, `pdm-backend` build requirement | Perfect match |
| pdm-project/pdm-backend | 2.4.9 | PDM | Self-hosting (`backend-path = ["src"]`, `build-backend = "pdm.backend.intree"`) | Perfect match |
| pypa/flit | 4.0.2 | Flit | Self-hosting, PEP 621-native | Perfect match |
| hukkin/tomli | 2.4.1 | Flit | PEP 621-native, mypyc-compiled extension modules published in the wheel | Perfect match except mypyc `.so` files (known gap, see below) |
| python-poetry/poetry-core | 2.4.1 | Poetry | Self-hosting (persists the case already validated in the Poetry round above) | Perfect match |
| PyCQA/pydocstyle | 6.3.0 | Poetry | PEP 621 + `[tool.poetry]` | Perfect match |
| pytest-dev/pytest-asyncio | 1.4.0 | setuptools | PEP 621, plugin-shaped package (pytest entry points) | Perfect match |
| psf/requests | 2.34.2 | setuptools | Legacy `[project.license] = {text = ...}` TOML-table form, deprecated `tool.setuptools.license-files`, legacy `License ::` classifier -- three overlapping PEP 621->639 migration states at once | Perfect match after fix -- see Findings |

Two Hatchling packages (psf/black, encode/httpx) and two `uv_build`
packages (langfuse/langfuse-python, rendercv/rendercv) were also
vendored in the same pass as regression/forward-looking fixtures, not
part of this round's PDM/Flit validation count -- see the fixtures
README for their own notes.

### Findings

- **8/8 perfect matches.**
  - Every config style available in a real PDM/Flit-core package --
    self-hosting, plain PEP 621, a compiled-extension package --
    resolved to exactly the real wheel's file set (`.dist-info/*`
    excluded, as every discoverer excludes it).
  - Neither `discover()` needed a code change after the two
    implementation-time findings below were addressed.
  - The requests case below needed a test-suite-only fix, not a
    `discover()` change.
- **`pdm.backend.wheel.WheelBuilder.get_files()` writes to disk as a
  side effect.**
  - `_get_metadata_files()` unconditionally calls
    `context.ensure_build_dir()`, which creates `.pdm-build/` and
    writes a `.gitignore` into it, then writes
    `METADATA`/`WHEEL`/`RECORD` there too.
  - That's a real build-time side effect the "static-config read,
    never a build" contract (`sbom-lifecycle-stages.md`) forbids.
  - **Fixed**: call the base `Builder.get_files()` (still dispatching
    to `WheelBuilder`'s own overridden `_collect_files()` for
    `src/`-layout prefix-stripping) plus `_get_wheel_data()` directly,
    skipping `_get_metadata_files()` entirely.
  - See `_models_wheel_pdm.py`'s docstring.
- **PDM-backend's own package auto-discovery is cwd-relative, not
  `Builder.location`-relative.**
  - `pdm.backend.base._find_top_packages()` calls `os.listdir(".")`,
    ignoring the `Builder`'s own `location`.
  - Confirmed by constructing a `Builder` from a non-cwd path and
    observing zero packages discovered.
  - **Fixed**: PDM-backend added to `_WRITER_BACKENDS` in
    `_models_wheel.py`, joining setuptools as the second backend whose
    `discover()` needs a process-wide `os.chdir()` for the duration of
    its call.
- **tomli's mypyc-compiled `.so` files are a documented known gap.**
  - Same category `black`'s Hatchling fixture already established.
  - Files a separate CI compilation step adds to the published wheel
    that never exist as source files in the sdist -- outside what any
    static rescan can see in principle.
- **requests' three legacy license/classifier forms only fail under
  pytest's own strict-warnings config, never in real usage.**
  - setuptools *warns* (via `SetuptoolsDeprecationWarning`) on the
    table-form `project.license`, the deprecated
    `tool.setuptools.license-files` key, and the `License ::`
    classifier during `apply_configuration()` -- it never raises
    outside a test run.
  - Confirmed by calling `discover()` directly (no pytest involved): it
    returns the correct 20-file result every time.
  - Root cause: Pitloom's own `filterwarnings = ["error"]` (OpenSSF
    `warnings_strict`) turns these three warnings into a hard
    `discover()` failure during the test suite specifically -- not a
    `_models_wheel_setuptools.py` bug at all.
  - **Fixed**: scoped `ignore::setuptools.warnings.SetuptoolsDeprecationWarning:
    setuptools.config._apply_pyprojecttoml` entry in `pyproject.toml`'s
    `filterwarnings` (category+module-scoped, not message-scoped, since
    the three distinct legacy forms share this one category/module and
    a real-world project may combine them in yet other ways).
  - Regression test: `test_discover_succeeds_on_legacy_table_form_license`
    in `tests/core/models_wheel/test_models_wheel_setuptools.py`,
    covering all three forms in one synthetic fixture. Confirmed to
    fail without the filter and pass with it.

## Setuptools license-form diversity (6 packages, 2026-09-03)

Extends the setuptools fixture set specifically for license-declaration
diversity -- PEP 621 vs. PEP 639 vs. legacy classifier-only forms, and
projects old enough to mix `pyproject.toml`/`setup.cfg`/`setup.py`
non-trivially, per the multi-file precedence contract documented in
`pitloom.extract._setuptools`' own module docstring
(`pyproject.toml [project]` > `setup.cfg` > `setup.py`) and
`_models_wheel_setuptools.py`'s (`setup.cfg` applied first, then
`pyproject.toml` on top).

| Package | Version | Config style | Result |
| :--- | :--- | :--- | :--- |
| tkem/cachetools | 7.1.8 | Strict PEP 639 (`license = "MIT"` + `license-files`), `setuptools-scm` dynamic version | Perfect match |
| PyCQA/flake8 | 7.3.0 | No `pyproject.toml` at all -- `setup.cfg [metadata]` is the sole source (`version = attr:`, `src/`-layout `where =`), bare `setup.py` shim | Perfect match |
| pallets/markupsafe | 3.0.3 | PEP 639 + `license-files`, real C accelerator (`_speedups.c`, compiled `build_ext`) | Perfect match except the C source/compiled extension (known gap) |
| numpy/numpydoc | 1.10.0 | License via `License ::` classifier only (no `license` field at all), `pyproject.toml` + `setup.cfg` (egg_info-only) side by side | Perfect match |
| yaml/pyyaml | 6.0.3 | Legacy imperative `setup.py` referencing module-level constants (`setup(name=NAME, ...)`, not literals), custom `build-backend = "_pyyaml_pep517"` wrapper | Correctly out of scope for both file discovery and metadata extraction -- see Findings |
| python-trio/sniffio | 1.3.1 | Compound license expression (`license = {text = "MIT OR Apache-2.0"}`), `setuptools_scm` dynamic version | Perfect match |
| EFS-OpenSource/calibration-framework (PyPI `netcal`) | 1.4.0 | `[project.license]` as its own TOML table-header section (a third syntactic variant, alongside inline-table and dotted-key forms), `[tool.setuptools.dynamic] version = {attr = "netcal.__version__"}` | Perfect match after fix -- see Findings |

Also added `tests/fixtures/projects/sampleproject-setuptools-license-dotted/`,
a small synthetic fixture (not from a real sdist -- modeled on
apple/tree-sitter-pkl's real `pyproject.toml`, which isn't published on
PyPI) covering PEP 621's TOML dotted-key license form (`license.text =
"..."`). Confirmed via `tomllib` that it parses to an identical dict as
the inline-table form (`license = {text = "..."}`) -- no code-level
handling needed either way, just a regression test
(`test_read_pyproject_license_toml_dotted_key_matches_inline_table` in
`tests/extract/test_pyproject.py`) documenting the equivalence.

### Findings

- **markupsafe's C accelerator (`_speedups.c`/`.cpython-*.so`) is a
  known gap.**
  - Same category as `black`/`tomli`'s mypyc extensions.
  - `discover()` only models `build_py`'s file-copying, never runs
    `build_ext`, so neither the C source nor the compiled extension is
    statically reachable via `package_data`/manifest analysis.
  - Contrast: `_speedups.pyi`, a plain type stub, *is* discovered
    normally.
- **PyYAML surfaced a real `read_project()` metadata-extraction bug**,
  found while vendoring this fixture -- not just the already-documented
  file-discovery/backend-detection "correctly out of scope" case from
  the original setuptools round.
  - Bug: `read_project()` (`src/pitloom/extract/project.py`) dispatched
    on `pyproject.toml`'s mere *existence*, never checking whether it
    actually had a usable `[project]` table before committing to
    `read_pyproject()`'s path.
  - Trigger shape: `pyproject.toml` present but `[build-system]`-only
    (no `[project]`, no `[tool.poetry]`), with real metadata living in
    `setup.py`/`setup.cfg` -- exactly PyYAML's case.
  - Effect: `read_pyproject()`'s poetry-or-bare-stub fallback ran
    instead of `read_setuptools()`, silently returning an **empty,
    nameless, versionless `ProjectMetadata`** for `loom project`
    against any project shaped this way (confirmed: `name=''`,
    `version=None`).
  - Why this wasn't already caught: the original validation round's
    "PyYAML: Correctly out of scope" finding was about *file discovery*
    only (`_models_wheel.py` already has its own
    `has_resolvable_pyproject_config()` check for this exact shape) --
    metadata extraction had no equivalent guard at all until now.
  - **Fixed**: `read_project()` now falls back to `read_setuptools()`
    when `read_pyproject()` resolves no name and `setup.cfg`/`setup.py`
    exist, with a `WARNING:` (never silent).
  - Remaining limit: PyYAML itself still can't be fully resolved even
    with this fix -- its `setup.py` passes `setup(name=NAME,
    version=VERSION, ...)` referencing module-level constants, not
    literals, which `_setuptools_py.py`'s AST scan deliberately never
    resolves (documented scope boundary, same as any other
    unresolvable dynamic value). `read_project()` now raises
    `FileNotFoundError` for it instead of silently succeeding with
    empty metadata -- loud-and-correct beats quiet-and-wrong.
  - See `test_read_project_falls_back_past_build_system_only_pyproject`/
    `test_read_project_build_system_only_pyproject_no_setuptools_fallback`
    in `tests/extract/test_project.py`.
- **netcal surfaced a second real metadata-extraction gap.**
  - Directive: `[tool.setuptools.dynamic] version = {attr =
    "netcal.__version__"}` -- setuptools' own dynamic-version
    directive.
  - Symptom: resolved to `version=None` even though netcal's
    `pyproject.toml` has a normal, complete `[project]` table (so
    `read_project()` correctly dispatches to `read_pyproject()`, unlike
    PyYAML's case above).
  - Why: `pyproject-metadata`'s `StandardMetadata` is backend-agnostic
    and has no concept of `[tool.setuptools.dynamic]` at all, and
    `_extract_dynamic_version()` (`_pyproject_dynamic.py`) only checked
    `[tool.hatch].version.path` plus a generic
    `__about__.py`/`__version__.py` file-candidate scan -- neither
    covers this setuptools-specific directive.
  - **Fixed**: added `_extract_setuptools_dynamic_version()` to
    `_pyproject_dynamic.py`, checked first, delegating to
    `_setuptools_cfg.py`'s existing `_resolve_cfg_attr_directive()`/
    `_resolve_cfg_version_file_directive()` -- the exact same AST-scan/
    file-read logic `read_setuptools()` already uses for `setup.cfg`'s
    `version = attr: ...`, not a second implementation. Falls through
    to the Hatchling/generic-candidate checks unchanged when the
    directive is absent or doesn't resolve. (`_pyproject.py` was also
    split at this point -- all PEP 621 `dynamic` field resolution now
    lives in `_pyproject_dynamic.py`, keeping the parent module from
    growing into a dumping ground.)
  - See `test_extract_dynamic_version_setuptools_dynamic_attr`/`_file`/
    `_missing_falls_through` in `tests/extract/test_pyproject.py`.
- **Every other license style in this round needed no code changes.**
  - Covered: PEP 639 strings, compound expressions, classifier-only, a
    table-header `[project.license]` section, `setuptools_scm`-driven
    dynamic versions.
  - `numpydoc`'s classifier-only license, `sniffio`'s compound `MIT OR
    Apache-2.0` expression, netcal's `[project.license]` table-header
    section, and `cachetools`'/`sniffio`'s `setuptools_scm`
    dynamic-version resolution all already worked correctly through the
    existing generic `StandardMetadata.from_pyproject()`/`discover()`
    paths.

## pipenv (1 package, 2026-09-03)

Large, mature, real-world setuptools package -- also the reference
implementation for PEP 751 (`pipenv/utils/pylock.py`), though pipenv's
own packaging doesn't use PEP 751 for itself.

| Package | Version | Config style | Result |
| :--- | :--- | :--- | :--- |
| pypa/pipenv | 2026.8.0 | `license = {text = "MIT License (MIT)"}`, 4.5MB sdist (vendors its own dependencies under `pipenv/vendor/`/`pipenv/patched/`) | Perfect match after fix -- see Findings |

### Findings

- **`license = {text = "MIT License (MIT)"}` was fuzzy-matched to the
  wrong SPDX ID.**
  - `read_project()` resolved `license_name = "AML"` -- not MIT, not
    even a plausible near-miss.
  - Why: `"MIT License (MIT)"` is a short *label* (18 characters), not
    real license *text*. `detect_license_from_text()`
    (`_license.py`) ran `licenseid`'s similarity matcher on it anyway,
    with no minimum-length guard, and a short string can spuriously
    score above the 0.85 threshold against an equally short reference
    text in the database.
  - **Fixed**: added `_MIN_LICENSE_TEXT_LENGTH = 100` to
    `detect_license_from_text()` -- text shorter than that returns
    `None` immediately, before any fuzzy match is attempted. Every real
    SPDX license body is far longer than 100 characters (0BSD, the
    shortest, is ~500), so this only ever excludes non-license-body
    input like pipenv's label.
  - After the fix: `read_project()` now falls back to the raw declared
    string `"MIT License (MIT)"` as `license_name` -- not a clean SPDX
    ID, but honest and traceable, instead of confidently wrong.
  - See `test_detect_license_from_text_rejects_short_label` in
    `tests/assemble/test_license_normalization.py`.
