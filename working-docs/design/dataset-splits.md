---
Created: 2026-10-20
Last-Modified: 2026-10-20
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Dataset splits: the whole and its parts

See also: [ai-dataset-linking.md](../implementation/ai-dataset-linking.md)
(one dataset, several roles: built),
[provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md)
(the role names are provisional and revised there).

Unbuilt. Nothing here is emitted today.

## Question

A train and a test split come from one dataset, yet the model receives
different data from each. Two levels:

1. **The whole:** one source or pool: one name, licence, creator, version.
2. **A part:** the data one stage actually received. Parts differ from each
   other; each is inside the whole.

## What the vocabularies say (read 2026-10-20)

- **Croissant 1.1** (`docs/croissant-spec-1.1.md`, section "Splits"): a split
  is a `RecordSet` with `dataType: cr:Split` (a `name` and a `url` field, one
  record per split); other record sets refer to it through an ordinary field
  with `references`, so the tool can fetch only the files one split needs. The
  spec's COCO example gives the `url` values `cr:TrainingSplit`,
  `cr:ValidationSplit`, `cr:TestSplit`, but `croissant.ttl` defines
  `croissant:TrainSplit`, `TestSplit` and `ValidationSplit`: the two disagree
  on the training name. A split there is a labelled partition of one dataset,
  not a second dataset. The spec also says its ML features are experimental.
- **Hugging Face Hub** (datasets manual configuration): a split is a set of
  files (`configs[].data_files[]` with `split` and `path`, globs allowed).
  There is a level above it: a `config_name` (subset), each with its own
  splits. So whole -> config -> split -> files.
- **SPDX 3.0.1 `DatasetPackage`**: no property or relationship for a part or
  split (13 dataset properties, none about parts). Parts can use `contains`
  ("The `from` Element contains each `to` Element"); a part's role is already
  the model's `trainedOn` / `testedOn`.
- **SPDX 3.1-dev** adds `finetunedOn`, `pretrainedOn` and `validatedOn` (the
  three Pitloom writes as `other` plus a comment under 3.0.1). Its
  `DatasetPackage` also has no split concept. Cardinalities were taken from the
  3.0.1 model file (`tests/fixtures/spdx-model/v3.0.1/spdx-model.ttl`), not from
  the rendered pages: only `datasetType` has a minimum of 1 there.

## Options (SPDX 3.0.1 terms)

1. Nothing: one package for the whole; `trainedOn` / `testedOn` point at it.
   Today's behaviour; no per-part information.
2. **Chosen direction.** One `DatasetPackage` per split, named as the source
   names it (Croissant `splits/name`), under the whole by `contains`; the model's
   `trainedOn` / `testedOn` point at the split. Facts that belong to the whole
   (licence, creator, version) stay on the whole; a split carries only what
   differs (size, files). The role stays on the relationship, so no split type
   is needed.
3. A `software_File` group per split (fits the Hub, where a split is files;
   fits a Croissant record partition less well).
4. Describe the splits in the dataset's `comment` (no machine reading).

## Rules for option 2

- Only a split the source states is recorded; never invented.
- Pitloom links a model to a split only when a source says which split was
  used. Croissant lists a dataset's splits, not which one a model used; else
  the model links to the whole.
- Use the `splits/name` value as written; Croissant's `cr:TrainingSplit` (spec
  example) and `croissant:TrainSplit` (ontology) disagree.
- A split is a record set of type `cr:Split`, a field of any name referencing
  it. The reader needs one stated rule for that.
- Checkers judge each `DatasetPackage`: a split must not look incomplete for
  lacking the whole's creator or licence.

## SPDX proposal (after option 2 has been tried)

`contains` says a part is inside the whole; nothing standard says what the part
is for. Raise with the SPDX AI/Dataset profile group: a way to state a part's
intended use, and whether a part inherits the whole's licence and creator. Bring
concrete gaps found while building option 2, not a design in advance.

## Risks

- `trainedOn` the whole and `trainedOn` a split are both valid and differ: one
  stated rule for which Pitloom emits.
- Reachability: the checkers follow `contains` and `trainedOn` / `testedOn`, so
  a split reached only through `contains` is judged as a dataset.
