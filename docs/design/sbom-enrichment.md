---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM enrichment and AI SBOMs

This document outlines strategies for enriching SBOMs with additional metadata,
focusing on AI model and dataset information in Pitloom.

## Current implementation

Pitloom maps extracted model metadata to SPDX 3 native AI profile fields on
`ai_AIPackage`. The mapping is handled in `pitloom.assemble.spdx3.ai`:

| `AiModelMetadata` field | SPDX 3 field |
| :---- | :---- |
| `name` | `name` |
| `version` | `software_packageVersion` |
| `description` | `description` |
| `type_of_model` | `ai_typeOfModel` |
| `hyperparameters` | `ai_hyperparameter` (list of `DictionaryEntry`) |
| `inputs` / `outputs` | `ai_informationAboutApplication` (JSON string) |
| `format_version` | not yet mapped — candidate: `comment` or custom `ExternalRef` |
| `framework` | not yet mapped — candidate: `ai_informationAboutApplication` or `comment` |
| `framework_version` | not yet mapped — candidate: `comment` or `ExternalRef` |
| `properties` | not yet mapped (stored in `AiModelMetadata.properties`, not emitted to SPDX) |
| `provenance` | `comment` |

`ai_AIPackage` elements are linked to the main Python package via an SPDX
`contains` relationship.

## Planned: dataset-to-model relationship linking

A current gap in Pitloom's SBOM output is that only the AI model itself is
documented, not its associated training, evaluation, or fine-tuning datasets.

SPDX 3 provides the `dataset_DatasetPackage` class and dedicated relationship
types between `ai_AIPackage` and `dataset_DatasetPackage`:

| SPDX 3 Relationship type | Meaning |
| :---- | :---- |
| `trainedOn` | Primary dataset used to train the model |
| `testedOn` | Dataset(s) used to evaluate the trained model |
| `finetunedOn` | Dataset used for fine-tuning a pre-trained model |
| `validatedOn` | Dataset used for validation during training |
| `pretrainedOn` | Dataset used to pre-train a foundation model |

### Implementation approach

1. Extend `AiModelMetadata` with a `datasets` field (list of `DatasetReference`
   dataclass) carrying: role (trained/tested/etc.), name, URI, and license.
2. Add `dataset_DatasetPackage` element creation to `pitloom.assemble.spdx3.ai`.
3. Emit the appropriate relationship type for each dataset reference.
4. Append `ProfileIdentifierType.dataset` to `profileConformance` when at least
   one dataset element is present.

### Dataset metadata sources

When a dataset is available on a recognised hub, its metadata can be retrieved
in machine-readable Croissant format (JSON-LD extension of `schema.org/Dataset`),
adopted by Hugging Face, Kaggle, and OpenML.
<https://github.com/mlcommons/croissant>

To avoid SBOM bloat, only top-level identity fields (name, license, task) should
be inlined into the `dataset_DatasetPackage` element; exhaustive provenance can
be linked via an `ExternalRef` pointing to the Croissant document URL.

## Planned: SBOM enrichment from external sources

Model formats that carry little embedded metadata (PyTorch classic, Scikit-learn
pickles, some HDF5 files) can be enriched with information from external sources.
This is analogous to what
[AIMMX](https://github.com/IBM/AIMMX) does at the repository level and what
[Parlay](https://github.com/snyk/parlay) does by querying third-party services
such as OpenSSF Scorecard and package registries.

### Enrichment data sources

| Source | What it provides | Network required | Default |
| :----- | :--------------- | :--------------- | :------ |
| Repository README / model card | Task description, intended use, dataset references, license notes | No (local file) | Enabled |
| Hugging Face Hub metadata | Architecture, tags, license, dataset links, paper references | Yes | User opt-in |
| OpenSSF Scorecard | Supply chain security posture of the upstream project | Yes | Enabled (low cost, public API) |
| Parlay package enrichment | Package ecosystem metadata (description, homepage, license) | Yes | Enabled |
| PyPI / conda metadata | Version history, maintainers, download stats | Yes | User opt-in |

### Enable/disable per source

Because some enrichment functions require a network connection or may raise
licensing questions (e.g., pulling data from a hub that has terms of use),
Pitloom should allow users to enable or disable each source independently in
`pyproject.toml`:

```toml
[tool.pitloom.enrich]
local = true          # README / model card — always safe, on by default
openssf_scorecard = true   # public API, no auth required
huggingface = false   # opt-in: requires network, data under HF ToS
pypi = false          # opt-in: requires network
```

OpenSSF Scorecard should be enabled by default as it is a public API with
no authentication requirement and provides immediate supply chain security value.

### Enricher implementation approach

1. Add an `enrich/` subpackage to `pitloom` with one module per data source
   (e.g., `enrich/readme.py`, `enrich/openssf.py`, `enrich/huggingface.py`).
2. Each enricher accepts an `AiModelMetadata` and updates it in-place, following
   the same in-place mutation pattern used by the model extractors.
3. The `generate_sbom()` orchestrator reads the `[tool.pitloom.enrich]` config
   and dispatches to the enabled enrichers after extraction but before assembly.
4. Provenance is recorded for each enriched field (source, field path)
   using the existing `AiModelMetadata.provenance` dict.

## AI SBOM field mapping: `pitloom:ai` namespace (CycloneDX)

When Pitloom gains CycloneDX output support, SPDX 3 native fields have no
direct equivalent and must be expressed as CycloneDX `properties` entries.
The following namespace is reserved for that purpose:

### Model identification and architecture

- `pitloom:ai:model:type` — broad category (e.g., `transformer`, `cnn`)
- `pitloom:ai:model:architecture_family` — specific structural family
- `pitloom:ai:model:parameters_count` — total parameter count
- `pitloom:ai:model:format_version` — version of the model file format
  (e.g., `v2` for Keras v2, `1.0` for NumPy 1.0)
- `pitloom:ai:model:framework` — base framework/format
  (e.g., `pytorch`, `onnx`, `keras`)
- `pitloom:ai:model:framework_version` — version of the framework that produced
  the model (e.g., `2.15.0` for Keras 2.15.0)

### Training and hyperparameters

- `pitloom:ai:training:learning_rate`
- `pitloom:ai:training:batch_size`
- `pitloom:ai:training:epochs`
- `pitloom:ai:training:optimizer` — optimizer algorithm (e.g., `adamw`, `sgd`)
- `pitloom:ai:training:random_seed`

### Dataset constraints and provenance

- `pitloom:ai:dataset:training:name` — name or URI of the training dataset
- `pitloom:ai:dataset:training:size` — volume of data (e.g., `1.2TB`)
- `pitloom:ai:dataset:training:split` — ratio or segment used (e.g., `train`)
- `pitloom:ai:dataset:preprocessing` — normalization or transformation applied

### Metrics and evaluation

- `pitloom:ai:metric:accuracy`
- `pitloom:ai:metric:f1_score`
- `pitloom:ai:metric:loss`

### Ethical and compliance considerations

- `pitloom:ai:compliance:license_category` — e.g., `open-weights`
- `pitloom:ai:safety:bias_mitigation` — notes on debiasing techniques applied
- `pitloom:ai:safety:intended_use` — approved use cases
- `pitloom:ai:safety:restricted_use` — explicitly prohibited use cases
