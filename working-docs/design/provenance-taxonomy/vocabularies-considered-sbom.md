---
Created: 2026-11-23
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Vocabularies considered: SBOM formats, guidance and other tools

See also: [vocabularies-considered.md](vocabularies-considered.md) (how
each vocabulary is used, the summary table, the general vocabularies,
what none of them gave; this page was part of it until 2026-11-23),
[README.md](README.md) (the claim model).

**Status:** draft. One entry each, in the form of the first page: what
it is, its domain, why it bears on this work, and how it is used here
or not. Each description is from the text's own published form, read
2026-11-16 (CISA) or 2026-11-19 (the rest), unless an entry gives
another date; quoted words are the source's.

## SBOM formats and guidance

### SPDX 3

- **What:** the SBOM specification Pitloom's output conforms to (version
  3.0.1, JSON-LD).
- **Domain:** software bills of materials, with profiles for licensing,
  AI and datasets.
- **Relevance:** every claim ends as an SPDX property or relationship,
  and three of its terms force a decision the taxonomy has to make:
  `hasDeclaredLicense` against `hasConcludedLicense`, the relationship
  `completeness`, and the "no assertion" and "none" individuals.
- **Use:** output and mapping. The licence table goes from Asserter to
  the two licence relationships ([asserter-licence.md](asserter-licence.md));
  `originatedBy`, `createdUsing` and `createdBy` name three of the five
  asserters; value strength maps to `NoAssertionLicense` and
  `NoneLicense` ([value-strength.md](value-strength.md)).
- **Not enough alone, because:** version 3.0.1 has no property for the
  provenance of one field of an element. Pitloom writes it in
  Annotations, and the facets here are what a provenance profile would
  need (issue #110).

### CycloneDX evidence

- **What:** OWASP CycloneDX, "a full-stack Bill of Materials (BOM)
  standard", also published as ECMA-424 (version 1.7 schema read). Its
  component `evidence` object documents "evidence collected through
  various forms of extraction or analysis".
- **Domain:** bills of materials: software, services, hardware, models.
- **Relevance:** the one SBOM format read with evidence for a single
  field. An identity entry names the `field`, a `concludedValue`, and
  `methods`, each a `technique` (one of ten: `manifest-analysis`,
  `binary-analysis`, `hash-comparison`, `filename`, `attestation`,
  `other`, and four more) with a `confidence` from 0 to 1. For a
  licence it has three notions: an `acknowledgement` of `declared`
  ("the initial intentions of authors") or `concluded` ("verified and
  confirmed"), and observed licences in `evidence.licenses`, "the
  evidence necessary to substantiate a concluded license".
- **Use:** mapping only: method classes and evidence values to
  `technique` and `confidence`, `selected` to `concludedValue`, source
  location to `evidence.occurrences` ([method.md](method.md),
  [basis.md](basis.md), [source.md](source.md),
  [conflict.md](conflict.md)).
- **Not adopted as the vocabulary, because:** Pitloom writes SPDX; the
  method and confidence exist for nine identity fields only (group,
  name, version, purl, cpe, omniborId, swhid, swid, hash), and the
  licence evidence carries neither; one `technique` word holds what was
  read and how; and it names the tools of an analysis, not the party
  whose statement a value is.

### CISA 2026 Minimum Elements

- **What:** "2026 Minimum Elements for a Software Bill of Materials
  (SBOM)", by CISA and co-authoring agencies (version 2.1, 2026-07-29).
  Guidance on the data fields and practices of an SBOM; it updates the
  NTIA document of 2021.
- **Domain:** SBOMs; its intended audience is organisations "that
  produce software, procure software, or operate software".
- **Relevance:** it names three parties by data field (Component
  Producer, SBOM Author, SBOM Tool Name) and holds the practice
  "Explicitly Identifying Unknown Information" (unknown against
  withheld).
- **Use:** pattern and mapping. The three parties match `originator`,
  `sbom-author` and `sbom-tool`; `not-measured` with a reason is its
  "unknown" for a content fact; `withheld` is reserved as a seventh
  basis value ([basis.md](basis.md)).
- **Not a vocabulary to adopt:** it is guidance, publishes no term
  identifiers (the mapping rows use placeholder IRIs), and its "third
  party" is another sense than `other-party`.

### BSI TR-03183-2

- **What:** the German Federal Office for Information Security's
  Technical Guideline "Cyber Resilience Requirements for Manufacturers
  and Products, Part 2: Software Bill of Materials (SBOM)" (version
  2.1.0, 2025-08-20). It "describes the requirements" for an SBOM.
- **Domain:** SBOM content and format, in the setting of the EU Cyber
  Resilience Act.
- **Relevance:** it splits licence information in three: original
  ("assigned by the creator of the component"), distribution ("under
  which a component ... can be used by a licensee") and effective
  ("under which the component is used by the licensee that is the
  creator of the current SBOM"). Its reason is this redesign's own: the
  terms "concluded licences" and "declared licences" are "not defined
  and used consistently throughout different SBOM standards and
  implementations".
- **Use:** deferred, and mapping. A `stage` key with those three values
  has a reserved place ([conflict.md](conflict.md), "Reserved: stage").
  Its mapping of "original licence" to `hasDeclaredLicense` is one of
  three texts the licence-file ruling agrees with
  ([asserter-licence.md](asserter-licence.md)).
- **Not built now, because:** deferred by ruling (2026-11-14). Its own
  mapping sends distribution licences to `hasConcludedLicense` and
  original ones to `hasDeclaredLicense`, which is another reading of
  "concluded" than the licence table here; adding the stage means
  reading that table again.

### OpenVEX

- **What:** "an implementation of Vulnerability Exploitability eXchange
  (VEX) designed to be lightweight, and embeddable" (specification
  0.2.0; a draft, steered by its community).
- **Domain:** statements on whether a vulnerability affects a product.
- **Relevance:** a neighbour of the SBOM with the same problem of
  machine-readable reasons. A `not_affected` status carries one of five
  justification labels, "fixed labels defined by VEX", "predefined and
  machine-readable", with free text beside them (`impact_statement`).
- **Use:** pattern for one list. The conflict rules follow that shape: a
  small closed set of codes, free text in `Note`
  ([conflict.md](conflict.md)).
- **Not used further, because:** its labels are about vulnerabilities.
  No mapping row.

### OWASP AIBOM Foundations Guide

- **What:** "OWASP AIBOM Foundations Guide v1.0" of the OWASP AIBOM
  project (41 pages, CC BY-SA 4.0; the text read in full 2026-11-21,
  the figures not). An introduction, not a schema: it says an AIBOM is
  written in CycloneDX 2.0, which was not read here.
- **Domain:** bills of materials for AI systems, and their adoption.
- **Relevance:** it asks of a whole document what this taxonomy asks of
  one value. An AIBOM has a header (scope, a completeness claim, who
  authored, reviewed and approved it, how it was generated), components,
  data flows, and evidence and provenance references on single claims.
- **Agrees with the draft:** every claim has a party that asserts it
  (p. 8); a producer does not assert what it cannot show, such as the
  inside of a provider's service (p. 24); another party's chain is kept
  apart from one's own (p. 35); a known gap is written down (p. 30); no
  score, rating or assurance level (p. 26), and more fields are not more
  assurance (p. 27).
- **Differs in two words.** Its *evidence* is a thing a claim points to
  and a reader can check: a hash, a signature, a model card, a licence
  file (p. 19). Our `Evidence`, now `Basis`, is a kind: how the asserter
  came to the value. Its
  *provenance* is how an artefact came to exist (base model, training
  run); ours is where a recorded value came from.
- **Points it raises** (all ruled, 2026-11-22 and 2026-11-23):
  1. The facet key is `Basis`, not `Evidence`, and the README says that
     provenance here is of a claim (ruled 2026-11-22; [basis.md](basis.md)).
  2. For each basis value, what a reader can check again (p. 19). A
     table in [basis.md](basis.md), ruled 2026-11-23.
  3. A source that can change with no release (an alias, an API, a
     branch): what pins it (p. 7, 24, 29, 37). Four rules in
     [source.md](source.md), ruled 2026-11-23.
  4. Review apart from authorship (p. 8, 36). Ruled 2026-11-23: a
     confirmed `ai-agent` claim is `sbom-author`'s, the agent in `Tool`.
  5. Silence means nothing without a completeness claim (p. 8, 17, 22).
     Three rules in [value-strength.md](value-strength.md), ruled.
- **Not in scope:** flows, trust zones, behaviours, agents at run time,
  the adoption roadmap.

## Other tools' vocabularies

### LicenseID resolution categories

- **What:** the categories LicenseID returns when it resolves a written
  licence string to an SPDX licence id (`exact`, `lexical`,
  `alias_name`, `plus_to_or_later`, `assumed_only` and others;
  seventeen in release 0.9.0, read 2026-11-19). Each has a `trust` word:
  `identity`, `list_data`, `author_words`, `resolver_rule` or `none`. A
  detection also has `method` (`tag`, `field`, `id`, `name`, `text`),
  `exact`, `score` and `variant_stated`.
- **Domain:** licence identifiers.
- **Relevance:** they are the finest record of how a licence value was
  changed. `trust` says who decided a reading: a list, the author's
  words or a rule of the tool. `variant_stated` says whether the input
  chose between `-only` and `-or-later`.
- **Use:** quoted. Pitloom records them unchanged in `Resolution-<n>`
  and `Expansion-<n>` and maps each to one of five step kinds for
  `Change` ([change.md](change.md)).
- **Not renamed, because:** the names are LicenseID's interface. They
  stay snake_case inside the quoted keys.
- **Used:** `variant_stated`, quoted beside a guessed variant (ruled
  2026-11-19; [change.md](change.md)); `exact` and `score`, quoted
  beside a licence text match (ruled 2026-11-20;
  [asserter-licence.md](asserter-licence.md)).
- **Not the gate:** `exact` and `score`. A text match is declared when
  it is decisive, which no one field says (ruled 2026-11-19;
  [asserter-licence.md](asserter-licence.md)).
- **Not used yet:** `trust`.

