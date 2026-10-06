---
Created: 2026-03-24
Last-Modified: 2026-10-06
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Setuptools support -- implementation notes

See also: [sbom-lifecycle-stages.md](sbom-lifecycle-stages.md) for why
wheel file discovery below stays a static-config read (never executes
`setup.py`), and how this compares to the Hatchling backend and to
`loom wheel`/`embed-wheel`'s build-stage path; [poetry-support.md](poetry-support.md)
for the sibling Poetry backend's wheel-file discovery, which delegates
to poetry-core's own builder instead of hand-rolling static-config
resolution the way this file's setuptools discovery has to;
[setuptools-config-followups.md](../design/setuptools-config-followups.md)
for open `setup.cfg` directive gaps.

## Motivation

Pitloom initially targeted only Hatchling-based projects.  Many real-world
Python packages still use setuptools as their build backend and declare
metadata in `setup.cfg` or `setup.py`.  This document records the design
decisions, conflict resolution strategy, and known limitations of the
initial setuptools support added in the `setuptools-support` branch.

## Source files

| File | Role |
| :--- | :--- |
| `src/pitloom/extract/project/setuptools.py` | Extraction facade and backend detection |
| `src/pitloom/extract/project/_setuptools_options.py` | `setup.py`/`setup.cfg` options merged as setuptools merges them; builds the `ProjectMetadata`; records conflicts |
| `src/pitloom/extract/project/_field_agreement.py` | When two sources agree on a field, and the one conflict-recording rule (shared with `_installed_reconcile.py`) |
| `src/pitloom/extract/project/setuptools_cfg.py` | `setup.cfg` metadata and `[tool:pitloom]` parser (split from `setuptools.py`) |
| `src/pitloom/extract/project/setuptools_py.py` | `setup.py` AST metadata parser (split from `setuptools.py`) |
| `src/pitloom/extract/project/reader.py` | Shared resolver (`read_project()`) used by both the CLI and `generate_project_sbom()` |
| `src/pitloom/cli/` | CLI updated to accept projects without `pyproject.toml` (originally in `__main__.py`, since split into `cli/` -- see `cli-test-coverage-roadmap.md`) |
| `tests/extract/project/test_setuptools_cfg.py`, `test_setuptools_cfg_backend.py`, `test_setuptools_cfg_config.py`, `test_setuptools_py.py`, `test_setuptools_integration.py` | Unit and integration tests (originally `tests/test_setuptools.py`, later split into these modular suites -- see `cli-test-coverage-roadmap.md`) |
| `tests/fixtures/projects/sampleproject-setuptools/` | Transitional-layout fixture project |
| `src/pitloom/core/_models_wheel.py` | Backend-dispatch facade for wheel file discovery (`get_wheel_files()`), shared per-file hashing/header loop |
| `src/pitloom/core/_models_wheel_setuptools.py` | Setuptools wheel file discovery -- static config only, see below |
| `src/pitloom/core/_models_wheel_hatchling.py`, `_models_wheel_types.py` | Hatchling discovery module and shared types, siblings of the facade above |
| `tests/core/models_wheel/test_models_wheel_setuptools.py`, `test_models_wheel_dispatch.py` (same directory) | Wheel file discovery tests (setuptools-specific, and facade dispatch/fallback) |
| `tests/fixtures/projects/sampleproject-setuptools-data/` | `package_data`/`include_package_data`/`MANIFEST.in` fixture for the manifest-analysis discovery path |

## Extraction functions

### `detect_build_backend(project_dir)`

Reads `[build-system] build-backend` from `pyproject.toml` and returns a
lower-case backend identifier (`"setuptools"`, `"hatchling"`, `"flit"`, …).
When no `pyproject.toml` is present but `setup.cfg` or `setup.py` exist,
returns `"setuptools"` by convention.

### `read_setup_cfg(project_dir)`

Parses `[metadata]` and `[options]` using stdlib `configparser`.

**Supported `[metadata]` fields:**

| setup.cfg key | `ProjectMetadata` field |
| :--- | :--- |
| `name` | `name` |
| `version` | `version` |
| `description` / `summary` | `description` |
| `long_description` | `readme` |
| `author` + `author_email` | `authors` |
| `license` | `license_name` |
| `keywords` | `keywords` (space, comma, or newline separated) |
| `url` | `urls["Homepage"]` |
| `project_urls` | `urls` (multi-line key = value) |

**Supported `[options]` fields:**

| setup.cfg key | `ProjectMetadata` field |
| :--- | :--- |
| `python_requires` | `requires_python` |
| `install_requires` | `dependencies` |

**Version directives:**

- **Literal** (`version = 1.2.3`) -- used as-is.
- **`file:` directive** (`version = file: VERSION`) -- reads the referenced
  file; expects a plain version string on a single line.
- **`attr:` directive** (`version = attr: package.__version__`) -- resolves via
  AST parsing of the referenced module file.  Checks both flat-layout
  (`package.py`) and src-layout (`src/package/__init__.py`).  Falls back to
  `None` when the attribute is dynamic (e.g., assigned by a function call).

**Pitloom configuration:**

`[tool:pitloom]` (note the colon separator, which is the `setup.cfg`
convention for tool namespaces) mirrors `[tool.pitloom]` in `pyproject.toml`.
An optional `[tool:pitloom:creation]` sub-section mirrors
`[tool.pitloom.creation]`.  Either section can exist independently.

### `read_setup_py(project_dir)`

Parses `setup.py` using `ast.parse()`.  Extracts **literal** keyword
arguments from the first `setup()` or `setuptools.setup()` call found.

**What is extractable:**

```python
setup(
    name="mypackage",           # ✅ string literal
    version="1.0.0",            # ✅ string literal
    install_requires=[          # ✅ list of string literals
        "requests>=2.0",
        "click",
    ],
    ...
)
```

**What is skipped (with a `WARNING:` naming the keyword):**

```python
setup(
    version=get_version(),  # ✗ function call
    name=PKG_NAME,  # ✗ variable
    install_requires=REQS,  # ✗ variable
)
```

Skipping non-literal values is intentional: it avoids executing untrusted
code and keeps the extractor predictable.  A skipped keyword is not an
option: `setup.cfg`'s value is used.  A `setup.py` without a literal `name=`
is still read (its other keywords count; name from `setup.cfg`).

`read_setup_py_options()` returns the options as
`SetupOption(value, source, given, declared)`; `given` is setuptools' own
test (truthiness of the raw value, of the normalised one for `version` and
`install_requires`) and decides whether a keyword overrides `setup.cfg`.
A `**` unpacking in `setup()` is not read, with a `WARNING:`.  `setup.py` has no Pitloom configuration section;
`read_setup_py` always returns a default `PitloomConfig()`.

### `read_setuptools(project_dir)`

Reads both files' options (`read_setup_cfg_options`,
`read_setup_py_options`), merges them with `build_setuptools_metadata()` and
records conflicts with `record_setuptools_conflicts()`; see
[Precedence](#precedence).  Returns the `PitloomConfig` from `setup.cfg`
(read only when `setup.cfg` names the project), else a default instance.
A nameless `setup.cfg` still contributes its options.  `FileNotFoundError`
when neither file names the project.  An unparseable `setup.py` beside a
`setup.cfg` that names the project gives one `WARNING:` and `setup.cfg` is
read alone.

## Precedence

setuptools applies the `setup()` keywords first, then `setup.cfg`
(`setuptools/config/setupcfg.py`, `ConfigHandler.__setitem__`): a
`setup.cfg` option is applied only when the keyword's current value is
falsy ("Already inhabited. Skipping."). So, per option:

- `author`/`author_email` and `url`/`project_urls` are separate options;
- a list replaces the other, never joins it;
- `""`, `[]`, `{}`, `None` defer to `setup.cfg`; `"  "`, `"UNKNOWN"`,
  `"NONE"` count as given;
- `version` and `install_requires` are normalised first
  (`Distribution.__init__`): `version=0` is `"0"`, given;
  `install_requires=["# x"]` is `[]`, not given;
- name: `setup.py`'s literal, else `setup.cfg`'s.

Measured with real setuptools 84 builds (`prepare_metadata_for_build_wheel`;
`Version` 0.0.0 where unset):

| Case | `setup.py` | `setup.cfg` | setuptools METADATA | Pitloom |
| :--- | :--- | :--- | :--- | :--- |
| Whitespace string | `description="  "` | `description = From cfg` | `Summary: "  "` | stripped: no value, so `setup.cfg`'s |
| `None` | `license=None` | `license = MIT` | `License: MIT` | same |
| Author per field | `author="Py A"` | `author = Cfg A`, `author_email = cfg@x.org` | `Author: Py A`, `Author-email: cfg@x.org` | same |
| URLs apart | `url="https://py.example"` | `project_urls` Source | `Home-page` and `Project-URL` both | same |
| Empty name | `name=""` | `name = cfgname` | `Name: cfgname` | same |
| Empty list | `install_requires=[]` | `install_requires = requests` | `Requires-Dist: requests` | same |
| `"NONE"` | `license="NONE"` | `license = MIT` | `License: NONE` | same |
| Placeholder | `license="UNKNOWN"` | `license = MIT` | `License: UNKNOWN` | `MIT` (difference b) |
| Field vs classifier | `license="MIT"` | classifier BSD | `License: MIT` and the classifier | MIT; the field beats a classifier; conflict recorded |
| Classifier vs field | classifier MIT | `license = Apache-2.0` | `License: Apache-2.0` and the classifier | Apache-2.0; conflict recorded |
| Version | `version="2.0"` | `version = 1.0` | `Version: 2.0` | 2.0; `setup.cfg`'s as a conflict |
| `python_requires` | `""` | `>=3.9` | `Requires-Python: >=3.9` | same |
| Empty dict | `project_urls={}` | `project_urls` Doc | `Project-URL: Doc` | same |
| `[DEFAULT]` | none | `[DEFAULT] license = MIT` | `License: MIT` | inherited, same |

Accepted differences from setuptools:

- (a) `setup.py` is read, never run: a non-literal value is ignored with a
  `WARNING:` and `setup.cfg`'s is used. So is a value Pitloom does not read:
  a type setuptools rejects (`version=True`, `classifiers='x'`) or converts
  (`url=1`, `project_urls={'a': 1}`, a nested `install_requires` list). A
  version number is converted as setuptools does (`version=1.5` ->
  `"1.5"`), and requirements are read line by line as setuptools reads
  them (`requirement_lines`: a string split into lines, ` #` comments
  dropped, `\` continuations joined; a one-line `setup.cfg` value split on
  `;`); a `setup.cfg` `file:` directive is not (follow-up below).
- (b) A placeholder licence (`UNKNOWN`/`NOASSERTION`) in `setup()` gives
  way to the licence classifier kept (`setup.py`'s replace `setup.cfg`'s),
  else to the `setup.cfg` `license` it overrode
  (`resolve_setuptools_licence`); `NONE` is a statement. A `setup.cfg`
  placeholder gives way as in setuptools. `setup(license='UNKNOWN',
  classifiers=[<no licence>])` keeps `UNKNOWN` over a `setup.cfg` licence
  classifier, as the wheel does: the classifiers were replaced.
- (c) A whitespace-only `setup()` string is ignored with a `WARNING:` and
  `setup.cfg`'s is used: setuptools keeps the blank, which states nothing
  (and for `name` fails the build).
- (d) When `setup.py` overrides a different real name (PEP 503), licence,
  version or `python_requires`, Pitloom keeps `setup.py`'s and records the other as a
  conflict Annotation (one declared licence, not two), with one `WARNING:
  <dir>: setup.py and setup.cfg disagree on <field> (setup.py ...,
  setup.cfg ...) -- keeping <file>'s`, one per field. For the licence a
  real field beats a classifier in either file, so `setup.cfg`'s `license`
  can beat a `setup.py` classifier; a `setup()` placeholder gives way to
  `setup.py`'s own classifier first. Equality is PEP 440 / licence equivalence
  (`_field_agreement.values_agree`).
- (e) In-tree installed metadata (`.egg-info`/`.dist-info`) disagreeing
  too adds to the conflict record instead of replacing it
  (`_installed_reconcile.py`).

Only directory surfaces (`loom project`, `generate <dir>`,
`generate_project_sbom()`) read the two files; sdist and wheel surfaces read
the metadata setuptools wrote, so they agree except for (a)-(c).

Rejected:

- Merging at the `ProjectMetadata` level with `merge_project_metadata()`:
  its name is always the primary's and a falsy value with provenance is
  authoritative, the opposite of setuptools (`""` defers there).
- Joining lists (`keywords`, `install_requires`): setuptools replaces.
- Executing `setup.py` for exact values: out of scope (untrusted code).

## Out-of-scope follow-ups

- An sdist without `PKG-INFO` ignores `setup.cfg`/`setup.py`.
- `pyproject.toml` `dynamic` fields supplied by `setup.py`/`setup.cfg`.
- `[project]` vs `[tool.poetry]` precedence (the other merged pair).
- Resolving module constants for `setup(name=NAME)`.
- First-match `setup()` call: an earlier `logger.setup()` wins.
- `setup(license_expression=...)` (setuptools' current spelling, written as
  `License-Expression`) is not read from `setup.py`.
- `setup.cfg` `install_requires = file: requirements.txt`: setuptools
  reads the file, Pitloom keeps the text.
- A `setup()` string's trailing whitespace: setuptools keeps it in
  `Summary`, Pitloom strips both ends.
- `keywords = a b`: setuptools keeps one string, Pitloom splits on
  whitespace and commas.
- `[tool:pitloom]` is ignored when only `setup.py` names the project.
- `apply_in_package_license` treats a weak licence as stated.
- A real-world sdist parity test (directory vs sdist vs wheel).
- A non-empty value only inherited from `setup.cfg` `[DEFAULT]` has no
  provenance for the presence-gated fields (`install_requires`,
  `keywords`, `python_requires`, authors, urls); gate on "declared or
  value".
- `setup.cfg` spellings setuptools accepts and Pitloom ignores: dashed
  keys (`author-email`, `home-page`, `python-requires`,
  `install-requires`, `long-description`), the aliases `home_page` and
  `classifier`, and setuptools' first-wins order of `summary` and
  `description`.
- A project can carry two `field: "license"` conflict Annotations: the
  `setup.py`/`setup.cfg` one and the declared-vs-detected one; each is a
  separate disagreement, told apart by its candidates' sources.

## Wheel file discovery (`_models_wheel_setuptools.discover()`)

`get_wheel_files()` (`src/pitloom/core/_models_wheel.py`) dispatches to
`pitloom.core._models_wheel_setuptools.discover()` for any project whose
`detect_build_backend()` result is `"setuptools"`. Same static-only
boundary as metadata extraction above -- resolves
`packages`/`package_dir`/`packages.find`/`package_data`/
`include_package_data` via setuptools' own official config-resolution
API (`setuptools.config.pyprojecttoml`/`setupcfg`'s
`apply_configuration()`), which fully populates a `Distribution` the
same way a real setuptools build would, without executing `setup.py`.
See [sbom-lifecycle-stages.md](sbom-lifecycle-stages.md) for why.

Unlike metadata extraction's `read_project()` (see "Conflict
resolution" below), this module applies **both** `setup.cfg` and
`pyproject.toml` when both are present, `setup.cfg` first: setuptools'
own `apply_configuration()` calls are cumulative on the same
`Distribution`, so `pyproject.toml` (applied second) can supply
`[tool.setuptools.dynamic]`/PEP 621 fields on top of `setup.cfg`'s
`packages`/`package_dir`, matching how a real setuptools build
consults both rather than treating them as mutually exclusive. A
`pyproject.toml` carrying only a PEP 621 `[project]` table, with no
`[tool.setuptools]` table at all, is also resolved -- setuptools'
own zero-config auto-discovery applies there.

`apply_configuration()` runs with the process cwd already set to the
target project directory (`_chdir`, run under `_models_wheel.py`'s
`_DiscoveryLock` in exclusive write mode -- a multi-reader/single-writer
lock, not a plain `threading.Lock`, so this setuptools call is kept from
overlapping any other backend's concurrent `discover()` call, including
Hatchling's, without needlessly serializing two Hatchling-only calls
against each other): `[tool.setuptools.dynamic]`/`attr:`
resolution can import the target project's own modules, and running
that import from the wrong cwd risks resolving it against an
unrelated module reachable from Pitloom's own `sys.path` instead of
the intended one.

**Module files** (`.py`): `setuptools.command.build_py.build_py`'s
`find_all_modules()`, called after `finalize_options()`.

**Data files** (`package_data`, and `include_package_data` +
`MANIFEST.in`): `build_py._get_data_files()`, which internally runs
setuptools' manifest analysis. `include_package_data=True` triggers a
real `egg_info` command invocation -- redirected via the command's own
`egg_base` option to a `tempfile.TemporaryDirectory()` so the project
directory is never mutated by what is meant to be a read-only
discovery pass (verified by a regression test asserting no `.egg-info`
artifact is left behind).

**No static config at all** -- a `pyproject.toml` with only
`[build-system]` (no `[project]`, no `[tool.setuptools]`) and no
`setup.cfg`, meaning packages/data files are only resolvable by
executing an imperative `setup.py` -- returns `None` from this module,
same "out of scope" boundary as `read_setup_py`'s literal-only AST
parsing above. At the facade level (`_models_wheel.py`), when the
`pyproject.toml` also has no `[project]` table at all (missing,
unparseable, or `[build-system]`-only), Hatchling's own discovery is
guaranteed to fail the same way, so the facade returns an empty file
list directly with a logged warning -- it never attempts the
Hatchling-branded heuristic for this case. Only a project whose
`pyproject.toml` *does* have a `[project]` table falls back to the
Hatchling-based heuristic when this module's own static config can't
be resolved. Files resolved from static config are also deduplicated
by distribution path (a `package_data` glob can overlap a `.py` module
already found by module discovery); each output entry is unique.

**Fixes the exact bug from `working-docs/design/roadmap.md`'s
"Non-Hatchling file discovery" item**: a `where = ["lib"]`-style
`[options.packages.find]` layout previously reported
`lib/mypkg/__init__.py` (wrong -- carried the `where=` source directory
into the distribution path); now correctly reports `mypkg/__init__.py`.

## Conflict resolution

Multiple metadata sources may coexist in a single project (common during
migration to pyproject.toml).  Resolution happens in `read_project()` in
`src/pitloom/extract/project.py`, the single entry point used by both the
CLI and `generate_project_sbom()`'s default parsing path:

1. If `pyproject.toml` exists at all (existence check only -- regardless of
   whether it has a `[project]` section), it is the sole metadata source,
   via `read_pyproject()`. `setup.cfg`/`setup.py` are not consulted, even if
   present -- there is no cross-source field merge at this level.
2. Otherwise, if `setup.cfg` and/or `setup.py` exist, `read_setuptools()` is
   used as the sole source (the merge of [Precedence](#precedence) applies
   only between `setup.cfg` and `setup.py`, not `pyproject.toml`).
3. If none of the three files exist, `FileNotFoundError` is raised.

**Why pyproject.toml wins:** PEP 517 and PEP 621 designate `[project]` in
`pyproject.toml` as the canonical metadata location.  Setuptools itself gives
`pyproject.toml` precedence over `setup.cfg` when both are present.

**Known limitation:** a transitional project with `[build-system]`-only
`pyproject.toml` plus real metadata in `setup.cfg` (see the fixture project
below) does not currently get its `setup.cfg` metadata merged in -- step 1
above takes `pyproject.toml`'s (mostly empty) metadata as-is. Field-level
merging across `pyproject.toml` and `setup.cfg` is a possible future
enhancement, not yet implemented.

## Provenance tracking

Each field records its source using the same `"Source: X | Field: Y"` /
`"Source: X | Method: Y"` pattern as `read_pyproject`:

```text
name         -> "Source: setup.cfg | Field: metadata.name"
version      -> "Source: VERSION | Method: file_directive"
version      -> "Source: src/mypkg/__init__.py | Method: attr_directive"
authors      -> "Source: setup.py | Field: setup(author=...)"
```

Provenance follows the option that won: a `setup.cfg` value used because the
`setup()` keyword was empty carries `setup.cfg`'s label; an overridden real
value is kept as a conflict candidate. A field built from two options from
different files (`author` from `setup.py`, `author_email` from `setup.cfg`;
`url` and `project_urls`) names both, `setup.py` first, comma-separated in
one string (`_joint_source`):

```text
authors -> "Source: setup.py, setup.cfg | Field: setup(author=...), metadata.author/author_email"
```

Rejected: brackets (`Source: [setup.py, setup.cfg]` reads as a JSON array
but is a string), a JSON list for `source` (changes the `pitloom/1` field
type for every reader), per-part keys (`author_email`, `project_urls`: keys
no other producer writes), a `Method:` marker (says merged, not from where).
Every name in the source is a manifest, so `minimal` detail still hides it
(`_is_high_signal`).

## Fixture project

`tests/fixtures/projects/sampleproject-setuptools/` demonstrates the common
**transitional layout**:

```text
sampleproject-setuptools/
├── pyproject.toml        # [build-system] only -- no [project] section
├── setup.cfg             # [metadata] + [options] + [tool:pitloom]
├── setup.py              # bare setup() shim
├── README.md
└── src/
    └── sampleproject_setuptools/
        └── __init__.py   # __version__ = "0.1.0"
```

This mirrors the pattern seen in many real projects that have adopted
`pyproject.toml` for the build-system declaration but still keep metadata
in `setup.cfg`.

## Known limitations

| Limitation | Notes |
| :--- | :--- |
| Dynamic `setup.py` values | Variables, function calls, `f`-strings are skipped with a `WARNING:`; `setup.cfg`'s value, else `None`. |
| `attr:` with complex paths | Only `module.ATTR` (two-part) is resolved; deeper paths (e.g., `pkg.sub.module.ATTR`) fall back to `None`. |
| Multiple authors in `setup.cfg` | `author` / `author_email` yield at most one entry; setuptools supports comma-separated lists but pitloom does not yet parse them. |
| Optional / extras dependencies | `[options.extras_require]` is not extracted. |
| Wheel file discovery, no static config | A setuptools project with no `[project]`/`[tool.setuptools]` in `pyproject.toml` and no `setup.cfg` (packages only resolvable via imperative `setup.py`) returns an empty file list -- the facade skips the Hatchling-based heuristic entirely for this case (logged warning), since it's guaranteed to fail Hatchling's own discovery too; same static-only boundary as metadata extraction. |
| Build-time dynamic metadata | `version` set via Git tags, `importlib.metadata`, or other runtime mechanisms is not resolved statically.  See [working-docs/design/metadata-sources.md](../design/metadata-sources.md) for the planned PEP 517 approach. |
| Wheel file discovery, `setup.py` overrides packaging imperatively | A project can look statically resolvable (a `setup.cfg`/zero-config auto-discovery finds *something*) while its real `setup.py` also passes `packages`/`package_data`/etc. imperatively -- silently dropping files (real-world boto3) or including spurious ones (real-world cffi's implicit-namespace-package guess for a non-package `src/c/` dir). Neither is fixable without executing `setup.py` (out of scope), so `discover()` AST-scans `setup.py` for these argument names and logs a `WARNING:` when present, rather than staying silent. See [backend-file-discovery-validation.md](backend-file-discovery-validation.md#findings). |

## Real-world validation

`discover()` is checked against real PyPI packages, not just the
synthetic fixtures under `tests/fixtures/projects/` -- method, the
current 10-package results, and findings now live in
[backend-file-discovery-validation.md](backend-file-discovery-validation.md)
(shared with the Hatchling backend's own validation).

## Planned enhancements

- **`attr:` with deep module paths** (e.g., `pkg.sub.module.ATTR`).
- **Multiple authors** from comma-separated `setup.cfg` `author` fields.
- **`[options.extras_require]`** extraction.
- **PEP 517 `prepare_metadata_for_build_wheel`** as an opt-in higher-priority
  source for dynamic metadata.  See
  [working-docs/design/metadata-sources.md](../design/metadata-sources.md).
