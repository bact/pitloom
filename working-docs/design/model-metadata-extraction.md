---
Created: 2026-03-05
Last-Modified: 2026-11-21
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
| JAX (Orbax) | Higher | `orbax-checkpoint` for pytree structure inspection without full restoration. See [jax-orbax-support.md](jax-orbax-support.md) for the verified on-disk format, detection marker, and field mapping | jax, orbax-checkpoint. Stores checkpoints as directories, one subdirectory per step |
| CRFsuite | Built in #294 | Pure-Python header and label reader in `formats/`: magic `lCRF`, label strings, attribute/feature counts; no weights. See [crfsuite-support.md](../implementation/crfsuite-support.md) | none at runtime; python-crfsuite only to generate test fixtures |
| Flax msgpack | Higher, with JAX | Walk the msgpack tree, read each array's shape and dtype, skip its bytes. See [jax-orbax-support.md](jax-orbax-support.md#flax-msgpack-files-flax_modelmsgpack) | open: a bounded stdlib walker or the `msgpack` package; `flax` only to generate fixtures |
| TensorFlow Lite | Higher | Parse the FlatBuffer (`TFL3` identifier at offset 4) without the TF runtime. See [tensorflow-lite-savedmodel-support.md](tensorflow-lite-savedmodel-support.md) | stdlib-only walker, or the `tflite` bindings (flatbuffers, numpy) |
| TensorFlow SavedModel | Planned | Parse `saved_model.pb` via Protocol Buffers; inspect `MetaGraphDef` for signature defs; a directory target, like Orbax. Same file | tensorflow (or `tensorflow.core.protobuf.saved_model_pb2` for protobuf-only parsing) |
| Scikit-learn | Planned, complex | Pickle/joblib serialisation -- no single standard format; `fickling` for safe AST inspection to extract estimator class and `get_params()` values | scikit-learn, fickling (already an optional dependency). Common extensions: `.pkl`, `.joblib`. The challenge is that the serialised type varies widely (`Pipeline`, `GridSearchCV`, etc.) |
| MLflow model flavors | Planned | `MLmodel` YAML file in the artifact directory records `flavors`, `run_id`, and artifact paths | Not built. A `loom.from_mlflow_run()` helper is planned (see [mlflow-extractor.md](mlflow-extractor.md)); direct model flavor parsing is a separate step |

## Fields the built readers could read

Found by the fact-check of the AI SBOM workshop paper (2026-11-14, 0.24.0
code): data each format carries that its reader leaves unread. Built
2026-11-21 (model-reader gaps PR): GGUF datasets (`general.datasets` and
`general.dataset.<id>.*` as `trainedOn`), the PT2 parameter count and
`torch_version`, the CRFsuite parameter count (`FEAT.num`), the ONNX
producer as the file's writing tool, Safetensors plain `license` and
`model_version`. See [docs/ai-model-formats.md](../../docs/ai-model-formats.md).
Still open:

- **PT2 trainable-parameter count from `is_param`.** The PT2 count sums
  every stored weight (parameters and buffers), as every other format's
  `parameters` entry does and as the package comment says ("elements in
  the model's stored tensors"). `is_param` would give a separate trainable
  count, which needs its own key or property (FG-1 in
  [sbom-format-gaps.md](sbom-format-gaps.md)), not the `parameters` entry.
- **PT2 input and output dtype and shape.** `models/model.json`
  `tensor_values` holds each signature tensor's `dtype` (a `torch.export`
  `ScalarType` number) and `sizes`; mapping the number needs the schema's
  enum (`torch/_export/serde/schema.py`), checked against a real export.
- **GGUF lineage.** `general.base_model.count` with
  `general.base_model.N.{name,organization,version,repo_url,...}` could map
  to `descendantOf`, and `general.source.url` and
  `general.source.huggingface.repository` to where the model came from.
  Open: the base-model package today assumes a Hub id (its `externalRef` is
  `https://huggingface.co/<id>`), and a GGUF entry is a display name plus a
  URL; one model may name several. Kept as properties until decided. See
  also [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md)
  (`general.base_model.N.*`).
- **The Hub's declared per-file SHA-256.** `model_info(files_metadata=True)`
  gives each LFS file's `lfs.sha256` (and `size`): a hash the Hub states,
  never measured by Pitloom. Not built: the Hub route writes one
  `ai_AIPackage` for the repository and no per-file element, so there is
  nowhere to hang a declared hash yet. Decide first the element (one
  `software_File` per repository file, `contains` from the package, as a
  local LFS pointer file gets with its `oid`, FG-10) or a record (a
  provenance record listing paths and hashes, as the PyPI acquisition
  record, FG-15), and the cost (`files_metadata=True` returns every file's
  entry: tens of thousands for a large repository), on top of #507, which
  reworked the same `model_info()` call (timeouts). Record it as declared
  (evidence level `declared`, source the Hub API; see
  [evidence-levels.md](evidence-levels.md)). Related: the Hub per-file
  format entry in [known-bugs](known-bugs/ai-models-readers-and-metadata.md)
  and [hub-model-file-range-read.md](hub-model-file-range-read.md).

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
