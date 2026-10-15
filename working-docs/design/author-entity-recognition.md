---
Created: 2026-10-10
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Author strings: splitting and typing (NLP / NER follow-up)

See also: [roadmap.md](roadmap.md),
[extras-parity.md](../implementation/extras-parity.md) (the author reading
built today),
[provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md)
(fact vs fuzzy inference),
[sbom-generator-field-notes/spdx-modelling.md](../implementation/sbom-generator-field-notes/spdx-modelling.md)
(paper note, section 5).

**Status:** a warning, not a heuristic, is built; the NLP / named-entity-recognition
(NER) approach below is a candidate follow-up, not planned for a release.

## Problem

Two separate questions hide in one free-text author string such as
`Holger Krekel, Bruno Oliveira and others` or `Google, LLC, Alice Smith`:

1. **Splitting (span detection):** where does one entity end? A comma may
   separate two authors (`Ann Lee, Bob Ray`), order one name (`Doe, Jane`),
   or sit inside a legal name (`Acme, Inc.`). Core-metadata `Author:`,
   `setup.cfg` `author` and `setup.py` `author=` are free text, so a reader
   has to guess; PEP 621 forbids a comma in a pyproject author name, so a
   `[project].authors` entry never needs splitting.
2. **Typing (classification):** is a span a `Person` or an `Organization`
   (or neither known)? Pitloom takes every project author as a `Person`
   today. `Pallets`, `Explosion AI GmbH` and `the Mailman Cabal` are not.

Both are small named-entity-recognition tasks over short, unpunctuated,
verb-less strings, which general NER models are weak at.

## What is built (no heuristic; decided 2026-10-10)

A free-text author field splits on `,` and `and` with one `WARNING:` per
document; a structured entry never splits; every project author is a
`Person`. The rule and its surfaces are in
[extras-parity.md](../implementation/extras-parity.md#what-was-decided-and-built),
the limits (`Doe, Jane` becomes two authors on a bare wheel) in its
"Measured limits".

An earlier plan was a simple heuristic (split only between multi-word names,
keep `Inc.`/`LLC` suffixes, drop `and others`). Rejected: it would be right
often enough to hide the cases where it is wrong. It returns only as the
rule-based first stage of the pipeline below, with evaluation data.

## Candidate: two-stage pipeline (from the user's notes, 2026-10-10)

Decouple the tasks, as the notes argue, instead of using one end-to-end NER
model:

1. **Span detection by rules:** an RFC 822 address-list parser (quoted
   commas), a protected-suffix list, `and`/`&`/`;`/`/` delimiters outside
   quotes and parentheses, placeholder filtering (`others`, `contributors`,
   `[More Information Needed]`), parenthetical affiliations
   (`Robin Rombach (Stability AI)`), BibTeX `and`-separated blocks where a
   comma means `Surname, Given`.
2. **Typing per span:** legal-suffix match (a small pure-Python legal-form
   list such as `cleanco`, which also maps suffix to jurisdiction), keyword
   match (`foundation`, `project`, `team`, `labs`), role e-mail local part
   (`security@`, `team@`), then a CRF personal-name tagger such as
   `probablepeople` (python-crfsuite, about 1 MB) for the rest. Heavier NER
   (spaCy, GLiNER) is poor on isolated names without a carrier sentence.
3. **Fall back to `Core/Agent`:** SPDX 3.0.1 `Agent` is concrete and the range
   of `suppliedBy`/`originatedBy`, so when neither type is deterministic
   (`TheBloke`, `Qwen`, a lone handle) emit the base `Agent`, not a guessed
   `Person`.
4. **Online only:** query the hub (Hugging Face user vs organization
   overview) to resolve a single-token namespace; never offline.

Figures for footprint, accuracy and the example table come from the notes and
are **unverified**: measure on real PyPI `Author`/`Author-email` and model
card data before choosing a library or any claim in the paper.

## Why it matters (regulatory framing, from the notes)

Person vs Organization changes downstream use: EU AI Act and Cyber Resilience
Act duties attach differently to natural and legal persons (open-source
steward regime for legal persons), personal data in an SBOM (a `Person` with an
e-mail) is processed under GDPR where a corporate contact is not, and
sanction/registry screening needs organisations typed as organisations. A
commit author at a lab is not the supplier; `originatedBy` vs `suppliedBy`
must not be collapsed (the one deliberate exception: a Hugging Face model's
repository owner is both, because the repository is the distribution source;
see [g7-model-producer-parameter-count.md](../implementation/g7-model-producer-parameter-count.md)).
These are the reasons to prefer `Agent` over a wrong
guess. Legal readings need review before they reach user docs.

## Constraints for any NLP step

- **Deterministic:** same input, same output, on every platform and library
  version (pin the model; a CRF is deterministic, a downloaded model that
  changes is not). The SBOM must stay bit-for-bit reproducible.
- **Offline by default;** network lookups opt-in and recorded in provenance.
- **Provenance:** a typed agent says how it was typed (`Method`: heuristic or
  model, not a stated fact); a stated type from the project always wins.
- **Footprint and licence:** optional extra, not a core dependency; check the
  model and training-data licence of each library.
- **Core vs Skill:** the deterministic rules belong in core; fuzzy typing may
  belong in a Skill, as for the AI-model Person/Org split in
  [roadmap.md](roadmap.md) (G7).

## Open questions

1. Is a fuzzy classifier core or an optional extra / Skill?
2. Which rows of the provenance taxonomy record "typed by heuristic"?
3. Does the `Agent` fallback belong now for every unknown author, or only for
   hub namespaces?
4. Evaluation set: how many real `Author` strings, labelled by whom?
