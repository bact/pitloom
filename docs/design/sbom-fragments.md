---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM fragments: design, standards alignment, and integration plan

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

- **`software_Sbom`** — a typed collection of SPDX elements describing a
  specific artifact. Multiple `software_Sbom` objects can exist within
  one `SpdxDocument`.
- **`SpdxDocument.imports`** — an `ExternalMap` allowing a document to
  formally declare dependencies on other SPDX documents by their namespace
  URI, enabling verified cross-document references.
- **Element identity** — every element has a `spdxId` URI. Elements in
  different documents may safely overlap in the graph if their IDs are
  globally unique.

In Pitloom, a **fragment** is an independently-generated set of SPDX 3
elements (typically one `software_Sbom` element and its related elements)
that is produced outside the main build process and later merged into the
primary SBOM document.

### CycloneDX terminology

CycloneDX addresses composition via:

- **BOM-Link** — a URI scheme (`urn:cdx:bomSerialNumber/version#componentRef`)
  that allows one BOM to reference a component or the entirety of another BOM
  document, preserving organizational boundaries without embedding the full
  content.
- **Assemblies** — nested `component` entries that describe sub-assemblies,
  mapping directly to the multi-team ownership scenario.
- **Compositions** — formal declarations of how complete or incomplete a BOM
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
environment information — all of which are relevant to fragment content.

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

`merge_fragments` iterates fragment object sets and calls `exporter.object_set.add()`
for each object. This approach:

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

### 3. `loom.py` SDK: sparse API surface

The current `Shoot` context manager supports only `set_model` and
`add_dataset`. This is far less expressive than ML tracking SDKs that
practitioners already use daily. Key missing capabilities:

- No equivalent of `log_param` / `log_metric` / `log_tag` / `log_artifact`.
- No incremental / accumulative recording suitable for notebooks
  (running a cell multiple times should append, not overwrite).
- No Jupyter integration (IPython magic commands, cell-level provenance).
- No serialisation of individual dataset elements with schema, provenance,
  or curation notes.
- No model evaluation / scoring records.
- Error is raised if `loom.*` functions are called outside a `Shoot` block;
  notebook workflows need a more lenient persistent-session mode.

### 4. No W&B Weave integration

W&B Weave captures automatic execution traces, versioned model objects,
versioned dataset objects, and structured evaluation results — all of which
map cleanly to SPDX 3 AI and Dataset profile elements. There is currently no
extractor for Weave, even though it is rapidly becoming the primary tracking
layer for LLM-based applications.

### 5. No DVC integration

DVC tracks data and model files via metafiles committed to Git. The
`dvc.yaml` pipeline graph and `.dvc` content-addressed pointers are rich
provenance sources for dataset and model file elements in SPDX.

### 6. No Jupyter / notebook recording mode

Interactive notebooks build up knowledge about a dataset or model
incrementally. There is no mechanism to accumulate BOM records across
multiple notebook cells or sessions, nor to attach cell-level provenance
to SPDX elements. Existing research tools such as ProvBook and MLProvLab
demonstrate demand for this capability, but use RDF-based ontologies
(REPRODUCE-ME, PROV-O, P-Plan) rather than SPDX, leaving a gap that
Pitloom can fill.

---

## Redesigned fragment configuration

### Structured fragment declaration in `pyproject.toml`

Replace the flat `list[str]` with a list of structured fragment descriptors:

```toml
# Minimal form — backward-compatible; role defaults to "software"
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

1. **Pre-merge validation** — for each configured fragment:
   - Check file existence; if missing and `required=True`, raise; if `False`,
     log warning and skip.
   - If `sha256` is set, verify the file hash matches.
   - Parse the JSON-LD and validate it is a valid SPDX 3 document (using
     `spdx3-validate` or the built-in `JSONLDDeserializer` + schema check).
   - Log a structured merge summary entry (path, element count, validation
     result).

2. **Namespace-aware element ingestion** — for each element in the fragment:
   - If the element's `spdxId` already exists in the main object set,
     log a warning and skip (first-writer-wins). Future enhancement:
     implement merge-by-identity using PURL or hash comparison.
   - Otherwise, add the element to the main object set.

3. **Fragment-to-main relationship** — if `link_to_main` is set and the
   fragment contains a `software_Sbom` or a root element identifiable via
   the fragment's `rootElement` list, emit an SPDX `Relationship` from the
   project's main package to the fragment's root element using the specified
   relationship type.

4. **External document reference** — for each successfully merged fragment,
   add an `ExternalMap` entry to `SpdxDocument.imports` recording the
   fragment's namespace URI and integrity checksum.

5. **Merge summary** — after all fragments are processed, emit a structured
   log entry (or write to a sidecar `.merge-report.json`) listing:
   - Fragment path, role, element count, relationships added.
   - Skipped element count and reason (duplicate IDs).
   - Failed fragments and error messages.

### Updated `merge_fragments` signature

```python
def merge_fragments(
    project_dir: Path,
    fragments: list[FragmentConfig],   # replaces list[str]
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

## Enhanced `loom.py` SDK

### Design goals

The redesigned SDK should feel familiar to practitioners who already use
MLflow, W&B, or Weave — using the same vocabulary where possible — while
emitting SPDX 3 elements rather than metrics records.

The API adopts the MLflow `log_*` naming convention because it is widely
understood and directly maps to the double-instrumentation problem described
in `docs/design/mlflow-extractor.md`.

### Proposed public API

```python
from pitloom import loom

# --- Context-managed fragment recording (existing, enhanced) ---
with loom.shoot("fragments/bert-v3.spdx3.json") as shot:
    shot.set_model("my-bert", type_of_model="transformer")

    # MLflow-compatible logging functions
    shot.log_param("learning_rate", 3e-4)
    shot.log_param("batch_size", 32)
    shot.log_metric("accuracy", 0.91)
    shot.log_metric("f1_score", 0.88)
    shot.log_tag("domain", "natural_language_processing")
    shot.log_tag(stav.INFO_TRAINING, "Fine-tuned on FLORES-200")

    # Dataset documentation
    ds = shot.add_dataset("flores-200", dataset_type="text")
    ds.set_size(rows=5_000_000)
    ds.set_license("CC-BY-4.0")
    ds.set_source_url("https://huggingface.co/datasets/facebook/flores")
    ds.set_preprocessing("tokenized, lowercased, de-duplicated")
    ds.log_tag("language_count", "200")

    # Evaluation results (maps to SPDX Annotation)
    shot.log_evaluation("flores-dev", {"accuracy": 0.91, "bleu": 42.3})

# --- Persistent session mode (for notebooks) ---
loom.start_session("fragments/notebook-run.spdx3.json")

# ... cell 1 ...
loom.set_model("incremental-model", type_of_model="classifier")
loom.log_param("epochs", 10)

# ... cell 2 (appends to same session) ...
loom.log_metric("accuracy", 0.85)
loom.add_dataset("my-dataset", dataset_type="tabular")

# ... cell N (explicit save / auto-saved on kernel shutdown) ...
loom.save_session()
loom.end_session()
```

### Accumulation mode for notebooks

The persistent session is backed by an `_ActiveSession` object (distinct
from `_ActiveShot`) that persists in module-level state and writes a
checkpoint file to disk on each `loom.save_session()` call. If the kernel
restarts, `loom.resume_session("fragments/notebook-run.spdx3.json")` reads
the last checkpoint and continues accumulating.

Key difference from `Shoot`: a session does **not** discard partial output
on exception; it preserves whatever has been recorded up to the crash.

### IPython magic integration

```python
# In a Jupyter notebook cell:
%load_ext pitloom.loom.magic

%%pitloom_record model=my-bert role=ai output=fragments/cell3.spdx3.json
learning_rate = 3e-4
epochs = 5
# Cell body executed normally; pitloom captures locals() as log_param entries
# and writes a fragment on cell completion.
```

The `%%pitloom_record` cell magic:

- Captures all assigned scalar variables as `log_param` entries.
- Records the cell source code as a `comment` on the fragment.
- Records the notebook file name and cell index as provenance.
- On error, writes a partial fragment tagged `status=error`.

---

## W&B Weave extractor

### Why Weave is significant

W&B Weave ([github.com/wandb/weave](https://github.com/wandb/weave)) is a
next-generation tracing layer specifically designed for LLM-based
applications. Unlike MLflow's run-centric model or W&B's artifact-centric
model, Weave captures the **full call graph** of an AI application —
automatically, via function decoration — including:

- All inputs and outputs to every decorated function (`@weave.op()`).
- Model versioning based on code hash (a new version is created whenever
  the function body changes).
- Dataset object versioning with row-level identity.
- Structured evaluation results linking a specific model version to a
  specific dataset version, with per-scorer metrics.
- Parent/child relationships between nested calls (execution traces).

This call graph structure maps with high fidelity to SPDX 3 elements:
SPDX relationships capture the `from/to` structure of Weave's trace tree;
SPDX `Annotation` elements carry evaluation metrics; `software_Sbom`
elements group the Model + Dataset + Evaluation into a coherent AI BOM.

### Object mapping

| Weave concept | SPDX 3.0 element / field |
| :---- | :---- |
| `weave.Model` + version hash | `ai_AIPackage` with `software_packageVersion` = Weave version URI |
| `weave.Dataset` + version | `dataset_DatasetPackage` with `ExternalRef` to Weave ref URI |
| `weave.Evaluation` result | `Annotation` elements attached to `ai_AIPackage` |
| `@weave.op()` call inputs | `ai_hyperparameter` (training-time params) |
| `@weave.op()` call outputs | `comment` with structured output summary |
| `weave.ref(...)` URI | `software_downloadLocation` or `ExternalRef` |
| Trace `trace_id` + `parent_id` | SPDX `Relationship` (`generatedFrom`, `usedBy`) |
| Token usage metadata | `ai_energyConsumption` (inference cost) or `Annotation` |

### Extractor design: `pitloom.extract.weave`

```python
class WeaveExtractor:
    """Extracts SPDX 3 AI BOM metadata from a W&B Weave project.

    Args:
        project: Weave project reference ("entity/project").
        model_ref: Specific model ref URI or name:version string.
        evaluation_ref: Optional evaluation ref to include metrics.
        api_key: Optional W&B API key. Uses WANDB_API_KEY env var if unset.
    """

    def extract(self) -> WeaveRunMetadata: ...
    def to_fragment(self, output_file: str | Path | None = None) -> str: ...
```

```python
# loom.py public API addition
def from_weave_model(
    model_ref: str,
    project: str,
    output_file: str | Path,
    evaluation_ref: str | None = None,
    api_key: str | None = None,
) -> None:
    """Generate an SPDX fragment from a W&B Weave model object."""
```

The extractor accesses Weave via the `weave` Python client, which is
available as `pip install weave`. The `WANDB_API_KEY` environment variable
provides authentication. All Weave imports are lazy (deferred inside
functions) to keep the optional-dependency pattern consistent.

### Weave-specific provenance patterns

Weave model versions use content-addressed URIs:
`weave:///entity/project/object/ModelName:abc123def456`

This URI is a natural fit for `software_downloadLocation` on
`ai_AIPackage` — it is both a stable reference and an integrity signal
(the hash is part of the URI). The full Weave trace URL provides a
navigable link back to the execution record in the W&B UI.

---

## DVC integration

DVC ([dvc.org](https://dvc.org)) tracks data files and ML models via small
metafiles (`.dvc`, `dvc.lock`) committed to Git. The `dvc.yaml` file
defines a pipeline of stages, each with declared inputs (`deps`),
outputs (`outs`), and commands.

### What DVC provides for SBOMs

| DVC artefact | SBOM value |
| :---- | :---- |
| `.dvc` file (content hash + remote path) | Dataset `verifiedUsing` hash + `downloadLocation` |
| `dvc.yaml` stage definition | Build step provenance (command, inputs, outputs) |
| `dvc.lock` (frozen deps + hashes) | Deterministic, auditable dataset/model ancestry |
| DVC remote URL | `ExternalRef` pointing to the remote storage location |
| Git commit where `.dvc` was modified | Timestamp and version anchor for `createdTime` |

### Extractor design: `pitloom.extract.dvc`

```python
class DvcExtractor:
    """Reads dvc.yaml and dvc.lock to extract dataset and model provenance.

    Args:
        project_dir: Root of the DVC repository.
        stage: Specific stage name to extract (e.g., "train"). If None,
            extracts all stages and their outputs.
    """

    def extract(self) -> list[DatasetMetadata | AiModelMetadata]: ...
```

The extractor reads `dvc.lock` (the frozen, hash-committed view of the
pipeline) rather than `dvc.yaml` (the mutable intent) to ensure that the
SBOM reflects the actual data used, not just what was planned.

---

## Jupyter / notebook integration

### Notebook provenance challenge

Notebooks execute cells in user-defined order, re-execute cells, and may
run for hours. The SBOM recording challenge is that:

- There is no single "entry point" or "build step" to hook into.
- Each "training run" may span multiple cells with intermediate checkpoints.
- The user wants to accumulate BOM notes incrementally, correcting or
  supplementing earlier cells as understanding evolves.
- The final fragment should reflect the *intention* of the complete session,
  not just the last state of every variable.

### Approach: persistent session with manual checkpoints

The `loom.start_session()` / `loom.end_session()` API (described under the
SDK redesign above) is the primary mechanism. The session writes a checkpoint
JSON on every `loom.save_session()` call; the IPython magic `%%pitloom_record`
triggers an implicit checkpoint.

Additionally, Pitloom can read existing provenance captured by ProvBook
(which stores REPRODUCE-ME RDF in notebook cell metadata) and translate it
to SPDX elements, bridging the RDF-based provenance research community with
the SBOM community.

### Auto-capture of the notebook environment

When a Pitloom session is active inside a Jupyter kernel, Pitloom can
optionally capture:

- The list of installed packages at session start (via `importlib.metadata`).
- The Python version and platform.
- The notebook file name and path (via `ipykernel` / `IPython.display`).
- The kernel start time.

These are emitted as a `build_BuildEnvironment` element (SPDX 3 Build
profile) and a `software_Sbom` with `software_sbomType = runtime`,
linking to the notebook file as a `software_File` element.

### Notebook file as a `software_File` element

When the session ends and the output path is configured, Pitloom creates
a `software_File` element for the notebook file itself (`.ipynb`), with:

- `verifiedUsing`: SHA-256 hash of the notebook at session end.
- `software_fileKind`: `file`.
- An SPDX `Relationship` of type `generatedFrom` from the model/dataset
  element to the notebook file element.

This makes the notebook a first-class provenance artefact in the SBOM,
satisfying transparency requirements for AI systems under the EU AI Act
(which requires documentation of training procedures and data sources).

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
| `fragment validate` | Run `spdx3-validate` against a fragment file; report errors and warnings. |
| `fragment merge --dry-run` | Simulate the full build-time merge without writing wheel output. Print the merge report. |
| `fragment list` | Read `pyproject.toml`, list each configured fragment with: path, role, exists?, last-modified, element count (if parseable), sha256 match. |
| `fragment sign` | Compute SHA-256 of a fragment file and write it back to the matching entry in `[tool.pitloom.fragments]`. |

---

## Integration with MLflow (existing design, updates)

See `docs/design/mlflow-extractor.md` for the full MLflow extractor design.

Updates motivated by this document:

1. **Dataset references from MLflow runs** — MLflow 2.x supports
   `mlflow.log_input(mlflow.data.from_pandas(...))` to log dataset provenance
   per run. The MLflow extractor should read `run.inputs.dataset_inputs` and
   emit `dataset_DatasetPackage` elements linked via `trainedOn` / `testedOn`
   relationships. This eliminates manual `add_dataset` calls in most workflows.

2. **MLflow Model Registry** — a registered model version in the Model Registry
   has a `model_uri` (`models:/name/version` or `runs:/run_id/artifacts/model`).
   This URI maps to `software_downloadLocation` on `ai_AIPackage`.
   The `MlflowExtractor` should accept a registered model version reference
   as an alternative to a raw run ID.

3. **Artifact logging** — `mlflow.log_artifact(path)` uploads files.
   Large non-model artifacts (dataset files, evaluation outputs) could be
   translated to `software_File` elements with `verifiedUsing` checksums
   if MLflow stores the artifact hash (it does in MLflow 2.9+).

---

## `DocumentModel` extensions

The format-neutral `DocumentModel` should gain a `fragments` field to make
fragment metadata available to assemblers without re-reading the config:

```python
@dataclass
class DocumentModel:
    project: ProjectMetadata
    creation: CreationMetadata = field(default_factory=CreationMetadata)
    ai_models: list[AiModelMetadata] = field(default_factory=list)
    fragments: list[FragmentConfig] = field(default_factory=list)  # NEW
```

This lets the SPDX 3 assembler emit `SpdxDocument.imports` entries
for each successfully merged fragment, and lets future CycloneDX or
AIDOC assemblers reference the same fragment metadata without reading
`pyproject.toml` again.

---

## Implementation roadmap

The work is ordered by user-impact priority. No item depends on completing
all earlier items; each can be delivered independently.

### Phase 1: Structural improvements (high impact, low effort)

1. **`FragmentConfig` data class** — replace `list[str]` in `PitloomConfig`.
   Loader remains backward-compatible with plain strings.
2. **`merge_fragments` rewrite** — add pre-merge validation, duplicate-ID
   detection, link-to-main relationship emission, and merge report logging.
3. **`fragment list` CLI command** — cheapest way to surface fragment status
   to developers; reads config and checks file existence + parse validity.
4. **SHA-256 verification in merge** — add `fragment sign` CLI command +
   hash check on merge.

### Phase 2: SDK improvements (notebook and ML workflow ergonomics)

1. **`log_param`, `log_metric`, `log_tag` on `_ActiveShot`** — expands the
   existing `Shoot` API without breaking changes.
2. **`add_dataset` builder object** — replace the current `add_dataset(name,
   type)` with a fluent builder that supports `set_size`, `set_license`, etc.
3. **`log_evaluation` on `_ActiveShot`** — maps to SPDX `Annotation` elements.
4. **Persistent session mode** — `loom.start_session()` / `loom.end_session()`.
5. **IPython magic** — `%%pitloom_record` cell magic; optional, only activated
   if `ipython` is installed.

### Phase 3: New extractors

1. **MLflow dataset input extraction** — read `run.inputs.dataset_inputs`;
   update `MlflowExtractor.extract()`.
2. **W&B Weave extractor** — `pitloom.extract.weave.WeaveExtractor`; add
   `loom.from_weave_model()` to public API; add `weave` optional-dependency
   group to `pyproject.toml`.
3. **DVC extractor** — `pitloom.extract.dvc.DvcExtractor`; reads `dvc.lock`;
   emits `dataset_DatasetPackage` elements with content hashes.

### Phase 4: Compliance and interoperability

1. **`SpdxDocument.imports` population** — add `ExternalMap` entries for
   each merged fragment in the assembler.
2. **CycloneDX BOM-Link emission** — when the CycloneDX assembler is
   implemented, emit `bom-link` references for fragments instead of
   inlining all elements.
3. **`fragment validate` CLI command** — wraps `spdx3-validate`; clear
   error messages with line numbers.
4. **Fragment completeness declaration** — add a `completeness` field to
   `FragmentConfig` (values: `complete`, `incomplete`, `unknown`) that
   maps to CycloneDX `compositions` and is emitted as an SPDX `Annotation`
   on the fragment's `software_Sbom` element.

---

## Existing tools and community resources

The following tools and communities are directly relevant to Pitloom's
fragment work and should be monitored for alignment opportunities.

| Tool / resource | Relevance |
| :---- | :---- |
| [CycloneDX BOM-Link](https://cyclonedx.org/capabilities/bomlink/) | Cross-BOM reference standard; model Pitloom's external fragment reference on this |
| [CISA SBOM Sharing Lifecycle](https://www.cisa.gov/sites/default/files/2023-04/sbom-sharing-lifecycle-report_508.pdf) | Author/Distributor/Consumer roles; use to frame the multi-team workflow |
| [NTIA / CISA Minimum Elements 2025](https://www.cisa.gov/sites/default/files/2025-08/2025_CISA_SBOM_Minimum_Elements.pdf) | Required fields for composed SBOMs |
| [OpenChain AI SBOM Guide](https://github.com/OpenChain-Project/Reference-Material/blob/master/AI-SBOM-Compliance/en/Artificial-Intelligence-System-Bill-of-Materials-Compliance-Management-Guide.md) | AI-specific SBOM requirements; compliance checklist |
| [SPDX spdx-spec#1362](https://github.com/spdx/spdx-spec/issues/1362) | Open issue on canonical serialization; track for updates affecting fragment merging |
| [W&B Weave](https://github.com/wandb/weave) | LLM tracing and evaluation; target for Phase 3 extractor |
| [DVC](https://dvc.org) | Data/model versioning with reproducible pipelines; target for Phase 3 extractor |
| [ProvBook](https://github.com/Sheeba-Samuel/ProvBook) | Jupyter provenance via REPRODUCE-ME ontology; possible bridge to Pitloom notebook mode |
| [MLProvLab](https://github.com/fusion-jena/MLProvCodeGen) | JupyterLab ML provenance extension; inspiration for `%%pitloom_record` magic |
| [AIMMX](https://github.com/IBM/AIMMX) | AI model metadata extraction at repository level; comparable to Pitloom's AI extractor |
| [Parlay](https://github.com/snyk/parlay) | SBOM enrichment from third-party sources; inspiration for Pitloom's enrichment layer |
| [spdx3-validate](https://pypi.org/project/spdx3-validate/) | Used in `fragment validate` and pre-merge validation |
| [STAV](https://github.com/bact/stav) | Shared vocabulary for AI SBOM tags; already used in MLflow extractor |

---

## References

- CISA. 2023. "SBOM Sharing Lifecycle Report."
  <https://www.cisa.gov/sites/default/files/2023-04/sbom-sharing-lifecycle-report_508.pdf>.
- CISA. 2025. "2025 Minimum Elements for a Software Bill of Materials (SBOM)."
  <https://www.cisa.gov/sites/default/files/2025-08/2025_CISA_SBOM_Minimum_Elements.pdf>.
- CycloneDX. 2024. "BOM-Link."
  <https://cyclonedx.org/capabilities/bomlink/>.
- Linux Foundation AI & Data. 2024.
  "SPDX AI Bill of Materials (AI BOM) with SPDX 3.0."
  <https://www.linuxfoundation.org/research/ai-bom>.
- NTIA. 2021. "The Minimum Elements for a Software Bill of Materials (SBOM)."
  <https://www.ntia.gov/files/ntia/publications/sbom_minimum_elements_report.pdf>.
- OpenChain Project. 2024. "AI SBOM Compliance Management Guide."
  <https://github.com/OpenChain-Project/Reference-Material/blob/master/AI-SBOM-Compliance/en/Artificial-Intelligence-System-Bill-of-Materials-Compliance-Management-Guide.md>.
- Samuel, Sheeba. 2022. "ProvBook: Provenance-based Notebook Analysis."
  <https://github.com/Sheeba-Samuel/ProvBook>.
- SPDX Group. 2024. "SPDX 3.0.1 Specification."
  <https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf>.
- W&B Weave. 2024. "Weave Documentation."
  <https://weave-docs.wandb.ai/>.
