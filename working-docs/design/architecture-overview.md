---
Created: 2026-02-06
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Architecture overview

See also (parts of this document):

- [architecture-overview.md](architecture-overview.md) -- introduction,
  supply chain transparency and the SBOM lifecycle, the SPDX 3.0 ontology,
  Python packaging standards (PEPs), the build log extraction strategy,
  Python-Rust performance architecture and project structure.
- [architecture-overview-integration.md](architecture-overview-integration.md)
  -- integration with the SCA pipeline and DevOps ecosystem: information
  sources and extractors, planned integrations, data flow, JSON-LD `@graph`
  element ordering, end-to-end flow.
- [architecture-overview-references.md](architecture-overview-references.md)
  -- problem quantification, existing toolchain, general implementation
  steps, references, and the AI-assistance notes and original prompts.

Author-year citations such as (Alpha Omega 2025) refer to the reference list in
[architecture-overview-references.md](architecture-overview-references.md#references).

The transition of the global software industry toward a more transparent and
secure supply chain has reached a critical juncture.
Modern software development is no longer characterized by the creation of
monolithic, self-contained codebases; rather, it is a process of assembling
diverse, often opaque, components from a myriad of upstream sources (IBM 2026).
This shift has introduced profound security challenges, most notably the
"phantom dependency" problem, where bundled libraries and build-time artefacts
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
reactive, manual inspection of their environments--a process that is
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
| Binary SBOM | Compiled Artefacts | Symbols, hashes, embedded signatures (Wiz 2026). |
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

**`specVersion` must track which profiles/classes a document actually
uses, not a fixed default.** Pitloom currently hardcodes
`CreationInfo.specVersion = "3.0.1"` in `assemble/spdx3/creation_info.py`,
which is correct today only because 3.0.1 is the sole released SPDX 3.x
version and nothing Pitloom emits requires a later one. This will stop
being sufficient the moment Pitloom emits a class or property first
introduced in a later minor version -- for example, the Hardware profile,
introduced in SPDX 3.1 and absent from 3.0/3.0.1. At that point
`specVersion` needs to be computed as the maximum version required by
whatever profiles/classes/properties are actually present in the
document, not left as a static string.

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
of an AI system's origin--a requirement increasingly mandated
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
linked into the artefact (Alpha Omega 2025).

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

See [working-docs/implementation/file-map.md](../implementation/file-map.md)
for the canonical, up-to-date project tree.
