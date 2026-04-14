---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Architecture overview

The transition of the global software industry toward a more transparent and
secure supply chain has reached a critical juncture.
Modern software development is no longer characterized by the creation of
monolithic, self-contained codebases; rather, it is a process of assembling
diverse, often opaque, components from a myriad of upstream sources (IBM 2026).
This shift has introduced profound security challenges, most notably the
"phantom dependency" problem, where bundled libraries and build-time artifacts
remain hidden from standard security audits (Alpha Omega 2025).
To mitigate these risks, the Software Bill of Materials (SBOM) has emerged as
the definitive standard for communicating the composition, provenance,
and heritage of software systems (IBM 2026; Larson 2025).

The development of an automated SBOM generator, hereafter referred to as
**Pitloom**, requires a sophisticated understanding of the underlying software
build process, the ontological structures of metadata standards,
and the regulatory landscape that mandates their use (Wiz 2026; Larson 2025).
By intercepting signals from compilers, linkers, and build systems,
Pitloom produces a high-fidelity inventory that serves as a single source of truth
for both developers and downstream consumers (Alpha Omega 2025).

This report provides a detailed strategic plan for Pitloom,
focusing initially on the Python ecosystem with Hatchling
as the primary build backend, while leveraging the modular capabilities of
the SPDX 3.0 specification (SPDX Group 2024; Hatch 2026).

## Theoretical foundation of supply chain transparency and the SBOM lifecycle

An SBOM is essentially a machine-readable "ingredients list" for a software
application, providing exhaustive details on every library, framework, and
sub-module included in the distribution (IBM 2026).
In the context of increasing cybersecurity threats, such as the Log4j and
XZ Utils exploits, the absence of an accurate SBOM forces organizations into
reactive, manual inspection of their environments—a process that is
fundamentally unscalable (Alpha Omega 2025).

The utility of an SBOM spans across visibility, security, and
legal compliance. For security teams, it enables the rapid identification of
vulnerable components within minutes of a new CVE disclosure (Wiz 2026).
For legal departments, it provides a clear record of license obligations,
preventing the accidental distribution of conflicting intellectual property
(Nijhof-Verhees 2026).

| Component Identification Phase | Data Source | Primary Metadata Captured |
| :---- | :---- | :---- |
| Design SBOM | Architecture Specs | Proposed components, licensing requirements (Dey Roy 2025). |
| Source SBOM | Manifests/Lockfiles | Direct and transitive package versions (Dey Roy 2025). |
| Build SBOM | Compiler/Linker Logs | Bundled binaries, toolchain details (Alpha Omega 2025). |
| Binary SBOM | Compiled Artifacts | Symbols, hashes, embedded signatures (Wiz 2026). |
| Runtime SBOM | Execution Environment | Loaded modules, dynamic dependencies (Wiz 2026). |

Pitloom aims to produce "Decision-Ready" SBOMs, which are documents that provide
enough context to drive automated risk-management outcomes (OpenSSF 2025).
Furthermore, the emergence of the Pipeline Bill of Materials (PBOM) adds
the "how" to the "what," capturing the full build story,
including security scan results and environment conditions (Jung 2025).

## Architectural evolution: the SPDX 3.0 ontology

The System Package Data Exchange (SPDX) 3.0 specification represents
a complete re-architecting of the world's most widely used SBOM format.
Moving away from the document-centric model of SPDX 2.x, version 3.0 adopts
an object-oriented, ontological approach based on linked data (JSON-LD)
(SPDX Group 2024).

### Core elements and profile modularity

In SPDX 3, every entity is a subclass of the central Element class,
which ensures that all items share a common set of metadata (Ismail 2024).
The specification is divided into profiles,
each targeting a specific functional domain (SPDX Group 2024).

| Profile Name | Functional Focus | Key Classes/Properties |
| :---- | :---- | :---- |
| Core | Foundational Metadata | Element, Relationship, Agent (Ismail 2024). |
| Software | Composition Analysis | Package, File, packageUrl (SPDX Group 2024). |
| Licensing | Legal Compliance | AnyLicenseInfo, License-Expression (Nijhof-Verhees 2026). |
| AI | Model Provenance | AIPackage, hyperparameter, EnergyConsumption (Linux Foundation 2024). |
| Dataset | Data Integrity | DatasetPackage, datasetSize, confidentialityLevel (Linux Foundation 2024). |
| Build | Build Attestation | BuildType, BuildParameters, buildEnvironment (SPDX Group 2024). |
| Security | Vulnerability Tracking | VulnerabilityAssessment, VEX, CVSS (FOSSA 2024). |

### Deep dive: the AI package and dataset package

For the development of an SBOM generator that supports AI contexts,
the AI and Dataset profiles are indispensable (Linux Foundation 2024).

The `AIPackage` class captures model architecture via the `typeOfModel` property
and documents configuration through hyperparameter entries
(Linux Foundation 2024).
Crucially, it includes fields for `informationAboutTraining` and limitations
(Linux Foundation 2024).

The `DatasetPackage` class provides a standardized way
to document data collection processes, preprocessing steps,
and privacy considerations, such as the `hasSensitivePersonalInformation` flag
(Linux Foundation 2024). By linking an `AIPackage` to its constituent
`DatasetPackage` via SPDX relationships, Pitloom provides a complete picture
of an AI system's origin—a requirement increasingly mandated
by global security frameworks (Linux Foundation 2024).

## Python ecosystem standards: PEPs and packaging evolution

The development of Pitloom aligns with established and emerging standards
from the Python Packaging Authority (PyPA).

### PEP 770: Measuring the unmeasurable

Wheels often bundle shared libraries (e.g., Pillow, NumPy) that do not appear
in the top-level METADATA file (Alpha Omega 2025). PEP 770 addresses this
"phantom dependency" problem by reserving the .dist-info/sboms directory for
storing SBOM documents within the package archive (Larson 2025).
Pitloom will utilize this mechanism to ensure SBOMs remain accessible after
the installation process (Larson 2025; Trivy 2025).

### PEP 639: Standardized licensing with SPDX expressions

Prior to PEP 639, licenses were often declared using ambiguous Trove
classifiers or free-form text fields (Nijhof-Verhees 2026).
PEP 639 updates the core metadata specification to version 2.4, adopting the
SPDX license expression syntax as the authoritative way to declare licenses
(Nijhof-Verhees 2026). Pitloom will automatically populate the licensing profile
of the SPDX 3 output with case-normalized identifiers (Nijhof-Verhees 2026).

### PEP 740: Digital attestations and provenance

PEP 740 defines cryptographically verifiable attestations hosted by indices
like PyPI (Trail of Bits 2024). It allows maintainers to establish
authenticated links between packages and their source hosts using
short-lived signing keys bound to trusted identities (Trail of Bits 2024).
Pitloom will support the generation of these attestation objects to provide
a tamper-evident history of the build process
(Trail of Bits 2024; OpenSSF 2025).

## Engineering architecture: the build log extraction strategy

Pitloom's primary differentiator is the extraction of data from build logs
generated by compilers and linkers (Alpha Omega 2025).
Intercepting logs offers precision, capturing the actual flags (e.g., \-lssl)
and library paths used during the build to reveal precisely which binaries are
linked into the artifact (Alpha Omega 2025).

### Performance architecture: Python-Rust hybrid engine

While the first iteration of Pitloom will target the Python ecosystem with
pure Python for fast iteration, its architecture is designed for
a high-performance backend as the project scales (KDNuggets 2025).

- **Orchestration Layer (Python):** Python handles high-level workflows,
  manages configurations via pyproject.toml, and integrates with observation
  tools like MLflow (KDNuggets 2025; MLflow 2026).
- **Execution Layer (Rust):** A future Rust core will handle CPU-bound tasks
  where performance and concurrency matter most, such as parsing compiler logs,
  performing large-scale graph traversal for transitive dependencies,
  and serializing deeply nested JSON-LD (The New Stack 2025; Taft 2025).
- **Integration:** Pitloom will utilize **PyO3** to create native Python
  extensions and **Maturin** for packaging, ensuring near-native performance
  while maintaining Python's flexibility (Taft 2025; hamza-senhajirhazi 2024).

| Task Type | Target Backend | Reasoning |
| :---- | :---- | :---- |
| CLI & Hook Management | Python | Faster developer onboarding and rapid plugin development (KDNuggets 2025). |
| Log Parser (Initial) | Python | Quick prototyping of parsing rules for GCC/MSVC logs (Alpha Omega 2025). |
| Enrichment Engine | Rust (Future) | 10-100x speedups in CPU-bound graph processing (DevTools Academy 2025). |
| JSON-LD Serialization | Rust (Serde) | Superior speed in generating large, linked-data ontologies (serde-spdx 2024). |

## Software engineering design and project structure

Pitloom will follow modern Python software engineering best practices,
utilizing the "src" layout to prevent subtle import-path bugs and ensure
the development environment mirrors production (Ghadge 2025).

See [docs/implementation/summary.md](../implementation/summary.md) for the
canonical, up-to-date project tree.

## Integration with the SCA pipeline and DevOps ecosystem

Pitloom serves as a critical node in the broader Software Component Analysis (SCA)
pipeline (Wiz 2026). Its core role is as a **SBOM assembler**: it collects
information from every available source — the source repository, the build
backend, model files, ML tracking platforms, dataset registries, and
pre-generated partner SBOM fragments — and assembles them into a single,
compliant, composite SBOM document.

This assembly model reflects the reality that no single tool or team
has visibility into the full provenance of a modern AI system.
See `docs/design/sbom-fragments.md` for the detailed design of the
fragment system, vocabulary alignment with SPDX 3 / CycloneDX / CISA
standards, and the roadmap for new integrations.

### Information sources and extractors

| Source | Extractor / mechanism | What it contributes |
| :---- | :---- | :---- |
| `pyproject.toml` | `pitloom.extract.pyproject` | Package identity, version, license, dependencies, authors |
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
See `docs/design/hatchling-build-hook.md`.

#### 2. PEP 770 wheel embedding

The SBOM is placed at `{name}-{version}.dist-info/sboms/sbom.spdx3.json`
inside the wheel archive. Downstream tools (Trivy, Grype, pip-audit) can
discover and consume the SBOM without any separate distribution step.
Implemented as part of the Hatchling build hook.

#### 3. MLflow run extractor (`pitloom.extract.mlflow`)

Reads a completed MLflow run and maps its tags, parameters, and metrics
to an SPDX 3 AI BOM fragment. Uses
[STAV](https://github.com/bact/stav) constants as a shared vocabulary
layer so projects already tagging MLflow runs with STAV keys require no
additional instrumentation. The top-level `pitloom.loom.from_mlflow_run()`
function provides the public API.
See `docs/design/mlflow-extractor.md`.

#### 4. W&B Weave extractor (`pitloom.extract.weave`) [planned]

Reads versioned model and dataset objects from W&B Weave
([github.com/wandb/weave](https://github.com/wandb/weave)), a tracing layer
for LLM applications that automatically captures full call graphs, model
parameter versions, and structured evaluation results.
Weave's model version URIs (`weave:///entity/project/object/Name:hash`)
map naturally to SPDX `ai_AIPackage` with a content-addressed
`software_downloadLocation`. Evaluation results become SPDX `Annotation`
elements. The top-level function is `pitloom.loom.from_weave_model()`.
See `docs/design/sbom-fragments.md` for the full object mapping.

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
See `docs/design/sbom-fragments.md`.

### Data flow: extraction → document model → assembly

```text
Information sources
───────────────────
pyproject.toml            → ProjectMetadata          (pitloom.extract.pyproject)
model.onnx / .gguf / …    → AiModelMetadata          (pitloom.extract.ai_model)
dataset.croissant.json    → DatasetMetadata           (pitloom.extract.dataset)
MLflow run                → SPDX AI fragment          (pitloom.extract.mlflow) [planned]
W&B Weave model object    → SPDX AI fragment          (pitloom.extract.weave)  [planned]
dvc.lock                  → SPDX Dataset elements     (pitloom.extract.dvc)    [planned]
Jupyter notebook session  → SPDX AI/Dataset fragment  (pitloom.loom session)   [planned]
fragments/*.spdx3.json    → pre-generated elements    (partner / vendor SBOMs)

Assembly (format-neutral)
─────────────────────────
DocumentModel(
    project=ProjectMetadata,
    creation=CreationMetadata,
    ai_models=[AiModelMetadata, ...],
    fragments=[FragmentConfig, ...],    # structured fragment metadata [planned]
)

Serialization and merge
───────────────────────
compute_wheel_merkle_root(project_dir)          → merkle_root (or None)
build(doc: DocumentModel, merkle_root)          → Spdx3JsonExporter → JSON-LD
merge_fragments(fragments, exporter, ...)       → elements inlined; imports recorded
exporter.to_json(pretty=...)                    → composite SBOM string / file
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

1. **Type-priority tier** — promote `CreationInfo`, `SpdxDocument`,
   `software_Sbom` to the front (in that order), then root `software_Package`,
   then all other elements.
2. **`@id` lexicographic order** — within each tier, sort by the element's
   `@id` (or `_:ClassName` for blank nodes) so output is fully deterministic.

**Relationship to JSON canonicalization standards.**
RFC 8259 §4 ([datatracker.ietf.org/doc/rfc8259](https://datatracker.ietf.org/doc/rfc8259/))
defines JSON arrays as *ordered sequences* of values, meaning `@graph` element
order is semantically meaningful and is preserved by all conforming parsers.
RFC 8259 §4 also defines JSON objects as *unordered* collections of name/value
pairs, so parsers must not rely on property order within an object.

RFC 8785 (JSON Canonicalization Scheme, JCS —
[datatracker.ietf.org/doc/rfc8785](https://datatracker.ietf.org/doc/rfc8785/))
addresses object-property ordering by requiring lexicographic sorting of
property names (by UTF-16 code units). However, JCS explicitly states that
**array element order MUST NOT be changed** — it only recurses into objects
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
→ loom.from_mlflow_run(run_id, "fragments/run.spdx3.json")
        └── pitloom.extract.mlflow → SPDX AI fragment [planned]

Build time (zero extra commands)
─────────────────────────────────
hatch build  /  python -m build
  └── PitloomBuildHook.initialize()
        ├── read_pyproject()         (reads pyproject.toml)
        ├── compute_wheel_merkle_root() (WheelBuilder file set → deterministic UUID)
        ├── DocumentModel → build(merkle_root) → Spdx3JsonExporter
        ├── merge fragments/run.spdx3.json    (AI provenance)
        └── → .dist-info/sboms/sbom.spdx3.json  ← PEP 770

Downstream consumption
───────────────────────
trivy image mypackage-1.0.whl     → reads .dist-info/sboms/
pip show mypackage                → SBOM included in .dist-info
```

## Quantifying the problem: Python dependency proliferation

The importance of build-time extraction is underscored by the scale of
unrecorded system libraries bundled in Python wheels (Alpha Omega 2025).
Statistical analysis of top PyPI packages reveals that over 30% of standard
wheels bundle at least one shared library not declared in
the project's metadata (Alpha Omega 2025).

| Common System Library | Usage in Python Projects | Total Monthly Ingress Volume |
| :---- | :---- | :---- |
| libgcc\_s | 112 projects | 2,750,000,000 downloads (Alpha Omega 2025). |
| libstdc++ | 64 projects | 1,500,000,000 downloads (Alpha Omega 2025). |
| libz | 47 projects | 1,000,000,000 downloads (Alpha Omega 2025). |
| libgfortran | 15 projects | 650,000,000 downloads (Alpha Omega 2025). |
| libopenblas | 6 projects | 600,000,000 downloads (Alpha Omega 2025). |

## Identification of existing toolchain and libraries

The implementation of Pitloom can leverage several high-quality open-source
components.

### Core tooling and frameworks

- **Hatchling (Build Backend):** The primary backend for the MVP,
  providing a stable and extensible BuildHookInterface (Hatch 2026).
- **spdx-tools (High-Level Library):** Provides functions for parsing and
  validating SPDX documents. Support for version 3.0 is currently experimental
  (Ismail 2024).
- **spdx-python-model (Core Bindings):** Pitloom has fully adopted the official
  generated bindings for the SPDX 3 ontology, offering full coverage of spec
  classes like AIPackage (SPDX Group 2026).
- **license-expression (Validation):** Essential for normalizing license
  expressions according to PEP 639 (NexB 2025).

### Analysis and enrichment tools

- **Tern (Container Analysis):** An open-source tool that creates SBOMs from
  container images, providing a layer-by-layer view of how components were
  introduced (Wiz 2023). Pitloom can utilize Tern's layer insights for
  container-based distribution (Wiz 2023; Nathan Naveen 2025).
- **purldb-toolkit:** Facilitates identifying software components by mapping
  binaries back to source packages using Package URLs (PURLs) (PurlDB 2026).
- **scan-build (Intercept-build):** Part of the LLVM ecosystem,
  this tool intercepts compiler calls to create a compilation database,
  serving as a blueprint for Pitloom's log parser (Binutils 2024).

## General steps for project implementation

1. **Specification Review:** Analysis of the SPDX 3.0 JSON-LD schema for
    AIPackage and DatasetPackage classes (SPDX Group 2024).
2. **Build Hook Prototyping:** Creation of a minimal Hatchling build hook
    that captures simple linker flags (Hatch 2026).
3. **Ontological Mapper Development:** Construction of an internal component
    model that holds all data for Core, Software, AI, and Dataset profiles
    (Ismail 2024).
4. **Log Interception Engine:** Developing a robust regex library to parse
    compiler and linker logs across Linux and Windows
    (Binutils 2024; Alpha Omega 2025).
5. **PEP Compliance Validation:** Testing the ability to produce valid PEP 770
    directory structures and PEP 639 license expressions
    (Larson 2025; Nijhof-Verhees 2026).
6. **Observability Integration:** Implementing the MLflow plugin to log SBOMs
    as structured dictionaries (MLflow 2026).
7. **Downstream Testing:** Validating output against SCA scanners like Trivy
    and Grype to ensure interoperability (Wiz 2026; Trivy 2025).
8. **Performance Optimization:** If performance bottlenecks arise during
    enrichment, migration of the core logic to a Rust backend using PyO3
    (Taft 2025; KDNuggets 2025).

## References

- Alpha Omega. 2025.
  "Python White Paper: Identifying and Mitigating Supply Chain
  Vulnerabilities." <https://alpha-omega.dev/wp-content/uploads/sites/22/2025/08/Python-White-Paper-for-AO-3.pdf>.
- Binutils. 2024.
  "Linker Options: ld \--trace." Binutils Documentation.
  <https://sourceware.org/binutils/docs/ld/Options.html>.
- Dey Roy, Ratnadeep. 2025.
  "Unified BOM: The Complete Guide to Software, SaaS, AI, and Cloud
  Assets." Medium. <https://medium.com/@ratnadeepdeyroy/unified-bom-the-complete-guide-99a7ca284023>.
- DevTools Academy. 2025.
  "UV and Ruff: Turbocharging Python Development with Rust-Powered
  Tools." <https://www.devtoolsacademy.com/blog/uv-and-ruff-turbocharging-python-development-with-rust-powered-tools/>.
- FOSSA. 2024.
  "SPDX 3.0 Is Released." FOSSA Blog.
  <https://fossa.com/blog/spdx-3-0/>.
- Ghadge, Aditya. 2025.
  "Python Project Structure: Why the src Layout Beats Flat Folders."
  Medium. <https://medium.com/@adityaghadge99/python-project-structure-why-the-src-layout-beats-flat-folders-808844d16f35>.
- hamza-senhajirhazi. 2024.
  "How I Published My 1st Rust-Python Binding Package." Medium.
  <https://hamza-senhajirhazi.medium.com/how-i-published-my-1st-rust-python-binding-package-cb44bc4e2e94>.
- Hatch. 2026.
  "Build Hook Reference." Hatch Documentation.
  <https://hatch.pypa.io/1.8/plugins/build-hook/reference/>.
- IBM. 2026.
  "What is a Software Bill of Materials (SBOM)?" IBM Think Topics.
  <https://www.ibm.com/think/topics/sbom>.
- Ismail, Ahmed H. 2024.
  "spdx-tools: Python Library for SPDX Documents." PyPI.
  <https://pypi.org/project/spdx-tools/>.
- Jung, Timothy. 2025.
  "PBOM vs SBOM – Building a Complete Security Bill of Materials."
  Apiiro Blog. <https://apiiro.com/blog/pbom-versus-sbom-complete-bom/>.
- KDNuggets. 2025.
  "Integrating Rust and Python for Data Science."
  <https://www.kdnuggets.com/integrating-rust-and-python-for-data-science>.
- Larson, Seth. 2025.
  "PEP 770 – Improving Measurability of Python Packages with Software
  Bill-of-Materials." Python Enhancement Proposals.
  <https://peps.python.org/pep-0770/>.
- Linux Foundation. 2024.
  "SPDX AI Bill of Materials (AI BOM) with SPDX 3.0."
  <https://www.linuxfoundation.org/research/ai-bom>.
- MLflow. 2026.
  "MLflow Tracking APIs." MLflow Documentation.
  <https://mlflow.org/docs/latest/ml/tracking/tracking-api/>.
- Nathan Naveen. 2025.
  "Choosing an SBOM Generation Tool." OpenSSF Blog.
  <https://openssf.org/blog/2025/06/05/choosing-an-sbom-generation-tool/>.
- NexB Inc. 2025.
  "license-expression: Parse, Compare and Normalize License
  Expressions." PyPI. <https://pypi.org/project/license-expression/>.
- Nijhof-Verhees, Tom. 2026.
  "PEP 639 – Improving License Clarity with Better Package Metadata."
  Python Enhancement Proposals.
  <https://peps.python.org/pep-0639/>.
- OpenSSF. 2025.
  "Improving Risk Management Decisions with SBOM Data."
  <https://openssf.org/blog/2025/09/18/improving-risk-management-decisions-with-sbom-data-a-new-whitepaper-from-the-openssf-sbom-everywhere-sig/>.
- Pullflow. 2025.
  "Go vs Python vs Rust: Complete Performance Comparison."
  <https://pullflow.com/blog/go-vs-python-vs-rust-complete-performance-comparison/>.
- PurlDB. 2026.
  "PurlDB: Package URL Database." <https://purldb.readthedocs.io/>.
- serde-spdx. 2024.
  "Serde Serialization for SPDX Files." crates.io.
  <https://crates.io/crates/serde-spdx>.
- SPDX Group. 2024.
  "SPDX 3.0.1 Specification."
  <https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf>.
- SPDX Group. 2026.
  "spdx-python-model: Generated Python Code for SPDX Spec Version 3." GitHub.
  <https://github.com/spdx/spdx-python-model>.
- Taft, Darryl K. 2025.
  "Rust: Python's New Performance Engine." The New Stack.
  <https://thenewstack.io/rust-pythons-new-performance-engine/>.
- The New Stack. 2025.
  "Combining Rust and Python for High-Performance AI Systems."
  <https://thenewstack.io/combining-rust-and-python-for-high-performance-ai-systems/>.
- Trail of Bits. 2024.
  "Are we PEP 740 yet? Index Hosted Attestations."
  <https://trailofbits.github.io/are-we-pep740-yet/>.
- Trivy. 2025.
  "Support PEP 770 (SBOM metadata in Python packages)." GitHub Issues.
  <https://github.com/aquasecurity/trivy/issues/10021>.
- Wiz. 2026.
  "Software Bill of Materials (SBOM) 2025 Guide." Wiz Academy.
  <https://www.wiz.io/academy/application-security/software-bill-of-material-sbom>.
- Wiz. 2023.
  "Top Open-Source SBOM Tools." Wiz Academy.
  <https://www.wiz.io/academy/application-security/top-open-source-sbom-tools>.

## Notes

### AI-assistance declaration

This document is created by assistance from an AI agent (Google Gemini).
It is a consolidation of two generated documents that were outputs from
the two initial prompts displayed below, followed by a series of interactions.
It may include inaccurate or out-of-date information, including non-existing
references.

This document is used as an input for GitHub Copilot to help create a
package directory structure and initial source code files for a prototype.
See the interaction here: <https://github.com/bact/pitloom/pull/1>.

### Prompt 1

> I'm thinking about building a tool that creating a software bill of materials
> for a Python package. My idea is to have if as a plugin to an existing
> packaging tool (like Hatch). Which existing packaging tool that I should
> target for, considering its wide adoption, future adoption, ecosystem,
> ease of plugging (from technical perspective), and community

#### Prompt 2

> Help me plan the development of an SBOM generator.
> I want to develop a generator for Software Bill of Materials, using build
> data from software builder, compiler, linker.
>
> The generator should find and include information about license, software
> dependency, source of data (in both AI and non-AI context) into the SBOM,
> at the very least.
>
> The SBOM generator will see itself as part of larger software component
> analysis pipelines. Where the SBOM generator consumes data from earlier
> processors like compiler, and generates SBOM for the consumption of other
> downstream processors.
>
> First iteration of this generator will target Python ecosystem,
> with hatchling as build backend, and output SPDX 3 JSON.
> It could read Python build log and use that to generate SBOM.
> This may be slower but doesn’t require tight integration or change in Python
> build system, and potentially can plug into existing ecosystem like MLflow
> and other DevOps or observation tools.
>
> Next iterations in the roadmap will include support for other Python build
> backends, other programming languages, and other SBOM formats.
>
> Help me plan and identify resources.
>
> Provide general steps.
>
> Suggest software engineering architecture.
>
> Suggest project structure in Python.
>
> Link this with Python PEPs and standards and area that can gain support
> and adoption from Python developers community.
