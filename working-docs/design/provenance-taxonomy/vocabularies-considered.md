---
Created: 2026-11-19
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Vocabularies considered

See also: [README.md](README.md) (the claim model),
[vocabularies-considered-sbom.md](vocabularies-considered-sbom.md) (the
entries for SBOM formats, guidance and other tools: split off
2026-11-23), [alignment.md](alignment.md) (the model read in PROV-O, SOSA, SSN and SIO;
ODRL for licence claims), the "Mappings" section of each facet page, and
[mappings/](mappings/pitloom-provenance.sssom.tsv) (the rows, as SSSOM).

**Status:** draft, 2026-11-19. A record of every ontology, taxonomy and
guidance text weighed during the design, so that a later reader need not
ask "why not X". One entry each: what it is, the domain it was made for,
why it bears on this work, and how it is used here or not, with the
reason. Detail stays on the page that uses the term; this page points.

Each description is from the vocabulary's own published text, read
2026-11-16 (PROV-O, SOSA, SSN, SIO, ODRL, CISA) or 2026-11-19 (the rest).
Quoted words are the source's.

## How each one is used

No external vocabulary is written into an SBOM as provenance: the
provenance strings and the Annotation records keep Pitloom's own keys and
values. An external vocabulary has one or more of these uses.

| Use | Meaning |
| --- | --- |
| output | Pitloom writes its terms: it is the format of the SBOM |
| pattern | it shaped the model: a facet, a test or a list follows it |
| mapping | its terms are targets of loose mapping rows; nothing else |
| format | it is the format or the predicates of the mapping file |
| quoted | another tool's vocabulary, recorded unchanged |
| deferred | a place is kept for it; not built |

## Summary

| Vocabulary | Made for | Use here |
| --- | --- | --- |
| PROV-O | provenance of any thing, any domain | pattern, mapping |
| SOSA, SSN | sensors and their observations | pattern, mapping |
| PAV | authorship and versioning of web resources | pattern (one line), mapping |
| SIO | biomedical knowledge, over a general upper layer | pattern (the grade), mapping |
| ECO | evidence in biological research | mapping |
| SSSOM, SEMAPV | sharing mappings between vocabularies | format, mapping |
| SKOS | knowledge organisation systems | format |
| Wikidata statements | a general knowledge base | pattern (status, rule), mapping |
| DQV | quality of datasets | mapping (two rows) |
| ODRL | rights and usage policies | pattern (licence claims only), mapping |
| SPDX 3 | SBOMs | output, mapping |
| CycloneDX evidence | bills of materials | mapping |
| CISA 2026 Minimum Elements | SBOM guidance | pattern, mapping |
| BSI TR-03183-2 | SBOM requirements | deferred, mapping |
| OpenVEX | vulnerability status statements | pattern (one list) |
| OWASP AIBOM Foundations Guide | AIBOM guidance | the facet name `Basis`; five points, all ruled |
| LicenseID categories | licence id resolution | quoted |

## Provenance and observation

### PROV-O

- **What:** the W3C provenance ontology (Recommendation, 2013-04-30). It
  "provides a set of classes, properties, and restrictions that can be
  used to represent and interchange provenance information generated in
  different systems and under different contexts". Three kinds of thing:
  entity, activity, agent.
- **Domain:** any. Its data model calls itself "domain-agnostic".
- **Relevance:** the nearest general answer to "who is responsible for a
  value, what made it, what it came from".
- **Use:** pattern and mapping. The model reads as two PROV entities (the
  statement in the source, the value Pitloom recorded) and two acts (the
  asserter's, Pitloom's); Asserter is `prov:wasAttributedTo`, Source is
  what Pitloom's act `prov:used`, Change is `prov:wasRevisionOf`
  ([alignment.md](alignment.md)).
- **Not adopted as the vocabulary, because:** it has no word for the
  basis of a value, nor for a value that was not obtained (`lower-bound`,
  `not-measured`); it names no kinds of revision; and writing it out
  needs a graph of entities and acts per value, where an SBOM has one
  string or one record.

### SOSA and SSN

- **What:** the W3C and OGC ontology (Recommendation, 2017-10-19) "for
  describing sensors and their observations, the involved procedures,
  the studied features of interest, the samples used to do so, and the
  observed properties, as well as actuators". SOSA is its "lightweight
  but self-contained core"; SSN adds systems, stimuli and capabilities.
- **Domain:** sensing: satellite imagery, scientific monitoring, the Web
  of Things. A sensor may be a device, an agent or software.
- **Relevance:** the user asked for alignment with it (2026-11-16). A
  tool that reads a file is, in its terms, a sensor that carries out a
  procedure on a feature of interest.
- **Use:** pattern and mapping. Method class and technique read as
  `sosa:Procedure`, `Tool` as `sosa:Sensor`, Pitloom as `sosa:Platform`
  ([method.md](method.md)); `measured` and `detected` are loosely
  `sosa:Observation`; `lower-bound` is a value beyond a measurement range
  ([basis.md](basis.md)). Its own alignment to PROV-O, which is not
  normative, is the bridge between the two readings.
- **Not adopted as the vocabulary, because:** it has no class for a value
  that is stated and not observed, which is most of what an SBOM holds;
  and it has one class for every observation, so the lines between
  `measured`, `detected` and `inferred` are not in it. The proxy test in
  [basis.md](basis.md) is Pitloom's own: `ssn:isProxyFor` holds for
  every stimulus and marks no value as inferred.

### PAV

- **What:** "a lightweight ontology for tracking Provenance, Authoring
  and Versioning" (version 2.3.1, 2014; a community ontology). It
  "specializes the W3C provenance ontology PROV-O in order to describe
  authorship, curation and digital creation of online resources": its
  agent properties are sub-properties of `prov:wasAttributedTo`, its
  source properties of `prov:wasDerivedFrom`.
- **Domain:** resources on the Web; its own examples are biomedical
  databases. It tells apart "contributors, authors, curators and digital
  artifact creators".
- **Relevance:** it splits what PROV-O leaves as one relation, along
  lines close to two facets here: who (authored, created, curated,
  provided) and how the content came over (retrieved, imported,
  derived).
- **Use:** pattern for one line, and mapping. PAV's three source
  properties are the line between three method classes: copied as it is
  (`pav:retrievedFrom`, `read`), "preserved, but transcribed"
  (`pav:importedFrom`, `parsed`), "further refined or modified"
  (`pav:derivedFrom`, `derived`) ([method.md](method.md)). Asserter
  values map to `pav:authoredBy`, `pav:createdBy`, `pav:providedBy`,
  `pav:curatedBy` ([asserter.md](asserter.md)).
- **Not adopted as the vocabulary, because:** its terms are properties
  of a whole resource, not of one value of one field; an author and a
  creator are roles in making a document, where an asserter is a party
  placed against the element and the SBOM; and it has no word for
  the basis of a value.

## Evidence and argument

### SIO

- **What:** the Semanticscience Integrated Ontology, a community
  ontology (version 1.62 read). Its own description: "a simple,
  integrated ontology (types, relations) for objects, processes and their
  attributes".
- **Domain:** biomedical knowledge; it gives "foundational support for
  the Bio2RDF ... and SADI ... projects". Its upper layer (proposition,
  evidence, measurement value) is general.
- **Relevance:** the one vocabulary read that grades disagreement: `is
  supported by`, `is disputed by`, `is refuted by`.
- **Use:** pattern for one thing, mapping for the rest. The grade of a
  conflict (`compatible`, `incompatible`) follows `is disputed by` and
  `is refuted by` ([conflict.md](conflict.md)). Loose rows for
  `statement`, `measurement value`, `conclusion`, `justification`,
  `plan`, `has source`, `quote`, `is alternate of`.
- **Not adopted as the vocabulary, because:** it is an upper ontology
  for another field, most of its terms are of no use here, and its file
  holds no mapping to PROV-O, SOSA or SSN beyond two annotations. Its
  `hypothesis` is not `inferred`, and its `disagreement` is about
  consensus in a group, not about two statements.

### ECO

- **What:** the Evidence and Conclusion Ontology (release 2026-07-10
  read; an OBO Foundry ontology). It "describes types of scientific
  evidence within the biological research domain that arise from
  laboratory experiments, computational methods, literature curation, or
  other means".
- **Domain:** biocuration: the evidence behind an assertion such as
  "gene product X has function Y".
- **Relevance:** it has the two axes of this model. Its two root classes
  are "evidence" ("a type of information that is used to support an
  assertion") and "assertion method" ("a means by which a statement is
  made about an entity"), the second either manual or automatic.
- **Use:** mapping only: `author statement` for `declared` and
  `originator`, `automatic assertion` for `sbom-tool` and `ai-agent`,
  `manual assertion` for `sbom-author`, `imported information` for
  `other-party`, `similarity evidence` for a best match
  ([asserter.md](asserter.md), [basis.md](basis.md),
  [method.md](method.md)).
- **Not adopted as the vocabulary, because:** its evidence types are
  those of biology (an author statement is one "by the author of a
  paper, which is read by a curator"), and its working terms join the
  two axes into one ("computational evidence used in automatic
  assertion"; some 1,500 terms of that shape). The released `Role` held
  two axes in one word in the same way; this model keeps them apart.

## Mapping between vocabularies

### SSSOM and SEMAPV

- **What:** SSSOM, the Simple Standard for Sharing Ontological Mappings,
  is "a community-driven standard designed to facilitate the exchange
  and integration of semantic entity mappings": a table format with
  metadata slots. SEMAPV, the Semantic Mapping Vocabulary, is "about the
  processes, entities and agents involved in the curation of mappings",
  made with SSSOM; it calls itself beta.
- **Domain:** mappings between the terms of two vocabularies.
- **Relevance:** twofold. The mapping rows of this draft need a format.
  And a mapping is a claim with provenance, so SSSOM's slots answer the
  same questions as the facets: who (`author_id`, `creator_id`,
  `reviewer_id`, `mapping_provider`, `mapping_tool`), how
  (`mapping_justification`, `subject_preprocessing`), by which rule
  (`curation_rule`).
- **Use:** format and mapping. The mapping file is an SSSOM table,
  checked with `sssom validate`; every row's justification is
  `semapv:ManualMappingCuration`. Loose rows from Asserter to the agent
  slots, from Change step kinds to SEMAPV's normalisation and matching
  terms, and from a conflict rule to `curation_rule`
  ([asserter.md](asserter.md), [change.md](change.md),
  [conflict.md](conflict.md)).
- **Not adopted as the vocabulary, because:** both describe a mapping
  between two terms, not a value of a field; SEMAPV's processes are
  matching processes and have nothing for reading, counting or hashing.

### SKOS

- **What:** the Simple Knowledge Organization System (W3C
  Recommendation, 2009-08-18), "a common data model for sharing and
  linking knowledge organization systems via the Web".
- **Domain:** thesauri, taxonomies, classification schemes.
- **Relevance:** its mapping properties say how near two terms are.
- **Use:** format only. Every mapping row uses `skos:relatedMatch` (an
  associative link; most rows), `skos:broadMatch` (a hierarchical link)
  or `skos:closeMatch` ("sufficiently similar that they can be used
  interchangeably in some information retrieval applications"). No row
  uses `skos:exactMatch`.
- **Not used further:** the taxonomy is not published as a SKOS concept
  scheme. That is a later step, should the terms get IRIs that resolve.

## Statement models

### Wikidata statements

- **What:** the statement model of Wikidata, a general knowledge base,
  as its help pages describe it. A statement can carry references
  ("where a data value comes from") and one of three ranks; ranks
  "provide a mechanism for annotating multiple values for a statement".
- **Domain:** any subject.
- **Relevance:** the closest working model of "several claims for one
  field, one of which stands, with a reason". Reference properties name
  the source (P248 "stated in", P813 "retrieved", P958 "section, verse,
  paragraph, or clause") and the way a value was reached (P459
  "determination method or standard", P887 "based on heuristic", P3452
  "inferred from"); P7452 is "reason for preferred rank".
- **Use:** pattern and mapping. Candidate status follows the ranks:
  `selected` is the preferred rank, `coexisting` the normal rank, and a
  recorded rule is a reason for preferred rank
  ([conflict.md](conflict.md)). `passed-over` maps to the normal rank
  too, not to the deprecated one, which is "for statements that are
  known to include errors".
- **Not adopted as the vocabulary, because:** a rank states "the
  consensus opinion", reached by editors, and is "not a way of asserting
  your view for a disputed value". A status here is the outcome of a
  rule one tool applied, and is recorded as that. The model has no
  asserter and no word for the basis of a value either.

### DQV

- **What:** the W3C Data Quality Vocabulary (Working Group Note,
  2016-12-15; not a Recommendation), "a framework in which the quality
  of a dataset can be described".
- **Domain:** datasets published on the Web; an extension to DCAT.
- **Relevance:** small. It tells a measurement against a metric
  (`dqv:QualityMeasurement`) from a rating or feedback
  (`dqv:QualityAnnotation`).
- **Use:** two loose mapping rows, for `measured` and `declared`.
- **Not used further, because:** it is about how good a whole dataset
  is, not about where one value came from.

## Rights

### ODRL

- **What:** the W3C Open Digital Rights Language (version 2.2,
  Recommendation, 2018-02-15), "a policy expression language" for
  "representing statements about the usage of content and services":
  permissions, prohibitions and duties over an asset.
- **Domain:** rights and usage policies for content and services.
- **Relevance:** a licence is a usage policy, and ODRL tells a policy
  proposed by its issuer from one that is only claimed, and names
  strategies for a conflict.
- **Use:** pattern for licence claims only, and mapping. `odrl:Offer`
  against `odrl:Assertion` mirrors the originator's declared licence
  against every other claim ([asserter-licence.md](asserter-licence.md)); its conflict
  strategies are a pattern for the rule names of picking a concluded
  licence, for which no rule is set (ruled 2026-11-23;
  [conflict.md](conflict.md)).
- **Not used further, because:** it models what a licence permits, not
  who claimed which licence applies. Pitloom does not write licences as
  policies. `odrl:Assertion` is in its common vocabulary, which is not
  normative.

## SBOM formats, guidance and other tools

On their own page,
[vocabularies-considered-sbom.md](vocabularies-considered-sbom.md): SPDX
3, CycloneDX evidence, CISA 2026 Minimum Elements, BSI TR-03183-2,
OpenVEX, the OWASP AIBOM Foundations Guide, and the LicenseID resolution
categories.

## What none of them gave

The taxonomy stays Pitloom's own, with mappings, for five gaps.

1. One scale over a value that is stated, one that is observed, and one
   that was not obtained. PROV-O and PAV have no scale; SOSA covers the
   observed part only; ECO's is for biology.
2. A party named by its place against the element and the SBOM
   (`originator`, `sbom-author`, `other-party`). The others name a role
   in making a document, or a property of an artefact.
3. Classes for what a tool did to a file. CycloneDX's `technique` is the
   nearest, for identity fields only.
4. Status, rule and grade for the candidates of one field, as a rule a
   tool applied. Wikidata has status and reason by consensus; SIO has
   the grade; ODRL has strategies for policies.
5. A form that fits one string or one Annotation in an SBOM.

## Not read

Named so that nobody takes them as weighed. No page of this draft cites
Schema.org, the NIEM Model or FIBO, which the project's naming rule lists
beside OBO Foundry (reached here through ECO). Attestation formats, such
as the one behind the PyPI attestation of example PT-4
([examples/other-party.md](examples/other-party.md)), were not read
either. The 2023 Edition of SSN is a Working Draft and was read only for
what it moves ([basis.md](basis.md)).
