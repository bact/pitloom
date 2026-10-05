---
Created: 2026-05-10
Last-Modified: 2026-10-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# License detection pipeline

This document describes how Pitloom detects, carries, and exports
licence information from its various input sources into a finished
SPDX 3 SBOM document.

See also: [license-typing.md](license-typing.md) -- how a value is
classified (expression, text, `NOASSERTION`/`NONE` individuals), the
dependency cascade, conflicts and the decisions behind them;
[license-rules.md](../design/license-rules.md)
-- the open questions before the rules are made systematic.

## Overview

Licence data flows through three distinct stages:

1. **Extract** -- one or more source-specific extractors read licence
   information from files and remote APIs.
2. **Model** -- extracted data is normalised into a format-neutral
   intermediate representation (`ProjectMetadata` or `AiModelMetadata`).
3. **Assemble and export** -- the assembler converts the intermediate model
   into SPDX 3 elements and serialises them as JSON-LD.

## Data flow diagram

```text
Source inputs
──────────────────────────────────────────────────────────────────────────────
pyproject.toml      AI model file          HuggingFace Hub repo
setup.cfg           (PT2 extra/license)    (model card YAML)
CITATION.cff                               (LICENSE file + licenseid)
codemeta.json
LICENSE / LICENCE /
  COPYING file
  (+ licenseid)
      │                    │                        │
      ▼                    ▼                        ▼
──────────────────────────────────────────────────────────────────────────────
EXTRACT LAYER  (src/pitloom/extract/)
──────────────────────────────────────────────────────────────────────────────
pyproject.py         pytorch_pt2.py         huggingface.py
setuptools.py        (zip entry            ┌──────────────────────────────┐
poetry.py, sdist.py   extra/license)       │ 1. card YAML license:        │
hatchling.py                               │    if vague/missing:         │
_license.py ─────────────────────────      │ 2. _detect_license_          │
 apply_in_package_license()                │      from_hf_files()         │
  ├─ (manifest licence read first)         │      → licenseid library     │
  ├─ CITATION.cff    license:              │        (≥ 0.85 confidence)   │
  ├─ codemeta.json   license:              └──────────────────────────────┘
  └─ LICENSE file    (via licenseid)
      │                    │                        │
      ▼                    ▼                        ▼
──────────────────────────────────────────────────────────────────────────────
FORMAT-NEUTRAL MODEL  (src/pitloom/core/)
──────────────────────────────────────────────────────────────────────────────
ProjectMetadata                       AiModelMetadata
  .license_name: str | None             .license: str | None
  .provenance["license"]: str           .provenance["license"]: str
      │                                       │
      ▼                                       ▼
──────────────────────────────────────────────────────────────────────────────
ASSEMBLE LAYER  (src/pitloom/assemble/spdx3/)
──────────────────────────────────────────────────────────────────────────────
document.py build()              document.py build_model()
 main package / deps              standalone AI model
      │                                       │
      └──────────────────┬────────────────────┘
                         │
                 ai.py add_ai_models()
                 deps_license.py build_license_elements()
                   └─ _license_elements.py (the one builder)
                        classify_license(): expression │ text │
                                            NOASSERTION │ NONE │ absent
                        ├─ reuse the element if duplicate (kind, value)
                        ├─ LicenseExpression  (valid SPDX expression)
                        ├─ SimpleLicensingText  (other text)
                        ├─ NoAssertionLicense / NoneLicense  (individual,
                        │    no element)
                        └─ absent: nothing
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
    Relationship             Relationship
    hasDeclaredLicense       hasConcludedLicense
    (package → license)      (package → license)
      │
      ▼
──────────────────────────────────────────────────────────────────────────────
EXPORT LAYER  (src/pitloom/export/spdx3_json.py)
──────────────────────────────────────────────────────────────────────────────
Spdx3JsonExporter.to_json()
  └─ JSON-LD graph  (@context + @graph)
       ├─ simplelicensing_LicenseExpression / _SimpleLicensingText
       ├─ Relationship  {relationshipType: hasDeclaredLicense}
       └─ Relationship  {relationshipType: hasConcludedLicense}
```

## Stage 1: extract

### Python project sources

`src/pitloom/extract/project/_pyproject_license.py` resolves the licence
after `pyproject.toml` is parsed, in priority order:

1. `project.license` in `pyproject.toml` (PEP 639 SPDX expression or
   legacy text/file pointer). Text that `licenseid` identifies gives the
   id (`Method: licenseid_detection`); other text is kept as written.
2. A `License ::` classifier, when `project.license` is absent, blank or
   `UNKNOWN`/`NOASSERTION` (`license_or_classifier`, the wheel/sdist rule).
3. Only when neither states a licence, the project's own licence files
   (`apply_in_package_license()` in `_license.py`): `license:` in
   `CITATION.cff`, then `codemeta.json` (URL values reduced to their SPDX
   ID segment), then the text of `LICENSE`, `LICENCE`, `COPYING` or
   `COPYRIGHT` (with common suffixes) via `licenseid` (≥ 0.85 confidence).
   When the manifest states a licence (not blank), they are the G2
   concluded second opinion instead.

`setuptools_cfg.py` (`license`, then `classifiers`), `setuptools_py.py`
(`setup(license=...)`, then `setup(classifiers=...)`) and `hatchling.py`
(the build hook: `core.license_expression or core.license`, then
`core.classifiers`) use the same rule
and fall back to the licence files the same way. `poetry.py` reads `license`
only: `poetry-core` derives the licence classifier from it. The result is
`ProjectMetadata.license_name`.

All extractors record their source in `provenance["license"]` using the
`Source: … | Field: …` convention.

#### Root-file detection (`_license_detect.py`)

Sources 2-4 are read by `collect_license_candidates()`, a thin directory
adapter over a pure bytes core, `license_candidates_from_members()`
(`{root-level name: bytes}` -> candidates). The core does no I/O; an
sdist feeds it the archive members its one scan already holds. A
drift-guard test pins that a directory and the same files as bytes give
identical candidates. Every project reader then applies the result
through one helper, `apply_in_package_license(metadata, candidates)`
(stated licence: concluded; silent or blank: declared):

| Surface | Reader | Licence files read from |
| :--- | :--- | :--- |
| `loom project <dir>`, library | `pyproject.py`, `setuptools.py`, `poetry.py` | the project directory |
| Hatchling hook | `hatchling.py` | the project directory |
| sdist (`.tar.gz`, `.zip`) | `sdist.py` (`_sdist_scan.py`) | root members of `PKG-INFO`'s top directory |
| wheel, installed metadata | `wheel.py`, `installed.py` | not read (0.21.0, `License-File:`) |

The sdist scan (`_sdist_scan.py`) reads the candidate names
(`license_source_names()`) among the root-level members of the top
directory holding the first root-level `PKG-INFO` (else `pyproject.toml`,
else `setup.cfg`), in its single pass; regular members only (tar links
are not read), names normalised as for the file list. Its provenance adds
the archive: `Source: LICENSE | File: x.tar.gz | Method:
licenseid_detection | Tool: licenseid==v`. With no `PKG-INFO`, the
sdist's `pyproject.toml` gives `project.license` and its classifiers
through the directory's rule (`license_from_project_table()`); a
`license.file` is read only when it is one of those root members. Rules:

- **Case** (core): names match the `LICENSE`/`LICENCE`/`COPYING`/
  `COPYRIGHT` x `""`/`.txt`/`.rst`/`.md` list ignoring case
  (`pick_license_names()`). Where several names differ only in case (a
  case-sensitive file system, an archive), the list's own spelling wins,
  else the smallest in `str` order -- never the listing order, which made
  the directory pick nondeterministic before.
- **Size cap** (reader; the directory adapter and the sdist scan): a root
  file over `LICENSE_FILE_MAX_BYTES` (256 KiB) is skipped, read no further
  than one byte past the cap, with one `WARNING:` naming it
  (`warn_over_cap()`, in the `logging_config.FILE_OVER_CAP_WARNING`
  wording the usage scan shares). Once per file and process (`warn_once`):
  one run reads a project twice when a lock-file re-read follows the peek.
  Real licence texts are a few KiB to some tens of KiB, and `licenseid` is
  slow on large text.
- **Text** (core): UTF-8 with replacement and universal newlines, as
  `Path.read_text()` gave it; an empty or whitespace-only file gives no
  candidate. `codemeta.json` is parsed from bytes, so a UTF-8 BOM is
  accepted; one that is not a JSON object states nothing.

The directory side follows a symlinked licence file, as a plain read does;
an sdist's link member is not read.

### AI model file sources

Only formats that embed metadata in the file itself can carry a licence:

| Format      | Extractor              | Licence field               |
| :---------- | :--------------------- | :-------------------------- |
| PyTorch PT2 | `pytorch_pt2.py`       | `extra/license` zip entry   |
| GGUF        | `gguf.py`              | not yet mapped              |
| Safetensors | `safetensors.py`       | not yet mapped              |
| ONNX        | `onnx.py`              | not yet mapped              |
| Others      | various                | not yet mapped              |

The `AiModelMetadata.license` field is `None` when no embedded licence
is found; the assembler handles this gracefully by emitting no licence
relationships.

### HuggingFace Hub source

`huggingface.py` implements a two-step resolution in `_resolve_license()`:

1. **Card YAML** -- reads `license:` from the model card frontmatter. If
   the value is not a vague sentinel (`other`, `custom`, `proprietary`,
   `unlicensed`; `unknown` is handled below), it is passed through `canonicalize_license_id()`,
   which calls `.match(license_id=raw)` on a process-wide cached
   `AggregatedLicenseMatcher` (see `_get_matcher()`) from the `licenseid`
   library for a direct database lookup. Recognised SPDX
   License IDs are returned in canonical casing (e.g. `"apache-2.0"` →
   `"Apache-2.0"`). Values not recognised — proprietary or non-SPDX
   identifiers such as `"gemma"`, `"llama3.2"`, or deprecated bare
   copyleft forms — are returned verbatim. The result is stored in
   `AiModelMetadata.license`.
2. **File detection** -- when the card YAML value is absent or vague,
   `_detect_license_from_hf_files()` iterates through candidate files in
   the repository (`LICENSE`, `LICENCE`, `COPYING`, `NOTICE`, and
   suffixed variants) in priority order. Each file is downloaded via
   `hf_hub_download` and its text is passed to `detect_license_from_text()`
   from the `licenseid` library. The first match above the 0.85 confidence
   threshold is accepted. The original vague card value is preserved in
   `extra_data["hf.license_raw"]` for auditability. A card value of
   `unknown` (any case) that file detection cannot improve is returned as
   stated, with card provenance, and becomes the `NoAssertionLicense`
   individual; `other`/`custom`/`proprietary`/`unlicensed` give nothing.

### `licenseid` dependency

Text-based licence detection (`detect_license_from_text()` in
`_license.py`) uses the `licenseid` package, which is a mandatory
pitloom dependency. The database must be built before detection is
possible:

```shell
licenseid update
```

When the database has not been built, `detect_license_from_text()`
logs a warning and returns `None`; other licence sources (card YAML,
`CITATION.cff`, `codemeta.json`) are unaffected.

The database is stored at
`~/.local/share/licenseid/licenses.db`. Detection uses cosine similarity
against vectorised licence texts with a default threshold of 0.85.

## Stage 2: format-neutral model

After extraction, licence data lives in one of two dataclasses:

- `ProjectMetadata.license_name: str | None` -- for Python projects.
- `AiModelMetadata.license: str | None` -- for AI model files and
  HuggingFace Hub models.

Both carry a `provenance: dict[str, str]` where the `"license"` key
records a human-readable source description, for example:

```text
Source: pyproject.toml | Field: project.license
Source: Hugging Face Hub | File: LICENSE | Method: licenseid_detection
Source: model.pt2 | Field: extra/license
```

## Stage 3: assemble and export

### `build_license_elements()` -- `assemble/spdx3/deps_license.py`

This shared helper is called by every code path that needs to emit
licence relationships. It asks `get_or_create_license_element()`
(`assemble/spdx3/_license_elements.py`, the one builder; see
[license-typing.md](license-typing.md)) for the element, then builds the
relationship(s):

1. `classify_license()` sorts the value. `None` (absent or blank) stops
   here: no element, no relationship.
2. `exporter.find_license(kind, value)` reuses an existing element of the
   same `(kind, value)`; an expression and a text with the same string
   stay apart.
3. Otherwise a `simplelicensing_LicenseExpression`
   (`simplelicensing_licenseExpression`: the canonical form) or a
   `simplelicensing_SimpleLicensingText` (`simplelicensing_licenseText`: the
   text as written less leading blank space and final line breaks, first
   seen; deduplicated on the stripped text) is created, with `name` (first
   line, at most 60 characters). Several `License ::` classifiers give one
   `LicenseExpression` whose `customIdToUri` maps each
   `LicenseRef-pitloom-classifier-` term to its name's text element. Its
   provenance (`comment`, `"Metadata provenance: license: <provenance>"`,
   and an Annotation) is written only when high-signal at the
   default `detail = "minimal"` -- a non-manifest source, a `Method`, a
   `Normalized-From`/`Deprecated-License-Id` note -- and always at
   `detail = "full"` (`filter_high_signal()`).
   `NOASSERTION`/`UNKNOWN`/`NONE` create no element: the relationship's `to`
   is the named individual.
4. A `hasDeclaredLicense` or `hasConcludedLicense` relationship is built
   (single value: declared when the source is the package's own statement,
   concluded for a third-party record -- PyPI, a dependency's installed
   copy; two values, main package only: both, with a conflict Annotation
   when they differ, see license-typing.md).

A note about how the value changed (`Normalized-From`, `Normalizer`,
`Deprecated-License-Id`) goes on the new element, or, when the element
already existed, on this source's relationship; for an individual always
on the relationship.

The caller is responsible for adding the relationships to the exporter.

### Call sites

| Call site | Subject package | Trigger condition |
| :--- | :--- | :--- |
| `document.py build()` | main Python package | a licence value is stated |
| `document.py build()` | each dependency | installed metadata, installed classifiers, then PyPI (weak `NOASSERTION` last; see license-typing.md) |
| `ai.py add_ai_models()` | each AI model | `ai_model.license` is stated |
| `document.py build_model()` | standalone AI model | `model.license` is stated |
| `_document_files.py` | each tagged source file | `SPDX-License-Identifier:` header |

A package with no stated licence gets no relationship at all.

### `profileConformance`

Derived from the finished graph by
`assemble/spdx3/_licensing_profiles.py`, for every builder and for
fragment merge: `simpleLicensing` when the graph has a licence element or a
declared/concluded licence relationship, `expandedLicensing` when it uses an
`expandedlicensing_*` element or an individual (which implies
`simpleLicensing`), neither otherwise.

### Output elements

For a package with a licence the JSON-LD graph contains, for example:

```jsonc
{
  "type": "simplelicensing_LicenseExpression",
  "spdxId": "https://spdx.org/spdxdocs/<name>-<uuid>#License-1",
  "name": "Apache-2.0",
  "simplelicensing_licenseExpression": "Apache-2.0"
},
{
  "type": "Relationship",
  "spdxId": "https://spdx.org/spdxdocs/<name>-<uuid>#Relationship-1",
  "relationshipType": "hasDeclaredLicense",
  "from": "https://spdx.org/spdxdocs/<name>-<uuid>#Package-1",
  "to": ["https://spdx.org/spdxdocs/<name>-<uuid>#License-1"]
}
```

A source that said `NOASSERTION` gives only the relationship, with
`"to": ["expandedlicensing_NoAssertionLicense"]`.

## License files are not listed (PEP 639)

`[project.license-files]` is a PEP 639 glob list naming licence *text
files* (e.g. `LICENSE`, `LICENSES/*.txt`) that the build backend copies
into the wheel's own `<name>-<version>.dist-info/licenses/`. Pitloom
lists none of them in an SBOM, on any surface, and does not read the
field at all (no `ProjectMetadata` field, no provenance key).

Rule: an SBOM describes the project that is packaged, not the package
container. Nothing under a wheel's own `.dist-info` -- `RECORD`,
`METADATA`, `licenses/`, `sboms/` -- gets a `software_File` element, a
directory element, or a relationship. Pitloom never writes
`.dist-info/licenses/*` into a wheel; the wheel keeps whatever the
backend put there, untouched. Package-level licence assertions stay:
`hasDeclaredLicense` on the package (from `[project.license]`/`METADATA`)
and the concluded licence are unaffected. A source file's own
`SPDX-License-Identifier:` header still gets its file-level
`hasDeclaredLicense` (`_emit_file_license_relationship()`).

Path rejected (built in PR #207, then removed):
`resolve_license_file_entries()` synthesised a `ProjectFile` per
declared entry at the reproduced `.dist-info/licenses/<path>` path,
flagged `is_license_file=True`, and
the assembler gave each a file-level `hasDeclaredLicense` pointing at the
project's declared licence. It filled a "static discovery never sees
`.dist-info`" gap that is not a gap under the rule above; it also listed
a file the project's own source tree already carries at its real path,
and asserted a licence on a licence text. The wheel-reading surfaces drop
the whole own `.dist-info` in `extract/wheel.py` for the same reason.
The follow-up it implied (auto-discovering the backends' default
`LICEN[CS]E*`/`COPYING*`/`NOTICE*`/`AUTHORS*` glob when the field is
undeclared) is moot for the same reason and was dropped from the
metadata-quality roadmap.

Regression test: `tests/assemble/test_license_files_not_listed.py`
(library and Hatchling-hook surfaces, plus the vendored
`cachetools-7.1.8`/`markupsafe-3.0.3` real-world sdists), including a
project that declares `license-files` *and* has a header-tagged source
file, so the surviving header path is proven untouched.

## Limitations and future work

- `hasDeclaredLicense` and `hasConcludedLicense` may point at the same
  element (one value) or at two (two-candidate mode, main package only).
  Multiple declared licences concluded as a conjunction are not modelled.
- GGUF, Safetensors, ONNX, and most other model formats do not embed a
  machine-readable licence field. Licence data for those models must come
  from an external source such as HuggingFace Hub or a user-supplied
  fragment.
- `licenseid` text detection is probabilistic (threshold 0.85). Unusual
  licence texts or heavily modified standard licences may not be
  detected. Always verify the concluded licence in the SBOM.
- A `License ::` classifier such as `OSI Approved :: MIT License` gives the
  text `MIT License`, not the SPDX id (a known deviation, see
  license-typing.md).
- A warning for an unknown id in a field that must hold an SPDX expression
  (PEP 639 `license`, `License-Expression`) is a 0.21.0 follow-up.

## Related source files

| File | Role |
| :--- | :--- |
| `src/pitloom/extract/_license.py` | `detect_license_from_text()`, `stated_license()`, `license_from_candidates()`, `apply_in_package_license()` (the one stated/silent rule), `detect_license_for_project()` |
| `src/pitloom/extract/_license_detect.py` | Root-file detection: bytes core, directory adapter, case rule, size cap |
| `src/pitloom/extract/_license_classify.py` | `classify_license()`, `same_licence()` and the provenance notes of a rewrite |
| `src/pitloom/extract/_core_metadata.py` | `core_metadata_license_with_source()` (unfolded headers), `license_cascade()`/`first_license()` (the weak cascade), `license_or_classifier()`, `license_from_classifiers()` (trove parents and a lone `License :: OSI Approved` dropped) |
| `src/pitloom/extract/wheel.py`, `src/pitloom/extract/project/sdist.py`, `src/pitloom/extract/project/installed.py` | Core Metadata readers (wheel, sdist `PKG-INFO`, installed metadata) via `core_metadata_license_with_source()` |
| `src/pitloom/extract/project/_installed_reconcile.py` | static vs installed licence check by `same_licence()`; a weak static value gives way |
| `src/pitloom/extract/project/_setup_cfg_directives.py` | `setup.cfg` `file:`/`attr:` directives; `file:` lists as setuptools reads them (wrapped, blank entries dropped), missing classified by `path_probe`, an unreadable file (a `version` file too) one `UNREADABLE_FILE_WARNING` per run |
| `src/pitloom/extract/license_refs.py` | several classifiers as an AND of `LicenseRef-pitloom-classifier-` terms |
| `src/pitloom/extract/project/_pyproject_license.py` | `pyproject.toml` licence and classifiers |
| `src/pitloom/extract/project/pyproject.py` | Python project licence extraction and detection |
| `src/pitloom/extract/project/_sdist_scan.py` | sdist single pass: root members, licence sources (capped) |
| `src/pitloom/extract/project/hatchling.py` | Hatchling build-hook licence extraction |
| `src/pitloom/extract/project/setuptools.py` | setuptools project licence extraction |
| `src/pitloom/extract/project/poetry.py` | Poetry project licence extraction |
| `src/pitloom/extract/remote/huggingface.py` | HuggingFace Hub card YAML and file-based detection |
| `src/pitloom/extract/ai_model/pytorch_pt2.py` | PT2 archive `extra/license` entry |
| `src/pitloom/core/project.py` | `ProjectMetadata.license_name` field |
| `src/pitloom/core/ai_metadata.py` | `AiModelMetadata.license` field |
| `src/pitloom/assemble/spdx3/deps_license.py` | `build_license_elements()`, `build_file_declared_license()`, `WeakLicense`/`emit_weak_license()` |
| `src/pitloom/assemble/spdx3/_license_elements.py` | the one licence element builder |
| `src/pitloom/assemble/spdx3/_licensing_profiles.py` | licensing profiles from the graph |
| `src/pitloom/core/license_individuals.py` | the named licence individuals table |
| `src/pitloom/assemble/spdx3/_document_files.py` | `_add_package_files()`, `_emit_file_license_relationship()` -- file-level licence wiring |
| `src/pitloom/assemble/spdx3/document.py` | `build()` -- licence wiring (`build_model()` moved to `_document_model.py`, re-exported here) |
| `src/pitloom/assemble/spdx3/ai.py` | `add_ai_models()` -- AI model licence wiring |
| `src/pitloom/export/spdx3_json.py` | `Spdx3JsonExporter.find_license(kind, value)`, `add_license()` |
| `tests/extract/test_license_detect.py` | Case rule, size cap, and the directory-vs-bytes drift guard |
| `tests/assemble/test_license_sdist_parity.py` | One licence value on the directory (CLI, library), the hook and the sdist (tar.gz, zip) |
| `tests/extract/project/test_sdist_license.py` | sdist licence members: top directory, case, cap, links, unsafe names; `PKG-INFO`-less fallback |
| `tests/assemble/test_license_detection.py`, `tests/assemble/test_license_normalization.py` | Unit tests for `_license.py` utilities (originally `tests/test_license.py`, later split -- see `cli-test-coverage-roadmap.md`) |
| `tests/core/generator/test_generator_project_enrichment.py`, `tests/core/generator/test_generator_project_structure.py` | End-to-end licence export tests with fixture files (originally `tests/test_generator.py`, since split by generation target and further by section -- see `cli-test-coverage-roadmap.md`) |
| `tests/assemble/test_license_files_not_listed.py` | Declared `[project.license-files]` yield no SBOM element (library, Hatchling hook, vendored real-world fixtures) |
| `tests/assemble/test_deps_license.py` | Unit tests for `build_license_elements()`/`is_license_concluded()`/`get_or_create_license_element()`, split out of `test_deps_enrichment_pypi_fallback.py` to stay under the file-size soft limit |
