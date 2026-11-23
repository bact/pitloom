---
Created: 2026-11-14
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Provenance taxonomy: the claim model

See also: [asserter.md](asserter.md) (with
[asserter-licence.md](asserter-licence.md) for the licence field),
[source.md](source.md),
[method.md](method.md), [basis.md](basis.md),
[value-strength.md](value-strength.md), [change.md](change.md),
[conflict.md](conflict.md),
[alignment.md](alignment.md) (the model in PROV-O, SOSA, SSN and SIO;
ODRL for licence claims),
[vocabularies-considered.md](vocabularies-considered.md) and
[vocabularies-considered-sbom.md](vocabularies-considered-sbom.md) (every
external vocabulary weighed, and how each is used or not),
[renames-and-migration.md](renames-and-migration.md),
[findings-to-fix-first.md](findings-to-fix-first.md) (what to fix in
LicenseID and Pitloom before the code stage),
[examples/](examples/README.md) (the Asserter and Basis matrix on real
inputs),
[mappings/](mappings/pitloom-provenance.sssom.tsv) (SSSOM), and what this
replaces: [provenance-enrichment-vocabulary.md](../provenance-enrichment-vocabulary.md),
[role-vocabulary.md](../../implementation/provenance/role-vocabulary.md),
[evidence-levels.md](../evidence-levels.md),
[license-rules.md](../license-rules.md) (sections 1, 2, 4; questions 5, 13,
14), [generic-multi-candidate-fields.md](../generic-multi-candidate-fields.md).

**Status:** agreed as a whole on 2026-11-23 (stage (c): the taxonomies as
design documents; drafted from 2026-11-14). "Draft" in the status line of
another page of this folder is from before that day. Not built: the code
still emits the old vocabulary. Nothing here changes the output until the
code stage, which is not started and needs its own agreement.

Ruled on 2026-11-23, after a last look before the code stage: the
names stand. They are the facet `Asserter` and its five values;
`Basis` (named `Evidence` until 2026-11-22; [basis.md](basis.md),
"The name") as the home of the released `Role`'s "how" words, with
six values; the conflict rule `basis-order` and the grades
`compatible` and `incompatible` ([conflict.md](conflict.md)). Each
was ruled "for now" before (2026-11-16, 2026-11-18, 2026-11-22).
The casing of values is ruled (kebab-case, 2026-11-14).

## Why

Pitloom grew eleven vocabularies that describe where a recorded value came
from. They overlap: `declared` meant three things, `role` three, `method`
two; a `Method` value could say who, how or how sure; the licence code
decided "declared or concluded" by two different rules. This folder defines
one model and one vocabulary per question.

## The model

A **claim** is one value recorded for one field of one element. Provenance
describes a claim through **facets**. Each facet answers one question and has
one vocabulary.

Provenance here is of a claim: where a recorded value came from. It is not
the provenance of an artefact: how a model or a package came to exist (a
base model, training data, a build). That lineage, where Pitloom records
it, is elements and relationships of the SBOM (`trainedOn`, a dependency),
and such a relationship is a claim with provenance of its own (ruled
2026-11-22; [basis.md](basis.md), "The name").

| Facet | Question | Values | Page |
| --- | --- | --- | --- |
| Source | Where did Pitloom read it? | a label, with a closed `kind` | [source.md](source.md) |
| Asserter | Who brought the value in: whose determination is it? | 5, closed | [asserter.md](asserter.md) |
| Basis | How did the asserter come to the value? | 6, closed, with reason codes | [basis.md](basis.md) |
| Method | What did Pitloom do to get the value? | 5 classes, closed; registered techniques | [method.md](method.md) |
| Change | How does the value differ from what was written? | step kinds | [change.md](change.md) |

Two more vocabularies are about several claims, not one:

| Vocabulary | Question | Page |
| --- | --- | --- |
| Value strength | Is this a real statement, a placeholder or an explicit "none"? | [value-strength.md](value-strength.md) |
| Conflict | Several claims for one field: which one stands, by which rule, and can two of them both be true? | [conflict.md](conflict.md) |

The facets are independent. A value from the PyPI JSON API is
`Source: PyPI JSON API` (kind `registry`) and `Asserter: originator`: Pitloom
read it from the registry, and it is the project's own uploaded statement.

Asserter and Basis are the two axes the released `Role` held in one
word. Asserter serves provenance and trust by proxy (how good is the party
that brought the value in); Basis serves trust by the nature of the
information itself. They vary apart: a hosting service's licence detector
is `other-party` with `detected`; a paper's statement is `other-party` with
`declared`.

The model can be read in existing vocabularies
([alignment.md](alignment.md)). A recorded value is a `prov:Entity`
derived from a statement. Asserter reads as the statement's
`prov:wasAttributedTo`. Basis says whether the asserter's own act is
known, and of what kind. Method names the plan (`prov:Plan`,
`sosa:Procedure`) of Pitloom's act, which `prov:used` the Source. Change
reads as `prov:wasRevisionOf`. SIO has relations for two claims that
agree, differ or exclude each other, the base of the grade of a conflict in
[conflict.md](conflict.md). ODRL, read for the licence field only, tells a
licence proposed by its issuer from one that is only claimed. All are
mapping targets; none is written into an SBOM.

## Rules for every vocabulary

1. **One question per facet.** A term that answers another facet's question
   moves there (`Method: lfs_pointer` said what kind of source was read;
   `Method: repository_owner` was a location; `Method: latest-release` was a
   selection rule).
2. **One grammar per facet, and no word in two vocabularies.** Asserter
   values are nouns that name a party (`other-party`). Method classes say
   what Pitloom did (`parsed`). Basis values say how the value is known
   (`measured`).
3. **One casing.** Values are kebab-case (ruled 2026-11-14): lower-case
   words joined by one hyphen, matching `^[a-z0-9]+(-[a-z0-9]+)*$`, so an
   abbreviation has one spelling (`ai-agent`, `sbom-author`). They are
   spelled as identifiers are, the American way (`synthesized`,
   `artifact-content`). A `Reason` code is a message catalogue code and
   has the same casing, so the SBOM, stderr and the skills use one string.
   Keys are one capitalised word; a key of a JSON record is kebab-case
   too (`value-type`). A term of another vocabulary keeps its own spelling
   (`hasDeclaredLicense`, `trainedOn`). In Python the member name is the
   value with `-` as `_`.
4. **Closed lists.** Every vocabulary is a closed list, checked by the one
   builder that writes it. Method techniques are a registered list: adding
   one is a code change with a docs row, never free text.
5. **Every term has** a definition in one sentence; no term is defined by
   example only. Before the taxonomy is final each also gets a decision
   question, an example and a mapping. Missing today: source kinds,
   techniques, conflict rules and statuses, value-strength classes.
6. **No tool, format or product name inside a value.** The tool goes in
   `Tool`; the format is known from the source.
7. **Three facets are always written; one default is not.** Ruled
   2026-11-23: `Asserter`, `Basis` and, on a claim that has a source,
   `Kind` are written on every claim, in the string and in the JSON
   record. A hand-written fragment that omits `Asserter` must not be
   read as the originator's own claim, and a reader that had to work
   out a missing `Basis` would need the table of defaults by asserter
   and method class. Each facet still states its default: it says
   which value Pitloom writes when nothing says otherwise. The one
   default that is not written is `Method: read`
   ([method.md](method.md)).
8. **A word of the same nature is the same word.** `declared` means "a
   party said so", as a basis value and in SPDX's declared licence;
   the released word stays. `concluded` is an SPDX word only.
9. **The grammar stays.** `Key: value | Key: value` strings and the
   Annotation envelopes keep their shape. Keys and values change.

## Keys

| Key | Holds | Was |
| --- | --- | --- |
| `Source` | label of what Pitloom read | `Source` |
| `Kind` | source kind | (looked up from the label) |
| `Location` | where inside the source | `Field` (JSON `location`) |
| `Container` | archive, repository or directory that holds the source | `File` (one of its four meanings) |
| `Asserter` | who brought the value in | `Role` (`externalReported`, `sbomAuthorSupplied`, and the party the other three implied) |
| `Method` | method class | `Method` |
| `Technique` | registered technique | `Method` |
| `Tool` | tool and version that did it | `Tool` |
| `Basis`, `Reason` | how the asserter came to the value; catalogue code | `Evidence`; `Role` (`declared`, `detected`, `inferred`) |
| `Written`, `Change` | value as written; step kinds | `Normalized-From`; `Resolution-n`, `Expansion-n` stay for licence operands |
| `Superseded` | a retired identifier the source used, with its successor | `Deprecated-License-Id` |
| `Rule` | selection rule, when a claim stands because others were passed over | `Method: latest-release`, `Note: supersedes ...` |
| `Package`, `Value`, `Note`, `Budget`, `Count` | unchanged; `Package` also names a release (`requests==2.32.3`) when the claim was read at a state that is not the element's ([source.md](source.md), B1) | same |

## Worked examples

Old and new form of the same claim. The new strings are illustrations of the
vocabulary; the final string layout is a code-stage decision.

| Claim | Old | New |
| --- | --- | --- |
| Licence from the manifest | `Source: pyproject.toml \| Field: project.license` | `Source: pyproject.toml \| Kind: manifest \| Location: project.license \| Asserter: originator \| Basis: declared` |
| Licence matched from `LICENSE` | `Source: LICENSE \| Method: licenseid_detection \| Tool: licenseid==0.8.4` | `Source: LICENSE \| Kind: package-file \| Asserter: originator \| Method: matched \| Technique: license-text \| Tool: licenseid==0.8.4 \| Basis: declared` (form ruled 2026-11-21: [asserter-licence.md](asserter-licence.md)) |
| Dependency licence from PyPI | `Source: PyPI JSON API \| Package: requests` | `Source: PyPI JSON API \| Kind: registry \| Package: requests \| Asserter: originator \| Basis: declared` |
| Parameter count summed from tensors | `Source: model.safetensors \| Method: tensor_element_sum` | `Source: model.safetensors \| Kind: artifact-content \| Asserter: sbom-tool \| Method: derived \| Technique: tensor-element-sum \| Basis: measured` |
| Hash from a Git LFS pointer | `Source: weights.bin \| Method: lfs_pointer` | `Source: weights.bin \| Kind: pointer \| Location: oid \| Asserter: originator \| Basis: declared` |
| Hash not computed, file over the cap | `Source: data.bin \| Evidence: not_measured \| Reason: over-cap` | `Source: data.bin \| Kind: artifact-content \| Asserter: sbom-tool \| Method: derived \| Technique: content-hash \| Basis: not-measured \| Reason: over-cap` |
| Dataset named by an agent from README prose | `Source: AI agent \| Role: inferred` | `Source: README.md \| Kind: card \| Asserter: ai-agent \| Tool: <agent> <version> \| Basis: inferred` |
| Parameter total the Hub reports | `Source: Hugging Face Hub \| Method: tensor_element_sum` | `Source: Hugging Face Hub API \| Kind: registry \| Location: safetensors.total \| Asserter: other-party \| Basis: detected` (the Hub computed it; Pitloom did not) |
| Content type from `[tool.pitloom]` | `Source: a.bin \| Role: sbomAuthorSupplied` | `Source: pyproject.toml \| Kind: config \| Location: tool.pitloom.content-type.override \| Asserter: sbom-author \| Basis: declared` |

## Use cases the model serves

- **Triage by a consumer:** by the information (keep `declared` and
  `measured`, review `inferred`), by the party (review `other-party` and
  `ai-agent`), or both. Two keys, one question each.
- **Licence relationships:** one table from Asserter to
  `hasDeclaredLicense`/`hasConcludedLicense` ([asserter-licence.md](asserter-licence.md)).
- **Merge rules:** a fragment replaces a `synthesized` value; a value drops a
  `not-measured` entry. The code branches on a closed class, not on a list of
  method names.
- **Detail levels:** `minimal` keeps an entry whose asserter is not
  `originator`, or whose basis is not `declared`, or that has a
  `Method`, `Change` or `Rule`. No
  list of "transparent" source labels.
- **Skills:** read `Asserter` and `Basis` to choose what to enrich; write
  `Asserter: ai-agent` or `sbom-author`.
- **Minimum-elements reports:** `not-measured` with a reason is a known
  unknown that says why.
- **An SPDX proposal** (issue #110): the facets are the properties a
  provenance profile would need.

## Out of scope

Lifecycle scope for extras, extraction and recording gap kinds, the
minimum-elements status words, the names of the Annotation kinds, and the
licence resolution categories (LicenseID owns them; [change.md](change.md)
maps them). A BSI-style stage facet (original, distribution, effective) is
deferred; [conflict.md](conflict.md) reserves its slot.

## Open questions

1. Closed 2026-11-23: the names that were ruled "for now" and the six
   basis values stand (the list is under "Status", above). Looked at
   and not taken: the grades as `consistent` and `inconsistent`,
   since `compatible` can be read as licence compatibility in the
   legal sense; [conflict.md](conflict.md), G2, says it is not.
2. Closed 2026-11-23: `Kind` is its own key, written on every claim that
   has a source ([source.md](source.md), rule 8). Not taken: looked up
   from the label for fixed labels and written only for file names.
3. Closed 2026-11-23: rule 7's exception stands, `Asserter` is always
   written. Not taken: omitted when `originator`.
4. A library caller's metadata is ruled (2026-11-23: `originator`;
   [asserter.md](asserter.md)). Closed 2026-11-23: the licence work
   parked on 2026-11-16; every point has a ruling in
   [asserter-licence.md](asserter-licence.md), one of them a
   deferral (the scope of a licence file). Closed
   2026-11-23: the open point of [basis.md](basis.md) (`Basis` is
   always written) and that of
   [renames-and-migration.md](renames-and-migration.md) (three names).
5. Closed 2026-11-23: the grade of a conflict (`compatible`,
   `incompatible`; [conflict.md](conflict.md)) is written as `grades`, a
   list of pairs on the record, and Pitloom decides it for a licence
   pair by a closed test.
6. Closed 2026-11-23: the field-table rows that "acting on behalf of"
   bears on ([alignment.md](alignment.md)). `pipdeptree` is `sbom-tool`,
   `measured`; a registry's record of a maintainer's act (a yank, a
   gate, an owner's namespace) stays `other-party`, `declared`.
7. Closed 2026-11-23: the review points the examples raised
   ([examples/README.md](examples/README.md), "What the examples show").
   Nine of the fourteen have an answer there (1 to 5, 10, 12 to 14).
   Points 6 to 9 and 11 ask for no ruling: each is a note for the field
   table or for the code stage.
