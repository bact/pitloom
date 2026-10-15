---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Architecture overview -- integration and data flow

See also: [architecture-overview.md](architecture-overview.md) (the
overview and map of the parts) and
[architecture-overview-references.md](architecture-overview-references.md)
(references and notes).
Author-year citations such as (Alpha Omega 2025) refer to the reference list in
[architecture-overview-references.md](architecture-overview-references.md#references).

## Integration with the SCA pipeline and DevOps ecosystem

Pitloom serves as a critical node in the broader Software Component Analysis (SCA)
pipeline (Wiz 2026). Its core role is as a **SBOM assembler**: it collects
information from every available source -- the source repository, the build
backend, model files, ML tracking platforms, dataset registries, and
pre-generated partner SBOM fragments -- and assembles them into a single,
compliant, composite SBOM document.

This assembly model reflects the reality that no single tool or team
has visibility into the full provenance of a modern AI system.
See `working-docs/design/sbom-fragments/` for the detailed design of the
fragment system, vocabulary alignment with SPDX 3 / CycloneDX / CISA
standards, and the roadmap for new integrations.

### Information sources and extractors

| Source | Extractor / mechanism | What it contributes |
| :---- | :---- | :---- |
| `pyproject.toml` | `pitloom.extract.project.pyproject` | Package identity, version, license, dependencies, authors |
| `setup.cfg` / `setup.py` | `pitloom.extract.project.setuptools` | Package identity, version, license, dependencies, authors |
| Python environment | `pitloom.extract.env` | Deployed environment dependency graph |
| Built wheel (`.whl`) | `pitloom.extract.wheel` / `binary` | Analyzed wheel metadata, files, and phantom dependencies |
| AI model files (GGUF, ONNX, SafeTensors, etc.) | `pitloom.extract.ai_model` | Model architecture, format, hyperparameters, framework |
| Dataset files (Croissant JSON-LD) | `pitloom.extract.dataset` | Dataset identity, schema, license, provenance |
| MLflow tracking server | `pitloom.extract.mlflow` [planned] | Training run tags, params, metrics, dataset inputs |
| W&B Weave | `pitloom.extract.weave` [planned] | Versioned model objects, dataset objects, evaluation traces |
| DVC repository | `pitloom.extract.dvc` [planned] | Content-hashed data/model files, pipeline stage provenance |
| Jupyter notebooks | `pitloom.loom` session API [planned] | Incrementally recorded model/dataset metadata, cell provenance |
| Pre-generated fragments | `pitloom.assemble.spdx3.fragments` | SBOM elements from external teams, binary vendors, or earlier builds |
| Build backend (Hatchling) | `pitloom.plugins.hatch` | Wheel file set, Merkle root, build timestamp |

### Planned integrations

#### 1. Hatchling build hook (`pitloom.plugins.hatch`)

A Hatchling `BuildHookInterface` plugin that generates the SBOM automatically
during `hatch build` or `python -m build` and embeds it in the wheel's
`.dist-info/sboms/` directory per PEP 770. Users opt in by adding
`pitloom` to `build-system.requires` and enabling `[tool.hatch.build.hooks.pitloom]`.
See `working-docs/implementation/hatchling-build-hook.md`.

#### 2. PEP 770 wheel embedding

The SBOM is placed at `{name}-{version}.dist-info/sboms/{name}-{version}.spdx3.json`
inside the wheel archive (default basename; overridable via `sbom-basename`). Downstream tools (Trivy, Grype, pip-audit) can
discover and consume the SBOM without any separate distribution step.
Implemented as part of the Hatchling build hook.

#### 3. MLflow run extractor (`pitloom.extract.mlflow`)

Reads a completed MLflow run and maps its tags, parameters, and metrics
to an SPDX 3 AI BOM fragment. Uses
[STAV](https://github.com/bact/stav) constants as a shared vocabulary
layer so projects already tagging MLflow runs with STAV keys require no
additional instrumentation. The top-level `pitloom.loom.from_mlflow_run()`
function provides the public API.
See `working-docs/design/mlflow-extractor.md`.

#### 4. W&B Weave extractor (`pitloom.extract.weave`) [planned]

Reads versioned model and dataset objects from W&B Weave
([github.com/wandb/weave](https://github.com/wandb/weave)), a tracing layer
for LLM applications that automatically captures full call graphs, model
parameter versions, and structured evaluation results.
Weave's model version URIs (`weave:///entity/project/object/Name:hash`)
map naturally to SPDX `ai_AIPackage` with a content-addressed
`software_downloadLocation`. Evaluation results become SPDX `Annotation`
elements. The top-level function is `pitloom.loom.from_weave_model()`.
See `working-docs/design/sbom-fragments/extractor-integrations.md` for
the full object mapping.

#### 5. DVC extractor (`pitloom.extract.dvc`) [planned]

Reads `dvc.lock` (the frozen, hash-committed view of the DVC pipeline)
to extract content-hashed dataset and model file references.
DVC's content hashes map to SPDX `verifiedUsing` integrity elements,
and DVC remote URLs map to `software_downloadLocation`.
This provides strong, git-anchored provenance for projects that
use DVC for data versioning.

#### 6. SBOM fragment system (`pitloom.assemble.spdx3.fragments`) [partially implemented]

Merges pre-generated SPDX 3 fragment files from external teams, binary
vendors, or earlier build stages into the composite SBOM.
Current implementation performs basic element merge.
Planned improvements: structured fragment declaration in `pyproject.toml`
(with role, sha256, link-to-main relationship), pre-merge validation,
duplicate-ID detection, and `SpdxDocument.imports` population for
cross-document traceability.
See `working-docs/design/sbom-fragments/fragment-merge-design.md`.

### Data flow: extraction -> document model -> assembly

See [end-to-end-flow.md](../implementation/end-to-end-flow.md) for a
generic, stage-level version of this diagram -- the version here is the fuller,
more implementation/integration-specific picture, including the still-planned
pieces.

```text
Information sources
───────────────────
pyproject.toml            -> ProjectMetadata           (pitloom.extract.project.pyproject)
setup.cfg / setup.py      -> ProjectMetadata           (pitloom.extract.project.setuptools)
model.onnx / .gguf / …    -> AiModelMetadata           (pitloom.extract.ai_model)
dataset.croissant.json    -> DatasetMetadata           (pitloom.extract.dataset)
MLflow run                -> SPDX AI fragment          (pitloom.extract.mlflow)  [planned]
W&B Weave model object    -> SPDX AI fragment          (pitloom.extract.weave)   [planned]
dvc.lock                  -> SPDX Dataset elements     (pitloom.extract.dvc)     [planned]
Jupyter notebook session  -> SPDX AI/Dataset fragment  (pitloom.loom session)    [planned]
fragments/*.spdx3.json    -> pre-generated elements    (partner / vendor SBOMs)

Assembly (format-neutral)
─────────────────────────
DocumentModel(
    project=ProjectMetadata,
    creation_metadata=CreationMetadata,
    ai_models=[AiModelMetadata, ...],
    fragments=[FragmentConfig, ...],    # structured fragment metadata [planned]
)

Serialization and merge
───────────────────────
compute_wheel_merkle_root(project_dir)          -> merkle_root (or None)
build(doc: DocumentModel, merkle_root)          -> Spdx3JsonExporter -> JSON-LD
merge_fragments(fragments, exporter, ...)       -> elements inlined; imports recorded
exporter.to_json(pretty=...)                    -> composite SBOM string / file
```

### JSON-LD `@graph` element ordering

The `@graph` array in JSON-LD output contains one object per SPDX element.
Its order has direct implications for two concerns:

**Reproducibility.** `SHACLObjectSet` stores objects in a Python `set`, which
is unordered. `SHACLObjectSet.encode()` accepts a `key=` parameter and sorts
before serializing, but `JSONLDSerializer` does not pass one, so the emitted
order varies across runs. This makes byte-for-byte reproducibility impossible
and destabilizes text diffs and hash calculations (e.g., Merkle root, integrity
checksums embedded in the wheel).

**Stream-processing performance.** Consumers that parse the document
incrementally (validators, SCA scanners) must buffer the entire `@graph` before
they can resolve forward references. Placing high-centrality nodes near the
front of the list allows early rejection or early establishment of processing
context without reading the full document. The highest-priority nodes are:
`CreationInfo` (blank node referenced by every element), `SpdxDocument`
(document envelope and `profileConformance`), and `software_Sbom`
(root element pointer and `sbomType`).

**Approach.** Because `to_json()` already round-trips through `json.loads()`,
a deterministic sort can be applied to `data["@graph"]` before the final
`json.dumps()` call with no changes to `spdx-python-model`. A two-level key
suffices:

1. **Type-priority tier** -- promote `CreationInfo`, `SpdxDocument`,
   `software_Sbom` to the front (in that order), then root `software_Package`,
   then all other elements.
2. **`@id` lexicographic order** -- within each tier, sort by the element's
   `@id` (or `_:ClassName` for blank nodes) so output is fully deterministic.

**Relationship to JSON canonicalization standards.**
RFC 8259 §4 ([datatracker.ietf.org/doc/rfc8259](https://datatracker.ietf.org/doc/rfc8259/))
defines JSON arrays as *ordered sequences* of values, meaning `@graph` element
order is semantically meaningful and is preserved by all conforming parsers.
RFC 8259 §4 also defines JSON objects as *unordered* collections of name/value
pairs, so parsers must not rely on property order within an object.

RFC 8785 (JSON Canonicalization Scheme, JCS --
[datatracker.ietf.org/doc/rfc8785](https://datatracker.ietf.org/doc/rfc8785/))
addresses object-property ordering by requiring lexicographic sorting of
property names (by UTF-16 code units). However, JCS explicitly states that
**array element order MUST NOT be changed** -- it only recurses into objects
found within arrays to sort their properties. JCS therefore cannot, by itself,
produce a deterministic `@graph` element ordering.

This limitation is acknowledged in the SPDX specification repository
([spdx/spdx-spec#1362](https://github.com/spdx/spdx-spec/issues/1362)),
where the working group proposes referencing JCS as part of the canonical
serialization specification while noting that "additional specifications are
needed to cover items like graph serialization and handling contexts and
namespace prefixes." The issue remains open.

The SPDX 3.0.1 canonical serialization specification
([spdx.github.io/spdx-spec/v3.0.1/serializations](https://spdx.github.io/spdx-spec/v3.0.1/serializations/))
currently mandates alphabetical ordering of *properties within each object*,
but is silent on `@graph` element ordering. Imposing an explicit element order
is therefore compliant with RFC 8259, RFC 8785 (JCS), and the current SPDX
canonical specification, and fills a gap that none of the three yet closes.

### Revised end-to-end flow (with planned integrations)

```text
Training time
─────────────
mlflow.set_tag(stav.MODEL_TYPE, "transformer")
mlflow.log_metric(stav.METRICS_ACCURACY, 0.91)
-> loom.from_mlflow_run(run_id, "fragments/run.spdx3.json")
        └── pitloom.extract.mlflow -> SPDX AI fragment  [planned]

Build time (zero extra commands)
─────────────────────────────────
hatch build  /  python -m build
  └── PitloomBuildHook.initialize()
        ├── read_pyproject()         (reads pyproject.toml)
        ├── compute_wheel_merkle_root() (WheelBuilder file set -> deterministic UUID)
        ├── DocumentModel -> build(merkle_root) -> Spdx3JsonExporter
        ├── merge fragments/run.spdx3.json    (AI provenance)
        └── -> .dist-info/sboms/mypackage-1.0.spdx3.json  <- PEP 770

Downstream consumption
───────────────────────
trivy image mypackage-1.0.whl     -> reads .dist-info/sboms/
pip show mypackage                -> SBOM included in .dist-info
```
