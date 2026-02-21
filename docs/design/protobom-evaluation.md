---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Protobom evaluation for format-neutral representation

This report evaluates **Protobom** as the primary universal, format-neutral 
representation for Loom's core orchestration layer. Our specific focus is
regarding the ability to generate AI SBOMs at pre-build/build time and
preserving provenance for AI models and datasets natively.

## 1. Overview of Protobom

Protobom is an open-source project that leverages Protocol Buffers to define a
neutral, intermediate Software Bill of Materials (SBOM) data structure.
It is designed to interpret, manipulate, and seamlessly translate SBOMs across
major specifications such as SPDX (2.3/3.0) and CycloneDX (1.4/1.5/1.6).

By adopting Protobom as Loom's internal state (instead of the
`spdx-python-model` bindings directly), Loom could theoretically generate
`.spdx3.json`, `.spdx2.tv`, and `.cdx.json` formats from a single execution
run without writing custom data-mapping layers.

## 2. Topological considerations: graph vs. tree

### Background

Different SBOM specifications fundamentally perceive dependency hierarchies
differently:

- **CycloneDX** historically relies heavily on a hierarchical
  **tree structure** (components nested inside components).
- **SPDX 3.0** models logic entirely as a **semantic graph** leveraging
  JSON-LD, where every entity is a floating node mapped by directional edges.

### Evaluation

The Protobom spec is fundamentally engineered around a **Graph topology**.
Its Protobuf schema is based on an **Edge List**:

- `NodeList`: A flat list of distinct software components (the vertices).
- `EdgeList`: Identifying connections mapping `id` to `to_id` with
  an explicit relationship type.

**Conclusion:** This is highly advantageous for Loom. Because Protobom
internally operates as a graph, it aligns perfectly with our SPDX 3.0-first
prototype. When translating Protobom's graph out to CycloneDX, the Protobom
exporter library handles the complex flattening/nesting required to mimic
a tree structure via external references. This effectively offloads the
topological complexity away from the Loom ecosystem.

## 3. Analytical focus: AI and dataset constraints

The most significant risk of adopting Protobom revolves around
**information loss** specifically concerning the SPDX 3.0 AI and Dataset
profiles.

### The missing `NodeType` issue

Protobom defines elements via a strict `NodeType` enum (e.g., `BOM`,
`BUILD_SYSTEM`, `DOCUMENTATION`, `FILE`). 

Currently, the Protobom schema **does not possess native node classifications
for AI/ML domains**. 

- There is no `NodeType.AI_MODEL` equivalent to `spdx3.ai_AIPackage`.
- There is no `NodeType.DATASET` equivalent to `spdx3.dataset_DatasetPackage`.

### The missing relationships

SPDX 3.0 AI profiles introduce specialized semantic relationships such as
`trainedOn`, `hasDataFile`, or `finetunedFrom`. 
Protobom's `EdgeType` primitive focuses on traditional software supply chain
links (e.g., `DEPENDS_ON`, `CONTAINS`, `STATIC_LINK`).

### Resulting information loss

If Loom’s `bom.py` tracker extracts deep introspection data from a PyTorch
training loop (e.g., model architecture, preprocessing metrics, and dataset
constraints), passing it through a standard Protobom parser would cause
**forced downgrading**:

- An `AIPackage` would likely be flattened into a generic `PACKAGE` or `FILE`
  node type.
- `trainedOn` relationships would be collapsed into standard `DEPENDS_ON`
  edges.
- Highly specific metadata attributes (like hyperparameters or ethical
  constraints) would be lost or dumped into indistinguishable unstructured
  extensions.

## 4. Workarounds and potential solutions

To fulfill our goal of generating true AI SBOMs at build-time while maintaining
format-neutral capabilities, we have several architectural pathways:

### Option A: Upstream contribution (recommended long-term)

Protobom is an actively developing standard. Loom could author and submit PRs
to the `protobom/protobom` repository to introduce:

1. `NodeType.AI_MODEL` and `NodeType.DATASET`.
2. AI-specific properties inside the `Node` message (or leveraging standard
  Protobuf `Any` extensions designated for AI profiles).

### Option B: The "generic properties" hack

Protobom allows for injecting custom properties/key-values into its nodes.

- *Implementation:* We generate a generic `PACKAGE` Protobom node,
  but attach a custom property prefix: `loom:ai:hyperparameter:learning_rate`.
- *Caution:* This guarantees extreme information loss when exporting to SPDX
  3.0, as standard Protobom exporters will not know how to map `loom:ai:`
  strings back into the formal SPDX 3.0 `ai_AIPackage` class properties.

#### AI SBOM Field Mapping Design (The `loom:ai` Namespace)

To support this workaround and establish a foundation for AI SBOMs that works
across any format natively supporting key-value pairs (e.g., CycloneDX
`properties` or SPDX `Annotations`), we define a strict namespace.

**1. Model Identification & Architecture**

- `loom:ai:model:type`: Broad category (e.g., `transformer`, `cnn`).
- `loom:ai:model:architecture_family`: Specific structural family.
- `loom:ai:model:parameters_count`: Total number of parameters.
- `loom:ai:model:framework`: Base framework/format (e.g., `pytorch`, `onnx`).

**2. Training & Hyperparameters**

- `loom:ai:training:learning_rate`: The base learning rate.
- `loom:ai:training:batch_size`: Training batch size.
- `loom:ai:training:epochs`: Number of full passes over the dataset.
- `loom:ai:training:optimizer`: Optimizer algorithm (e.g., `adamw`, `sgd`).
- `loom:ai:training:random_seed`: Initialization seed for reproducibility.

**3. Dataset Constraints & Provenance**

- `loom:ai:dataset:training:name`: Name/URI of the dataset.
- `loom:ai:dataset:training:size`: Volume of the data (e.g., `1.2TB`).
- `loom:ai:dataset:training:split`: Ratio/segment used (e.g., `train`).
- `loom:ai:dataset:preprocessing`: Normalization or transformation applied.

**4. Metrics & Evaluation**

- `loom:ai:metric:accuracy`: Example: `0.95`.
- `loom:ai:metric:f1_score`: Example: `0.92`.
- `loom:ai:metric:loss`: Final evaluation loss.

**5. Ethical & Compliance Considerations**

- `loom:ai:compliance:license_category`: E.g., `open-weights`.
- `loom:ai:safety:bias_mitigation`: Notes on debiasing techniques applied.
- `loom:ai:safety:intended_use`: Approved use-cases.
- `loom:ai:safety:restricted_use`: Explicitly prohibited use-cases.

### Option C: The hybrid dual-state architecture (recommended short-term)

If we must adopt Protobom immediately for standard dependencies
(e.g., resolving `numpy` versions or Hatchling builds), we can design a
hybrid architecture inside `loom.generator`.

1. **Standard packages:** Python wheels, libraries, and compiler outputs are
  ingested into the `Protobom` universal graph.
2. **AI fragments:** Data emitted strictly from `loom.bom` (datasets, models)
  bypass Protobom and are maintained natively in `spdx-python-model` classes.
3. **Merge phase:** At export time, if the user targets SPDX 3.0, the Protobom
  exporter runs. We then dynamically merge our native `run.model` graphs into
  the serialized JSON output before writing to disk.

## 5. Answered questions from previous exploration

- **CycloneDX ML-BOM parity:** CycloneDX 1.7 (and 1.6/1.5) officially supports
  Machine Learning Components via `type="machine-learning-model"` and the
  `modelCard` element. However, Protobom's intermediate schema lacks the
  `NodeType.AI_MODEL` and inner constructs mapped to a `modelCard`.
  Consequently, Protobom downgrades the ML component into a standard `PACKAGE`
  or drops the `modelCard` data unless explicitly mapped via custom properties.

- **Protobom extensions (`google.protobuf.Any`):** Protocol Buffers natively
  support `Any` fields, allowing the embedding of arbitrary serialized protobuf
  messages. The Protobom Python SDK exposes this, meaning an entire SPDX 3.0
  `AIPackage` could be encapsulated. However, standard Protobom exporters
  (e.g., CycloneDX or SPDX serializers) don't inherentely know how to unpack or
  translate this custom payload. Data will remain an opaque binary blob in the
  serialized output without custom exporter logic.

## 6. Conclusion

Protobom successfully solves the Graph/Tree topology headache and offers
a beautiful solution for traditional Python software dependencies.
However, for Loom's advanced AI provenance tracking, Protobom will introduce
unacceptable data loss out-of-the-box. We must orchestrate a hybrid state or
invest heavily in contributing AI specifications upstream to Protobom before
migrating Loom's core exclusively to the neutral format.
