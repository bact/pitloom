---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Format-neutral SBOM representation

## Overview

The current Pitloom implementation integrates with `spdx-python-model` to produce
SPDX 3 output. While SPDX 3 is the primary target, the future software supply
chain landscape will require support for multiple output specifications and
formats — and potentially non-SBOM outputs such as AIDOC documentation or
TechOps reports.

To ensure long-term maintainability and flexibility, Pitloom introduces a
format-neutral internal document model. This approach decouples metadata
extraction from final output serialization, enabling the same extraction
pipeline to drive any requested output format.

## Goals

An ideal internal representation must be:

- **Format-neutral**: Not tied to SPDX, CycloneDX, or any other spec's
  structural quirks.
- **Lossless**: Preserves all captured information so every serializer can
  use what it needs.
- **Composable**: Combines metadata from multiple sources (pyproject.toml,
  AI model files, MLflow runs, pre-generated fragments) before serialization.
- **Serializer-agnostic**: Any number of serializers can consume the same
  `DocumentModel` independently.

## Architecture

```text
Extractors                     Core model              Serializers / Assemblers
──────────────────────         ─────────────────       ─────────────────────────
read_pyproject()           ─┐
read_ai_model()            ─┤─→  DocumentModel   ─→   Spdx3Assembler              → SPDX 3 JSON-LD
bom.track() (fragments)    ─┘    (pitloom.core)          [future] CycloneDXAssembler → CycloneDX JSON
                                                      [future] AidocRenderer      → AIDOC markdown
                                                      [future] TechOpsDoc         → documentation
```

### `DocumentModel` (``pitloom.core.document``)

```python
@dataclass
class DocumentModel:
    creation: CreationMetadata        # who/when generated this document
    project: ProjectMetadata          # from read_pyproject()
    ai_models: list[AiModelMetadata]  # from read_ai_model()
```

`DocumentModel` holds everything that *could* appear in any output format.
Serializers pick the fields they understand and ignore the rest.

### Separation of concerns

| Layer | Responsibility | Key types |
| :---- | :---- | :---- |
| **Extractors** | Read data sources; populate metadata objects | `ProjectMetadata`, `AiModelMetadata` |
| **Core model** | Format-neutral assembled document | `DocumentModel`, `PitloomConfig`, `CreationMetadata` |
| **Assemblers** | Translate `DocumentModel` → format-specific objects | `Spdx3JsonExporter`, future exporters |
| **Orchestrator** | Build `DocumentModel`, call assembler, merge fragments | `generate_sbom()` |

## Data classes in ``pitloom.core``

| Class | Module | Description |
| :---- | :---- | :---- |
| `ProjectMetadata` | `pitloom.core.project` | Python project fields from `pyproject.toml` |
| `AiModelMetadata` | `pitloom.core.ai_metadata` | AI model fields (GGUF, ONNX, Safetensors) |
| `PitloomConfig` | `pitloom.core.config` | `[tool.pitloom]` settings (`pretty`, `fragments`) |
| `CreationMetadata` | `pitloom.core.creation` | SBOM creator / timestamp |
| `DocumentModel` | `pitloom.core.document` | Composed document ready for serialization |

All of these are plain Python dataclasses with no dependency on any SBOM
library, making them easy to test and to target from any serializer.

## Adding a new output format

To add a CycloneDX serializer, for example:

1. Create `pitloom/assemble/cyclonedx/` subpackage.
2. Write `build(doc: DocumentModel) -> str` that reads `doc.project`,
   `doc.creation`, and `doc.ai_models`.
3. Add a `--format` flag to the CLI that selects the assembler.
4. No changes needed to `pitloom.extract` or `pitloom.core`.

## Protobom evaluation

Protobom was evaluated as a candidate for the format-neutral layer
(see `docs/design/protobom-evaluation.md`). While it provides a
Protocol Buffers–based universal SBOM representation with good support for
SPDX 2.x and CycloneDX conversion, it does not yet cover the SPDX 3
AI/Dataset/Build profiles that are central to Pitloom's use cases. Adopting
Protobom would introduce a significant dependency while leaving key fields
unmapped. The lightweight `DocumentModel` approach is preferred for the
current scope.

## Roadmap

- [x] `ProjectMetadata` as format-neutral Python project representation
- [x] `AiModelMetadata` as format-neutral AI model representation
- [x] `DocumentModel` composing both, passed to SPDX 3 assembler
- [ ] MLflow run metadata added to `DocumentModel`
- [ ] CycloneDX assembler consuming `DocumentModel`
- [ ] AIDOC renderer consuming `DocumentModel`
