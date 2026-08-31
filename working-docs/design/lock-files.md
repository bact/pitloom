---
Created: 2026-08-31
Last-Modified: 2026-08-31
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Parsing Python Lock Files: An SBOM Generation Roadmap for AI and PEP 751

See also: [poetry-support.md](../implementation/poetry-support.md)'s
"`poetry.lock` transitive dependencies" section -- `poetry.lock` support
(Phase 3 in the table below) already shipped (2026-08-31), ahead of this
roadmap's own priority order, as a scoped follow-on to Poetry wheel-file
discovery rather than as part of a general lock-file initiative. Its
design (source-stage-only scoping, direct/transitive dedup, additive
`dependsOn` edges tagged `RelationshipCompleteness.complete`) came from
[sbom-lifecycle-stages.md](sbom-lifecycle-stages.md)'s source/build/deployed
staging model, which this document's priority table doesn't use -- worth
reconciling if the two priority framings diverge as more formats land.
See `working-docs/design/roadmap.md`'s "Remaining lock formats as a
resolved-dependency source" item for the up-to-date status of every
other format below.

**Illustrative code only, not a drop-in design.** The Pydantic models and
hand-rolled `SPDXRef-*`/raw-dict SPDX 3 serializer below are a sketch,
not shaped to this codebase: Pitloom uses stdlib dataclasses
(`ProjectMetadata`/`ProjectFile`, not Pydantic), `spdx_python_model.bindings`
plus `generate_spdx_id()`'s UUID5-namespaced scheme (not hand-built
`SPDXRef-*` strings), `build_relationship()`, and per-field provenance
tracking via `emit_provenance()` throughout. A real implementation for
any format below should follow `_poetry_lock.py` (extraction) and
`deps.py`/`document.py` (assembly)'s established pattern instead of
adapting this sketch's shapes.

Python's dependency ecosystem is fragmented, especially in AI pipelines where
pure-Python packages mix with hardware-specific Conda binaries.
Building an effective SBOM generator requires targeting modern,
high-performance tools like `uv` and `pixi` while establishing the PEP 751
(`pylock.toml`) standard as a universal baseline.
The blueprint below outlines a prioritized extraction roadmap, an internal
normalization schema, and serializers for CycloneDX 1.7 and SPDX 3.0.
The provided code is illustrative—implementers should adapt and adjust these
foundational models to fit their specific system requirements.

## 1. Extraction Priority Roadmap

With PEP 751 (`pylock.toml`) serving as the official standard,
we treat it as the highest priority. By building a robust parser for this
format first, your scanner can instantly support tools like `uv` and `PDM`
simply by asking users to run `[tool] export --format pylock`.

| Phase | Target Format | Why It Matters for AI/ML & Python |
| --- | --- | --- |
| **1: The Universal Core** | `pylock.toml` (PEP 751) | The official Python interoperability standard. Universal fallback. |
| | `pyproject.toml` | Standard project metadata (PEP 621) to define the root SBOM component. |
| | `uv.lock` | The dominant lock file for modern, high-performance ML inference stacks (vLLM, FastAPI). |
| | `requirements.txt` | Ubiquitous in ML research Dockerfiles, PyTorch deployments, and Hugging Face spaces. |
| **2: AI/ML Native Binary** | `pixi.lock` | Essential for AI: natively resolves both Python packages and system-level C/C++ CUDA/Conda binaries. |
| | `conda-lock.yml` | Maps Conda data science packages alongside PyPI wheels. |
| **3: Corporate Standards** | `poetry.lock` | **Done (2026-08-31)** -- see the "See also" note above. Massive legacy and enterprise footprint in Data Engineering (Airflow, dbt). |
| **4: Legacy & Niche** | `pdm.lock` | PDM leads PEP standard compliance, but `pylock.toml` export handles most PDM use cases. |
| | `Pipfile.lock` | Largely legacy tooling. Low priority. |

---

## 2. Internal Normalization Schema (Pydantic)

This model acts as the translation layer. Parsers map proprietary lock file
syntax into this single, standard representation.

```python
from pydantic import BaseModel, Field, computed_field
from typing import List, Dict, Optional
from enum import Enum
import uuid
from datetime import datetime, timezone


class Ecosystem(str, Enum):
    PYPI = "pypi"
    CONDA = "conda"


class PackageHash(BaseModel):
    algorithm: str = Field(description="e.g., 'SHA-256'")
    value: str = Field(description="The cryptographic hash content")


class Package(BaseModel):
    name: str
    version: str
    ecosystem: Ecosystem = Field(default=Ecosystem.PYPI)
    hashes: List[PackageHash] = Field(default_factory=list)
    dependencies: List[str] = Field(
        default_factory=list, description="Names of direct dependency packages"
    )

    @computed_field
    @property
    def purl(self) -> str:
        """Generates standard Package URL used for CVE lookup."""
        return f"pkg:{self.ecosystem.value}/{self.name}@{self.version}"


class ProjectMetadata(BaseModel):
    name: str
    version: str = "0.0.0"


class NormalizedLockData(BaseModel):
    """Universal internal representation of a parsed lock file."""

    metadata: ProjectMetadata
    packages: Dict[str, Package] = Field(default_factory=dict)
    root_dependencies: List[str] = Field(default_factory=list)
```

---

## 3. Serialization Engines

These serializers take your `NormalizedLockData` model and project it into
the two dominant SBOM standards.

### CycloneDX 1.7 JSON Serializer

CycloneDX uses a flat array of components and a dedicated dependency
relationship graph. It is the preferred format for strict security and
vulnerability mapping.

```python
class CycloneDX17Serializer:
    @staticmethod
    def generate(data: NormalizedLockData) -> dict:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        root_purl = f"pkg:pypi/{data.metadata.name}@{data.metadata.version}"

        # 1. Build flat component list
        components = []
        for pkg in data.packages.values():
            components.append(
                {
                    "type": "library",
                    "name": pkg.name,
                    "version": pkg.version,
                    "purl": pkg.purl,
                    "bom-ref": pkg.purl,  # Used for relationship mapping
                    "hashes": [
                        {"alg": h.algorithm.upper(), "content": h.value}
                        for h in pkg.hashes
                    ],
                }
            )

        # 2. Build dependency graph using PURLs as references
        dependencies = []

        # Root project relationships
        dependencies.append(
            {
                "ref": root_purl,
                "dependsOn": [
                    data.packages[dep_name].purl
                    for dep_name in data.root_dependencies
                    if dep_name in data.packages
                ],
            }
        )

        # Package-to-package relationships
        for pkg in data.packages.values():
            if pkg.dependencies:
                dependencies.append(
                    {
                        "ref": pkg.purl,
                        "dependsOn": [
                            data.packages[dep_name].purl
                            for dep_name in pkg.dependencies
                            if dep_name in data.packages
                        ],
                    }
                )

        # 3. Assemble CDX 1.7 specification
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.7",
            "serialNumber": f"urn:uuid:{uuid.uuid4()}",
            "version": 1,
            "metadata": {
                "timestamp": timestamp,
                "component": {
                    "type": "application",
                    "name": data.metadata.name,
                    "version": data.metadata.version,
                    "bom-ref": root_purl,
                },
            },
            "components": components,
            "dependencies": dependencies,
        }
```

### SPDX 3.0 JSON-LD Serializer

SPDX 3.0 utilizes a JSON-LD data structure (the `@graph` list).
Everything—the document, the packages, and the relationships—is a flat element
in the graph connected via unique `spdxId` fields.

```python
class SPDX3Serializer:
    @staticmethod
    def generate(data: NormalizedLockData) -> dict:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        doc_spdx_id = f"SPDXRef-DOCUMENT"
        root_spdx_id = f"SPDXRef-RootPackage-{data.metadata.name}"

        # Context and core elements
        graph = [
            {
                "type": "SpdxDocument",
                "spdxId": doc_spdx_id,
                "name": f"{data.metadata.name}-SBOM",
                "creationInfo": {
                    "created": timestamp,
                    "creators": ["Tool-YourPythonSBOMGen"],
                },
            },
            {
                "type": "software_Package",
                "spdxId": root_spdx_id,
                "name": data.metadata.name,
                "packageVersion": data.metadata.version,
                "primaryPurpose": "APPLICATION",
            },
            {
                "type": "Relationship",
                "spdxId": f"SPDXRef-Rel-Doc-Root",
                "from": doc_spdx_id,
                "relationshipType": "DESCRIBES",
                "to": [root_spdx_id],
            },
        ]

        # Define all packages
        for pkg in data.packages.values():
            pkg_id = f"SPDXRef-Package-{pkg.name}-{pkg.version}"

            package_element = {
                "type": "software_Package",
                "spdxId": pkg_id,
                "name": pkg.name,
                "packageVersion": pkg.version,
                "primaryPurpose": "LIBRARY",
                "externalIdentifiers": [
                    {
                        "type": "ExternalIdentifier",
                        "externalIdentifierType": "purl",
                        "identifier": pkg.purl,
                    }
                ],
            }

            # Map hashes if present
            if pkg.hashes:
                package_element["verifiedUsing"] = [
                    {
                        "type": "Hash",
                        "algorithm": h.algorithm.lower(),
                        "hashValue": h.value,
                    }
                    for h in pkg.hashes
                ]

            graph.append(package_element)

            # Map dependencies (Library -> Library)
            for dep_name in pkg.dependencies:
                if dep_name in data.packages:
                    dep_pkg = data.packages[dep_name]
                    dep_id = f"SPDXRef-Package-{dep_pkg.name}-{dep_pkg.version}"

                    graph.append(
                        {
                            "type": "Relationship",
                            "spdxId": f"SPDXRef-Rel-{pkg.name}-dependsOn-{dep_name}-{uuid.uuid4().hex[:8]}",
                            "from": pkg_id,
                            "relationshipType": "DEPENDS_ON",
                            "to": [dep_id],
                        }
                    )

        # Map Root Dependencies
        for root_dep_name in data.root_dependencies:
            if root_dep_name in data.packages:
                root_dep_pkg = data.packages[root_dep_name]
                root_dep_id = (
                    f"SPDXRef-Package-{root_dep_pkg.name}-{root_dep_pkg.version}"
                )

                graph.append(
                    {
                        "type": "Relationship",
                        "spdxId": f"SPDXRef-Rel-Root-dependsOn-{root_dep_name}-{uuid.uuid4().hex[:8]}",
                        "from": root_spdx_id,
                        "relationshipType": "DEPENDS_ON",
                        "to": [root_dep_id],
                    }
                )

        return {
            "@context": "https://spdx.org/rdf/3.0.0/spdx-context.jsonld",
            "@graph": graph,
        }
```
