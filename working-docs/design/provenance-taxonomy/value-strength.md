---
Created: 2026-11-14
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Value strength: statement, placeholder or explicit none

See also: [README.md](README.md) (the claim model),
[conflict.md](conflict.md) (the rule `strength`),
[resweep-rulings.md](resweep-rulings.md) (C1 and C7, ruled 2026-11-28).
Generalises section 2 of
[license-rules.md](../license-rules.md) to every field (its question 14).

**Status:** draft.

## Definition

The **strength** of a value read from a source says what kind of statement
it is, before any source is compared with another. It is a classification
inside Pitloom that drives cascades. It is not a facet written on a claim;
what it decides shows in which claim stands and in the conflict record.

## Classes

| Class | Definition | In a cascade | Recorded |
| --- | --- | --- | --- |
| `absent` | The source has no value: the key is missing, or it is empty or blank where the format gives that no meaning (rule 1). | try the next source | nothing, silently |
| `placeholder` | The source has text that says "no information" and is not a value. | weak: gives way to any later `real` or `none`; kept only when nothing better follows | as the format's "no assertion" term, with the raw text in `Written` when a step other than `form` changed it ([change.md](change.md)) |
| `none` | The source states that there is none. | final: ends the cascade | as the format's "none" term |
| `real` | Anything else. | final: ends the cascade | the value |

A `placeholder` is text a source wrote. A stand-in that Pitloom makes
itself, where the format requires a value and no source gave one (the
package name `unknown`, a creation time of 1970), is a different thing:
it is no claim and has no strength. Such stand-ins are one small closed
list, each marked as a stand-in, as the draft's `placeholder-root` is (ruled
2026-11-28, [resweep-rulings.md](resweep-rulings.md), C7;
[basis.md](basis.md), rule 5; [method.md](method.md)). The members of
the list are open. Not built.

## Rules

1. **`absent` and empty-but-present differ.** A present key with an empty
   list is `real` with an empty value when the format gives the empty list a
   meaning (no dependencies), and `absent` otherwise. Each reader says which,
   per field.
2. **A placeholder is not a claim.** It never conflicts with a real value
   and never wins over one. The held placeholder is per item (per
   dependency, per file), never shared.
3. **`none` is a claim.** It conflicts with a `real` value.
4. **One classifier per field type.** The placeholder words are a table, not
   scattered comparisons.
5. **A source that can yield nothing needs its own "is this really a file of
   this format" check** before its `absent` lets a cascade move on.

## Placeholder words

| Field type | `placeholder` | `none` |
| --- | --- | --- |
| licence | `NOASSERTION`, `UNKNOWN` (any case) | `NONE` (any case) |
| author, maintainer, e-mail, URL | `UNKNOWN` | - |
| version | none read today (Pitloom's own `"unknown"` fallback for an unresolved dependency version is not a source's word; it becomes an absent version) | - |
| name of a model | an exporter's default graph name | - |
| any text field | none read today. `N/A`, `n/a`, `TBD`, `-` are a proposal for the code stage (ruled 2026-11-23: not adopted here; the class is the taxonomy's, the word list is data, to be added with real inputs and a before and after sweep) | - |

The Hub card's vague licence words (`other`, `custom`, `proprietary`,
`unlicensed`) are `absent`, as today: they give no value, not a weak one,
and send the reader to the repository's licence files
([license-rules.md](../license-rules.md)). That is a cascade step, written
in the order table, not a fifth class.

## Why not a facet

A consumer does not need the class: a recorded placeholder is already the
format's `noAssertion` term, and a recorded `none` its "none" term. Writing
the class as well would say the same thing twice.

## What silence means (ruled 2026-11-23)

Raised by the OWASP AIBOM Foundations Guide v1.0 (p. 8, 17, 22;
[vocabularies-considered-sbom.md](vocabularies-considered-sbom.md), point 5): a
thing a document does not list proves nothing, unless the document
claims to be complete for its scope; then the absence is the producer's
assertion that there is none. A Pitloom SBOM is silent at three levels:

| Level | Silent today | A reader cannot tell | A format's word for it |
| --- | --- | --- | --- |
| a source, for one field | the outcome `unavailable` ([basis.md](basis.md)): Pitloom read the source and it had no value (`absent`) | "read, nothing there" from "never tried". A source tried and not read (`failed`, `refused`) is recorded by the ruling of 2026-11-28 (S1); not built | none in SPDX 3 |
| a field of an element | no claim, when every source was `absent` (or was not read: its outcome is then on the element) | "no source states it" from "there is none" | SPDX 3: a `NoAssertion` or `None` individual. CISA 2026: "unknown" |
| a set of relationships (dependencies, files, datasets) | no `completeness` on any relationship (the one function that could give it returns none) | "this is all of them" from "these were found" | SPDX 3 `completeness`: `complete`, `incomplete`, `noAssertion`. CycloneDX 1.7 `compositions[].aggregate`: `complete`, `incomplete` and six narrower ones, `unknown`, `not_specified` |

Three rules, ruled 2026-11-23; S1 restated 2026-11-28:

- **S1. Silence is no claim.** A field with no claim says neither
  "none" nor "not known". "None" is said by a `none` value only; "not
  known" by a `placeholder` a source wrote, or by `not-measured` for a
  content fact. So a silent field means: every source Pitloom read
  lacked it (`absent`, or a placeholder that a later source beat); it
  never hides a source's "none". A source Pitloom tried and failed or
  refused to read is not hidden either: its outcome is recorded on the
  element, once per source, for a field of any kind
  (ruled 2026-11-28, [resweep-rulings.md](resweep-rulings.md), C1;
  [basis.md](basis.md#outcome-of-a-source)). The field itself stays
  silent. Not built. With this, silence still does not meet the CISA
  2026 practice of saying "unknown" (Mappings, below); an "unknown" of
  Pitloom's own for a silent field is not proposed.
- **S2. A source that had nothing stays unrecorded** (ruled
  2026-11-23). No entry per field for a source Pitloom read and found
  empty. Reasons: absent source data is not an error (the project's
  rule); most fields of most sources are empty, so the record would be
  most of the SBOM. Not taken: a list, per element, of the sources
  read, so that a silence reads as "not stated in these". So the first
  level of the table keeps no word: a reader cannot tell "read,
  nothing there" from "never tried" (a known loss; no format has a
  word for it). A source tried and not read is no longer in that loss
  (S1). S2 is about `absent` only. A source's "none" is a
  claim and is recorded (rule 3); a `placeholder` is recorded when
  nothing better follows, and one that a later source beat ends as
  silent as an `absent` value (rule 2). Confirmed with that
  2026-11-23.
- **S3. Completeness is a claim about a set, with the same facets**
  (ruled 2026-11-23, as the rule for when Pitloom may say so; the
  writing waits for the code stage, below). Not taken: no
  completeness at all.
  It is written as SPDX `completeness` on the relationship. Pitloom
  writes `complete` only on basis `measured`: it listed the whole of a
  thing it held (the members of an archive, the files of a tree). It
  writes `incomplete` when a cap stopped the walk (`lower-bound`). For
  a list a party declared (the dependencies of a manifest or a lock
  file) it writes nothing: the list is whole for what the party
  declared, and Pitloom cannot say that nothing else is used. Not
  written by rule: `noAssertion`, which says what the missing property
  says.

Not proposed: a completeness claim for the whole document. SPDX 3.0.1
has the property on a relationship only, and the scope of a Pitloom
SBOM (one project, one wheel, one model) is its root element.

For S3, read in the code 2026-11-23: Pitloom writes one `contains`
relationship per file and per directory, from the parent to that one
child (`_document_files.py`). The SPDX property is on one relationship
(the bindings' summary: "the completeness of relationships"), so
`complete` on a relationship with one `to` end says little. The SPDX
3.0.1 pages of `completeness` and `RelationshipCompleteness` (read
through a summary, 2026-11-23) do not say what "exhaustive" covers:
the `to` ends of one relationship, or every relationship of that type
from the element.

Ruled 2026-11-23: Pitloom reads `completeness` as covering the `to`
ends of the one relationship that carries it, which is what the
wording ("the relationship") says. So to say `complete` for a set,
Pitloom writes one relationship from the parent with every child in
`to`; a relationship with one child says nothing of the set. Not
taken: `complete` on each of several relationships, read as covering
all of that type from the element. For the code stage: the shape of
`contains` (one per child today), and an entry in
[sbom-format-gaps.md](../sbom-format-gaps.md), since the text does not
define the scope of "exhaustive".

Not read: CycloneDX 2.0, which the guide names for its "composition
declarations" (the 1.7 schema was read). Whether the files listed for
a wheel are every member of it was not checked.

## Mappings (loose)

| Class | SPDX 3 | CISA 2026 |
| --- | --- | --- |
| `absent` | the property or relationship is absent | - |
| `placeholder` | `NoAssertionLicense`, `NoAssertionElement`, `noAssertion` | "unknown" |
| `none` | `NoneLicense`, `NoneElement` | - |
| `real` | the value | - |

SPDX 3: a missing licence relationship is not `NoAssertionLicense`. Pitloom
records `placeholder` only when a source literally wrote one.

CISA 2026 (version 2.1, primary text read 2026-11-16): "unknown" is the SBOM
author's own statement that it lacks the information, asked for whenever a
required field is not provided. A `placeholder` is a source's statement, so
the match is loose; an `absent` value writes no mark and so does not meet
that practice by itself.
