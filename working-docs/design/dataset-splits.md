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

## Proposal (not decided)

One whole-dataset package; one small element per part, linked by `contains`;
the model points `trainedOn` / `testedOn` at the part. Since a Hub split is a
set of files, the part may be a `software_File` group rather than a second
`DatasetPackage`; to decide against Croissant's split record sets. Because the role sits on
the relationship, no "split type" is needed, only a standard way to say which
part. Raise with the SPDX AI/Dataset profile group only if `contains` plus a
naming convention proves insufficient: a controlled name for a part's role, and
whether a part inherits the whole's licence and creator.

## Risks

- Checkers judge each part: a missing producer counts for the whole and each
  part. Parts should carry only what differs.
- Reachability: parts need the `trainedOn`/`testedOn` edge, the whole needs
  `contains`.
- Sources rarely state parts. A part is never invented; absent stays absent.
- `trainedOn` the whole and `trainedOn` a part both read as valid and differ:
  one stated rule for which Pitloom emits.
