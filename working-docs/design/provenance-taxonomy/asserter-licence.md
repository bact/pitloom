---
Created: 2026-11-23
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Asserter and the licence field

See also: [asserter.md](asserter.md) (the facet: values, rules 1 to 8,
the default asserter and the field table; this page was part of it until
2026-11-23), [conflict.md](conflict.md), [change.md](change.md),
[basis.md](basis.md), [README.md](README.md) (the claim model).

**Status:** draft. What the asserter decides for a licence: the
relationship, the licence file as the originator's declaration, the gate
and the form of a text match, and the licence points that were parked,
each with its ruling. "Rule
n" here is a rule of [asserter.md](asserter.md).

## Licence relationships

One table for one value and for several (closes license-rules questions 13
and 14; replaces `is_license_concluded` and `THIRD_PARTY_SOURCES`).

| Asserter | Relationship | Note |
| --- | --- | --- |
| `originator` | `hasDeclaredLicense` | includes PyPI and a version-matched installed copy (ruled 2026-11-14: a change from today's `hasConcludedLicense`) |
| `sbom-tool` | `hasConcludedLicense` | Pitloom is the SBOM creator's tool, named in `CreationInfo` (agreed 2026-11-14). Only for a value Pitloom picked from, or combined out of, what the originator stated, with the rationale recorded (ruled 2026-11-16). No rule picks or combines yet (ruled 2026-11-23), so Pitloom alone writes no `hasConcludedLicense`. A match on a text that is not the element's own (a `linked-document`, also one the originator's `license_link` names) is `sbom-tool`, `detected`, and makes no relationship (ruled 2026-11-23): it is recorded as a provenance entry, as the `other-party` row is. The originator's declaration stays what the card states. The text is another party's file and can change after the card was written, and no state of a URL is pinned; ST-1 of the examples matched a vendor's own licence to `APSL-1.0` at 0.6754. To look at again when Pitloom fetches a linked text and records its digest |
| `sbom-author` | `hasConcludedLicense` | includes a library caller's `license_concluded` |
| `other-party` | no relationship | ruled 2026-11-14; recorded as a provenance entry for `license` on the element, value in `Value`, and as a candidate when there is a conflict |
| `ai-agent` | no relationship | recorded the same way, until the SBOM author confirms it (then `sbom-author`, with the agent kept: rule 8) |

### Licence paths, today and new

| Path today | Claim | New asserter | New result | Changes? |
| --- | --- | --- | --- | --- |
| manifest licence, an id or expression | read | `originator` | declared | no |
| manifest licence as a name, classifier or URL, read as its one id | read, with a change | `originator` | declared | no |
| manifest licence as a text (`project.license.text`, `file`), matched to an id | matched | `originator` | declared | no |
| `CITATION.cff` or `codemeta.json` licence | read | `originator` | declared; when it differs from the manifest's, both are declared and a conflict is recorded | yes: today it is the concluded second opinion |
| `LICENSE` text matched, manifest states a licence | matched | `originator` | declared; equal to the manifest's: one declared licence; different: both declared and a conflict recorded | yes: today concluded |
| `LICENSE` text matched, manifest silent | matched | `originator` | declared | no |
| `embed-wheel --project-dir`: the directory's match beside the wheel's licence | matched | `originator` (ruled 2026-11-23: the directory is the wheel's project, by the user's word) | declared; when it differs from the wheel's, both are declared and a conflict is recorded | yes: today concluded |
| dependency licence from PyPI or its installed copy | read | `originator` | declared | yes: today concluded |
| Hub card licence | read | `originator` | declared | no |
| Hub repository licence file matched | matched | `originator` | declared | no |
| a file's `SPDX-License-Identifier` tag | read | `originator` | declared | no |
| library `license_concluded=` | - | `sbom-author` | concluded | no |
| library `license_name=`, SDK `declared_license=` | - | `originator` (ruled 2026-11-23: [asserter.md](asserter.md), the argument table) | declared | no |
| a value with no source at all | - | none | a bug at the reader; not emitted as concluded | yes: today concluded |

Five rows of this table change today's result. Two pairs of sources
ruled below add to them (`CITATION.cff` against `codemeta.json`, a
model file against its card): today one declared licence is kept,
and both will be declared. The code stage runs a probe corpus through
HEAD and the tree and lists every relationship that moves.

## Ruled 2026-11-16: a licence file is the originator's declaration

1. A licence file in a project is the originator's statement that the licence
   applies, so its matched id is a declared licence. This agrees with SPDX
   3.0.1, which defines `hasDeclaredLicense` as: the artefact "was
   discovered to actually contain" the licence, "for example as detected by
   use of automated tooling"; with PEP 639 `License-File`, by which a
   project lists its licence files; and with BSI TR-03183-2 v2.1.0, which
   maps its "original licence" to `hasDeclaredLicense`.
2. When the originator's statements differ (a manifest licence and a licence
   file, or two files), every one is recorded as a declared licence and
   the Annotation says they conflict ([conflict.md](conflict.md)).
3. Pitloom may then pick one of them, or combine them into one licence
   expression, and record that as the concluded licence, with its
   rationale. That claim is `sbom-tool`'s.

## Notes 2026-11-28: declared, concluded and the SBOM creator (#570)

Notes from #569 and the user's question "the owner creates the SBOM, so
can we say concluded too?". Not ruled; input for #570 and the project
licence-file follow-up in [roadmap.md](../roadmap.md).

1. **Declared is the originator's statement.** A project's
   `project.license`, its own licence files, a dependency's Core Metadata,
   PyPI record and installed licence files: `originator`,
   `hasDeclaredLicense` (#569 for dependencies; the project's licence-file
   detection is still concluded, the follow-up).
2. **Concluded needs an asserter who concludes:** `sbom-tool` (Pitloom
   picks or combines, with a rationale; no rule yet, so none) or
   `sbom-author` (the person or organisation operating Pitloom states it).
   A LicenseID match is a reading of the originator's file, not a
   conclusion.
3. **One person can be originator and SBOM author.** An owner building
   their own project's SBOM may also conclude its licence, and both
   relationships are valid SPDX 3, to one element when equal. Pitloom
   cannot infer it: `loom project <git URL>` builds a stranger's project,
   and running Pitloom states nothing. `project.license` stays the
   originator's even when the owner wrote it (pointer rule 4 of
   [asserter.md](asserter.md): a value in X belongs to X's owner).
4. **The statement is explicit: #570.** A creator-supplied value (a
   `[tool.pitloom]` key or a data file beside the creation info) is
   `sbom-author`, so `hasConcludedLicense`, with the declared licence kept
   beside it. The library's `license_concluded=` is the same today. It
   serves the project ("I conclude MIT") and a dependency (rfc8785's
   Apache 2.0 text near-ties `Pixar`, so no declared id is read; the creator
   concludes `Apache-2.0`).
5. **Consequence for the project follow-up.** Once the licence-file
   detection is declared, a project SBOM has no `hasConcludedLicense`
   unless the creator states one (#570). FSCT COMP-007, mapped to concluded
   only, then reports the main package missing too (FG-17 in
   [sbom-format-gaps.md](../sbom-format-gaps.md)).

## Licence work: the points and their rulings

This work was parked on 2026-11-16 and waited for LicenseID 0.9.0. It
was released on 2026-11-19 and its output was read and run that day
(below). Every point has a ruling since (2026-11-19 to 2026-11-23),
written under the point; one of them is a deferral (the scope of a
licence file).

What LicenseID 0.9.0 returns (`detect`, SPDX License List 3.29.0 as
packaged; the first result, and the second where it ties):

| Input | `expression` | `method` | `exact` | `score` | `variant_stated` |
| --- | --- | --- | --- | --- | --- |
| the GPL version 3 text, bare | `GPL-3.0-only`, then `GPL-3.0-or-later` | `text` | false | 1.0, 1.0 | false |
| the id `GPL-3.0` | `GPL-3.0`, kept as written | `id` | true | 1.0 | false |
| `GPL-3.0 or later` | `GPL-3.0-or-later` | `id` | true | 1.0 | true |
| `GPLv3+` | `GPL-3.0-or-later` | `id` | false | 1.0 | true |
| `Apache License, Version 2.0` | `Apache-2.0` | `name` | false | 1.0 | none |
| an Apache 2.0 text, its copyright line filled in | `Apache-2.0` | `text` | false | 1.0 | none |
| OL-5 of the examples: an Apache 2.0 text without its appendix | `Pixar`, then `Apache-2.0` | `text` | false | 0.9947, 0.9937 | none |

- `variant_stated` is new: whether the input says which of `-only` and
  `-or-later` is meant. For the bare GPL text it is false, with
  `WARNING: input: variant not stated: GPL-3.0; using GPL-3.0-only`;
  `--variant as-written` gave the same answer for the text.
- `exact` is narrower than in 0.8.4: now false for a value a rewrite
  rule read (`Apache License, Version 2.0`). For a text it is false, as
  in 0.8.4, when a copyright line is filled in: nearly every real
  licence file is not exact.
- A wrong match is unchanged: OL-5 gives the same ids and scores as in
  0.8.4.
- LicenseID 0.9.1 (run 2026-11-23, same list 3.29.0) gives the same
  output as 0.9.0 on what was tried: `resolve` of twelve values (the
  ids and names of the table, two licence URLs, a classifier) and
  `detect` of five files (a bare GPL version 3 text, an Apache 2.0
  text with and without its appendix, a 13-line Apache notice, an
  LGPL version 3 text). The category and `trust` tables of
  `licenseid.resolvertypes` are equal in the two releases. The 197
  files of the gate's measurement were not run again.

The points:

- A match that is not exact. LicenseID 0.9.0 has no "fuzzy" result; each
  result has `exact`, `score`, `similarity` and `coverage`. `exact` alone
  cannot be the gate, and a score cannot. Ruled 2026-11-19: a match is
  a declared licence when it is decisive ("The gate for a text match"
  below). Ruled 2026-11-20: a licence file that does not pass, with no
  other statement that names a licence, is declared as a custom text;
  beside such a statement it adds no licence and no conflict. Also
  ruled that day: LicenseID's `exact` and `score` are quoted beside a
  match.
- Scope by position and name. By convention a licence file in the root
  governs the project, one in a folder governs that folder, and a name
  such as `LICENSE-DATA` likely governs the data. The first two are the
  originator's statement; the last is a reading of a name. Ruled
  2026-11-23: deferred, with no vocabulary for scope in this
  redesign. The claim records the file in `Source` and `Location`,
  nothing more. No route gives an input today: the project route
  reads root-level files of sixteen fixed names
  (`extract/_license_detect.pick_license_names`, base 257b7260),
  and the dependency route the files that `License-File` lists.
  The point comes back with the first reader that walks folders.
  Not taken: a `Scope` key now, a word with no writer.
- When and how Pitloom picks or combines (item 3 above): the rule names
  and the rationale's form. Ruled 2026-11-23: for now Pitloom does
  neither, and no rule name is set. Item 3 stays ("may"), and so
  does the `sbom-tool` row of the table above. The licence paths
  table has no row that gives an `sbom-tool` concluded licence, so
  a rule would have no writer; a conjunction of all declared
  licences was looked at and not taken: `AND` and `OR` are both
  valid operators of a licence expression, and separate
  statements do not say which holds between them, so Pitloom
  does not choose. A rule comes later with its name, its definition
  and a first real input. Until then the conflict is recorded and
  the concluded licence is left to the SBOM author.
- Several licence classifiers in one source (found by the sweep
  against `main`, 2026-11-23). Today they are one declared
  expression joined by `AND`, with a `WARNING:` that says `AND` is
  assumed (`license-ambiguous`). Ruled 2026-11-23: it stays, and
  the claim marks the operator as Pitloom's choice. A list of
  classifiers is one statement and carries no operator; `AND`
  and `OR` are both valid for it. The claim is `originator`,
  `declared`, with `Change: expanded` and the classifiers in
  `Written` ([change.md](change.md)); the warning stays. This is
  the bare GPL text again: the tool's reading is recorded and
  marked as its own (ruled 2026-11-19). Not taken: one declared
  licence per classifier, which changes every surface and leaves
  the same question to the reader of several relationships.
- Statements that differ inside one source (`License-Expression`, `License`
  and a classifier of one Core Metadata file): the same statement spelled
  three ways, or three statements. Ruled 2026-11-23: one statement.
  The format orders its own fields, so `source-order` picks
  (`License-Expression`, then `License`, then the classifier), one
  declared licence is written, and the others are `passed-over`.
  A difference is still recorded, with its grade and a `WARNING:`
  ([conflict.md](conflict.md)). This is today's result. From the
  Core Metadata specification (its source at packaging.python.org,
  read 2026-11-23): since version 2.4 `License` and
  `License-Expression` are mutually exclusive, and a tool that
  reads both disregards `License`; `License` is for a licence
  that is not among the classifiers, or to give the version or a
  variation of one a classifier names; the `License ::`
  classifiers are deprecated since 2.4 for `License-Expression`.
  The specification has no rule for a `License-Expression` beside
  a classifier: the order there is Pitloom's reading. Not taken:
  three declared licences, which would write `License` as a
  licence where the specification says to disregard it. The
  ruling of 2026-11-16 was for two sources and does not reach the
  fields of one.
- Statements that differ between sources where today one declared licence
  is kept and the other is recorded as a conflict: `setup.py` against
  `setup.cfg`, static against installed metadata, `PKG-INFO` against an
  archived `pyproject.toml`, `CITATION.cff` against `codemeta.json`, a
  model file against its card. The ruling of 2026-11-16 was given for a
  manifest licence against a licence file. Ruled 2026-11-23, by one
  test: where one source is made from the other, or the tool that
  owns the format merges the two, they are one statement; where the
  originator writes the two apart, they are two.

  | Pair | Relation | Result |
  | --- | --- | --- |
  | `setup.py`, `setup.cfg` | one setuptools configuration, merged by setuptools | one statement: `source-order`, one declared licence |
  | `PKG-INFO`, archived `pyproject.toml` | the backend writes the first from the second | one statement |
  | static, installed metadata | the installed copy relays the same metadata ([asserter.md](asserter.md), rule 2) | one statement |
  | `CITATION.cff`, `codemeta.json` | two files in two vocabularies, written apart | both declared, `coexisting`, a conflict recorded |
  | model file header, card | two artefacts; a converter may have written the file | both declared, `coexisting`, a conflict recorded |

  A difference inside one statement is still recorded, with a
  `WARNING:`; only the number of declared licences differs. Not
  taken: both declared for all five, which makes a second licence
  out of a stale installed copy or an old `PKG-INFO`; and one kept
  for all five, as today, which goes against the ruling of
  2026-11-16 for the last two. The order in which setuptools
  merges its two files is taken from today's code and was not
  read again.
- `embed-wheel --project-dir`: a licence file of a directory that is not
  the wheel. Ruled 2026-11-23: it is the wheel's own, `originator`
  and declared through the gate, as with `loom project`. The user
  names the directory as the project the wheel was built from, and
  the Build SBOM takes its authors from there today
  (`_embed_overlay.adopt_project_authors`). Not taken:
  `sbom-tool`, `detected` and no relationship, which is safe when
  the wrong directory is given and hides a real difference
  otherwise. Nothing compares the directory's name and version
  with the wheel's (base 257b7260): a check for the code stage
  ([renames-and-migration.md](renames-and-migration.md), hazard
  15).
- The `matched` exception ([asserter.md](asserter.md), under the
  default asserter table) or a `Change` step. A `Change` step
  needs a fifth step kind: none of the four in [change.md](change.md) is
  a text matched to an id. Ruled 2026-11-21: the `matched` exception
  ("The form of a text match" below).
- Statements that cannot both be true: `GPL-3.0-only` against "or
  later", each spelled out, about one element (grade `incompatible`;
  [conflict.md](conflict.md), "Grade of a conflict"). Both are the
  originator's and both are declared; Pitloom concludes neither
  reading, as for any pair (the point above, ruled 2026-11-23).
  Both statements grant version 3; they
  part on later versions only. ODRL 2.2 names strategies for a like
  choice, a permission against a prohibition in one policy or after a
  merge: `perm`, `prohibit`, `invalid` (the policy is void; the default).
  A pattern for rule names, should a rule come: a licence id is not
  an ODRL policy.
- A limit of rule 5 ("only names what was stated"): a GPL-family licence
  text states neither `-only` nor `-or-later`. The two ids share one
  text, and the choice is made by a notice in a source file or in the
  manifest. A matcher that names one of the two for a bare text would
  make a conflict the originator did not. LicenseID 0.9.0 names `-only`
  first for the bare text and says it is a guess (`variant_stated`
  false, above). Ruled 2026-11-19: Pitloom records that answer
  (`GPL-3.0-only`) and marks it as a guess; a claim whose variant is not
  stated makes no conflict with either variant
  ([conflict.md](conflict.md)). Also ruled 2026-11-19: where another
  statement about the same element states the variant (a manifest's
  `GPL-3.0-or-later`), the file's claim adds no second licence id. It
  is recorded as agreeing with the stated variant, so the declared slot
  holds one id. The guess is recorded only where no statement states
  the variant. The same holds for the retired id `GPL-3.0` beside a
  stated variant (ruled 2026-11-19); alone it stays as written, with
  `Superseded` ([change.md](change.md)). The mark of the guess is the
  step kind `expanded` in `Change`, with LicenseID's `variant_stated`
  quoted beside it (ruled 2026-11-19); the key that carries the quoted
  word is a code-stage choice. To reconcile: the design page
  `licence-variant-evidence.md` on `main` (option G, ruled "for now" on
  the same day, in other work) writes the bare text as the retired id
  `GPL-3.0`, never as `-only`. The two rulings differ for a bare text
  with no other statement.
- An entry in [sbom-format-gaps.md](../sbom-format-gaps.md) for the
  missing scope of a licence relationship, with the code change.

### The gate for a text match (measured 2026-11-19; ruled then and 2026-11-20)

Measured: `detect()` of LicenseID 0.9.0 on the licence files of the 166
distributions installed in the repository's environment, and Pitloom's
rule of today on the same files (the code at 257b7260, run with 0.9.0).
The files were picked by name (`LICEN*`, `COPYING*`) in each metadata
folder: 198, of which one is not a licence file (LicenseID's own SBOM,
by its name) and is left out, so 197. Today's rule reads the text as
written and without its copyright notice lines, and takes the better
reading. It names the top
id when the score is 0.85 or more and no other licence family is within
0.01 of it, unless that one fits the text worse (`similarity`,
`coverage`). A licence the manifest states wins a near tie; none was
given here.

| LicenseID's first result | Files | Today's rule names an id | Of which not LicenseID's first id |
| --- | --- | --- | --- |
| `exact` true | 20 | 18 | 0 |
| score 1, not exact | 108 | 108 | 0 |
| score 0.85 to 1 | 43 | 39 | 10 |
| score under 0.85 | 26 | 11 | 11 |

- `exact` is too narrow to be the gate: 20 files, each `Apache-2.0` or
  `MPL-2.0`. A filled-in copyright line makes a text not exact, so no
  MIT, BSD or ISC file is exact.
- `exact` is not one id either. The two MPL files are exact for
  `MPL-2.0` and for `MPL-2.0-no-copyleft-exception`: one text, two ids,
  and no field says so (`variant_stated` is for `-only` and
  `-or-later`). Today's rule calls it a tie and names none.
- `score` is not the gate. It is a ranking key: 1.0 for a 13-line Apache
  notice (`coverage` 0.06), 0.92 for a file with `similarity` 0.47.
  `Pixar` at 0.9963 is wrong and `MIT` at 0.9304 is right.
- The second reading does much of the work. In 21 files it names another
  id than LicenseID's first (`MIT-advertising`, `FSL-1.1-MIT`, `Xnet`,
  `X11-swapped` to `MIT`). The head of five was read (attrs, pytest,
  pydantic, MkDocs, Pygments): each begins as the licence the second
  reading names.
- Wrong today, nine files: an Apache 2.0 text without its appendix gives
  `Pixar` (six read: none has the appendix, and section 6 is Apache's).
  The SPDX License List template of `Apache-2.0` (3.29.0) marks the
  appendix as optional text; `Pixar` differs in section 6. A matcher
  that read the template's marks would name `Apache-2.0`.
- One id for a file that holds several, four read: mypy (the MIT text,
  then the Python licences, gives `Python-2.0.1`), NumPy (its own BSD
  text and a list of bundled licences, gives `LGPL-2.1-or-later`),
  python-dateutil (an Apache notice, then a BSD text that "applies to
  all code", gives `Apache-2.0`), PyMdown
  Extensions (MIT and third-party parts, gives `MIT`).
- Not a licence text: a notice (CacheControl's 13 lines name Apache 2.0
  and score 1.0) and a pointer (packaging's `LICENSE` names two other
  files; no id, rightly).

Item 1 is ruled (2026-11-19), and item 4 follows from it. Items 2 and 3
are ruled (2026-11-20).

1. **The gate is "decisive", not a field.** A text match is a declared
   licence id when one licence family is the answer of the better
   reading: it is `exact`, or it passes today's rule. `exact` passes at
   once; where two ids share the exact text, LicenseID's order names
   the id. The numbers (0.85, 0.01) and the second reading belong to
   the code, not to the taxonomy.
2. **Every text match says how good it was.** The claim quotes
   LicenseID's `exact` and `score` beside the match, as
   `variant_stated` is quoted (ruled 2026-11-20). Which keys record
   the match itself is the form, below. A reader who wants exact
   matches only can filter. `score` is quoted as LicenseID's ranking key, not as a
   measure of fit (the findings above). The keys that carry the two
   are a code-stage choice, as for `variant_stated`. A file that does
   not pass quotes no result in the SBOM (ruled 2026-11-23): the SBOM
   holds claims, not candidates the gate refused, and LicenseID's
   first result under 0.85 was the id today's rule named in none of
   26 files. The run says it instead, in a log message that gives the
   file, that the gate did not pass, and the nearest id and score; its
   level and wording are message-catalogue work of the code stage.
3. **A match that does not pass names no id.** Ruled 2026-11-20: where
   no other statement names a licence, the text of the file is declared
   as a custom licence (`LicenseRef-loom-text-...`), as an unmatched
   manifest text is today. Today such a file gives nothing. The gate
   cannot tell a custom licence from a file that is not a licence text
   (a pointer, a notice): alone, that one is declared the same way.
   Also ruled 2026-11-20: beside a statement that names a licence, the
   file adds no second licence and no conflict; it is recorded as a
   licence file with no id. All 19 files of the measurement that do not
   pass are of this second kind (each distribution has a licence in its
   Core Metadata): none of the 197 becomes a custom text. A passing
   match of another licence file of the same element is such a
   statement too (ruled 2026-11-23): a pointer file beside two licence
   files that pass (`LICENSE`, `LICENSE.APACHE` and `LICENSE.BSD` of
   `packaging`) adds no third licence. The cost is the same as beside
   a manifest: a real custom licence beside a file that passes is
   recorded as a licence file with no id.
4. **The two wrong classes are the matcher's, not the gate's**: optional
   text of the list's templates, and more than one licence text in a
   file. Both go to LicenseID. Until then an Apache 2.0 text without
   appendix, with no stated licence, is declared as `Pixar`.

Not chosen for item 1: `exact` only (one file in ten gets an id; every
MIT file becomes a custom text); a score floor alone (no floor parts
`Pixar` from `MIT`). Not chosen for item 3: the nearest id with a mark
(often a wrong id in the declared slot: of the 26 first results under
0.85, the second reading replaces 11 and names none for 15); nothing at
all, as today (an element with a licence file and no declared licence).

### The form of a text match (ruled 2026-11-21: form A)

A match that passes the gate is the originator's declared licence. Two
ways to write the match down, here for tomli 2.5.0 (`licenses/LICENSE`;
LicenseID 0.9.0: `MIT`, `exact` false, `score` 1.0; the metadata states
`MIT`). The quoted `exact` and `score` are left out: their keys are not
named yet.

```text
A  Asserter: originator | Method: matched | Technique: license-text | Tool: licenseid==0.9.0 | Basis: declared
B  Asserter: originator | Written: (the text, by its hash) | Change: (a fifth step kind) | Tool: licenseid==0.9.0 | Basis: declared
```

| Question | A: the `matched` exception | B: a `Change` step |
| --- | --- | --- |
| What the claim says Pitloom did | `Method: matched`, as the first question of [method.md](method.md) says | `read`, not written; the match is in `Change` |
| Exception needed | one: `matched` on the element's own licence text keeps `originator` and `declared` | one: the first question of method.md does not hold for the element's own licence text |
| New vocabulary | none | a fifth step kind in a closed list; a form of `Written` for a text |
| The same match on a text that is not the element's own (a `linked-document`; the example was `embed-wheel --project-dir` until that was ruled the wheel's own, 2026-11-23) | `Method: matched` too; the asserter differs | `Method: matched` there, `Change` here: one act, two spellings |
| To find every value a matcher named | `Method: matched` | `Method: matched`, and the fifth kind in `Change` |
| Against today's `Method: licenseid_detection` | a rename | a new shape |
| Beside a licence name, classifier or URL read as an id (`Change: respelled`) | differs | alike: `Written` and `Change` |

Either form must know whether the text is the element's own: A to keep
the asserter, B to choose `Change` over `Method`. B saves no decision.

No facet says a false thing in A. `Basis` is how the asserter came
to the value: the originator said so by placing the file, `declared`.
`Method` is what Pitloom did to the source: `matched`. The objection in
[basis.md](basis.md) (open point 2) is to `Basis: detected` on
this claim, which A does not write.

What weighed against A in the examples was a weak match read as the
originator's word (OL-3, 0.641). The gate takes that away: a match that
does not pass names no id. (OL-3 as written is under the floor of 0.85;
its second reading was not run.) A wrong match that passes (`Pixar`) is
wrong in both forms.

Ruled 2026-11-21: form A. With it:

1. `Basis` on the claim is `declared`, the originator's default
   (written, as every basis is: ruled 2026-11-23). `detected` is for a
   match Pitloom asserts itself (a text
   that is not the element's own).
2. A matched claim may carry a `Change` step (`expanded`, for a variant
   LicenseID chose; ruled 2026-11-19). It has no `Written` (ruled
   2026-11-23; [change.md](change.md), "Keys"), since the source wrote
   a text, which `Source` and `Location` name.
3. The exception stays as it is written in
   [asserter.md](asserter.md); open point 2 of
   basis.md and the `matched` row of method.md are closed.

## Mappings (loose)

Added 2026-11-23. Pitloom writes SPDX; the CycloneDX column says where
each asserter would land, and promises no CycloneDX output. The terms
are those of CycloneDX 1.7
([vocabularies-considered-sbom.md](vocabularies-considered-sbom.md),
"CycloneDX evidence").

| Asserter | SPDX 3 (the table above) | CycloneDX 1.7 |
| --- | --- | --- |
| `originator` | `hasDeclaredLicense` | a licence with `acknowledgement` `declared` |
| `sbom-tool`, `sbom-author` | `hasConcludedLicense` | a licence with `acknowledgement` `concluded` |
| `other-party`, `ai-agent` | no relationship; a provenance entry | `evidence.licenses` (nearest: an observed licence, neither declared nor concluded) |

The third row is a gap of SPDX 3: it has no place for a licence that
someone observed and that is neither declared nor concluded, so
Pitloom keeps it in provenance. It gets an entry in
[sbom-format-gaps.md](../sbom-format-gaps.md) with the code
([renames-and-migration.md](renames-and-migration.md), "Format gaps
ledger").
