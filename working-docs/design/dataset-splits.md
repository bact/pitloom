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

## What the vocabularies say (from memory; re-verify before citing)

- Croissant 1.0 models a split as data inside the dataset: a record set with a
  field of type `cr:Split` (`cr:TrainingSplit`, `cr:ValidationSplit`,
  `cr:TestSplit`) that other record sets reference. It is not a second dataset.
- A Hub card lists `configs` with `data_files` per `split` under one dataset id.
- SPDX 3.0.1 has no split concept. It has `contains`, and the model's
  `trainedOn` / `testedOn` already carries the role.

## Proposal (not decided)

One whole-dataset package; one small element per part, linked by `contains`;
the model points `trainedOn` / `testedOn` at the part. Because the role sits on
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
