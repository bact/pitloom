---
Created: 2026-03-05
Last-Modified: 2026-08-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model metadata extraction: planned formats and dataset linking

See [implementation/model-metadata-extraction.md](../implementation/model-metadata-extraction.md)
for what's already shipped (implemented format extractors, reference
tools/prior art). This file covers what isn't built yet.

## Planned format support

The formats below are on the roadmap.
Priority ordering reflects breadth of use and feasibility of safe extraction
without executing model code.

| Format | Priority | Extraction approach | Key Python libraries |
| :----- | :------- | :------------------ | :-------------------- |
| JAX (Orbax) | Higher | `orbax-checkpoint` for pytree structure inspection without full restoration | jax, orbax-checkpoint. Stores checkpoints as directories of arrays; metadata in YAML config files alongside checkpoint data |
| TensorFlow SavedModel | Planned | Parse `saved_model.pb` via Protocol Buffers; inspect `MetaGraphDef` for signature defs | tensorflow, tflite-support (or `tensorflow.core.protobuf.saved_model_pb2` for protobuf-only parsing) |
| TensorFlow Lite | Planned | Parse FlatBuffer binary without loading the TF runtime | flatbuffers -- no GPU/runtime required |
| Scikit-learn | Planned, complex | Pickle/joblib serialisation -- no single standard format; `fickling` for safe AST inspection to extract estimator class and `get_params()` values | scikit-learn, fickling (already an optional dependency). Common extensions: `.pkl`, `.joblib`. The challenge is that the serialized type varies widely (`Pipeline`, `GridSearchCV`, etc.) |
| MLflow model flavors | Planned | `MLmodel` YAML file in the artifact directory records `flavors`, `run_id`, and artifact paths | Partially addressed via `pitloom.loom.from_mlflow_run()` (SPDX fragment path); direct model flavor parsing is a separate step |

## AI dataset metadata extraction

If the dataset used for AI training, fine-tuning, or testing is
available on platforms like Hugging Face, Kaggle, or OpenML,
the dataset may have metadata in machine-readable Croissant format.
<https://github.com/mlcommons/croissant>

For dataset-to-model linking within the SBOM, SPDX 3 provides dedicated
relationship types between `ai_AIPackage` and `dataset_DatasetPackage`:
`trainedOn`, `testedOn`, `finetunedOn`, `validatedOn`, and `pretrainedOn`.
`trainedOn`/`testedOn` are implemented and emitted today (from Hugging
Face Hub extraction and the `sbom-enrich` README/model-card enricher);
`finetunedOn`/`validatedOn`/`pretrainedOn` are defined vocabulary with a
working fallback (`RelationshipType.other` plus an explanatory comment)
but not yet produced by any extractor or enricher. See
[sbom-enrichment.md](sbom-enrichment.md) for the dataset linking design
plan.
