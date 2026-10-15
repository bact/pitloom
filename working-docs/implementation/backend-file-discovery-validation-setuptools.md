---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Backend file discovery validation: setuptools rounds

See also:

- [Overview][main] (policy and method)
- [Hatchling and Poetry rounds][hp] (Hatchling, Poetry)
- [Flit-core and PDM-backend round][fp] (Flit-core, PDM-backend)
- [allow-build validation][ab] (`--allow-build` rounds)

[main]: backend-file-discovery-validation.md
[hp]: backend-file-discovery-validation-hatchling-poetry.md
[fp]: backend-file-discovery-validation-flit-pdm.md
[ab]: allow-build-validation.md

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

## Setuptools license-form diversity (6 packages, 2026-09-03)

Extends the setuptools fixture set specifically for license-declaration
diversity -- PEP 621 vs. PEP 639 vs. legacy classifier-only forms, and
projects old enough to mix `pyproject.toml`/`setup.cfg`/`setup.py`
non-trivially, per the multi-file precedence contract documented in
`pitloom.extract.project.setuptools`' own module docstring
(`pyproject.toml [project]` > `setup.cfg` > `setup.py`) and
`_models_wheel_setuptools.py`'s (`setup.cfg` applied first, then
`pyproject.toml` on top).

| Package | Version | Config style | Result |
| :--- | :--- | :--- | :--- | :--- |
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
`tests/extract/project/test_pyproject_license.py`) documenting the equivalence.

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
    literals, which `setuptools_py.py`'s AST scan deliberately never
    resolves (documented scope boundary, same as any other
    unresolvable dynamic value). `read_project()` now raises
    `FileNotFoundError` for it instead of silently succeeding with
    empty metadata -- loud-and-correct beats quiet-and-wrong.
  - See `test_read_project_falls_back_past_build_system_only_pyproject`/
    `test_read_project_build_system_only_pyproject_no_setuptools_fallback`
    in `tests/extract/project/test_project.py`.
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
    `_extract_dynamic_version()` (`pyproject_dynamic.py`) only checked
    `[tool.hatch].version.path` plus a generic
    `__about__.py`/`__version__.py` file-candidate scan -- neither
    covers this setuptools-specific directive.
  - **Fixed**: added `_extract_setuptools_dynamic_version()` to
    `pyproject_dynamic.py`, checked first, delegating to
    `setuptools_cfg.py`'s existing `_resolve_cfg_attr_directive()`/
    `_resolve_cfg_version_file_directive()` -- the exact same AST-scan/
    file-read logic `read_setuptools()` already uses for `setup.cfg`'s
    `version = attr: ...`, not a second implementation. Falls through
    to the Hatchling/generic-candidate checks unchanged when the
    directive is absent or doesn't resolve. (`pyproject.py` was also
    split at this point -- all PEP 621 `dynamic` field resolution now
    lives in `pyproject_dynamic.py`, keeping the parent module from
    growing into a dumping ground.)
  - See `test_extract_dynamic_version_setuptools_dynamic_attr`/`_file`/
    `_missing_falls_through` in `tests/extract/project/test_pyproject_dynamic.py`.
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
