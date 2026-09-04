---
Created: 2026-05-10
Last-Modified: 2026-09-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# License detection pipeline

This document describes how Pitloom detects, carries, and exports
licence information from its various input sources into a finished
SPDX 3 SBOM document.

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
pyproject.py         _pytorch_pt2.py        _huggingface.py
setuptools.py        (zip entry            ┌──────────────────────────────┐
poetry.py             extra/license)       │ 1. card YAML license:        │
                                           │    if vague/missing:         │
_license.py ─────────────────────────      │ 2. _detect_license_          │
 detect_license_for_project()              │      from_hf_files()         │
  ├─ pyproject.toml  project.license       │      → licenseid library     │
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
                 deps.py build_license_elements()
                   ├─ reuse SimpleLicensingText if duplicate
                   └─ else create simplelicensing_SimpleLicensingText
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
       ├─ simplelicensing_SimpleLicensingText
       ├─ Relationship  {relationshipType: hasDeclaredLicense}
       └─ Relationship  {relationshipType: hasConcludedLicense}
```

## Stage 1: extract

### Python project sources

`src/pitloom/extract/_pyproject.py` calls
`detect_license_for_project()` from `_license.py` after parsing
`pyproject.toml`. That function tries four sources in priority order:

1. `project.license` in `pyproject.toml` (PEP 639 SPDX expression or
   legacy text/file pointer).
2. `license:` scalar or list in `CITATION.cff`.
3. `license:` field in `codemeta.json` (URL values are reduced to their
   SPDX ID segment).
4. Text content of `LICENSE`, `LICENCE`, `COPYING`, or `COPYRIGHT`
   (with common suffixes) passed to `detect_license_from_text()` via
   the `licenseid` library (≥ 0.85 confidence).

`setuptools.py` and `poetry.py` follow the same pattern: they read
their respective `license` / `license_name` fields and store the result
in `ProjectMetadata.license_name`.

All extractors record their source in `provenance["license"]` using the
`Source: … | Field: …` convention.

### AI model file sources

Only formats that embed metadata in the file itself can carry a licence:

| Format      | Extractor              | Licence field               |
| :---------- | :--------------------- | :-------------------------- |
| PyTorch PT2 | `_pytorch_pt2.py`      | `extra/license` zip entry   |
| GGUF        | `_gguf.py`             | not yet mapped              |
| Safetensors | `_safetensors.py`      | not yet mapped              |
| ONNX        | `_onnx.py`             | not yet mapped              |
| Others      | various                | not yet mapped              |

The `AiModelMetadata.license` field is `None` when no embedded licence
is found; the assembler handles this gracefully by emitting no licence
relationships.

### HuggingFace Hub source

`_huggingface.py` implements a two-step resolution in `_resolve_license()`:

1. **Card YAML** -- reads `license:` from the model card frontmatter. If
   the value is not a vague sentinel (`other`, `custom`, `proprietary`,
   `unknown`, `unlicensed`), it is passed through `canonicalize_license_id()`,
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
   `extra_data["hf.license_raw"]` for auditability.

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

```
Source: pyproject.toml | Field: project.license
Source: Hugging Face Hub | File: LICENSE | Method: licenseid_detection
Source: model.pt2 | Field: extra/license
```

## Stage 3: assemble and export

### `build_license_elements()` -- `assemble/spdx3/deps_license.py`

This shared helper is called by every code path that needs to emit
licence relationships. It:

1. Looks up `exporter.find_license(license_id)` to reuse an existing
   `simplelicensing_SimpleLicensingText` element when the same licence
   identifier has already been registered (avoids duplicates when
   multiple packages share a licence).
2. If no match is found, creates a new
   `simplelicensing_SimpleLicensingText` element with:
   - `name`: first line of the identifier, truncated to 60 characters.
   - `simplelicensing_licenseText`: the full licence identifier string.
   - `comment`: `"Metadata provenance: license: <provenance>"`.
3. Builds and returns two fresh `Relationship` elements:
   - `hasDeclaredLicense` -- the licence declared in the software
     artefact itself.
   - `hasConcludedLicense` -- the licence as concluded by the SBOM
     creator (currently set to the same value; see in-code comment for
     planned refinement).

The caller is responsible for adding both relationships to the exporter.

### Call sites

| Call site | Subject package | Trigger condition |
| :--- | :--- | :--- |
| `document.py build()` | main Python package | `metadata.license_name` is set |
| `document.py build()` | each dependency | via `_enrich_from_installed()` |
| `ai.py add_ai_models()` | each AI model | `ai_model.license` is set |
| `document.py build_model()` | standalone AI model | `model.license` is set |

### `profileConformance`

When any licence relationship is added, the assembler appends
`simpleLicensing` to `SpdxDocument.profileConformance`. For documents
that mix Python and AI content, the check is de-duplicated so the
profile identifier appears exactly once regardless of how many packages
carry a licence.

### Output elements

For each package with a known licence, the JSON-LD graph contains:

```jsonc
{
  "type": "simplelicensing_SimpleLicensingText",
  "spdxId": "https://spdx.org/spdxdocs/License/Apache-2.0-1-<uuid>",
  "name": "Apache-2.0",
  "simplelicensing_licenseText": "Apache-2.0",
  "comment": "Metadata provenance: license: Source: pyproject.toml | Field: project.license"
},
{
  "type": "Relationship",
  "spdxId": "https://spdx.org/spdxdocs/Relationship/hasDeclaredLicense1-<uuid>",
  "relationshipType": "hasDeclaredLicense",
  "from": "https://spdx.org/spdxdocs/Package/mypackage-1-<uuid>",
  "to": ["https://spdx.org/spdxdocs/License/Apache-2.0-1-<uuid>"]
},
{
  "type": "Relationship",
  "spdxId": "https://spdx.org/spdxdocs/Relationship/hasConcludedLicense2-<uuid>",
  "relationshipType": "hasConcludedLicense",
  "from": "https://spdx.org/spdxdocs/Package/mypackage-1-<uuid>",
  "to": ["https://spdx.org/spdxdocs/License/Apache-2.0-1-<uuid>"]
}
```

## License-files bundling (PEP 639)

`[project.license-files]` is a separate, narrower PEP 639 field from
`[project.license]` above: a glob list naming one or more license *text
files* to bundle alongside the package (e.g. `LICENSE`, or
`LICENSES/*.txt` for a multi-license project), rather than the SPDX
expression string itself.

### Extraction

Neither `_pyproject.py` nor `hatchling.py` re-implements PEP 639's glob
matching -- both read an already-resolved, project-root-relative path
list from their respective metadata libraries, and both resolve to an
empty list unless `[project.license-files]` was **explicitly declared**:

- `_pyproject.py`: `pyproject_metadata.StandardMetadata.license_files`
  (`list[pathlib.Path] | None`), converted to POSIX strings. This
  library has no implicit default -- absent the key, it's `None`.
- `hatchling.py`: `_resolve_hatchling_license_files()` checks
  `"license-files" in core.config` (the raw, unprocessed `[project]`
  table) *before* reading `core.license_files`. This check is required,
  not cosmetic: `core.license_files` itself has its own default-glob
  fallback (`LICEN[CS]E*`/`COPYING*`/`NOTICE*`/`AUTHORS*`, the same
  convention `setuptools`' `_finalize_license_files()` and the `wheel`
  package document) when the field is absent, so reading it
  unconditionally would misreport an auto-discovered LICENSE file as an
  explicit declaration and silently diverge from `_pyproject.py` for
  any project that has a root LICENSE file but never declared the
  field -- i.e. nearly every Hatchling project. Confirmed with a
  regression test against real Hatchling `CoreMetadata` (not a mock,
  which can't reproduce this lazy, config-driven default):
  `tests/extract/test_hatch_hook_metadata.py::test_metadata_from_hatchling_no_license_files_with_real_core`.
  Whether Pitloom should ever replicate that ecosystem-wide default
  itself (for *both* paths, with its own distinct provenance) is a
  separate, not-yet-scoped roadmap item -- see
  [roadmap.md](../design/roadmap.md)'s Metadata quality section.

Both feed `ProjectMetadata.license_files`, provenance key
`"license_files"` (`"Source: pyproject.toml | Field: project.license-files"` /
the Hatchling-hook equivalent). The legacy, pre-PEP-639
`[tool.setuptools] license-files` key is a distinct, setuptools-specific
mechanism that neither metadata library resolves as part of the standard
`[project]` table -- `license_files` stays empty for a project using only
that form (see `requests-2.34.2` in the real-world fixtures below).

### The static-discovery gap

Pitloom's file discovery (`get_wheel_files()` /
`_discover_included_files()`, used by both `generate_project_sbom()` and
the Hatchling build hook) is a static, config-driven file-*selection*
walk -- never a real wheel build. A real build's
`WheelBuilder.add_licenses()` step is what actually copies
`[project.license-files]` matches into
`<name>-<version>.dist-info/licenses/<path>` inside the wheel; Pitloom's
discoverer never runs that step, for any backend, so those entries never
show up in `ProjectMetadata.files` on their own (confirmed for every
vendored real-world fixture by
`tests/core/models_wheel/test_models_wheel_real_world.py`, which excludes
`.dist-info/*` from its discovery-parity comparison for exactly this
reason).

`resolve_license_file_entries()` (`src/pitloom/extract/_license.py`)
fills this gap directly: given `project_dir`, the resolved
`license_files` list, and the project's name/version, it reads each file
from disk, hashes it, and returns one `ProjectFile` per entry with
`distribution_path` set to the same `<name>-<version>.dist-info/licenses/<path>`
convention a real build would produce, and `is_license_file=True`.

The `<name>` segment is escaped per the *current* [Binary Distribution
Format spec's "Escaping and
Unicode"](https://packaging.python.org/en/latest/specifications/binary-distribution-format/#escaping-and-unicode)
rule -- regular name normalization (PEP 503,
`packaging.utils.canonicalize_name`) followed by replacing every `-`
with `_` -- via `canonicalize_name(name).replace("-", "_")`. This is
**not** the same as PEP 503 normalization alone (which keeps hyphens):
an earlier version of this function used
`hatchling.metadata.utils.normalize_project_name()` (PEP 503 only) and
silently produced a wrong path for every hyphenated package name (e.g.
`pytest-asyncio-1.4.0.dist-info/...` instead of the real
`pytest_asyncio-1.4.0.dist-info/...`) -- caught by
`tests/assemble/test_license_edge_cases.py::test_resolve_license_file_entries_escapes_hyphenated_name`,
verified against the real published wheel filename. Also see this
page's own note: the escaping rule was *revised in 2021* to match real
tooling, so PEP 427 alone (the wheel format's originating PEP) is stale
on this specific point -- the spec page is authoritative, per
[resources.md](../../docs/resources.md)'s PEP-staleness note.

When `version` is `None` (a dynamic/SCM-resolved version that failed to
resolve, e.g. an sdist extracted outside a git checkout), there is no
real wheel filename to build a path from -- every declared entry is
skipped with a `WARNING:` naming the package and entry count, rather
than fabricating a placeholder version. An earlier version of this
function used `version or "0"`, which silently produced a plausible-
looking but fictional path (e.g. `pytest-asyncio-0.dist-info/...`) with
no warning at all -- a "no silent deviations" violation caught the same
way, via `test_resolve_license_file_entries_unresolved_version_skips_with_warning`.

Both `generate_project_sbom()` (`pitloom.assemble._generators`) and the
Hatchling build hook (`pitloom.plugins.hatch`) call
`resolve_license_file_entries()` and merge the result into
`project_files` *before* their `metadata.files = project_files`
assignment, so the entries survive that overwrite. Out of scope for now:
the sdist-archive target path (`read_project()` on a `.tar.gz`/`.zip`) --
`_sdist.py`'s metadata extraction doesn't resolve `license_files` at all
(a pre-existing, separate limitation of that shallower path, not
introduced by this feature); and `embed-wheel --project-dir`, whose
merge path (`_build_sbom_from_project_and_wheel()` in
`src/pitloom/embed.py`) sources its `ProjectMetadata` from the already-
built wheel's own `read_wheel()` result, not from `read_project()`, so
it never calls `resolve_license_file_entries()` at all -- a real wheel's
`.dist-info/licenses/*` entries land in the SBOM's file list either way
(via `read_wheel()`'s normal archive scan), just without the
`hasDeclaredLicense` relationship this feature adds elsewhere. Wiring
`embed-wheel` up is a candidate follow-up, not attempted here.

### Assembly

`_add_package_files()`
(`src/pitloom/assemble/spdx3/_document_files.py`) processes these
entries exactly like any other discovered file -- same directory-
containment relationships, same `software_File` element construction.
The only license-files-specific step is in
`_emit_file_license_relationship()`: a file with `is_license_file=True`
and no `SPDX-License-Identifier:` header tag of its own (it wouldn't have
one -- it *is* the license text, not source code) gets a
`hasDeclaredLicense` relationship built from the *project's* declared
license (`metadata.license_name`) instead. `build_file_declared_license()`
dedups by license-id string, so this reuses the same
`SimpleLicensingText` element the package-level `hasDeclaredLicense`
relationship already points to -- never a second license element for the
same license.

### Real-world validation

`tests/fixtures/real-world-projects/setuptools/{cachetools-7.1.8,markupsafe-3.0.3}`
(vendored real sdists using the proper `[project.license-files]` form)
and `.../requests-2.34.2` (the legacy `[tool.setuptools]` form, confirmed
to correctly resolve to an empty `license_files` -- documents the
boundary, see `tests/assemble/test_license_files_bundling.py`) exercise
this end-to-end, including asserting the produced `distribution_path`
matches each fixture's `expected.json`-recorded real wheel path exactly.

A broader one-off sweep across every vendored real-world fixture (every
backend: `flit`, `hatchling`, `pdm`, `poetry`, `setuptools`, `uv_build`)
found every produced `.dist-info/licenses/<path>` entry matches its
fixture's real recorded wheel path exactly -- including
`pdm/pdm-backend-2.4.9` (`pdm_backend-2.4.9.dist-info/...`, a hyphenated
name, confirming the escaping fix generalizes beyond the one dedicated
regression test) -- and that `hatchling/black-26.5.1` and
`setuptools/pytest-asyncio-1.4.0` (both `hatch-vcs`/`setuptools_scm`
dynamic-versioned, unresolvable outside their real git history) cleanly
skip with the expected `WARNING:` instead of producing a fabricated
path.

## Limitations and future work

- `hasDeclaredLicense` and `hasConcludedLicense` currently point to the
  same `SimpleLicensingText` element. The SPDX 3 specification allows
  them to differ (e.g. when multiple declared licences must be concluded
  as a conjunction). Separate handling is deferred to a future version.
- GGUF, Safetensors, ONNX, and most other model formats do not embed a
  machine-readable licence field. Licence data for those models must come
  from an external source such as HuggingFace Hub or a user-supplied
  fragment.
- `licenseid` text detection is probabilistic (threshold 0.85). Unusual
  licence texts or heavily modified standard licences may not be
  detected. Always verify the concluded licence in the SBOM.
- `[project.license-files]` bundling (above) is not resolved for an
  sdist-archive generation target, and does not resolve the legacy
  `[tool.setuptools] license-files` key.

## Related source files

| File | Role |
| :--- | :--- |
| `src/pitloom/extract/_license.py` | `detect_license_from_text()`,
  `find_license_files()`, `detect_license_for_project()`,
  `resolve_license_file_entries()` |
| `src/pitloom/extract/_pyproject.py` | Python project licence
  extraction and detection, including `[project.license-files]` |
| `src/pitloom/extract/hatchling.py` | Hatchling build-hook licence
  extraction, including `[project.license-files]` |
| `src/pitloom/assemble/_generators.py`,
  `src/pitloom/plugins/hatch.py` | Merge `resolve_license_file_entries()`
  results into `project_files` before the file list is finalized |
| `src/pitloom/extract/_setuptools.py` | setuptools project licence
  extraction |
| `src/pitloom/extract/_poetry.py` | Poetry project licence extraction |
| `src/pitloom/extract/_huggingface.py` | HuggingFace Hub card YAML
  and file-based detection |
| `src/pitloom/extract/_pytorch_pt2.py` | PT2 archive `extra/license`
  entry |
| `src/pitloom/core/project.py` | `ProjectMetadata.license_name`,
  `ProjectMetadata.license_files`, `ProjectFile.is_license_file` fields |
| `src/pitloom/core/ai_metadata.py` | `AiModelMetadata.license`
  field |
| `src/pitloom/assemble/spdx3/deps_license.py` | `build_license_elements()`,
  `build_file_declared_license()` shared helpers |
| `src/pitloom/assemble/spdx3/_document_files.py` | `_add_package_files()`,
  `_emit_file_license_relationship()` -- file-level licence wiring |
| `src/pitloom/assemble/spdx3/document.py` | `build()` -- licence wiring
  (`build_model()` moved to `_document_model.py`, re-exported here) |
| `src/pitloom/assemble/spdx3/ai.py` | `add_ai_models()` -- AI model
  licence wiring |
| `src/pitloom/export/spdx3_json.py` | `Spdx3JsonExporter.find_license()`,
  `add_license()` |
| `tests/assemble/test_license_detection.py`,
  `tests/assemble/test_license_normalization.py` | Unit tests for
  `_license.py` utilities (originally `tests/test_license.py`, later
  split -- see `cli-test-coverage-roadmap.md`) |
| `tests/core/generator/test_generator_project_enrichment.py`,
  `tests/core/generator/test_generator_project_structure.py` | End-to-end
  licence export tests with fixture files (originally
  `tests/test_generator.py`, since split by generation target and
  further by section -- see `cli-test-coverage-roadmap.md`) |
| `tests/extract/test_pyproject.py`,
  `tests/extract/test_hatch_hook_metadata.py` | `license_files`
  extraction tests (`_pyproject.py`/`hatchling.py` paths) |
| `tests/assemble/test_license_files_bundling.py` | End-to-end
  `[project.license-files]` bundling tests against the vendored
  real-world fixtures |
