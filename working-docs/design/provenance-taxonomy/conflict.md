---
Created: 2026-11-14
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Conflict: several claims for one field

See also: [README.md](README.md) (the claim model),
[asserter.md](asserter.md), [value-strength.md](value-strength.md),
[basis.md](basis.md), [alignment.md](alignment.md),
[resweep-rulings.md](resweep-rulings.md) (C3, ruled 2026-11-28). Revises
[multi-source-conflict.md](../../implementation/provenance/multi-source-conflict.md)
and answers
[generic-multi-candidate-fields.md](../generic-multi-candidate-fields.md)
and [license-rules.md](../license-rules.md) question 5.

**Status:** draft.

## Definitions

- A **slot** is one native place of the format for a field's value: a
  property, or one relationship type. A licence has two slots
  (`hasDeclaredLicense`, `hasConcludedLicense`); a version has one.
  A slot takes one value, except the declared licence slot, which takes
  every licence the originator stated (ruled 2026-11-16).
- A **candidate set** is every claim Pitloom holds for one field of one
  element.
- A **selection** picks, for one slot, the claim that fills it, by a named
  **rule**.
- A **conflict** is a candidate set in which two `real` or `none` values
  ([value-strength.md](value-strength.md)) differ after normalisation.

At the draft's base (257b7260) 37 places in the code chose between
candidates. Five recorded the loser in an Annotation, a few warned,
most recorded nothing. The Annotation lists candidates and does not say
which stood or why. The count is of the base and was not redone. Added
on `main` since (read at dfa11c14): the two-declared mode of a
dependency's licence, its licence file beside its stated licence text,
both declared, with a conflict Annotation when they differ
(`assemble/spdx3/deps_license.py:164-202`); a placeholder or blank
stated licence giving way to the licence files
(`assemble/spdx3/_deps_license_files.py:146-183`); and the stop when a
licence file holding the texts of several licences comes first
(`extract/_license.py:115-117`, no licence from the files).

## Before a selection: eligibility

Two checks run before any rule. A claim that fails the first is not a
candidate; the second fixes which slot a candidate may fill.

- **Version match.** A record about another version of the element is not
  about this element: a dependency's installed copy or a lock hash is used
  only when its version equals the expected one.
- **Slot.** The asserter table fixes which slot a licence claim may fill
  ([asserter-licence.md](asserter-licence.md)). An `other-party` or `ai-agent` licence
  claim has no slot: it is a candidate in the record, as `passed-over`,
  and no rule compares it.

## Candidate status

| Status | Definition |
| --- | --- |
| `selected` | fills a slot that takes one value; when other candidates were passed over, the slot's rule says why |
| `coexisting` | fills the declared licence slot together with other values; no rule chose between them |
| `passed-over` | fills no slot; kept in the record only: another candidate stood, or the claim's asserter has no slot |

`passed-over` does not say the value is wrong, only that another stood.

## Grade of a conflict

The model has a grade, with two values, `compatible` and
`incompatible` (ruled 2026-11-23; "for now" since 2026-11-18). Its
key and its place in a record are ruled too (G1, below). Status and
rule say what Pitloom did with the candidates.
They do not say whether two candidates that are not equal can both be
true. SIO has a relation for each case, from a proposition to what bears on it.

| Grade | Test | SIO | Example |
| --- | --- | --- | --- |
| `compatible` | not equal; both can be true of the one element | `is disputed by` ("does not directly support") | `MIT` in the manifest, `Apache-2.0` matched from `LICENSE`: the project may be under both |
| `incompatible` | each statement, at the precision its vocabulary allows, excludes the other | `is refuted by` ("is incompatible with") | a stated byte size against a measured one; `License-Expression: GPL-3.0-only` against the classifier "GNU General Public License v3 or later (GPLv3+)" |

The grade is of a pair of candidates in one slot, for one field of one
element (a candidate set, above). Two claims about two elements are no
candidate set and have no grade: file A under `-only` and file B under
`-or-later`.

Agreement is not a grade: candidates equal after normalisation make no
conflict ("What is recorded", item 5). SIO's `is supported by` is the
relation for it.

Where it is written:

- For a field that the artefact's bytes settle (a byte size, a hash), any
  two values that are not equal are `incompatible`. The grade follows
  from the field and is not written. A parameter count is not such
  a field: it is a content fact for precedence (ruled 2026-11-23;
  [basis.md](basis.md), "Precedence for content facts"), and two counts
  by two counting rules can both be true, so no grade follows from the
  field and none is written
  ([examples/other-party.md](examples/other-party.md), PT-8).
- For a licence both grades occur, so status and rule cannot show it: two
  declared licences that are `incompatible` are both `originator`, both
  `coexisting`, with no rule between them, as two `compatible` ones are.
  There the grade is written, when Pitloom can tell; when it cannot, no
  grade is written.

The key and its place (G1) and who decides the grade for a licence pair
(G2) are ruled.

- **G1. The key is `grades`, a list on the record, one entry per pair
  that Pitloom graded** (ruled 2026-11-23). An entry names the two candidates by their
  place in `candidates` and gives the grade. A pair Pitloom cannot
  grade has no entry; a field whose grade follows from the field has
  no list.

  ```json
  "grades": [{"pair": [0, 1], "grade": "incompatible"}]
  ```

  Not taken: one `grade` for the whole record (`incompatible` when
  any pair is). It is shorter and says, with three candidates, neither
  which two exclude each other nor which pairs were not graded.
- **G2. Pitloom decides the grade of a licence pair, by the table
  below and no other** (ruled 2026-11-23). The test for `incompatible` is a closed list of
  two: each side spells out a variant and they differ; an explicit "no
  licence" against a licence. Every other pair of licences that differ
  is `compatible`. LicenseID gives the facts the test reads
  (`variant_stated`), not the grade. `compatible` says that both
  statements can be true of the one element. It does not say that the
  two licences can be combined: licence compatibility in the legal
  sense is not graded here.

For a licence the grade is `compatible` unless the test for
`incompatible` is met:

| Pair, both about one element | Grade | Why |
| --- | --- | --- |
| `GPL-3.0-only` in one statement, "or later" in another, each spelled out | `incompatible` | they part on later versions, and each says so |
| an explicit "no licence" (`NONE`) against a licence | `incompatible` | the first excludes any licence |
| `LGPL-2.1-or-later` against the classifier "LGPLv2+" (OC-1 in the examples) | `compatible` | the classifier's vocabulary cannot say 2.1: coarse, not contrary |
| the retired id `GPL-3.0` against `GPL-3.0-or-later` | no conflict (ruled 2026-11-19) | the SPDX licence list reads the retired id as "v3.0 only" and names `GPL-3.0-only` its successor; LicenseID treats that reading as an assumption (`assumed_only`, [change.md](change.md)) and, from 0.9.0, keeps the id as written with `variant_stated` false. The rule of the next row holds here too: the bare id agrees with the stated variant, and the declared slot holds one id, `GPL-3.0-or-later` |
| `GPL-3.0-or-later` in the manifest; `LICENSE` holds the bare GPL text | no conflict (ruled 2026-11-19) | the text states neither, and a variant that is not stated conflicts with neither variant. The file agrees with the manifest: one declared id, `GPL-3.0-or-later`, with the file listed as a source of it ("What is recorded", item 5). With no statement of the variant, Pitloom records LicenseID's answer, `GPL-3.0-only`, marked as a guess ([asserter-licence-points.md](asserter-licence-points.md)). Not built: today (read at dfa11c14) the manifest's id is declared and the file's reading concluded, both relationships to one licence element (`assemble/spdx3/deps_license.py:174-179`), and no mark of a guess is written (below) |
| a licence named in the manifest; a licence file whose text does not pass the gate | no conflict (ruled 2026-11-20) | the file names no id, so nothing stands against the manifest. It is to be recorded as a licence file with no id ([asserter-licence.md](asserter-licence.md), "The gate for a text match"). Not built: today such a file is not recorded at all ("Nothing changes when no candidate gives a licence", `extract/_license.py:159-176`, read at dfa11c14) |

The GPL text leaves the choice to a notice. Version 3, section 14: where
"the Program specifies" a numbered version "or any later version", the
recipient may follow that version or a later one; where it specifies no
version number, any version ever published. In the SPDX licence list
`GPL-3.0-only` and `GPL-3.0-or-later` have one text and differ by the
notice.

A conflict can be the tool's making. A matcher that names `GPL-3.0-only`
for a bare licence text sets it against a manifest's `-or-later`
(LicenseID names it, and marks it as not stated; ruled 2026-11-19:
Pitloom keeps the mark and makes no conflict of it. Not built: today
the `-only` id is written unmarked, and the mark reaches only a relayed
`INFO:` line, `variant not stated`, read at dfa11c14 in
`extract/_licenseid_relay.py:68-74`); a wrong
match sets a licence against a manifest that agrees with the file (OL-5
in the examples). The candidate's `method` and `tool` are in the record
for that reason, and LicenseID's `exact` and `score` are quoted beside
a licence text match (ruled 2026-11-20; [asserter-licence.md](asserter-licence.md),
"The gate for a text match"). The keys that carry them are a code-stage
choice.

## Rules

Closed list. The candidates for one slot that takes one value are compared
by the first rule, in this order, that tells them apart. The record names
that rule. In the declared licence slot, a manifest licence and a licence
file that differ both stand, as `coexisting` (ruled 2026-11-16). The
licence fields of one Core Metadata file are one statement, settled
by `source-order` (ruled 2026-11-23). Two sources are one statement
too where one is made from the other or their format's tool merges
them (`setup.py` and `setup.cfg`, `PKG-INFO` and an archived
`pyproject.toml`, static and installed metadata); two that the
originator writes apart both stand (`CITATION.cff` and
`codemeta.json`, a model file and its card; ruled 2026-11-23,
[asserter-licence-points.md](asserter-licence-points.md)).

| # | Rule | Definition | Sites today (examples) |
| --- | --- | --- | --- |
| 1 | `strength` | a `placeholder` gives way to a `real` or `none` value | `first_license`; setup.py `UNKNOWN` against a real setup.cfg licence; a static placeholder against installed metadata |
| 2 | `synthesized-yields` | a `synthesized` value gives way to any other claim | a fragment's description over one generated from labels; a fragment's model name over a file-name stem |
| 3 | `basis-order` | for a content fact, Pitloom's `measured` value stands over another party's ([basis.md](basis.md), precedence); the rule was `evidence-level` until 2026-11-22; the name is ruled (2026-11-23) | `record_fact`; a measured size against a stated one |
| 4 | `explicit-pin` | a version the project pinned stands over a resolved or installed one | exact pin over lock over environment |
| 5 | `source-order` | the field's documented order of sources and locations | `License-Expression` over `License` over classifier (ruled 2026-11-23: the fields of one Core Metadata file are one statement; [asserter-licence-points.md](asserter-licence-points.md)); `setup.py` over `setup.cfg`; static over installed; `PKG-INFO` over archived `pyproject.toml`; the lock file cascade; `CITATION.cff` over `codemeta.json`; base document over fragment |
| 6 | `latest` | of several releases, the newest, when none was asked for | `latest-release` |
| 7 | `running-environment` | of several files, the one compatible with the running interpreter and platform | `running-environment` |
| 8 | `default-branch` | of several branches, the one the repository names as its default, when none was asked for (ruled 2026-11-23; [source.md](source.md), rule C) | (none: the Git and Hub routes read the default branch and record nothing) |
| 9 | `tie-break` | nothing else tells them apart, and the tool's fixed order chose (the first met, then a sort by name), with no judgement of the values; the others are `passed-over` (ruled 2026-11-28) | see "Sites of rules 9 and 10", below |
| 10 | `no-rule` | nothing tells them apart; the slot is left empty and every candidate is `passed-over` | see "Sites of rules 9 and 10", below |

`source-order` needs its order written down: one table per field and
surface, tested against every reader (license-rules question 6). The rule
name says an order was used; the table says which.

`tie-break` and `no-rule` meet the same case: candidates that no
earlier rule tells apart. The first fills the slot by an order that
says nothing about which value is right; the second leaves it empty.
Which of the two a site uses is open ("Open points"). `tie-break` is
not `source-order`: a source order is the field's documented order of
sources, a tie-break an order of the tool's own (the first reference
met, a sort by file name) (ruled 2026-11-28,
[resweep-rulings.md](resweep-rulings.md), C3).

### Sites of rules 9 and 10

Read in the code at dfa11c14 (the catalogue's "did" text was not taken
as evidence). None of them writes a conflict record today: each is
work for the code stage under "What is recorded", item 1.

| Site | What is selected | Rule, as read | Loser recorded today |
| --- | --- | --- | --- |
| `dataset-conflict`: `core/dataset_merge.py:89-112` | two references of a model to one dataset that set one field to different values: the value of the reference merged first (the order of first appearance) stays | `tie-break` | no: one `WARNING:`, the other value dropped |
| `fragment-conflict`: `assemble/spdx3/_fragments_props.py:103-138`, `:186-213` | a property, or a dictionary key, set twice: the value merged first stays (the project's own element, then the fragments in merge order; `loom merge` merges its files sorted by name, `assemble/spdx3/fragments.py:348-356`) | `source-order` for the base over a fragment (rule 5); `tie-break` between two fragments of `loom merge`; configured fragments in the configured order: not decided | no: one `WARNING:` naming kept and dropped |
| `installed-metadata-ambiguous`: `extract/project/installed.py:145-150`, `:236-248` | several in-tree `.dist-info`/`.egg-info` of the project: `.dist-info` before `.egg-info`, then by marker path | `source-order` (the kind), then `tie-break` (the path) | no: one `WARNING:` listing the candidates |
| `file-discovery-conflict`: `core/_models_wheel_setuptools.py:254-282` | two source files of one wheel path: the first found stays | `tie-break` (the discovery order). A member of a file set, not a field's value | no: one `WARNING:` |
| `model-field-conflict`, ONNX: `extract/ai_model/onnx.py:173-180`, `:185-197` | a `metadata_props` key repeated: the last value stays, as protobuf keeps it | not decided: the format's own reading (`source-order` on one source) or `tie-break` | no: one `WARNING:` naming the keys |
| `lock-entry-conflict`: `extract/lock/_pins.py:147-166`, `assemble/spdx3/_document_locked_deps.py:108-121` | one package at several versions in a lock, or in the locked dependencies of a document: no pin is written (a `requirements.txt` is dropped whole) | `no-rule` | no: the versions are on the `WARNING:` line only |
| `dist-info-ambiguous`, `WARNING:` route: `core/wheel_dist_info.py:384-412`, `extract/wheel.py:254-273` | several top-level `.dist-info` that the file name does not pick: none is read; the package is named `unknown` | `no-rule` (the name is a candidate stand-in; the members are open under C7) | no |

Not a site of this list: `registry-key-ambiguous`
(`id_registry/_session.py:69-79`, `id_registry/_generate.py:87-100`,
`id_registry/_ambiguous.py:280-309`), where several things share one ID
registry key and none is used for it. That is an identifier, not a
claim for a field (this page's reading, not ruled; see "Open points").
The GGUF line of `model-field-conflict`
(`extract/ai_model/_gguf_fields.py:130-143`) is read here as a clash
of names, so no selection: the file states a scalar under the name
Pitloom gives a derived array length (`<key>.length`), and the stated
scalar is kept. Open under ruling C9
([basis.md](basis.md#precedence-for-content-facts), open points).

Rules 6, 7 and 8 choose among releases, files and branches before any
metadata is read; they are in the list because the standing claim records
them the same way.

## What is recorded

1. **A conflict is always recorded.** Two `real` or `none` values that
   differ after normalisation: every candidate, with status, and the rule
   of each slot. This closes license-rules question 5 (a model file's
   `Apache-2.0` against its card's `mit` is silent today). It binds
   `tie-break` and `no-rule` too (ruled 2026-11-28,
   [resweep-rulings.md](resweep-rulings.md), C3): the candidates that
   gave way, or that left the slot empty, are listed as `passed-over`.
   A site that drops the loser today is work for the code stage, not an
   exception: every site in "Sites of rules 9 and 10" does.
2. **A placeholder that gave way is never a conflict.** The standing claim
   carries `Rule: strength`, so the reader sees that a weaker statement
   existed; the placeholder itself is not listed.
3. **Any other selection without a conflict** is recorded by its rule on
   the standing claim when the rule is `synthesized-yields`, `explicit-pin`,
   `latest`, `running-environment` or `default-branch`. An ordinary `source-order` cascade in
   which later sources agree or are absent writes nothing.
4. **Absent sources are never candidates.**
5. **Equal after normalisation is agreement**, recorded once; the sources of
   an agreeing value may be listed. A licence claim whose variant is not
   stated (a bare GPL text, the retired id `GPL-3.0`) agrees with a
   claim that states it (ruled 2026-11-19).
6. **A conflict also warns** (`WARNING:`), with a catalogue code. Today the
   licence conflict of the main package writes an Annotation and no warning
   (read at dfa11c14: `assemble/spdx3/deps_license.py:287-317` builds the
   Annotation and says nothing).
7. **Differing declared licences are all written, and the record says they
   conflict** (ruled 2026-11-16). Pitloom may pick one, or combine them
   into one licence expression, as the concluded licence: an `sbom-tool`
   candidate in the concluded slot with `status: selected`, a `rule` and
   the rationale in `note`. For now no rule picks or combines (ruled
   2026-11-23), and the closed list above has no name for one:
   the conflict is recorded and the concluded slot stays empty
   unless the SBOM author fills it
   ([asserter-licence-points.md](asserter-licence-points.md),
   "The points").

## Record shape

The `conflict` Annotation, next version. Each candidate carries the parsed
facets, not a raw provenance string. `rule` is per slot; the example has
two `originator` claims that differ, both in the declared slot, and no
concluded licence. The second candidate writes its match as `method`,
`technique` and `tool` (ruled 2026-11-21; [asserter-licence.md](asserter-licence.md),
"The form of a text match"). The tool's version is an illustration;
`main` at dfa11c14 pins `licenseid>=0.10.0,<0.11` (`pyproject.toml:68`).

```json
{
  "schema": "https://pitloom.dev/provenance/conflict/2",
  "kind": "conflict",
  "field": "license",
  "candidates": [
    {"value": "MIT", "status": "coexisting",
     "slot": "hasDeclaredLicense", "asserter": "originator",
     "basis": "declared",
     "source": {"label": "pyproject.toml", "kind": "manifest",
                "location": "project.license"},
     "ref": "<spdxId of the MIT licence element>"},
    {"value": "Apache-2.0", "status": "coexisting",
     "slot": "hasDeclaredLicense", "asserter": "originator",
     "basis": "declared",
     "method": "matched", "technique": "license-text",
     "tool": "licenseid==0.10.0",
     "source": {"label": "LICENSE", "kind": "package-file"},
     "ref": "<spdxId of the Apache-2.0 licence element>"}
  ],
  "grades": [{"pair": [0, 1], "grade": "compatible"}]
}
```

`grades` (ruled 2026-11-23, "Grade of a conflict") has one entry per
pair of candidates that Pitloom graded, each pair named by the places
of its two candidates in the list.

A candidate's `value` is typed by the field: a dependency version conflict
holds a specifier on one side and a version on the other; a `value-type`
(`version`, `specifier`) says which, so a reader does not assume.

## Asserters in a conflict

Any mix is possible: two `originator` claims (two manifest files, or a
manifest against a licence file), `originator` against `sbom-tool` (a stated
size against a measured one), `originator` against `other-party`. No rule
compares asserters; `synthesized-yields` compares method classes.

## Reserved: stage

BSI TR-03183-2 v2.1.0 splits a licence by supply-chain position: *original*
(assigned by the creator), *distribution* (under which a licensee can use
it), *effective* (under which the SBOM's creator uses it). These are three
true values, not a conflict. Deferred (2026-11-14). Its place is a
candidate key `stage` with those three values; claims with different
stages are never compared. BSI's own mapping sends original to `hasDeclaredLicense` and
distribution to `hasConcludedLicense`, so adding the stage will need the
licence table in [asserter-licence.md](asserter-licence.md) read again.

## Mappings (loose)

| Term | Wikidata | SSSOM | BSI v2.1.0 | CycloneDX |
| --- | --- | --- | --- | --- |
| `selected` | `wikibase:PreferredRank` | - | - | `evidence.identity[].concludedValue` |
| `coexisting` | `wikibase:NormalRank` | - | - | - |
| `passed-over` | `wikibase:NormalRank` (not deprecated: the value is not called wrong) | `predicate_modifier: Not` (nearest) | - | - |
| rule | P7452 reason for preferred rank | `curation_rule` | "the referenced BOM prevails" is a `source-order` | - |

OpenVEX's closed `justification` codes are the pattern the rule list
follows: a small closed set, plus free text in `Note`.

SIO 1.62 is the one vocabulary read that grades disagreement. Its
relations are sub-properties of `has evidence` and run from a proposition
to anything that bears on it, so each row is a related match.

| Term | SIO |
| --- | --- |
| agreement | `is supported by` (`SIO_000206`) |
| `compatible` | `is disputed by` (`SIO_000207`) |
| `incompatible` | `is refuted by` (`SIO_000774`) |
| the candidates of one field | `is alternate of` (`SIO_001098`) |
| a concluded licence | `conclusion` (`SIO_000262`) |
| its rationale in `note` | `justification` (`SIO_000683`) |

SIO's `disagreement` (`SIO_000967`) is a subclass of `agreement quality`,
"the degree of consensus for some set of assertions". It is about
consensus in a group, not about two propositions, and is a loose match
for a conflict.

PROV-O, SOSA and SSN have no term for two values that disagree. PROV-O's
`prov:alternateOf` relates the candidates without grading them: two
alternate entities "present aspects of the same thing", and the aspects
"may be the same or different" ([alignment.md](alignment.md)).

ODRL 2.2 names strategies, as the rule list does, for one case: a
permission that meets a prohibition, in one policy or after a merge of
policies. Its three core values may be extended by a profile.

| Term | ODRL | Its text |
| --- | --- | --- |
| rule | `odrl:conflict` | "the conflict-resolution strategy for a Policy" |
| - | `odrl:perm` | "Permissions take preference over prohibitions" |
| - | `odrl:prohibit` | "Prohibitions take preference over permissions" |
| `no-rule` | `odrl:invalid` | "The policy is void"; the default when no strategy is set |

Two differences. ODRL's strategy is set by the author of the policy, where
Pitloom's rule is Pitloom's own and is recorded. And ODRL's conflict is
between rules about what may be done with an asset, not between claims
about which licence applies. `perm` and `prohibit` are a pattern for the
rule names of picking a concluded licence, should a rule come (none
for now, ruled 2026-11-23;
[asserter-licence-points.md](asserter-licence-points.md)), and no more.

A permission against a prohibition, on one asset and for the same action
or one that includes the other, would be a sufficient test for
`incompatible` in some pairs, were each licence written as a policy. It
is not one for `-only` against `-or-later`: a later version is not an
action.

## Open points

1. Under C3 (ruled 2026-11-28,
   [resweep-rulings.md](resweep-rulings.md)): which sites keep
   `tie-break` and which become `no-rule`. A site that moves to
   `no-rule` loses a value that is written today, so the move needs a
   sweep of output before and after. Not decided here.
2. Whether the order a format's own library applies (ONNX keeps the
   last of a repeated key) is `source-order` or `tie-break`, and
   whether configured fragments, merged in the order the configuration
   lists them, are `source-order`.
3. Whether a clash of identifiers (`registry-key-ambiguous`) is in the
   scope of the conflict rules. This page leaves it out, as an
   identifier and not a claim for a field.
