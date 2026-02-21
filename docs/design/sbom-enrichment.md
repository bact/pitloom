---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM enrichment and AI SBOMs

This document outlines the strategies for enriching standard SBOMs with
additional metadata, specifically focusing on the generation of AI SBOMs for
machine learning models and datasets natively within Loom.

## 1. AI SBOM field mapping design (The `loom:ai` namespace)

To establish a foundation for AI SBOMs that works across any format natively
supporting key-value pairs (e.g., CycloneDX `properties` or SPDX
`Annotations`), we define a strict namespace.

**1.1 Model identification & architecture**

- `loom:ai:model:type`: Broad category (e.g., `transformer`, `cnn`).
- `loom:ai:model:architecture_family`: Specific structural family.
- `loom:ai:model:parameters_count`: Total number of parameters.
- `loom:ai:model:framework`: Base framework/format (e.g., `pytorch`, `onnx`).

**1.2 Training & hyperparameters**

- `loom:ai:training:learning_rate`: The base learning rate.
- `loom:ai:training:batch_size`: Training batch size.
- `loom:ai:training:epochs`: Number of full passes over the dataset.
- `loom:ai:training:optimizer`: Optimizer algorithm (e.g., `adamw`, `sgd`).
- `loom:ai:training:random_seed`: Initialization seed for reproducibility.

**1.3 Dataset constraints & provenance**

- `loom:ai:dataset:training:name`: Name/URI of the dataset.
- `loom:ai:dataset:training:size`: Volume of the data (e.g., `1.2TB`).
- `loom:ai:dataset:training:split`: Ratio/segment used (e.g., `train`).
- `loom:ai:dataset:preprocessing`: Normalization or transformation applied.

**1.4 Metrics & evaluation**

- `loom:ai:metric:accuracy`: Example: `0.95`.
- `loom:ai:metric:f1_score`: Example: `0.92`.
- `loom:ai:metric:loss`: Final evaluation loss.

**1.5 Ethical & compliance considerations**

- `loom:ai:compliance:license_category`: E.g., `open-weights`.
- `loom:ai:safety:bias_mitigation`: Notes on debiasing techniques applied.
- `loom:ai:safety:intended_use`: Approved use-cases.
- `loom:ai:safety:restricted_use`: Explicitly prohibited use-cases.

## 2. SBOM enrichment strategies for AI models

Beyond statically defining fields at compilation time, Loom can employ active
sub-component enrichment strategies post-build or during CI/CD pipelines to
construct a more complex and accurate AI SBOM.

This involves unifying traditional SCA/SBOM tools with AI-specific metadata
extractors.

### 2.1 Repository-level extraction (AIMMX)

[AIMMX](https://github.com/IBM/AIMMX) (Automated AI Model Metadata eXtractor)
represents a repository-level approach to metadata discovery. AIMMX infers AI
model characteristics by statically analyzing a software repository's structure,
README files, requirements, and training scripts.

**Loom integration strategy:**

- Invoke AIMMX against the target source repository prior to the build phase.
- Map the inferred architectural details, target tasks (e.g., Natural Language
  Processing), and dataset URIs discovered by AIMMX directly into the `loom:ai`
  namespace.
- **Value:** Fills gaps for models where explicit documentation (Model Cards)
  does not exist but context is present in the codebase.

### 2.2 Structural model introspection

Modern model serialization formats natively embed metadata alongside neural
weights. Loom's `bom.py` generator can directly parse these files during the
build process to enrich the Protobom graph dynamically.

- **Safetensors (`.safetensors`):** Prefix the file with an 8-byte length
  indicator followed by a JSON object containing the `__metadata__` field.
  - *Strategy:* Use `huggingface_hub.get_safetensors_metadata` to parse this
    JSON header without loading multi-gigabyte weight tensors. Extract framework
    details and training hyperparameters into `loom:ai:training:*`.

- **GGUF (`.gguf`):** A single-file binary format designed for edge deployments
  that mandates extensive key-value metadata within its header.
  - *Strategy:* Utilize `gguf-parser` to extract the architecture type and
    quantization parameters. Map quantization specifics to a new field like
    `loom:ai:model:quantization`.

- **ONNX (`.onnx`):** Open Neural Network Exchange uses protobufs and possesses
  defined properties like `doc_string` and a `metadata_props` dictionary.
  - *Strategy:* Use the `onnx` Python package to parse the graph properties. Map
    the ONNX `domain` and `producer_name` to standard SBOM fields while mapping
    custom `metadata_props` into the `loom:ai` extensions.

### 2.3 The hybrid AI-enrichment architecture

To achieve a complete AI SBOM, Loom should orchestrate a multi-stage pipeline:

1. **Standard SCA execution:** Loom runs traditional dependency scanners (e.g.,
  `syft` or `pip-audit`) to generate the baseline Protobom graph of standard
  libraries (`torch`, `numpy`).
2. **Deep introspection:** Loom actively scans for `.safetensors`, `.gguf`, or
  `.onnx` files, parses their headers, and extracts internal model state into
  `loom:ai:*` properties attached to the model's `PACKAGE` node.
3. **Repository contextualization:** Loom merges metadata derived from AIMMX
  analysis (e.g., intended use cases found in READMEs, license contexts) to
  populate compliance and safety fields (`loom:ai:safety:*`).
4. **Protobom export:** The final, enriched Protobom graph is serialized out to
  a complete CycloneDX 1.6/1.7 or SPDX 3.0 document.

### 2.4 External reference linking & dataset repositories

Attempting to aggressively inline the entirety of a dataset's metadata, 
descriptive statistics, and ethical considerations (RAI properties) directly
into the SBOM can lead to severe structural bloat. 

Instead, Loom should support persistent URI linking, specifically leveraging the
[Croissant format](https://mlcommons.org/working-groups/data/croissant/).
Croissant is a JSON-LD based extension of `schema.org/Dataset` heavily adopted 
for dataset representation by Hugging Face, Kaggle, and OpenML.

**Loom integration strategy:**

- **API interrogation:** If a dataset is ingested via a recognized hub, query
  its metadata API (e.g., `huggingface.co/api/datasets/{id}/croissant`).
- **Selective extraction:** Extract only crucial, top-level identity 
  characteristics (Name, License, Target Task) into the `loom:ai:*` schema for
  immediate SBOM visibility.
- **Machine-readable linking:** Create an `ExternalReference` node inside the
  Protobom representation bridging to the full metadata.
  - Map the Croissant document's canonical `@id` (or direct API endpoint) to
    this reference to establish a persistent URI.
  - In SPDX 3.0, map this to an `ExternalReference` with an explicit semantic
    relationship type.
  - In CycloneDX, place it within the `externalReferences` array.
- **Value:** This drastically prevents SBOM bloat while establishing a highly
  reliable, machine-readable cryptographic chain back to exhaustive RAI/MLCommons 
  standards that security tools can subsequently traverse and audit dynamically.
