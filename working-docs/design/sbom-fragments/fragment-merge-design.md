---
Created: 2026-04-13
Last-Modified: 2026-08-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM fragments: core design (merge, config, CLI)

See also [README.md](README.md) (index),
[loom-sdk-and-notebooks.md](loom-sdk-and-notebooks.md),
[extractor-integrations.md](extractor-integrations.md),
[roadmap-and-resources.md](roadmap-and-resources.md).

Split from this directory's former single `sbom-fragments.md`
(2026-08-25) -- this file covers the fragment mechanism itself:
vocabulary, current gaps in fragment declaration/assembly, the
redesigned config and merge protocol, `DocumentModel` extensions, and
CLI tooling. SDK/notebook and extractor-specific gaps and designs live
in the sibling files above.

## Problem statement

Not every component of a software system can be described in a single SBOM
generated at one point in time, by one team, from one build.

A real AI system is assembled from parts with very different origins and
lifecycles:

- A foundation model trained months ago by a separate team, who can supply
  their own SBOM fragment covering training data, hyperparameters, and
  evaluation results.
- A binary executable or compiled library whose source code is not available
  to the integrator; only a pre-built artifact and a partner-supplied SBOM.
- Datasets that are incrementally curated, filtered, and assembled inside
  interactive notebooks over weeks, with each session adding or refining
  documentation.
- Fine-tuned models where the fine-tuning run is tracked in MLflow or W&B
  Weave, and that tracking record is the authoritative source of truth.
- Third-party components shipped with their own SBOM by the upstream vendor.

The core challenge is that **SBOM information is distributed across time,
teams, tools, and ownership boundaries**. Pitloom's fragment system is the
mechanism for collecting and composing these partial records into a coherent,
compliant, final SBOM.

---

## Vocabulary alignment with existing standards

Before designing APIs and data structures, it is important to use language that
aligns with existing standards so that adopters can relate Pitloom's concepts
to what they already know.

### SPDX 3 terminology

SPDX 3 does not define a formal "fragment" type. The specification uses a
graph of `Element` objects, all of which can be part of any document. A single
`SpdxDocument` points to one or more `rootElement` entries; these root
elements may in turn contain or relate to any number of other elements.

The relevant composition mechanisms in SPDX 3 are:

- **`software_Sbom`** -- a typed collection of SPDX elements describing a
  specific artifact. Multiple `software_Sbom` objects can exist within
  one `SpdxDocument`.
- **`SpdxDocument.imports`** -- an `ExternalMap` allowing a document to
  formally declare dependencies on other SPDX documents by their namespace
  URI, enabling verified cross-document references.
- **Element identity** -- every element has a `spdxId` URI. Elements in
  different documents may safely overlap in the graph if their IDs are
  globally unique.

In Pitloom, a **fragment** is an independently-generated set of SPDX 3
elements (typically one `software_Sbom` element and its related elements)
that is produced outside the main build process and later merged into the
primary SBOM document.

### CycloneDX terminology

CycloneDX addresses composition via:

- **BOM-Link** -- a URI scheme (`urn:cdx:bomSerialNumber/version#componentRef`)
  that allows one BOM to reference a component or the entirety of another BOM
  document, preserving organizational boundaries without embedding the full
  content.
- **Assemblies** -- nested `component` entries that describe sub-assemblies,
  mapping directly to the multi-team ownership scenario.
- **Compositions** -- formal declarations of how complete or incomplete a BOM
  section is (e.g., `complete`, `incomplete`, `incomplete_first_party_only`).

The `compositions` concept is particularly valuable for Pitloom: it lets
producers declare honestly that a fragment covers only part of a component,
without requiring the whole component to be described before shipping.

### CISA / NTIA guidance

The CISA **SBOM Sharing Lifecycle Report** (2023) defines three roles that
map directly to Pitloom's fragment use cases:

| CISA role | Pitloom mapping |
| :---- | :---- |
| **Author** | Team that generates the fragment (e.g., model team, dataset team) |
| **Distributor** | CI/CD pipeline or artifact registry that passes fragments downstream |
| **Consumer** | The final build (Pitloom's `merge_fragments`) that assembles the product SBOM |

NTIA's **Minimum Elements for SBOM** (2021, updated 2025 by CISA) require
that composed SBOMs preserve supplier information, component names and
versions, cryptographic hashes, and known relationships. The updated 2025
elements also require dependency relationship declarations and build
environment information -- all of which are relevant to fragment content.

### Adopted Pitloom vocabulary

| Term | Definition |
| :---- | :---- |
| **Fragment** | A standalone, independently-generated SPDX 3 JSON-LD file covering a specific component or aspect (AI model, dataset, binary, build environment). May be incomplete (not all fields known). |
| **Composite SBOM** | The final assembled SBOM produced at build time by merging the project's own SBOM with all configured fragments. |
| **Fragment author** | The team, tool, or workflow that produced the fragment. |
| **Fragment role** | The SBOM type covered: `ai`, `build`, `dataset`, `software`, or `source`. Maps to `software_SbomType`. |
| **Component BOM** | A fragment whose scope is a single well-identified component (e.g., one AI model, one binary library). |
| **Provenance chain** | The linked sequence of fragments, relationships, and annotations that together trace a component from its origin to its deployment. |

---

## Current implementation gaps

The following gaps are identified in the existing Pitloom fragment system,
relative to the requirements above.

### 1. Fragment declaration: flat list, no metadata

`PitloomConfig.fragments` is a `list[str]` of file paths. There is no way
to declare:

- What role the fragment plays (AI, dataset, build, …).
- Whether the fragment is required or optional.
- A human-readable description of what it covers.
- Who authored it and when.
- A content hash for integrity verification.
- A relationship type connecting the fragment's root element to the
  project's main package.

### 2. Fragment assembly: no conflict resolution or deduplication

> **Status (2026-07): largely implemented.** `merge_fragments`
> (`src/pitloom/assemble/spdx3/fragments.py`) now unifies elements across
> fragments and the main document by (in priority order) shared `spdxId`,
> SHA-256 content equality (`verifiedUsing`), and structural equality
> modulo id for `Agent`/`Tool` -- never by name alone. Fragment
> `SpdxDocument`/`software_Sbom` envelopes are dropped, references
> remapped, duplicate relationships removed, `profileConformance` updated,
> and a second `software_Sbom` rooted at the merged `ai_AIPackage` added.
> Cross-fragment id stability comes from the `loom-ids.json` registry
> (`src/pitloom/ids.py`, `pitloom ids generate|import`), consulted by
> `pitloom.loom`, the build hook, and the CLI. `SpdxDocument.imports` is
> now populated too (`_add_fragment_imports()`, one `ExternalMap` per
> merged fragment's document id), and the merged graph's referential
> integrity is checked afterward (`_raise_on_dangling_references()`,
> raises `FragmentMergeError` on any `Relationship`/`Annotation` endpoint
> that resolves to neither a local object nor a declared `imports` entry).
> Pre-ingestion validation (checking a fragment file before merging, e.g.
> schema/hash checks ahead of time rather than catching brokenness only
> after the merge) remains open.

The original gap description below is kept for context.
`merge_fragments` iterated fragment object sets and called
`exporter.object_set.add()` for each object. That approach:

- Does not detect or resolve duplicate `spdxId` values across fragments.
- Does not deduplicate semantically equivalent elements (same package, same
  version, different UUID-based IDs) from independent fragments.
- Does not record a `SpdxDocument.imports` entry for each merged fragment,
  which would be required for full SPDX 3 compliance when fragments originate
  from separate namespaces.
- Does not validate fragment structure before ingestion.
- Does not link the fragment's root element to the project's main package via
  an explicit SPDX relationship.
- Does not produce any merge summary visible to the user (what was added,
  what was skipped, what failed).

## Redesigned fragment configuration

### Structured fragment declaration in `pyproject.toml`

Replace the flat `list[str]` with a list of structured fragment descriptors:

```toml
# Minimal form -- backward-compatible; role defaults to "software"
[tool.pitloom]
fragments = ["fragments/legacy.spdx3.json"]

# Recommended structured form
[[tool.pitloom.fragments]]
path = "fragments/model-bert-v3.spdx3.json"
role = "ai"
description = "BERT fine-tune training provenance from MLflow run bert-v3"
required = false
sha256 = "a3f1..."           # optional: verify integrity before merge
link_to_main = "trainedOn"  # SPDX relationship type to the main package

[[tool.pitloom.fragments]]
path = "fragments/training-dataset.spdx3.json"
role = "dataset"
description = "Curated multilingual NLI dataset, assembled in notebook"
required = false

[[tool.pitloom.fragments]]
path = "fragments/libssl-vendor.spdx3.json"
role = "software"
description = "Vendor-supplied SBOM for bundled libssl 3.2.1"
required = true             # build fails if this fragment is missing
sha256 = "b7e2..."
```

### Updated `PitloomConfig` data model

```python
@dataclass
class FragmentConfig:
    """Configuration for a single SBOM fragment source.

    Attributes:
        path: Path to the fragment file, relative to the project directory.
        role: SBOM type this fragment covers. Maps to software_SbomType.
            One of: "ai", "build", "dataset", "software", "source".
            Defaults to "software".
        description: Human-readable description of what the fragment covers.
        required: If True, a missing fragment aborts the build.
            Defaults to False (warning only).
        sha256: Optional expected SHA-256 hex digest of the fragment file.
            When set, Pitloom verifies integrity before merging.
        link_to_main: Optional SPDX relationship type to emit between the
            fragment's root element and the project's main package element.
            E.g., "trainedOn", "usedBy", "contains", "dependsOn".
    """

    path: str
    role: str = "software"
    description: str | None = None
    required: bool = False
    sha256: str | None = None
    link_to_main: str | None = None
```

A backward-compatible loader will accept both the old `list[str]` form
(converting each string to `FragmentConfig(path=s)`) and the new table form.

---

## Redesigned fragment assembly

### Merge protocol

1. **Pre-merge validation** -- for each configured fragment:
   - Check file existence; if missing and `required=True`, raise; if `False`,
     log warning and skip.
   - If `sha256` is set, verify the file hash matches.
   - Parse the JSON-LD and validate it is a valid SPDX 3 document (using
     `spdx3-validate`'s library API -- `spdx3_validate.validate()`,
     available since `spdx3-validate` v0.0.7 -- or the built-in
     `JSONLDDeserializer` + schema check).
   - Log a structured merge summary entry (path, element count, validation
     result).

2. **Namespace-aware element ingestion** -- for each element in the fragment:
   - If the element's `spdxId` already exists in the main object set,
     log a warning and skip (first-writer-wins). Future enhancement:
     implement merge-by-identity using PURL or hash comparison.
   - Otherwise, add the element to the main object set.

3. **Fragment-to-main relationship** -- if `link_to_main` is set and the
   fragment contains a `software_Sbom` or a root element identifiable via
   the fragment's `rootElement` list, emit an SPDX `Relationship` from the
   project's main package to the fragment's root element using the specified
   relationship type.

4. **External document reference** -- for each successfully merged fragment,
   add an `ExternalMap` entry to `SpdxDocument.imports` recording the
   fragment's namespace URI and integrity checksum.

5. **Merge summary** -- after all fragments are processed, emit a structured
   log entry (or write to a sidecar `.merge-report.json`) listing:
   - Fragment path, role, element count, relationships added.
   - Skipped element count and reason (duplicate IDs).
   - Failed fragments and error messages.

### Updated `merge_fragments` signature

```python
def merge_fragments(
    project_dir: Path,
    fragments: list[FragmentConfig],  # replaces list[str]
    exporter: Spdx3JsonExporter,
    main_package_spdx_id: str,
    spdx_document: spdx3.SpdxDocument,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
) -> list[FragmentMergeResult]:
    """Load, validate, and merge SPDX 3 fragment files into the exporter."""
```

---

## CLI tooling

The Pitloom CLI (`python -m pitloom`) gains a `fragment` subcommand group:

```text
pitloom fragment init   --role ai --output fragments/model.spdx3.json
pitloom fragment validate  fragments/model.spdx3.json
pitloom fragment merge  --dry-run          # preview merge without building
pitloom fragment list                       # list configured fragments + status
pitloom fragment sign   fragments/model.spdx3.json   # compute SHA-256 + write to config
```

| Command | Purpose |
| :---- | :---- |
| `fragment init` | Generate a skeleton fragment JSON-LD for the given role. Prompts for name, version, author. |
| `fragment validate` | Validate a fragment file via `spdx3-validate`'s library API (`spdx3_validate.validate()`); report errors and warnings. |
| `fragment merge --dry-run` | Simulate the full build-time merge without writing wheel output. Print the merge report. |
| `fragment list` | Read `pyproject.toml`, list each configured fragment with: path, role, exists?, last-modified, element count (if parseable), sha256 match. |
| `fragment sign` | Compute SHA-256 of a fragment file and write it back to the matching entry in `[tool.pitloom.fragments]`. |

---

## `DocumentModel` extensions

The format-neutral `DocumentModel` should gain a `fragments` field to make
fragment metadata available to assemblers without re-reading the config:

```python
@dataclass
class DocumentModel:
    project: ProjectMetadata
    creation_metadata: CreationMetadata = field(default_factory=CreationMetadata)
    ai_models: list[AiModelMetadata] = field(default_factory=list)
    fragments: list[FragmentConfig] = field(default_factory=list)  # NEW
```

This lets the SPDX 3 assembler emit `SpdxDocument.imports` entries
for each successfully merged fragment, and lets future CycloneDX or
AIDOC assemblers reference the same fragment metadata without reading
`pyproject.toml` again.
