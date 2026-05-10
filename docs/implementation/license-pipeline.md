---
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

1. **Extract** — one or more source-specific extractors read licence
   information from files and remote APIs.
2. **Model** — extracted data is normalised into a format-neutral
   intermediate representation (`ProjectMetadata` or `AiModelMetadata`).
3. **Assemble and export** — the assembler converts the intermediate model
   into SPDX 3 elements and serialises them as JSON-LD.

## Data flow diagram

```text
Source inputs
----------------------------------------------------------------------
pyproject.toml      AI model file     HuggingFace Hub repo
setup.cfg           (PT2 extra/       (model card YAML)
CITATION.cff         license)         (LICENSE file + licenseid)
codemeta.json
LICENSE / LICENCE /
  COPYING file
  (+ licenseid)
      |                  |                    |
      v                  v                    v
----------------------------------------------------------------------
EXTRACT LAYER  (src/pitloom/extract/)
----------------------------------------------------------------------
pyproject.py        _pytorch_pt2.py   _huggingface.py
setuptools.py       (zip entry        +---------------------------+
poetry.py            extra/license)  | 1. card YAML license:     |
                                     |    if vague/missing:       |
_license.py ------------------------ | 2. _detect_license_        |
 detect_license_for_project()        |      from_hf_files()       |
  |- pyproject.toml project.license  |      -> licenseid library  |
  |- CITATION.cff   license:         |         (>=0.85 confidence)|
  |- codemeta.json  license:         +---------------------------+
  +- LICENSE file   (via licenseid)
      |                  |                    |
      v                  v                    v
----------------------------------------------------------------------
FORMAT-NEUTRAL MODEL  (src/pitloom/core/)
----------------------------------------------------------------------
ProjectMetadata               AiModelMetadata
  .license_name: str | None     .license: str | None
  .provenance["license"]: str   .provenance["license"]: str
      |                               |
      v                               v
----------------------------------------------------------------------
ASSEMBLE LAYER  (src/pitloom/assemble/spdx3/)
----------------------------------------------------------------------
document.py build()         document.py build_model()
 main package / deps         standalone AI model
      |                               |
      +---------------+---------------+
                      |
              ai.py add_ai_models()
              deps.py build_license_elements()
                |- reuse SimpleLicensingText if duplicate
                +- else create simplelicensing_SimpleLicensingText
                      |
           +----------+----------+
           v                     v
  Relationship             Relationship
  hasDeclaredLicense       hasConcludedLicense
  (package -> license)     (package -> license)
      |
      v
----------------------------------------------------------------------
EXPORT LAYER  (src/pitloom/export/spdx3_json.py)
----------------------------------------------------------------------
Spdx3JsonExporter.to_json()
  +- JSON-LD graph  (@context + @graph)
       |- simplelicensing_SimpleLicensingText
       |- Relationship  {relationshipType: hasDeclaredLicense}
       +- Relationship  {relationshipType: hasConcludedLicense}
```

## Stage 1: extract

### Python project sources

`src/pitloom/extract/pyproject.py` calls
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

1. **Card YAML** — reads `license:` from the model card frontmatter. If
   the value is not a vague sentinel (`other`, `custom`, `proprietary`,
   `unknown`, `unlicensed`), it is accepted as-is and stored in
   `AiModelMetadata.license`.
2. **File detection** — when the card YAML value is absent or vague,
   `_detect_license_from_hf_files()` iterates through candidate files in
   the repository (`LICENSE`, `LICENCE`, `COPYING`, `NOTICE`, and
   suffixed variants) in priority order. Each file is downloaded via
   `hf_hub_download` and its text is passed to `detect_license_from_text()`
   from the `licenseid` library. The first match above the 0.85 confidence
   threshold is accepted. The original vague card value is preserved in
   `extra_data["hf.license_raw"]` for auditability.

### `licenseid` dependency

Text-based licence detection (`detect_license_from_text()` in
`_license.py`) relies on the optional `licenseid` package. When the
package is not installed or its database has not been built, detection
is silently skipped and the function returns `None`. To enable it:

```shell
pip install pitloom[license]
licenseid update
```

The database is stored at
`~/.local/share/licenseid/licenses.db`. Detection uses cosine similarity
against vectorised licence texts with a default threshold of 0.85.

## Stage 2: format-neutral model

After extraction, licence data lives in one of two dataclasses:

- `ProjectMetadata.license_name: str | None` — for Python projects.
- `AiModelMetadata.license: str | None` — for AI model files and
  HuggingFace Hub models.

Both carry a `provenance: dict[str, str]` where the `"license"` key
records a human-readable source description, for example:

```
Source: pyproject.toml | Field: project.license
Source: Hugging Face Hub | File: LICENSE | Method: licenseid_detection
Source: model.pt2 | Field: extra/license
```

## Stage 3: assemble and export

### `build_license_elements()` — `assemble/spdx3/deps.py`

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
   - `hasDeclaredLicense` — the licence declared in the software
     artefact itself.
   - `hasConcludedLicense` — the licence as concluded by the SBOM
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

## Related source files

| File | Role |
| :--- | :--- |
| `src/pitloom/extract/_license.py` | `detect_license_from_text()`,
  `find_license_files()`, `detect_license_for_project()` |
| `src/pitloom/extract/pyproject.py` | Python project licence
  extraction and detection |
| `src/pitloom/extract/setuptools.py` | setuptools project licence
  extraction |
| `src/pitloom/extract/poetry.py` | Poetry project licence extraction |
| `src/pitloom/extract/_huggingface.py` | HuggingFace Hub card YAML
  and file-based detection |
| `src/pitloom/extract/_pytorch_pt2.py` | PT2 archive `extra/license`
  entry |
| `src/pitloom/core/project.py` | `ProjectMetadata.license_name`
  field |
| `src/pitloom/core/ai_metadata.py` | `AiModelMetadata.license`
  field |
| `src/pitloom/assemble/spdx3/deps.py` | `build_license_elements()`
  shared helper |
| `src/pitloom/assemble/spdx3/document.py` | `build()` and
  `build_model()` — licence wiring |
| `src/pitloom/assemble/spdx3/ai.py` | `add_ai_models()` — AI model
  licence wiring |
| `src/pitloom/export/spdx3_json.py` | `Spdx3JsonExporter.find_license()`,
  `add_license()` |
| `tests/test_license.py` | Unit tests for `_license.py` utilities |
| `tests/test_generator.py` | End-to-end licence export tests with
  fixture files |
