---
Created: 2026-10-15
Last-Modified: 2026-10-24
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Backend file discovery validation: Flit-core and PDM-backend round

See also:

- [Overview][main] (policy and method)
- [Setuptools rounds][set] (setuptools, license-form diversity, pipenv)
- [Hatchling and Poetry rounds][hp] (Hatchling, Poetry)
- [allow-build validation][ab] (`--allow-build` rounds)

[main]: backend-file-discovery-validation.md
[set]: backend-file-discovery-validation-setuptools.md
[hp]: backend-file-discovery-validation-hatchling-poetry.md
[ab]: allow-build-validation.md

## Flit-core and PDM-backend (8 packages, 2026-09-02)

First systematic real-world validation of `_models_wheel_flit.py`'s and
`_models_wheel_pdm.py`'s `discover()`, alongside their metadata-side
siblings `pitloom.extract.project.flit`/`pitloom.extract.project.pdm`. Vendored as
persistent fixtures (see
[Policy](backend-file-discovery-validation.md#policy)) rather than cloned
and discarded -- see
[`tests/fixtures/real-world-projects/README.md`](../../tests/fixtures/real-world-projects/README.md)
for the fixture table, method, and per-fixture `known_gaps`.

| Package | Version | Backend | Config style | Result |
| :--- | :--- | :--- | :--- | :--- |
| tiangolo/typer | 0.27.2 | PDM | PEP 621, `pdm-backend` build requirement | Perfect match |
| pdm-project/pdm-backend | 2.4.9 | PDM | Self-hosting (`backend-path = ["src"]`, `build-backend = "pdm.backend.intree"`) | Perfect match |
| pypa/flit | 4.0.2 | Flit | Self-hosting, PEP 621-native | Perfect match |
| hukkin/tomli | 2.4.1 | Flit | PEP 621-native, mypyc-compiled extension modules published in the wheel | Perfect match except mypyc `.so` files (known gap, see below) |
| python-poetry/poetry-core | 2.4.1 | Poetry | Self-hosting (persists the case already validated in the [Poetry round](backend-file-discovery-validation-hatchling-poetry.md)) | Perfect match |
| PyCQA/pydocstyle | 6.3.0 | Poetry | PEP 621 + `[tool.poetry]` | Perfect match |
| pytest-dev/pytest-asyncio | 1.4.0 | setuptools | PEP 621, plugin-shaped package (pytest entry points) | Perfect match |
| psf/requests | 2.34.2 | setuptools | Legacy `[project.license] = {text = ...}` TOML-table form, deprecated `tool.setuptools.license-files`, legacy `License ::` classifier -- three overlapping PEP 621->639 migration states at once | Perfect match after fix -- see Findings |

Two Hatchling packages (psf/black, encode/httpx) and two `uv_build`
packages (langfuse/langfuse-python, rendercv/rendercv) were also
vendored in the same pass as regression/forward-looking fixtures, not
part of this round's PDM/Flit validation count -- see the fixtures
README for their own notes.

### Findings

- **8/8 perfect matches** against every vendored fixture's real wheel
  file list -- self-hosting, plain PEP 621, a compiled-extension
  package all resolved to exactly the real wheel's file set
  (`.dist-info/*` excluded, as every discoverer excludes it).
  - This is a statement about the *file-list-diffing* validation
    method specifically (`wheel - project` / `project - wheel`, see
    [Method](backend-file-discovery-validation.md#method))
    -- it does not mean no further code changes were needed. Three more real bugs (two code-execution risks, two
    disk-write side effects) surfaced afterward via a code-review pass
    over this same PDM/Flit-core work -- see the three findings below,
    added after this round's initial pass.
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
  - **Revised (PR #300)**: outside pytest the banners still reached
    stderr as untagged multi-line text (Python's default warning
    display). `discover()` now records them with
    `warnings.catch_warnings(record=True)` and logs each as one `DEBUG`
    line; the `pyproject.toml` ignore entry is gone. Regression test:
    `test_setuptools_banners_are_debug_lines` in
    `tests/test_setuptools_default_backend_surfaces.py` (a real
    `loom --debug project` process).
  - **Revised (#356)**: the manifest step
    (`include_package_data`) still wrote bare lines on stderr
    (`warning: no files found matching '*.js'`): `distutils.log` is the
    root logger, which with no handler falls to `logging.lastResort`, and
    `distutils.text_file` writes to `sys.stderr` itself. Both banners and
    these lines now go through one context manager,
    `core/_models_wheel_setuptools_relay.py`: it captures this thread's
    `sys.stderr` writes (`extract/stderr_capture.py`, promoted from
    `extract/ai_model/` for this second caller; 65,536 characters kept, the rest
    counted in a `DEBUG:` line) and relays each non-blank line as one
    escaped record, `WARNING:` for an `error:` line and `DEBUG:` otherwise.
    Capturing stderr, not filtering the root logger, also catches the
    direct writes and the records of `setuptools.config.*` loggers. A host
    that configures root logging itself still gets the `distutils.log`
    records through its own handlers, as Pitloom's own records reach them.
    Regression tests: `tests/core/models_wheel/test_models_wheel_setuptools_relay.py`,
    `test_manifest_step_lines_are_debug_lines` (every surface, a real
    process each) and the Git URL case in
    `tests/extract/remote/test_git_http_e2e.py`.
- **PDM discovery wrote to disk in two more cases**, found by a
  code-review pass over this round's own PDM/Flit work, not by the
  fixture-diffing method above (neither vendored fixture triggers
  either case).
  - `[tool.pdm.version] source = "scm"` with a `write_to` option (a
    common, documented PDM idiom for auto-embedding a `_version.py`)
    made `discover()` write the resolved version to
    `.pdm-build/<write_to>` via pdm-backend's own
    `DynamicVersionBuildHook.pdm_build_initialize()`. **Fixed**: stop
    calling `builder.initialize(context)` at all -- file discovery
    never needs the resolved version, so skipping it changes nothing
    about the returned file set.
  - The base `Builder.get_files()`'s `_collect_build_files()`
    unconditionally globs `context.build_dir` -- pointing it at the
    project's real `.pdm-build/` meant a directory left over from a
    prior real `pdm build` (normally only gitignored, not cleaned up)
    leaked its stale contents into the returned file list. **Fixed**:
    `build_dir` now points at a path guaranteed never to exist on disk.
  - See `test_discover_never_writes_scm_version_to_disk` and
    `test_discover_ignores_stale_pdm_build_directory` in
    `tests/core/models_wheel/test_models_wheel_pdm.py`; both confirmed
    to fail without their respective fix and pass with it.
- **Flit metadata/discovery could execute project code to resolve a
  non-literal dynamic field**, also found by code review, in two
  places:
  - `pitloom.core._models_wheel_flit.discover()`'s
    `[tool.flit.external-data]` handling called flit-core's own
    `make_metadata()`, which falls back to *importing* (executing) the
    target module whenever a dynamic `version`/`description` isn't an
    AST-resolvable literal (e.g. computed by a function call).
  - `pitloom.extract.project.flit.resolve_flit_dynamic_metadata()` had the
    identical exposure via the same `make_metadata()` call, for the
    same reason.
  - **Fixed**: both now call flit-core's
    `get_docstring_and_version_via_ast()` directly and stop there --
    never falling back to import -- matching the same no-execution
    stance `pitloom.extract.project.setuptools` already takes for `setup.py`.
    A dynamic field that isn't AST-resolvable is left unresolved (with
    a `WARNING:` from the discovery side) rather than resolved by
    running project code.
  - Confirmed via a live marker-file reproduction (the module's
    top-level code wrote a marker file when imported): the marker was
    written by the old code and never written after the fix. See
    `test_discover_external_data_never_executes_project_code`
    (`tests/core/models_wheel/test_models_wheel_flit.py`) and
    `test_resolve_flit_dynamic_metadata_never_executes_project_code`
    (`tests/extract/project/test_flit.py`).
