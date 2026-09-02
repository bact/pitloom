---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Real-world project fixtures

See also: [../real_world.py](../real_world.py) (the shared
sdist-extraction/manifest helper every test in this file uses);
[../projects/README.md](../projects/README.md) (small, synthetic,
single-behavior fixtures -- `include`/`exclude` globs, `.gitignore`
handling, src-layout -- covered there instead, since a real package's
sdist rarely isolates one config style at a time the way a hand-written
fixture can);
[`../../../working-docs/implementation/backend-file-discovery-validation.md`](../../../working-docs/implementation/backend-file-discovery-validation.md)
for the validation policy and method these fixtures satisfy;
[`../../core/models_wheel/test_models_wheel_real_world.py`](../../core/models_wheel/test_models_wheel_real_world.py)
for the regression test that runs against every fixture here.

## What's here

Each `<backend>/<project>-<version>/` directory holds:

- The project's real, published **sdist archive**, downloaded once from
  PyPI and committed as-is (e.g. `httpx-0.28.1.tar.gz`) -- not extracted.
  A test extracts it into a temp directory on demand
  (`tests/fixtures/real_world.py`'s `extract_sdist()`), so nothing here
  needs re-downloading to run the test suite.
- An `expected.json` sidecar recording the project's source URL, pinned
  PyPI version, license, declared build backend, and the **real
  published wheel's file list** (`wheel_files`) -- captured once, at
  fixture-creation time, by separately downloading that version's wheel,
  reading its file list, and discarding the wheel itself (never
  committed, to avoid binary bloat; a wheel isn't needed at test time,
  only the file list it implies).
- Optionally, `known_gaps` (a list of `wheel_files` entries, or the
  literal string `"ALL"`) with a `known_gaps_note` explaining files a
  backend's `discover()` is expected *not* to reproduce -- a compiled
  extension that doesn't exist as a source file until a real build
  compiles it, a VCS-generated version file, or (for `"ALL"`) an
  environment dependency the discovery module degrades gracefully
  around rather than crashing on. These are documented exceptions, not
  silently-ignored failures -- each one names why.

No `.git` history, no CI configs, no dev tooling -- just the sdist
archive a real `pip install <pkg>==<version>` would download, which is
also all `discover()` itself ever needs.

This directory (like the rest of `tests/fixtures/`) is excluded from
Pitloom's own published sdist (`pyproject.toml`'s
`[tool.hatch.build.targets.sdist]`), to avoid redistributing vendored
third-party source in a release artifact. `tests/fixtures/real_world.py`'s
`sdist_available()` lets
[`test_models_wheel_real_world.py`](../../core/models_wheel/test_models_wheel_real_world.py)
skip cleanly (not error) when a fixture's archive isn't present -- e.g.
a downstream packager running the test suite from a rebuilt,
fixture-stripped sdist.

## Method

For each project: look up its exact PyPI release URL via
`https://pypi.org/pypi/<pkg>/<version>/json` (no `pip download`/build
backend invocation needed -- a raw HTTP GET of the published artifact),
save the sdist, separately fetch the wheel to enumerate its files, then
discard the wheel. Before vendoring a candidate, confirm its declared
build backend by checking `[build-system] build-backend` in the
downloaded sdist itself -- a plausible-looking candidate can have moved
to a different backend since, or (as with a compiled/Rust project)
declare a Track B backend like `maturin` despite superficially looking
like a `uv_build` case.

## Fixtures

| Backend | Project | Version | License | Notes |
| :--- | :--- | :--- | :--- | :--- |
| Flit | [pypa/flit](https://github.com/pypa/flit) | 4.0.2 | BSD-3-Clause | Flit's own package (self-hosting case) -- perfect match, no known gaps. |
| Flit | [hukkin/tomli](https://github.com/hukkin/tomli) | 2.4.1 | MIT | Ships mypyc-compiled `.so` extensions built by a separate CI step outside flit-core itself -- see `known_gaps`. |
| Hatchling | [psf/black](https://github.com/psf/black) | 26.5.1 | MIT | mypyc-compiled extensions plus a `hatch-vcs`-generated `_black_version.py` -- see `known_gaps`. |
| Hatchling | [encode/httpx](https://github.com/encode/httpx) | 0.28.1 | BSD-3-Clause | Requires the optional `hatch-fancy-pypi-readme` plugin installed for discovery to run at all -- `known_gaps: "ALL"`, skipped. Environment gap, not a discovery bug (matches the original Hatchling validation round's finding for this same package). |
| PDM | [pdm-project/pdm-backend](https://github.com/pdm-project/pdm-backend) | 2.4.9 | MIT | PDM-backend's own package (self-hosting case) -- perfect match, no known gaps. **Primary case for the PDM-backend roadmap item.** |
| PDM | [tiangolo/typer](https://github.com/tiangolo/typer) | 0.27.2 | MIT | Perfect match, no known gaps. **Primary case for the PDM-backend roadmap item.** |
| Poetry | [python-poetry/poetry-core](https://github.com/python-poetry/poetry-core) | 2.4.1 | MIT | Perfect match -- persists the case already validated once in `backend-file-discovery-validation.md`. |
| Poetry | [PyCQA/pydocstyle](https://github.com/PyCQA/pydocstyle) | 6.3.0 | MIT | Perfect match, no known gaps. |
| setuptools | [tkem/cachetools](https://github.com/tkem/cachetools) | 7.1.8 | MIT | Strict PEP 639 `license = "MIT"` + `license-files`, `setuptools-scm` dynamic version. Perfect match, no known gaps. |
| setuptools | [PyCQA/flake8](https://github.com/PyCQA/flake8) | 7.3.0 | MIT | Legacy `setup.cfg`-only project (no `pyproject.toml` at all), `version = attr:` directive, `src/`-layout `[options.packages.find] where = src`. Perfect match, no known gaps. |
| setuptools | [pallets/markupsafe](https://github.com/pallets/markupsafe) | 3.0.3 | BSD-3-Clause | PEP 639 `license = "BSD-3-Clause"` + `license-files`, plus a real C accelerator (`_speedups.c`/`.so`) -- see `known_gaps`. |
| setuptools | [numpy/numpydoc](https://github.com/numpy/numpydoc) | 1.10.0 | BSD-3-Clause | PEP 621 license via a `License ::` classifier (no explicit `license` field), `pyproject.toml` + `setup.cfg` (egg_info only) side by side. Perfect match, no known gaps. |
| setuptools | [EFS-OpenSource/calibration-framework](https://github.com/EFS-OpenSource/calibration-framework) (PyPI: `netcal`) | 1.4.0 | Apache-2.0 | `[project.license]` as its own TOML table-header section (`text = "Apache-2.0"` on its own line -- a third syntactic variant of the same nested structure, alongside the inline-table and dotted-key forms), `[tool.setuptools.dynamic] version = {attr = "netcal.__version__"}`. Perfect match, no known gaps. |
| setuptools | [yaml/pyyaml](https://github.com/yaml/pyyaml) | 6.0.3 | MIT | Legacy imperative `setup.py` (`setup(name=NAME, ...)` referencing module-level constants, not literals), custom `build-backend = "_pyyaml_pep517"` wrapper, ambiguous flat-layout (`lib/`, `yaml/`, `packaging/`) -- `known_gaps: "ALL"`, skipped; correctly out of scope for both file discovery and (found while adding this fixture) metadata extraction, see the validation doc's Findings. |
| setuptools | [pytest-dev/pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) | 1.4.0 | Apache-2.0 | Perfect match, no known gaps. |
| setuptools | [psf/requests](https://github.com/psf/requests) | 2.34.2 | Apache-2.0 | Uses three legacy pre-PEP-639 license/classifier forms at once (`project.license` as a TOML table, `tool.setuptools.license-files`, a `License ::` classifier) -- setuptools warns but never raises on these outside pytest's own `filterwarnings = ["error"]`. Perfect match, no known gaps (see `pyproject.toml`'s scoped `SetuptoolsDeprecationWarning` ignore entry). |
| setuptools | [python-trio/sniffio](https://github.com/python-trio/sniffio) | 1.3.1 | MIT OR Apache-2.0 | Compound license expression (`license = {text = "MIT OR Apache-2.0"}`), `setuptools_scm` dynamic version. Perfect match, no known gaps. |
| setuptools | [pypa/pipenv](https://github.com/pypa/pipenv) | 2026.8.0 | MIT | Large (4.5MB sdist -- vendors its own dependencies), `license = {text = "MIT License (MIT)"}` -- a short label, not real license text, previously fuzzy-matched to the wrong SPDX ID ("AML") by `licenseid`, see `backend-file-discovery-validation.md`'s Findings. File discovery: perfect match, no known gaps. |
| `uv_build` | [langfuse/langfuse-python](https://github.com/langfuse/langfuse-python) | 4.15.1 | MIT | Confirmed genuine `uv_build` project (`build-backend = "uv_build"`). No `discover()` module exists for `uv_build` yet -- `known_gaps: "ALL"`, skipped for now; vendored so a real `discover_uv_build()` has something to validate against once it lands (roadmap item #5). |
| `uv_build` | [rendercv/rendercv](https://github.com/rendercv/rendercv) | 2.8 | MIT | Same as above -- confirmed genuine `uv_build` project, vendored ahead of the discovery module it will eventually validate. |
