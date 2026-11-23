---
Created: 2026-11-16
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Examples: the Asserter and Basis matrix on real inputs

See also: [../README.md](../README.md) (the claim model),
[../asserter.md](../asserter.md), [../basis.md](../basis.md),
[../method.md](../method.md). Pages of this folder:
[originator.md](originator.md), [sbom-tool.md](sbom-tool.md),
[other-party.md](other-party.md),
[ai-agent-and-sbom-author.md](ai-agent-and-sbom-author.md).

**Status:** draft, written for the review of the two axes. Each cell of the
matrix gets several inputs, real where one was found. The examples are also
the start of the "example" that README rule 5 asks of every term.

## Where the inputs come from

- **SBOM-MinBench**, working tree of release 0.2 (collected 2026-11-12 with
  Pitloom 0.24.0 and LicenseID 0.8.4): registry metadata and manifests of
  563 PyPI releases and 711 Hub model revisions, and its probes (model file
  headers, licence text matching, Hub licence files, PyPI attestations). An
  input is cited by its package URL. Release 0.2 is not published: only
  facts about public packages are quoted here.
- **Its cache of registry API responses** (PyPI JSON, Hub model API;
  not published, since raw responses hold personal data). Only
  repository ids and fields about the artefact are quoted: `yanked`,
  `gated`, `tags`, `pipeline_tag`, `library_name`, `safetensors`,
  `model-index`.
- **Its public review file** (`data/reviews/arthit.jsonl`, release 0.1):
  a person's decisions, used as the nearest real input to an SBOM
  author.
- **The SBOM-MinBench repository's own files** (`pyproject.toml`,
  `CITATION.cff`, its licence files, `uv.lock`), as a project input.
- **Hugging Face Hub documentation**, "Model Cards", read 2026-11-16: what
  the Hub works out itself when a card does not state it.
- **constructed** marks an example with no real input behind it.

The benchmark's expected values are not taken as true here: they come
from LicenseID detection, which is not always right. A matched id and
its score are shown as what LicenseID 0.8.4 returned, no more. Where a
page says what a licence file holds, the file itself was read
(2026-11-16), and the page says at which revision.

## How to read a row

- **Input** is what the source holds, as written.
- **Today** says whether Pitloom reads that field today (`yes`, `no`), from
  the code at `main` 257b7260.
- The forms are in a code block under each table, one line per example id.
  They illustrate the vocabulary; the string layout is a code-stage decision.
  `Basis` is written on every form (ruled 2026-11-23); the heading
  gives the cell an example sits in as well.
- **Q** marks a point the example leaves open; they are collected below.

## The matrix

Number of examples per cell. "never" and "-" are from the allowed-pairs table
of [../basis.md](../basis.md), rule 4; the nearest real input to a
closed cell is given where one helps.

| Asserter | `declared` | `measured` | `detected` | `inferred` | `lower-bound` | `not-measured` |
| --- | --- | --- | --- | --- | --- | --- |
| `originator` | [11, and 2 pairs that differ](originator.md#originator-declared) | - ([nearest](originator.md#closed-cells)) | - ([4 near](originator.md#originator-detected-and-inferred)) | - ([0 found](originator.md#originator-detected-and-inferred)) | - | - |
| `sbom-tool` | never ([nearest](sbom-tool.md#closed-cell)) | [5](sbom-tool.md#sbom-tool-measured), and [1 without a stored input](other-party.md#other-party-detected) (PT-7) | [1 real, 1 constructed](sbom-tool.md#sbom-tool-detected) | [2 real, 1 constructed](sbom-tool.md#sbom-tool-inferred) | [0 real, 1 near](sbom-tool.md#sbom-tool-lower-bound) | [2](sbom-tool.md#sbom-tool-not-measured) |
| `other-party` | [5 real](other-party.md#other-party-declared) | - ([nearest](other-party.md#closed-cell)) | [8 real](other-party.md#other-party-detected) | [3 real](other-party.md#other-party-inferred) | - | - |
| `ai-agent` | - ([nearest](ai-agent-and-sbom-author.md#closed-cell)) | - | - | [1 on a real input, 1 constructed](ai-agent-and-sbom-author.md#ai-agent-inferred) | - | - |
| `sbom-author` | [2 real (a reviewer), 1 on a real input, 1 constructed](ai-agent-and-sbom-author.md#sbom-author-declared) | - | - | [1 real (a reviewer), 2 constructed](ai-agent-and-sbom-author.md#sbom-author-inferred) | - | - |

The licence file matched to an id sits apart
([originator.md](originator.md#a-licence-file-matched-to-an-id)): its form
was parked when the examples were written, and five real inputs show
why. The gate and the form are ruled since
([../asserter-licence.md](../asserter-licence.md)).

## What the examples show

Points for the review, each with the example that raised it. Points 1
to 5, 10 and 12 to 14 have an answer (the last on 2026-11-23). Points 6
to 9 and 11 ask for no ruling: 6 and 11 are rows for the field table when
the code reads those fields, 7 is in the definition of `originator`
already, 8 and 9 are for the code stage.

1. **One doubtful input for `originator` with `detected`, none for
   `inferred`.** Pitloom seldom sees how an originator came to a value.
   The one candidate is a card the training tool wrote, known by a tag.
   The two cells were "when known" in the allowed-pairs table. (OX-1
   to OX-4) Answered 2026-11-23: both cells are closed, and the
   candidate is `declared` ([../basis.md](../basis.md), rule 4).
2. **A wrong licence match makes the parked exception say something
   untrue, and the score does not warn.** Three of the five matched
   files were read and do not hold the matched licence: a vendor's own
   licence matched to `OpenMDW-1.0` at 0.641, a plain Apache 2.0 text
   matched to `Pixar` at 0.9947, and a file whose full text is
   BSD-3-Clause matched to `Apache-2.0` at 0.9187. With
   `Asserter: originator` each would be written as the originator's
   declared licence; the second would also invent a conflict with the
   card. The originator declared a text, and the id is the tool's best
   match. (OL-2, OL-3, OL-5) Answered 2026-11-19 to 2026-11-21: a match
   is declared only when it passes the gate, `exact` and `score` are
   quoted beside it, and the two wrong classes that still pass go to
   LicenseID ([../asserter-licence.md](../asserter-licence.md)).
3. **The outcome word `declared-only` no longer fits** when the one value
   is another party's `detected` figure. (PT-2) Answered 2026-11-23:
   the word is dropped, the outcome is `used`
   ([../basis.md](../basis.md#outcome-of-a-source)).
4. **A header-only read gives an exact count.** The definition of
   `measured` said "read in full"; what is read in full is the part that
   carries the fact (the tensor table), not the file. (SM-3, SM-5)
   Answered 2026-11-23: the definition now says so
   ([../basis.md](../basis.md#values)).
5. **A gated repository has no reason code of its own.** The fetch is
   refused with HTTP 401; the closed set offers
   `download-network-failed`. (SN-2) Answered 2026-11-23: it keeps
   that code, as the message catalogue has it
   ([../basis.md](../basis.md#reason-codes)).
6. **One Hub field, two asserters.** `pipeline_tag` and `library_name` are
   the originator's when the card states them, and the Hub's inference when
   it does not: in some four of ten cached repositories. Pitloom reads the
   card's value only, today. An evaluation result is the originator's when
   self-reported and the Hub's when verified. (PI-1, PI-2, OD-11, PT-9)
7. **The asserter is relative to the element.** A quantiser's card naming
   the base model's licence is `originator` for the quantised repository
   and would be `other-party` for the base model. (PD-4)
8. **A reader with a cap gives nothing today, not a lower bound.** The one
   near input is an error with no fields. `lower-bound` has no writer and
   no real input. (SL-1)
9. **A PyPI attestation is an `other-party`, `detected` source** that
   Pitloom does not read today. (PT-4)
10. **No source kind fits a document a card links to**: a licence page, or
    a licence file in another repository. (ST-1, AI-1) Answered
    2026-11-23: the kind `linked-document`
    ([../source.md](../source.md), rule 9).
11. **The Hub's relation to a base model is read today with no sign that
    the Hub inferred it**, which it did in 266 of 285 cached cases. (PI-3)
12. **Four field-table rows have an example to decide them on**: the
    Hub's repository owner (PD-1), the gate (PD-3), `yanked` and its
    reason (PD-5), and what `pipdeptree` finds (PT-7). All decided
    2026-11-23: the first three stay `other-party`, `declared`; PT-7
    is `sbom-tool`, `measured` ([../alignment.md](../alignment.md),
    "Acting on behalf of").
13. **A parameter count is not "one right answer".** The Hub's total and
    Pitloom's own sum over the same file differ in 15 of 128
    repositories. The test of `measured` holds for the sum of the
    tensors read, not for the field's name. (SM-3, PT-8) Answered
    2026-11-23: the count stays a content fact, `measured` for what
    the technique names
    ([../basis.md](../basis.md#precedence-for-content-facts)).
14. **A card that relays another party's measurement** (a leaderboard
    score with a named source) has no rule: the mirror of the registry
    that relays the originator. (OX-3) Answered 2026-11-23: it
    stays `originator`, `declared`; rule 2 covers a relay a system
    makes ([../asserter.md](../asserter.md)).
