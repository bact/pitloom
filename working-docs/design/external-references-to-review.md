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
data-quality modelling, metadata sources or serialisation. Nothing here is
built, decided or checked yet: each entry says why it may matter and what to
look at. Record findings in the design doc named in its "Feeds" line, not
here. An entry from a GitHub issue names it; the issue stays a research note
until a finding turns it into work.

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

## ETSI EN 304 223 (cyber security requirements for AI)

- Issue: [#55](https://github.com/bact/pitloom/issues/55).
- Look at: which of its requirements an SBOM or AIBOM can evidence, and
  whether any maps to a property Pitloom can fill from a source.
- Feeds: [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md).

## Signposting

- Site: <https://signposting.org/>
- Issue: [#53](https://github.com/bact/pitloom/issues/53) (how to use it is
  not yet known).
- Look at: whether typed links a landing page (a model or dataset page)
  publishes could locate a licence, a citation or metadata to read, as a
  source for enrichment.
- Feeds: [sbom-enrichment.md](sbom-enrichment.md).

## SBOM-QA (Nokia)

- Issue: [#48](https://github.com/bact/pitloom/issues/48).
- Look at: run its quality checks on Pitloom's own and test SBOMs as a
  benchmark beside the conformance tests.
- Feeds: [testing-ci-followups.md](testing-ci-followups.md).

## orjson

- Repository: <https://github.com/ijl/orjson>
- Issue: [#46](https://github.com/bact/pitloom/issues/46).
- Look at: whether it can give RFC 8785 output (key order, number spelling)
  faster than the `rfc8785` package Pitloom uses today
  (`pitloom.core.canonical_json`, `pitloom.export.spdx3_json`).
- Feeds: [canonical-output-followups.md](canonical-output-followups.md).

## OpenRouter model metadata

- Site: <https://openrouter.ai/>
- Issue: [#129](https://github.com/bact/pitloom/issues/129).
- Look at: which model facts its API states (provider, context length,
  modalities) as a structured source beside the Hugging Face Hub, and its
  terms of use.
- Feeds: [model-metadata-extraction.md](model-metadata-extraction.md).
