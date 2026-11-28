---
Created: 2026-11-14
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Basis: how the asserter came to a value

See also: [README.md](README.md) (the claim model),
[asserter.md](asserter.md), [method.md](method.md),
[conflict.md](conflict.md). Takes over the three "how" words of the `role`
vocabulary
([role-vocabulary.md](../../implementation/provenance/role-vocabulary.md))
and widens the levels of [evidence-levels.md](../evidence-levels.md) to
every field; that page's principle ("caps bound reading, never reporting")
stands. One of its readings changes (ruled 2026-11-16): it calls every
value an API states `declared`; here a value the API's party computed
is `detected` (rule 2).

**Status:** draft. Scope and the six values are ruled (2026-11-23;
"for now" since 2026-11-16).
The key was `Evidence` until 2026-11-22 ("The name", below).

## Two axes

The released `Role` was described as "an epistemic-process label (*whose*
determination this is)" and defined each of its five values by a party.
Its words name two different things, which are apart now.

| Axis | Question | Serves |
| --- | --- | --- |
| [Asserter](asserter.md) | Who brought the value in? | provenance; trust by proxy (how good is that party) |
| Basis | How did the asserter come to the value? | trust by the nature of the information itself |

Three of the words say how (`declared`, `detected`, `inferred`) and are
basis values now. Two say who (`externalReported`, `sbomAuthorSupplied`)
and are asserter values now. Each old value becomes a pair
([renames-and-migration.md](renames-and-migration.md)).

## Definition

The **basis** of a claim says how its asserter came to the value: by
saying so, by a procedure on the thing itself, or by concluding it from
something else.

## The name: `Basis`, not `Evidence` (ruled 2026-11-22)

The key was `Evidence` in the released strings, and in this draft until
2026-11-22. That word has two senses in the vocabularies read
([vocabularies-considered.md](vocabularies-considered.md),
[vocabularies-considered-sbom.md](vocabularies-considered-sbom.md)).

| Sense | Used by | Example |
| --- | --- | --- |
| a kind: what sort of support a value has | ECO (evidence is a type of information that supports an assertion); Pitloom's released `Evidence` key and its rule that every fact has an evidence level | `declared`, `measured` |
| a thing: something a claim points to, which a reader can check | the OWASP AIBOM Foundations Guide v1.0 (p. 19) | a hash, a signature, a model card, a licence file |

CycloneDX's `evidence` object holds both: `occurrences` (a thing) and
`methods` (a kind, with a confidence). This facet is the first sense. The
second is recorded under other names:

| The guide's evidence | Where it is recorded |
| --- | --- |
| a model card, a licence file, a dataset record | `Source` and `Location` of the claim read from it ([source.md](source.md)) |
| a hash | `verifiedUsing` of the element; rule 8 says when it has a provenance entry |
| a signature or attestation | not recorded; attestation formats were not read |
| an evaluation result | a field of the element (SPDX `metric`), not provenance |

The guide's *provenance* differs too: how an artefact came to exist (a
base model, a training run). Here provenance is of a claim: where a
recorded value came from.

Ruled 2026-11-22: the key is `Basis`. In the SBOM field "evidence" means
a thing (CycloneDX, the guide); ECO, which has the other sense, is of
biology. A reader of an SBOM, and of a proposal to SPDX, takes `Evidence`
for a pointer. `Basis` is one word (README rule 3) and pairs with
Asserter: who says it, and on what basis. Pitloom needs no backward
compatibility, so a released key is no reason to keep it.

With the name:

1. The question is "how did the asserter come to the value?". It was
   "how did the value come to exist?", which is the guide's wording for
   the provenance of an artefact and is near Method's question. Taken
   with the name, not ruled on its own.
2. Two of the six values read less well: `Basis: lower-bound` and
   `Basis: not-measured` say how a read ended, not what supports a
   value. They stay.
3. Three names follow. This page was `evidence.md`. The conflict rule
   `evidence-level` is `basis-order` (ruled 2026-11-23)
   ([conflict.md](conflict.md)). The names in the code and its documents
   (the principle "every fact has an evidence level", among them) change
   at the code stage
   ([renames-and-migration.md](renames-and-migration.md), item 14).

Not chosen: keeping `Evidence` (the clash stays); `Evidence-Level` (two
words, against README rule 3; the word stays; and the six values are
kinds, ordered for content facts only).

Where the word was looked for (2026-11-22): SPDX 3.0.1 and 3.1, in the
Python bindings, have "basis" in descriptions only, as no class or
property; the text of the guide does not have it. Not looked for: PROV-O,
SOSA, SIO, ECO, CycloneDX, Wikidata (its P887, mapped in
[method.md](method.md), is "based on heuristic").

Also ruled 2026-11-22: the README says what provenance covers here, a
claim ([README.md](README.md), "The model"). The lineage of an artefact
(base model, training data, build) is elements and relationships of the
SBOM, not a facet.

## Values

| Value | Definition | Test | Was |
| --- | --- | --- | --- |
| `declared` | A party said so. | No procedure is known; the value is a statement. | role `declared`; evidence `declared` |
| `measured` | Pitloom got the exact value by a procedure on the thing itself: the part that carries the fact was read in full, or the file system was asked. | One right answer for the quantity the technique names; any correct tool that follows the technique's rule gives the same. | evidence `measured_read`, `measured_stat` |
| `detected` | A procedure on the thing itself gave the value, and Pitloom does not vouch for it as exact: Pitloom's best match in a reference set, or a value another party got by its own procedure, exact or not. | The result depends on the tool and its data, or the procedure was not Pitloom's. | role `detected`; evidence `declared` for a value an API's party computed |
| `inferred` | The value was concluded from a proxy (something that stands for the property and is not it), or by judgement. | The thing examined is not the property's own carrier, or the step is not repeatable. | role `inferred` |
| `lower-bound` | A read or walk stopped at its limit. Recorded with the limit (`Budget`), never the partial value. | A cap stopped the read. | evidence `lower_bound` |
| `not-measured` | No value: not safe or not possible to read, and no party states it. | Nothing was read. | evidence `not_measured` |

No `reported`: a statement by another party is `declared` with
`Asserter: other-party`; the word would repeat the asserter. No
`synthesized`: Pitloom cannot know that another party made a value up, and
its own composed value is `inferred` from a proxy (a name from a file name
stem), with `Method: synthesized` saying what Pitloom did.

The part that carries the fact (ruled 2026-11-23): `measured` asks
that this part was read in full, not the file. For a hash it is the
whole file. For a parameter count it is the tensor table, which holds
every shape: some 23 kB of a file of 344 MB, and the count is exact
([examples/sbom-tool.md](examples/sbom-tool.md#sbom-tool-measured),
SM-3, SM-5). The technique names the part. Two limits:

- The part is where the fact lives, not a statement about another
  part. An archive header's size for a member states what the
  member's bytes would show, so it stays `declared` (rule 2); a
  tensor's shape lives in the tensor table and nowhere else.
- A cap that stops the read inside the part gives `lower-bound`,
  as before.

The proxy test, with examples:

| Field | Examined | Basis |
| --- | --- | --- |
| content type | the file's bytes, by a matcher | `detected` |
| content type | the file name's extension | `inferred`: the extension stands for the content and can be wrong |
| model name | the file name stem | `inferred` |
| hash | the file's bytes | `measured` |
| parameter count | every tensor's shape | `measured` |

## Rules

1. **Read `Basis` together with `Asserter`.** It says how *that
   asserter* got the value. `Asserter: other-party | Basis: detected` is
   a hosting service's own detector; Pitloom checked nothing.
2. **`measured`, `lower-bound` and `not-measured` are Pitloom's only.** They
   occur with `Asserter: sbom-tool` and no other. A value another party
   got by its own procedure is `detected`, exact or not (ruled
   2026-11-16): a registry's file digest, the Hub's parameter total.
   Pitloom did not run that procedure and cannot vouch for it. This
   keeps the principle that a value Pitloom did not measure is never
   passed off as measured, and keeps a party's computed value apart
   from its plain statement.

   `detected` for another party needs the procedure to be known: the
   field table in [asserter.md](asserter.md) lists each such field. Any
   other stated value stays `declared` (rule 6; ruled 2026-11-16): an
   archive header's size, an LFS pointer's oid and size,
   `Content-Length`, a hash recorded in a lock file or in `RECORD`.
3. **`sbom-tool` never has `declared`.** Pitloom states nothing of its own.
4. **Allowed pairs:**

   | Asserter | `declared` | `measured` | `detected` | `inferred` | `lower-bound` | `not-measured` |
   | --- | --- | --- | --- | --- | --- | --- |
   | `originator` | always | - | - | - | - | - |
   | `sbom-tool` | never | by method | by method | by method | yes | yes |
   | `other-party` | default | - | when known | when known | - | - |
   | `ai-agent` | - | - | - | default | - | - |
   | `sbom-author` | default | - | - | when the author says so, or confirms an agent's value ([asserter.md](asserter.md), rule 8) | - | - |

   `originator` has `declared` only (ruled 2026-11-23; the two cells
   were "when known" until then). Pitloom does not see how an
   originator came to a value, so rule 6 applies. No real input was
   found for either cell
   ([examples/originator.md](examples/originator.md#originator-detected-and-inferred));
   the one candidate rested on a repository tag, which says nothing
   sure about the number beside it. To open a cell again takes a
   source that states its own procedure, and a row in the field
   table of [asserter.md](asserter.md), as for `other-party`.
5. **`Basis` is always written** (ruled 2026-11-23; README rule 7),
   in the string and in the JSON record. The one entry with none is
   the stand-in `placeholder-root`, which is no claim
   ([method.md](method.md)). Where nothing says otherwise, the value
   is:
   - `originator`, `sbom-author`: `declared`.
   - `ai-agent`: `inferred`.
   - `sbom-tool`: by the method class ([method.md](method.md)):
     `derived` gives `measured`, `matched` gives `detected`, `synthesized`
     gives `inferred`.
   - `other-party`: `declared`. All Pitloom knows is that the party said
     so. Where the field table in [asserter.md](asserter.md) knows that
     the party computed the value (a registry's file digest), `detected`
     is written.
   - A `lower-bound` or `not-measured` claim carries the method class and
     technique of the read that was tried, so its asserter derives as
     `sbom-tool`.
6. **No "unknown" value.** A value whose making Pitloom cannot see is
   `declared`: from where Pitloom stands, a party said so. So every claim
   has a basis value, and it is written.
7. **`measured_stat` and `measured_read` are one value.** How the value was
   observed is a technique: `file-stat` or `content-hash`. The caveat that
   a pointer's `stat()` size is the pointer's own is a source matter
   (`Kind: pointer`).
8. **A project file's hash keeps having no provenance entry** (and so no
   `Asserter`); the hash itself is the record. It counts as `measured`.
9. **`declared` is also the SPDX licence word, and means the same thing**:
   a party said so. An `other-party` licence claim with basis `declared`
   is still not a declared licence: the licence table in
   [asserter-licence.md](asserter-licence.md) reads the asserter, not this facet.

## What a reader can check again (ruled 2026-11-23)

Raised by the OWASP AIBOM Foundations Guide v1.0 (p. 8, 19;
[vocabularies-considered-sbom.md](vocabularies-considered-sbom.md), point 2): a
claim with a reference to its support is "a claim a consumer can
independently verify", one with none is a bare assertion, and which of
the two a claim is tells a reader how much weight it bears. The basis
says which kind of check a claim allows; other keys hold what the check
needs.

| Basis, asserter | A reader can check again | Cannot | The check needs |
| --- | --- | --- | --- |
| `declared`; `originator`, `other-party` | that the party said so: the source read again, at its state, at the location | that the statement is true | `Source`, `Location`, `Container`; the state on the element ([source.md](source.md), rules A, B). For a moving source (rule D): only what it says now |
| `declared`; `sbom-author` | that the file says so, when the value is in a file (`[tool.pitloom]`, a fragment) | that it is true; anything, for a value given by a CLI flag or an Action input | `Source`, `Location` |
| `measured` | the value itself: the procedure done again on the thing gives the same, with any correct tool | nothing, when the reader has the thing | the thing (the element, with its state or digest), `Technique` |
| `detected`; `sbom-tool` | the result: the same tool, version and reference data give the same match. Another tool may give another, and that is no error | that the match is right | the thing, `Technique`, `Tool` with its version, the version of the reference data (for a licence, `simplelicensing_licenseListVersion` of the expression) |
| `detected`; `other-party` | that the party stated it, as for `declared`; and, with the thing in hand, the value by a procedure of the reader's own (a file digest) | the party's procedure | as for `declared`. The procedure is named in the field table of [asserter.md](asserter.md), not on the claim |
| `inferred`; `sbom-tool` | the step: the proxy is named and the rule is fixed, so the same proxy gives the same value | that the value is true of the property | the proxy (`Source`), `Technique` |
| `inferred`; `ai-agent` | only that the text the agent read is there | the step, which is not repeatable; the value | `Source`, `Location`, `Tool` (the agent and its version) |
| `inferred`; `sbom-author` (row added 2026-11-23, after the table was ruled) | that what the author or the agent read is there, when a source is named; with a `Tool`, that an agent made the reading and the author confirmed it ([asserter.md](asserter.md), rule 8) | the step; the value | `Source`, `Note`; `Tool` for a confirmed reading |
| `lower-bound` | that a read with the same limit stops there; a full read gives the value | - | the thing, `Technique`, `Budget` |
| `not-measured` | whether the cause still holds, by trying the read | a value: there is none | `Reason` |

So three kinds of check, from strong to weak: the value can be had
again (`measured`, and `detected` by another party when the reader has
the thing); the step can be done again (`detected` and `inferred` by
Pitloom); only the source can be read again (`declared`, and `inferred`
by an agent or by the author). The table adds no key and no value: it
says what the keys already there are for. Pairs of rule 4 with no row
(`detected` or `inferred` by the `originator`; `inferred` by an
`other-party`) are checked as `declared` is: only that the party said
so.

What the SBOM does not hold today for a check (code at the branch base,
read 2026-11-23):

- The version of the reference data of a match. A licence match writes
  `licenseid==` and the package version, a content type match `magika==`
  and its version; neither writes the data the match was made against.
  LicenseID 0.9.0 names the list an answer rests on, with its version
  (`ListInfo`); this base pins LicenseID below 0.9, and `main` at
  01d1a726 (#513; this checkout's copy of the remote branch) pins 0.9
  and has no code that reads it. Whether a Magika package version fixes
  its model was not checked.

  Ruled 2026-11-23: no new key. The reference data of a match is a
  state, and by rule B of [source.md](source.md) it is written once,
  where the format has a place. For a licence SPDX 3.0.1 has one:
  `simplelicensing_licenseListVersion` on the `LicenseExpression`
  ("The version of the SPDX License List used in the license
  expression", from the bindings). Pitloom builds its licence
  expressions without it today (code stage). A real LicenseID 0.9.0
  answer (run 2026-11-23) names the list `spdx-license-list`, version
  `3.29.0`, which fits the property's pattern. For a match with no
  such place (a content type) the tool's version in `Tool` stands for
  the data, if the data ships inside the tool; that is the Magika
  check above.

  Tried, reverted the same day: a key on the claim (`Reference`, with
  a value such as `spdx-license-list==3.29.0`). Ruled first, then
  withdrawn, since the format's own property holds the one case there
  is. Should a match come whose data ships apart from its tool and
  has no property in the format, the key is looked at again.
- The state of a source, for the routes that write none
  ([source.md](source.md), code stage list).

Not looked at: whether an `ai-agent` claim written by the skills gives a
`Location`; whether `Technique` and `Budget` are on every claim the
table says needs them.

## Precedence for content facts

For a fact that the artefact's own bytes or the file system settle (a hash,
a byte size, a count): Pitloom's `measured` value stands over a value any
other asserter gave (whether `declared`, `detected` or `inferred`), which
stands over `lower-bound`, which stands over `not-measured`. A stronger
fact replaces a weaker one; an equal or weaker one is ignored. When a
measured value and one from another asserter differ, the measured one
stands and the difference is a
[conflict](conflict.md) with rule `basis-order`: a ZIP that states a
small size and expands large is the attack case.

A count stays a content fact (ruled 2026-11-23), with two conditions:

- **The technique states its counting rule.** A parameter count is
  not a hash: which tensors count is a rule, and two correct tools
  with two rules differ. Pitloom's count is `measured` for what
  `tensor-element-sum` names ([method.md](method.md)), not for
  every meaning of "parameter count". The Hub's total and
  Pitloom's sum over the same file differ in 15 of 128
  repositories
  ([examples/other-party.md](examples/other-party.md#other-party-detected),
  PT-6, PT-8); Pitloom's value stands and the Hub's is kept in the
  conflict record. Not taken: no precedence for a count, which
  would leave the slot to another rule or empty.
- **Both values are about one element.** The Hub's total is of a
  repository, Pitloom's sum of a file; the precedence applies only
  where both claims sit on the same element. Whether a route puts
  them on one element was not checked.

A value Pitloom did not measure never permits a read and never gates a cap;
it may stop a read early.

For any other field, the basis sets no precedence; the
[conflict](conflict.md) rules do.

## Reason codes

A `Reason` is a message catalogue code, kebab-case, so the SBOM, stderr and
the skills carry one string. Closed set, checked by `evidence_segment`.

| Code | Why the fact is `not-measured` |
| --- | --- |
| `over-cap` | a read or download cap |
| `download-timeout` | the wait was too long |
| `download-network-failed` | the fetch was refused or broke; a gated or private repository read without access (HTTP 401, 403) is here too |
| `lfs-pointer` | only the pointer arrived, and it states nothing usable |
| `file-unreadable` | a permission or I/O error |
| `dir-unlistable` | a directory could not be listed |

The two `download-` codes were `timeout` and `network-failed` until the
message catalogue named them (`main` 01d1a726,
`pitloom.core.evidence.REASON_CODES`); neither has a writer yet.

A gated repository has no code of its own (ruled 2026-11-23). The
catalogue's `download-network-failed` covers a 401 and a 403, with the
advice to sign in, and a `Reason` follows the catalogue. Not taken: a
code `access-denied`, which would let a reader of the SBOM tell a gate
from a fault. It would need a new catalogue message, and the Hub API
answers 404 for a private repository, so a split by status would miss
those. To look at again when the first writer of a network reason is
built ([examples/sbom-tool.md](examples/sbom-tool.md#sbom-tool-not-measured),
SN-2).

The skills write `Reason: <free text>` today, which parses into this closed
key. A free-text reason moves to `Note`.

### Ruled 2026-11-28: the reason list is the taxonomy's own

The first sentence of this section and the paragraph on a gated
repository are replaced by a ruling of 2026-11-28: the taxonomy owns a
closed list of reasons, and a catalogue code maps to it. The ruling,
what was agreed with it and what is still open: [reason.md](reason.md).
This section is not yet rewritten to it.

## Outcome of a source

What happened when Pitloom went to a source for a content fact. Three
are recorded; `unavailable` stays silent (absent data is not an error).

| Outcome | Recorded as | Was |
| --- | --- | --- |
| `used` | the claim; its `Asserter` and `Basis` say whose value it is and how it was got | `used`, `declared_only` |
| `unavailable` | nothing | same |
| `refused` | `not-measured` with `over-cap` | same |
| `failed` | `not-measured` with `download-timeout`, `download-network-failed`, `file-unreadable` or `dir-unlistable` | same |

No `declared-only` (dropped 2026-11-23). The word was made before the
asserter facet: it marked a source of which only another party's
value reached Pitloom. `Asserter` and `Basis` are written on every
claim and say this; and the word misled where that party computed
the value, which is `detected`
([examples/other-party.md](examples/other-party.md#other-party-detected),
PT-2). Such a source is `used`. A new name (`stated-only`,
`not-own-measure`) was looked at and not taken. Pitloom's own measure
that was skipped leaves no entry beside the claim: the other party's
value replaces `not-measured` ("Precedence for content facts").

## Unknown and withheld

The 2026 Minimum Elements for an SBOM (CISA and co-authoring agencies,
version 2.1, 2026-07-29; primary text read 2026-11-16) hold the practice
"Explicitly Identifying Unknown Information": where the information for a
data field is not provided, the SBOM author should state whether it is
*unknown* to the author or *withheld* by the author. The document calls it a
practice for the whole SBOM lifecycle, not a data field, and five field
texts repeat it: a hash when the author has no access to the artefact, a
licence the author is not aware of, a component version its producer does
not provide, a tool version, and a producer that cannot be told ("unknown
provenance"). `not-measured` with a reason is the unknown case for a content
fact, with its cause. Pitloom withholds nothing today; `withheld` is
reserved as a seventh value should a redaction option be built, and is not
to be used for anything else.

## Mappings (loose)

SSN/SOSA (W3C Recommendation, 2017) describes the observed half: an
`sosa:Observation` is an act of carrying out a `sosa:Procedure` to "estimate
or calculate a value of a property" of a `sosa:FeatureOfInterest`, made by a
`sosa:Sensor` (a device, an agent or software). It has no class for a
value that is stated and not observed; its one mention is an example under
`sosa:ObservableProperty`, where the value of a classic car "is not
(directly) observable but asserted". Terms and quotes checked against the
Recommendation, 2026-11-16. A 2023 Edition is a Working Draft: it moves
`Stimulus` and `isProxyFor` to the `sosa:` namespace, drops the
`ssn-system:` namespace with `Accuracy` and `MeasurementRange`, and drops
the classic car example.

| Value | SSN/SOSA | SPDX 3 | CISA 2026 | CycloneDX | ECO |
| --- | --- | --- | --- | --- | --- |
| `declared` | "asserted"; no class | - | - | `technique: attestation`, `manifest-analysis` | `ECO:0000204` author statement |
| `measured` | `sosa:Observation` | `completeness: complete` on the relationship that carries the fact | - | `hash-comparison`, `binary-analysis`, `confidence: 1` | `ECO:0007669` computational evidence used in automatic assertion |
| `detected` | `sosa:Observation`, by any `sosa:Sensor`; for a best match, `ssn-system:Accuracy` below the full | - | - | `technique` with `confidence` below 1 | `ECO:0000041` similarity evidence (the best-match case) |
| `inferred` | no class; `ssn:isProxyFor` is related only (see below) | - | - | `technique: other` | `ECO:0000363` computational inference used in automatic assertion |
| `lower-bound` | a value beyond `ssn-system:MeasurementRange` | `completeness: incomplete` | - | - | - |
| `not-measured` | no observation made | `completeness: noAssertion`; `NoAssertionElement` | unknown | - | - |

The proxy test of this page is this model's own. `ssn:isProxyFor` relates
a stimulus to the property it stands for, and in SSN every stimulus does:
its example is a thermometer ("the expansion of quicksilver is a stimulus
that serves as a proxy for some temperature property"). So SSN's proxy
does not mark `inferred`; the word is shared, the line is not (corrected
2026-11-16, after a fact-check).

SOSA aligns itself to PROV-O in a non-normative module (Observation to
`prov:Activity`, Sensor to `prov:Agent` and `prov:Entity`, Procedure to
`prov:Plan`, Result to `prov:Entity`), which is the bridge from this model
to PROV for a single value. PROV-O itself has no word for a basis: it
tells `declared` (the asserter's own act is not known) from `measured`,
`detected` and `inferred` (it is known). The lines between those three
are this model's own: SOSA has one class for every observation, and SSN's
proxy marks none of them (above). SIO has loose matches for three
values: `statement` for `declared`, `measurement value` for a `measured`
quantity, `conclusion` ("reached
after considering the evidence, arguments or premises") for `inferred`.
Its `hypothesis` ("a proposed explanation for a phenomenon") is not
`inferred`: an inferred value explains nothing. The pattern:
[alignment.md](alignment.md).

SPDX has no property for the basis of a value; it stays in the
Annotation, and the gap is FG-13 (with FG-10 for a declared hash) in
[sbom-format-gaps.md](../sbom-format-gaps.md).

## Open points

1. Closed 2026-11-23: `Basis` is always written, in both forms (rule
   5), so a consumer filters on one key and need not know the
   defaults. Not taken: the default left unwritten; or written in
   the JSON record only, where the two forms would differ.
2. Closed 2026-11-21. A licence file matched to an id is
   `Asserter: originator`, `Basis: declared`, with the match as
   `Method: matched` and its `Tool` ([asserter-licence.md](asserter-licence.md), "The
   form of a text match"). `Basis: detected` there would say the
   originator detected it.
