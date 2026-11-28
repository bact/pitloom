---
Created: 2026-11-28
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Asserter and the licence field: the points and their rulings

See also: [asserter-licence.md](asserter-licence.md) (the relationship
table, the gate for a text match, the form of a text match and the open
decisions; this page was its section "Licence work: the points and their
rulings" until 2026-11-28),
[asserter-licence-measurement.md](asserter-licence-measurement.md) (what
LicenseID answered, and today's detection path), [asserter.md](asserter.md),
[conflict.md](conflict.md), [change.md](change.md).

**Status:** draft, re-based 2026-11-28 on `main` dfa11c14 (release
0.25.1) with LicenseID 0.10.0, as
[asserter-licence.md](asserter-licence.md) is. Each point keeps its
ruling; **Today** marks the state of the code, read at dfa11c14 (paths
under `src/pitloom/`). "Rule n" is a rule of [asserter.md](asserter.md);
"item n" of the 2026-11-16 ruling is one of
[asserter-licence.md](asserter-licence.md#ruled-2026-11-16-a-licence-file-is-the-originators-declaration).

## The licence work and what LicenseID gives

This work was parked on 2026-11-16 and waited for LicenseID 0.9.0. It
was released on 2026-11-19 and its output was read and run that day.
Every point has a ruling since (2026-11-19 to 2026-11-23), written
under the point; one of them is a deferral (the scope of a licence
file).

What LicenseID 0.9.0 and 0.9.1 returned (2026-11-19, 2026-11-23), and
what 0.10.0 returns on the same kinds of input (run 2026-11-28), is on
[asserter-licence-measurement.md](asserter-licence-measurement.md).
Since 0.9.0, LicenseID added `same_text` (the ids that share the
answer's text), `texts` (the List texts the input holds, in file
order; an answer in a file of several stands only when its text comes
first) and, in the command's record only, `reason`; its output
documentation now gives a rule for "a caller that declares one licence
for a file" (section "Which field to read"). An Apache 2.0 text
without its appendix now ranks `Apache-2.0` first.

## The points

- A match that is not exact. LicenseID 0.9.0 has no "fuzzy" result; each
  result has `exact`, `score`, `similarity` and `coverage`. `exact` alone
  cannot be the gate, and a score cannot. Ruled 2026-11-19: a match is
  a declared licence when it is decisive ("The gate for a text match"
  of [asserter-licence.md](asserter-licence.md#the-gate-for-a-text-match-measured-2026-11-19-ruled-then-and-2026-11-20)).
  Ruled 2026-11-20: a licence file that does not pass, with no
  other statement that names a licence, is declared as a custom text;
  beside such a statement it adds no licence and no conflict. Also
  ruled that day: LicenseID's `exact` and `score` are quoted beside a
  match. **Today:** neither is quoted (grep: no `exact` or `score` in
  any provenance builder), and a file that does not pass gives nothing.
- Scope by position and name. By convention a licence file in the root
  governs the project, one in a folder governs that folder, and a name
  such as `LICENSE-DATA` likely governs the data. The first two are the
  originator's statement; the last is a reading of a name. Ruled
  2026-11-23: deferred, with no vocabulary for scope in this
  redesign. The claim records the file in `Source` and `Location`,
  nothing more. **Today:** the project route reads, at its root,
  `CITATION.cff`, `codemeta.json` and sixteen fixed licence-file names
  (`extract/_license_detect.py:33-35`, `:99-104`); the dependency route
  reads the files its `License-File` values name, else its
  `.dist-info` root files by those names
  (`assemble/spdx3/_deps_license_files.py:78-103`, #569). A
  `License-File` value may name a file in a folder (`licenses/hdf5.txt`,
  a vendored `src/.../LICENSE`; commit a918cb87), so a file below the
  root can now be read, as the package's own. **Open:** whether that
  brings the point back; not checked. Not taken: a `Scope` key now, a
  word with no writer.
- When and how Pitloom picks or combines (item 3 of the 2026-11-16
  ruling): the rule names
  and the rationale's form. Ruled 2026-11-23: for now Pitloom does
  neither, and no rule name is set. Item 3 stays ("may"), and so
  does the `sbom-tool` row of the table of
  [asserter-licence.md](asserter-licence.md#licence-relationships). The
  licence paths table there has no row that gives an `sbom-tool` concluded licence, so
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
  ([conflict.md](conflict.md)). **Today:** the pick is built, the
  record is not: the first field that states a licence is kept and a
  later one is not compared, so no difference is recorded and nothing
  is said (`extract/_core_metadata.py:227-243`, read). From the
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
- Statements that differ between sources, where one declared licence
  is kept today: `setup.py` against `setup.cfg`, static against
  installed metadata, `PKG-INFO` against an archived `pyproject.toml`,
  `CITATION.cff` against `codemeta.json`, a model file against its
  card. The ruling of 2026-11-16 was given for a manifest licence
  against a licence file. Ruled 2026-11-23, by one test: where one
  source is made from the other, or the tool that owns the format
  merges the two, they are one statement; where the originator writes
  the two apart, they are two.

  | Pair | Relation | Result (ruled) | Today (read at dfa11c14) |
  | --- | --- | --- | --- |
  | `setup.py`, `setup.cfg` | one setuptools configuration, merged by setuptools | one statement: `source-order`, one declared licence | one kept; `metadata-conflict` `WARNING:` and a conflict Annotation (`extract/project/_setuptools_options.py:393`) |
  | `PKG-INFO`, archived `pyproject.toml` | the backend writes the first from the second | one statement | not checked |
  | static, installed metadata | the installed copy relays the same metadata ([asserter.md](asserter.md), rule 2) | one statement | one kept; `metadata-conflict` `WARNING:` and a conflict Annotation (`extract/project/_installed_reconcile.py:107`) |
  | `CITATION.cff`, `codemeta.json` | two files in two vocabularies, written apart | both declared, `coexisting`, a conflict recorded | the first that gives an id is kept; the other is not read, nothing recorded (`extract/_license.py:110-114`) |
  | model file header, card | two artefacts; a converter may have written the file | both declared, `coexisting`, a conflict recorded | the local README card only fills a missing licence, nothing recorded (`enrich/readme.py:288-304`; open in known bugs); the Hub card against a model file: not checked |

  A difference inside one statement is still recorded, with a
  `WARNING:`; only the number of declared licences differs. Not
  taken: both declared for all five, which makes a second licence
  out of a stale installed copy or an old `PKG-INFO`; and one kept
  for all five, as today, which goes against the ruling of
  2026-11-16 for the last two. The order in which setuptools
  merges its two files is taken from the code and was not
  read again.
- `embed-wheel --project-dir`: a licence file of a directory that is not
  the wheel. Ruled 2026-11-23: it is the wheel's own, `originator`
  and declared through the gate, as with `loom project`. The user
  names the directory as the project the wheel was built from, and
  the Build SBOM takes its authors from there
  (`_embed_overlay.adopt_project_authors`). Not taken:
  `sbom-tool`, `detected` and no relationship, which is safe when
  the wrong directory is given and hides a real difference
  otherwise. **Today:** the licence is still concluded
  (`_embed_overlay.py:71-88`). Since 0.25.0 a directory that names
  another project than the wheel (by PEP 503 name) gets
  `metadata-conflict` and its authors are not used (the catalogue
  entry, `messages/_metadata_dynamic.py:184-207`; emitted at
  `_embed_overlay.py:122`, grep); its licence is read all the same.
  Whether the version is compared: not checked (hazard 15 of
  [renames-and-migration.md](renames-and-migration.md)).
- The `matched` exception ([asserter.md](asserter.md), under the
  default asserter table) or a `Change` step. A `Change` step
  needs a further step kind: none of the five in [change.md](change.md) is
  a text matched to an id. Ruled 2026-11-21: the `matched` exception
  ("The form of a text match" of
  [asserter-licence.md](asserter-licence.md#the-form-of-a-text-match-ruled-2026-11-21-form-a)).
  (Ruling C5 of 2026-11-28 adds
  a fifth kind, `escaped`, for another purpose; it does not reopen
  this.)
- Statements that cannot both be true: `GPL-3.0-only` against "or
  later", each spelled out, about one element (grade `incompatible`;
  [conflict.md](conflict.md), "Grade of a conflict"). Both are the
  originator's and both are declared; Pitloom concludes neither
  reading, as for any pair (the point "When and how Pitloom picks or combines" above, ruled
  2026-11-23).
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
  make a conflict the originator did not. LicenseID (0.9.0 to 0.10.0)
  names `-only` first for the bare text and says it is a guess
  (`variant_stated` false; since 0.9.2 `same_text` names the
  `-or-later` twin). Ruled 2026-11-19: Pitloom records that answer
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
  word is a code-stage choice. **Today:** with nothing stated, Pitloom
  writes the `-only` id with no mark (the family rule treats the two
  as one, `_license_text_match.py:196-199`); only the relayed `INFO:
  licenseid: input: variant not stated: ...` says it, once per text.
  With a stated variant the stated id wins the tie (`:173-193`), but
  for the project it is written as a concluded licence beside the
  declared one, both to one element, not as one declared id. To
  reconcile: the design page `licence-variant-evidence.md` on `main`
  (option G, ruled "for now" on the same day, in other work) writes
  the bare text as the retired id `GPL-3.0`, never as `-only`. The two
  rulings differ for a bare text with no other statement.
- An entry in [sbom-format-gaps.md](../sbom-format-gaps.md) for the
  missing scope of a licence relationship, with the code change.

