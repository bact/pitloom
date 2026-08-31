---
Created: 2026-08-28
Last-Modified: 2026-08-31
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
`_models_wheel_poetry.py`) and any future one -- gets checked against
**at least 10 diverse real PyPI packages** before being considered
production-ready, not just the synthetic fixtures under
`tests/fixtures/projects/`. Synthetic fixtures
are precise (they isolate one config style at a time, and drive the
unit/regression test suite) but they can't substitute for real
packages: real maintainers combine config styles in ways a fixture
author wouldn't think to construct, and only real PyPI wheels give an
independent ground truth to diff against.

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
  Confirmed by bisecting in scratch venvs: under 65.5.0, the requests
  case silently lost its `py.typed` marker (the implicit
  `include_package_data=True` PEP 621 default resolves differently),
  and Django's PEP 639 string-form `license` was rejected outright
  (pre-70's config schema only accepted `{file=...}`/`{text=...}`
  dicts). `discover()`'s results are only as good as the `setuptools`
  version actually installed at runtime.
- **Doomed-Hatchling-attempt skip was too narrow** (certifi): it only
  checked "no `pyproject.toml` file at all", not "`pyproject.toml`
  exists but has no `[project]` table". Both are guaranteed to fail
  Hatchling's own discovery the same way. **Fixed**: widened the check
  in `_models_wheel.py`'s `_discover_included_files()` to
  `pyproject_data is None or "project" not in pyproject_data`.
- **boto3 -- silent partial result.** A project can have a `setup.cfg`
  that exists but declares no packaging config (only
  `[options.extras_require]`, say), while the real packages/package_data
  live in an imperative `setup.py` call. Because *some* `setup.cfg`
  makes `_load_distribution()` treat the project as "resolvable",
  zero-config auto-discovery correctly finds the `.py` modules -- but
  the imperative `package_data` dict is invisible to static analysis.
  For boto3 specifically this drops all ~23 `boto3/data/**/*.json`
  files (the AWS API resource definitions -- most of the package's
  actual content).
- **cffi -- over-inclusion.** Zero-config auto-discovery treats `src/c`
  (a directory of C sources with no `__init__.py`, used only to compile
  `_cffi_backend`) as an implicit namespace package, because it
  contains one stray `.py` file. Static analysis reports 10 spurious
  `.c`/`.h` files that never reach the real wheel, because cffi's
  actual `setup.py` explicitly overrides `packages=['cffi']` only --
  code we don't execute.
- **Both fixed the same way**: neither case is reliably resolvable
  without executing `setup.py` (out of scope by design -- see
  [sbom-lifecycle-stages.md](sbom-lifecycle-stages.md)), so rather than
  two special-case heuristics, `discover()` now AST-scans `setup.py`
  (when present) for any of `packages`, `py_modules`, `package_dir`,
  `package_data`, `include_package_data`, `exclude_package_data`,
  `data_files` passed to the `setup()` call -- regardless of whether
  the value itself is a resolvable literal (`find_packages()` calls
  included). If any are found, `discover()` still returns its
  statically-resolved file list (often still correct for the `.py`
  modules, and strictly better than returning nothing), but with a
  `WARNING:` that it may be incomplete or wrong. See
  `_setup_py_packaging_kwargs()` /
  `_warn_if_setup_py_overrides_packaging()` in
  `_models_wheel_setuptools.py`. Verified against all 10 packages in
  the table above: fires only for boto3 and cffi, silent for the other
  8 (including python-dateutil and requests, whose `setup.py` files
  exist but pass no packaging-relevant arguments).

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
  enough to compare (attrs, Pygments, wcwidth, Twisted, black) --
  `_models_wheel_hatchling.py`'s pre-existing logic needed no changes.
- **`loom project` hard-crashed on 5/10** (colorama, platformdirs,
  httpx, virtualenv, redis-py) with `Failed to parse project metadata:
  Setting "project.license" to an SPDX license expression is not
  compatible with 'License ::' classifiers`. This is
  [pyproject-metadata](https://github.com/pypa/pyproject-metadata)'s
  own strict PEP 639 validation in the shared, backend-agnostic
  metadata path (`src/pitloom/extract/_pyproject.py`) -- not specific
  to Hatchling, and not something any of the setuptools packages above
  happened to trigger. Real projects mid-PEP-639-migration routinely
  keep both the new SPDX `license` string and the legacy `License ::`
  classifier rather than deleting the classifier the same release. That
  turned out to be the *majority* case in this sample, not an edge
  case. **Fixed**: `read_pyproject()` now catches this one specific,
  narrow validation error (`ConfigurationError` with
  `key == "project.license"` and `"License ::"` in the message), logs
  a `WARNING:`, drops the redundant classifiers, and retries -- keeping
  the SPDX expression as authoritative (the newer, more specific PEP
  639 source). Any other `project.license` failure still raises
  unchanged. See `_is_license_classifier_conflict()` and
  `_drop_redundant_license_classifiers()` in `_pyproject.py`.
- **Environment gap, not a code issue**: httpx additionally failed
  Hatchling's own wheel-file discovery with `Unknown metadata hook:
  fancy-pypi-readme` until the optional `hatch-fancy-pypi-readme`
  plugin was installed in the validation venv -- attrs and Twisted also
  declare it but don't actually invoke the hook for file discovery, so
  they didn't surface the gap. Already degraded gracefully (a `WARNING:`
  and an empty file list, not a crash) before the plugin was installed;
  no code change needed, same shape as the `setuptools>=70` dev-venv
  gotcha in [setuptools-support.md](setuptools-support.md).

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

- **11/11 perfect matches, no code changes needed.** Every config style
  in the diversity matrix -- implicit auto-discovery, explicit
  `packages = [...]` lists, `src/`-layout `{include=..., from=...}`, and
  explicit `include`/`exclude` -- resolved to exactly the wheel's real
  file set (`wheel - project` was dist-info files only in every case;
  `project - wheel` was empty in every case). No `WARNING:` about
  discovery failing or falling back ever fired across all 22 `loom`
  invocations (11 `project` + 11 `wheel`), confirming the dispatch-table
  registration in `_models_wheel.py` and poetry-core delegation both
  worked cleanly for every sample.
- **poethepoet tripped the same PEP 639 `license`/`License ::`
  classifier conflict** documented under Hatchling above (`WARNING:`
  logged, redundant classifiers dropped, SPDX expression kept). This is
  the pre-existing, backend-agnostic `read_pyproject()` fix from that
  earlier round doing its job again -- not a new gap, and not specific
  to Poetry.
- **rich's `pyproject.toml` triggered poetry-core's own deprecation
  notice** (`The "poetry.dev-dependencies" section is deprecated...`)
  printed directly by poetry-core during `Factory().create_poetry()`.
  Harmless and expected: `discover()` only reads `find_files_to_add()`
  output, never `dev-dependencies`, so this doesn't affect the file
  list and needed no handling.
- **No environment gaps encountered** -- unlike Hatchling's optional
  metadata-hook plugins, none of the 11 packages required anything
  beyond `poetry-core` itself (already the sole runtime dependency this
  module needs) to resolve correctly.
- Conclusion: `_models_wheel_poetry.py` is production-ready as written;
  this validation round required no changes to it.
