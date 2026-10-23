---
Created: 2026-10-21
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# External work to review

See also: [roadmap.md](roadmap.md),
[provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md),
[g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md),
[g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md).

Sources to read before the next change to AI-system, data-provenance or
data-quality modelling. Nothing here is built, decided or checked yet: each
entry says why it may matter and what to look at. Record findings in the
design doc named in its "Feeds" line, not here.

## AI system card (Red Hat)

- Repository: <https://github.com/RedHatProductSecurity/ai-system-card>
- Specification: <https://access.redhat.com/ai/system-card>
- Paper: <https://arxiv.org/abs/2509.20394>
- Look at: how a system card describes an AI *system* (models, data, services,
  controls) and how it relates to SBOM formats; compare with the G7 system-level
  rules, where Pitloom has no system element beyond the root package.
- Feeds: [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md).

## Data Provenance Standard (OASIS TC)

- Technical committee: <https://www.oasis-open.org/tc-dps/>
- Draft: Data Provenance Metadata v1.0, Committee Specification Draft 01
  (2026-05-07):
  <https://docs.oasis-open.org/dps/prov-meta/v1.0/csd01/prov-meta-v1.0-csd01.html>
- Look at: its provenance vocabulary and taxonomy as input to redesigning
  Pitloom's provenance taxonomy.
- Idea, not designed: use it for data provenance *annotation* of datasets, in
  addition to the SBOM. As read from the draft, a `DataProvenance` JSON record
  describes one dataset (`source`, `provenance` with links to source datasets
  for lineage, `use` with licence, consent and AI use) and does not mention
  SBOMs. How the two fit is open: a record beside the SBOM, one per dataset
  package, or an external reference from the dataset element to the record.
  Questions: which SPDX 3 element or relationship points at a record; which
  record fields Pitloom could fill from sources without guessing (`license`,
  `AIUse`, source links from Croissant or a Hub card), leaving the rest
  absent; whether the draft's JSON Schema is stable enough to emit (only JSON
  has content; JADN, YAML and XML are placeholders). Check whether the record
  should be an output of `loom` or only of the `loom.run` SDK.
- Feeds: [provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md).

## ETSI data quality metrics (Data Solutions, DATA)

Development and identification of data quality metrics.

- Press release: <https://www.etsi.org/newsroom/press-releases/etsi-launches-new-framework-to-measure-data-quality-a-key-enabler-for-trustworthy-ai/>
- ETSI TR 104 180 V1.1.1:
  <https://www.etsi.org/deliver/etsi_tr/104100_104199/104180/01.01.01_60/tr_104180v010101p.pdf>
- Look at: which data-quality metrics a dataset element could carry, and which
  Pitloom could extract without guessing (a metric a source does not state
  stays absent).
- Feeds: [g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md)
  (dataset statistics and what SPDX 3.0.1 cannot record).
