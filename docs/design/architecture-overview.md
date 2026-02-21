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
**Loom**, requires a sophisticated understanding of the underlying software
build process, the ontological structures of metadata standards,
and the regulatory landscape that mandates their use (Wiz 2026; Larson 2025).
By intercepting signals from compilers, linkers, and build systems,
Loom produces a high-fidelity inventory that serves as a single source of truth
for both developers and downstream consumers (Alpha Omega 2025).

This report provides a detailed strategic plan for Loom,
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

Loom aims to produce "Decision-Ready" SBOMs, which are documents that provide
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

In SPDX 3.0, every entity is a subclass of the central Element class,
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
`DatasetPackage` via SPDX relationships, Loom provides a complete picture
of an AI system's origin—a requirement increasingly mandated
by global security frameworks (Linux Foundation 2024).

## Python ecosystem standards: PEPs and packaging evolution

The development of Loom aligns with established and emerging standards
from the Python Packaging Authority (PyPA).

### PEP 770: Measuring the unmeasurable

Wheels often bundle shared libraries (e.g., Pillow, NumPy) that do not appear
in the top-level METADATA file (Alpha Omega 2025). PEP 770 addresses this
"phantom dependency" problem by reserving the .dist-info/sboms directory for
storing SBOM documents within the package archive (Larson 2025).
Loom will utilize this mechanism to ensure SBOMs remain accessible after
the installation process (Larson 2025; Trivy 2025).

### PEP 639: Standardized licensing with SPDX expressions

Prior to PEP 639, licenses were often declared using ambiguous Trove
classifiers or free-form text fields (Nijhof-Verhees 2026).
PEP 639 updates the core metadata specification to version 2.4, adopting the
SPDX license expression syntax as the authoritative way to declare licenses
(Nijhof-Verhees 2026). Loom will automatically populate the licensing profile
of the SPDX 3.0 output with case-normalized identifiers (Nijhof-Verhees 2026).

### PEP 740: Digital attestations and provenance

PEP 740 defines cryptographically verifiable attestations hosted by indices
like PyPI (Trail of Bits 2024). It allows maintainers to establish
authenticated links between packages and their source hosts using
short-lived signing keys bound to trusted identities (Trail of Bits 2024).
Loom will support the generation of these attestation objects to provide
a tamper-evident history of the build process
(Trail of Bits 2024; OpenSSF 2025).

## Engineering architecture: the build log extraction strategy

Loom's primary differentiator is the extraction of data from build logs
generated by compilers and linkers (Alpha Omega 2025).
Intercepting logs offers precision, capturing the actual flags (e.g., \-lssl)
and library paths used during the build to reveal precisely which binaries are
linked into the artifact (Alpha Omega 2025).

### Performance architecture: Python-Rust hybrid engine

While the first iteration of Loom will target the Python ecosystem with
pure Python for fast iteration, its architecture is designed for
a high-performance backend as the project scales (KDNuggets 2025).

- **Orchestration Layer (Python):** Python handles high-level workflows,
  manages configurations via pyproject.toml, and integrates with observation
  tools like MLflow (KDNuggets 2025; MLflow 2026).
- **Execution Layer (Rust):** A future Rust core will handle CPU-bound tasks
  where performance and concurrency matter most, such as parsing compiler logs,
  performing large-scale graph traversal for transitive dependencies,
  and serializing deeply nested JSON-LD (The New Stack 2025; Taft 2025).
- **Integration:** Loom will utilize **PyO3** to create native Python
  extensions and **Maturin** for packaging, ensuring near-native performance
  while maintaining Python's flexibility (Taft 2025; hamza-senhajirhazi 2024).

| Task Type | Target Backend | Reasoning |
| :---- | :---- | :---- |
| CLI & Hook Management | Python | Faster developer onboarding and rapid plugin development (KDNuggets 2025). |
| Log Parser (Initial) | Python | Quick prototyping of parsing rules for GCC/MSVC logs (Alpha Omega 2025). |
| Enrichment Engine | Rust (Future) | 10-100x speedups in CPU-bound graph processing (DevTools Academy 2025). |
| JSON-LD Serialization | Rust (Serde) | Superior speed in generating large, linked-data ontologies (serde-spdx 2024). |

## Software engineering design and project structure

Loom will follow modern Python software engineering best practices,
utilizing the "src" layout to prevent subtle import-path bugs and ensure
the development environment mirrors production (Ghadge 2025).

### Suggested Python project structure

```text
loom/
├── pyproject.toml \# Unified configuration (Hatchling)
├── README.md \# Project documentation
├── LICENSE \# Software license
├── src/
│ └── loom/
│ ├── **init**.py
│ ├── **main**.py \# Typer CLI entry point (Ghadge 2025).
│ ├── core/ \# Core business logic
│ │ ├── models.py \# SPDX 3.0 internal ontology classes (Ismail 2024).
│ │ ├── pipeline.py \# Execution flow controller
│ │ └── engine.rs \# Potential future Rust-backend code
│ ├── extractors/ \# Domain-specific data collection
│ │ ├── manifest.py \# pyproject.toml parser (Hatch 2026).
│ │ └── log\_parser.py \# Regex engine for GCC/MSVC logs (Alpha Omega 2025).
│ ├── plugins/ \# Build system integrations
│ │ └── hatch.py \# Hatchling BuildHookInterface implementation (Hatch 2026).
│ └── exporters/ \# Format-specific writers
│ ├── spdx3\_json.py \# SPDX 3.0 JSON-LD serializer (Ismail 2024).
│ └── mlflow.py \# MLflow API integration layer (MLflow 2026).
├── tests/ \# Pytest-based testing suite
└──.github/workflows/ \# CI/CD pipeline definitions
```

## Integration with the SCA pipeline and DevOps ecosystem

Loom serves as a critical node in the broader Software Component Analysis (SCA)
pipeline (Wiz 2026). It exposes the `loom.bom` tracking SDK, a wrapper
interface that seamlessly intercepts metrics from training scripts and notebooks
to output SBOM fragments representing models and datasets.

These fragments are dynamically aggregated during the `hatch build` phase.
This ensures that every model deployed from an MLflow registry is accompanied by
a cryptographically verifiable record of its constituent software
and data sources, meeting emerging AI governance requirements
(Linux Foundation 2024).

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

The implementation of Loom can leverage several high-quality open-source
components.

### Core tooling and frameworks

- **Hatchling (Build Backend):** The primary backend for the MVP,
  providing a stable and extensible BuildHookInterface (Hatch 2026).
- **spdx-tools (High-Level Library):** Provides functions for parsing and
  validating SPDX documents. Support for version 3.0 is currently experimental
  (Ismail 2024).
- **spdx-python-model (Core Bindings):** Loom has fully adopted the official
  generated bindings for the SPDX 3.0 ontology, offering full coverage of spec
  classes like AIPackage (SPDX Group 2026).
- **license-expression (Validation):** Essential for normalizing license
  expressions according to PEP 639 (NexB 2025).

### Analysis and enrichment tools

- **Tern (Container Analysis):** An open-source tool that creates SBOMs from
  container images, providing a layer-by-layer view of how components were
  introduced (Wiz 2023). Loom can utilize Tern's layer insights for
  container-based distribution (Wiz 2023; Nathan Naveen 2025).
- **purldb-toolkit:** Facilitates identifying software components by mapping
  binaries back to source packages using Package URLs (PURLs) (PurlDB 2026).
- **scan-build (Intercept-build):** Part of the LLVM ecosystem,
  this tool intercepts compiler calls to create a compilation database,
  serving as a blueprint for Loom's log parser (Binutils 2024).

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
See the interaction here: <https://github.com/bact/loom/pull/1>.

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
