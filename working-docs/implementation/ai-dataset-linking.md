---
Created: 2026-09-17
Last-Modified: 2026-10-20
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Dataset-to-model relationship linking

See also: [roadmap.md](../design/roadmap.md) (Near-term -- "Extractors"),
[sbom-enrichment.md](../design/sbom-enrichment.md) (the enrichment
design this feeds into).

Split out of `roadmap.md` (2026-09-17) once this item's detail grew
past a summary.

## What shipped

`AiModelMetadata` carries dataset references (`DatasetReference`,
`pitloom.core.dataset_metadata`). `add_datasets_for_model()`
(`src/pitloom/assemble/spdx3/dataset.py`) emits `trainedOn`/`testedOn`
`Relationship`s natively, falling back to `RelationshipType.other` plus
an explanatory comment for the three relationship types SPDX 3.0.1
itself lacks: `finetunedOn`, `validatedOn`, `pretrainedOn`.

Wired in from `assemble/spdx3/ai.py` and `_document_model.py`.

## One dataset, several roles

`add_datasets_for_model()` first merges the references that name one dataset
(`pitloom.core.dataset_merge`, key from `core/dataset_names.dataset_key`), then
builds one package, creator and licence elements per dataset and one
relationship per role.

- The first reference's values win. A later one fills a field the first leaves
  unset (`None`, empty text or list; a stated `0` is a value), with that
  field's provenance; `license` and `further_licenses` move together.
- Two references that both set a field to different values keep the first and
  log one `WARNING: DATASET=<name> FIELD=<field>: ...` per field.
- Enrichment's creation info is looked up under every merged spelling.
- Not merged: a dataset's parts (train, test). See
  [dataset-splits.md](../design/dataset-splits.md).
