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
[basis.md](basis.md), [README.md](README.md) (the claim model),
[asserter-licence-measurement.md](asserter-licence-measurement.md) (what
LicenseID answered: 0.9.0 on 2026-11-19, 0.10.0 on 2026-11-28; today's
detection path), [asserter-licence-points.md](asserter-licence-points.md)
(the licence points and their rulings),
[resweep-rulings.md](resweep-rulings.md) (C6), [reason.md](reason.md).

**Status:** draft. What the asserter decides for a licence: the
relationship, the licence file as the originator's declaration, the gate
and the form of a text match, and the licence points that were parked,
each with its ruling. "Rule
n" here is a rule of [asserter.md](asserter.md).

**What "today" means on this page** (re-based 2026-11-28): the code at
`main` dfa11c14 (release 0.25.1) with LicenseID 0.10.0, the release its
pin `licenseid>=0.10.0,<0.11` takes (`pyproject.toml:68`). Each
statement is marked **ruled** (a design decision, not changed by the
re-base), **today** (the code), or **open**. Evidence: "read" (file and
line at dfa11c14, paths under `src/pitloom/`), "run" (what, when, which
version), "not checked". A LicenseID match is tool output, not the truth
about a licence file.

## Licence relationships

**Ruled.** One table for one value and for several (closes license-rules
questions 13 and 14; replaces `is_license_concluded` and
`THIRD_PARTY_SOURCES`).

| Asserter | Relationship | Note |
| --- | --- | --- |
| `originator` | `hasDeclaredLicense` | includes PyPI and a version-matched installed copy (ruled 2026-11-14: a change from the `hasConcludedLicense` of that day; built for dependencies in #569) |
| `sbom-tool` | `hasConcludedLicense` | Pitloom is the SBOM creator's tool, named in `CreationInfo` (agreed 2026-11-14). Only for a value Pitloom picked from, or combined out of, what the originator stated, with the rationale recorded (ruled 2026-11-16). No rule picks or combines yet (ruled 2026-11-23), so Pitloom alone writes no `hasConcludedLicense`. A match on a text that is not the element's own (a `linked-document`, also one the originator's `license_link` names) is `sbom-tool`, `detected`, and makes no relationship (ruled 2026-11-23): it is recorded as a provenance entry, as the `other-party` row is. The originator's declaration stays what the card states. The text is another party's file and can change after the card was written, and no state of a URL is pinned; ST-1 of the examples matched a vendor's own licence to `APSL-1.0` at 0.6754. To look at again when Pitloom fetches a linked text and records its digest |
| `sbom-author` | `hasConcludedLicense` | includes a library caller's `license_concluded` |
| `other-party` | no relationship | ruled 2026-11-14; recorded as a provenance entry for `license` on the element, value in `Value`, and as a candidate when there is a conflict |
| `ai-agent` | no relationship | recorded the same way, until the SBOM author confirms it (then `sbom-author`, with the agent kept: rule 8) |

**Today**, against the `sbom-tool` row: Pitloom on its own still writes
`hasConcludedLicense` (read):

- a project's licence file matched beside a licence its manifest states
  (the "second opinion"): `extract/_license.py:173-175`, then the
  two-candidate mode of `assemble/spdx3/deps_license.py:247-319`, on
  every project route (CLI, Hatchling hook, sdist, setuptools, Poetry);
  pinned by `test_an_sdist_concludes_its_own_licence`
  (`tests/assemble/test_license_detection_corpus.py`);
- `embed-wheel --project-dir`: `_embed_overlay.py:71-88`;
- a value whose provenance has no `Source:` segment
  (`assemble/spdx3/_provenance_encoders.py:70-79`, used at
  `deps_license.py:216`): reached only from library input (PIT-9).

A fragment's own `hasConcludedLicense` passes `loom merge` unchanged; the
merge decides no relationship type (read in part:
`_fragments_licenses.py`, `_fragments_license_ranges.py`). The skill's
example has an AI agent write one
(`skills/sbom-enrich/references/examples.md:128-147`), where the
`ai-agent` row says no relationship.

### Licence paths, today and new

| Path today | Claim | New asserter | New result | Changes? |
| --- | --- | --- | --- | --- |
| manifest licence, an id or expression | read | `originator` | declared | no |
| manifest licence as a name, classifier or URL, read as its one id | read, with a change | `originator` | declared | no |
| manifest licence as a text (`project.license.text`, `file`), matched to an id | matched | `originator` | declared | no |
| `CITATION.cff` or `codemeta.json` licence | read | `originator` | declared; when it differs from the manifest's, both are declared and a conflict is recorded | yes: today concluded when the manifest states a licence, declared when it is silent; the first of the project's licence sources that gives an id ends the search, so the others are not compared (`extract/_license.py:100-122`, `:168-178`) |
| `LICENSE` text matched, manifest states a licence | matched | `originator` | declared; equal to the manifest's: one declared licence; different: both declared and a conflict recorded | yes: today concluded, with a conflict Annotation when different |
| `LICENSE` text matched, manifest silent | matched | `originator` | declared | no |
| `embed-wheel --project-dir`: the directory's match beside the wheel's licence | matched | `originator` (ruled 2026-11-23: the directory is the wheel's project, by the user's word) | declared; when it differs from the wheel's, both are declared and a conflict is recorded | yes: today concluded |
| dependency licence from PyPI or its installed copy | read | `originator` | declared | done in #569 (bdf35a29, 2026-11-28): declared, from Core Metadata, PyPI or the installed licence files |
| Hub card licence | read | `originator` | declared | no |
| Hub repository licence file matched | matched | `originator` | declared | no |
| a file's `SPDX-License-Identifier` tag | read | `originator` | declared | no |
| library `license_concluded=` | - | `sbom-author` | concluded | no |
| library `license_name=`, SDK `declared_license=` | - | `originator` (ruled 2026-11-23: [asserter.md](asserter.md), the argument table) | declared | no |
| a value with no source at all | - | none | a bug at the reader; not emitted as concluded | yes: today concluded |

Four rows of this table still change today's result; the fifth, the
dependency row, was built in #569. Two pairs of sources ruled on
[asserter-licence-points.md](asserter-licence-points.md) add
to them (`CITATION.cff` against `codemeta.json`, a model file against
its card): today the second of each pair is not compared at all, and
both will be declared. The code stage runs a probe corpus through HEAD
and the tree and lists every relationship that moves.

### Today's detection path (dfa11c14, LicenseID 0.10.0)

In full, step by step and route by route, with file and line, on
[asserter-licence-measurement.md](asserter-licence-measurement.md#todays-detection-path-dfa11c14-licenseid-0100).
In short (read at dfa11c14): one function,
`read_license_text` (`extract/_license_text_match.py:367-410`), reads
each text twice (as written and without copyright notice lines), asks
LicenseID `detect()` with no option, gives no id for a file of two or
more List texts and ends the file search there (#554, #563), lets a
stated licence win a near-tie, and else takes the top id at 0.85 or
more with no other licence family within 0.01. It reads `score`,
`similarity`, `coverage` and the number of `texts`; it ignores
`exact`, `same_text`, `variant_stated` and `method`. A match is written
`Source: <file> | Method: licenseid_detection | Tool:
licenseid==<version>` (the Hub leaves out `Tool`, PIT-11). Nothing is
said for a file below the gate, a near-tie, a file of several texts, or
a G2 difference (PIT-18).

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

**Today:** half built. Item 1 holds for a dependency's licence files
(#569), a project whose manifest states nothing, and a Hub repository;
not for a project's file beside a stated licence, nor for
`embed-wheel --project-dir` (concluded, above). Item 2 holds for a
dependency's stated text against its file (two declared, a conflict
Annotation); for the project the second is concluded. In neither case
does a message say so. Item 3: no rule, as ruled.

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
   Apache 2.0 text gets no declared id; the creator concludes
   `Apache-2.0`). Corrected 2026-11-28: on requests' like text LicenseID
   0.10.0 ranks `Apache-2.0` first with `Pixar` 0.0037 below, and
   `texts` confirms `Apache-2.0`; it is Pitloom's own near-tie rule that
   names no id when nothing is stated (run on requests 2.34.2, not on
   rfc8785: [asserter-licence-measurement.md](asserter-licence-measurement.md)).
5. **Consequence for the project follow-up.** Once the licence-file
   detection is declared, a project SBOM has no `hasConcludedLicense`
   unless the creator states one (#570). FSCT COMP-007, mapped to concluded
   only, then reports the main package missing too (FG-17 in
   [sbom-format-gaps.md](../sbom-format-gaps.md)).

## Licence work: the points and their rulings

The licence points parked on 2026-11-16 (a match that is not exact,
scope by position and name, picking or combining, several classifiers,
statements inside one source and between sources, `embed-wheel
--project-dir`, the `matched` exception, statements that cannot both be
true, the GPL variant, the ledger entry) are on
[asserter-licence-points.md](asserter-licence-points.md), each with its
ruling and today's state. The two that shape every text match, the gate
and the form, stay below.

### The gate for a text match (measured 2026-11-19; ruled then and 2026-11-20)

The measurement that fed these rulings (LicenseID 0.9.0, 197 licence
files, 2026-11-19; not run again on 0.10.0) and a run of 0.10.0 on 15
files (2026-11-28) are on
[asserter-licence-measurement.md](asserter-licence-measurement.md). In
short, for 0.9.0: `exact` was too narrow to be the gate (20 files);
`score` is a ranking key, not a fit (1.0 for a 13-line notice); the
second reading named another id than LicenseID's first in 21 files; an
Apache 2.0 text without its appendix gave `Pixar` in nine. On 0.10.0,
on the 15 files run, the second reading changed no first id, and
`Apache-2.0` ranks first.

Item 1 is ruled (2026-11-19), and item 4 follows from it. Items 2 and 3
are ruled (2026-11-20).

1. **The gate is "decisive", not a field.** A text match is a declared
   licence id when one licence family is the answer of the better
   reading: it is `exact`, or it passes the rule of the day. `exact`
   passes at once; where two ids share the exact text, LicenseID's
   order names the id. The numbers (0.85, 0.01) and the second reading
   belong to the code, not to the taxonomy. **Today:** the rule of
   2026-11-19 is built; "`exact` passes at once" is not. `exact` is not
   read, so an exact `MPL-2.0` text is a near-tie with its twin and
   gives no id (run on 0.10.0 with a copy of the gate, 2026-11-28). The
   code has since added the several-texts stop ("Today's detection
   path" above).
2. **Every text match says how good it was.** The claim quotes
   LicenseID's `exact` and `score` beside the match, as
   `variant_stated` is quoted (ruled 2026-11-20). Which keys record
   the match itself is the form, below. A reader who wants exact
   matches only can filter. `score` is quoted as LicenseID's ranking key, not as a
   measure of fit (LicenseID's documentation says so since 0.10.0). The
   keys that carry the two
   are a code-stage choice, as for `variant_stated`. A file that does
   not pass quotes no result in the SBOM (ruled 2026-11-23): the SBOM
   holds claims, not candidates the gate refused, and LicenseID's
   first result under 0.85 was the id the rule named in none of
   26 files (0.9.0, 2026-11-19). The run says it instead, in a log
   message that gives the file, that the gate did not pass, and the
   nearest id and score; its level and wording are message-catalogue
   work of the code stage. **Today:** not built: nothing is quoted and
   nothing is said.
3. **A match that does not pass names no id.** Ruled 2026-11-20: where
   no other statement names a licence, the text of the file is declared
   as a custom licence (`LicenseRef-loom-text-...`), as an unmatched
   manifest text is today. The gate
   cannot tell a custom licence from a file that is not a licence text
   (a pointer, a notice): alone, that one is declared the same way.
   Also ruled 2026-11-20: beside a statement that names a licence, the
   file adds no second licence and no conflict; it is recorded as a
   licence file with no id. All 19 files of the measurement that do not
   pass are of this second kind (each distribution has a licence in its
   Core Metadata; 0.9.0, 2026-11-19): none of the 197 becomes a custom
   text. A passing
   match of another licence file of the same element is such a
   statement too (ruled 2026-11-23): a pointer file beside two licence
   files that pass (`LICENSE`, `LICENSE.APACHE` and `LICENSE.BSD` of
   `packaging`) adds no third licence. The cost is the same as beside
   a manifest: a real custom licence beside a file that passes is
   recorded as a licence file with no id.

   **Ruled 2026-11-28 (C6, [resweep-rulings.md](resweep-rulings.md)):**
   a matcher that could not run is not one that ran and found nothing.
   With no usable database the file makes no custom-text claim: it is
   a source outcome (C1: recorded per source, on the element) with a
   reason of the class "not able" (the classes of
   [reason.md](reason.md) are proposed, not agreed). The custom text
   of item 3 is for a matcher that ran.

   **Today:** a file that does not pass gives nothing and is not
   recorded, and the search goes on to the next licence file
   (`extract/_license.py:118-122`; known bug "a near-tie in the first
   licence file lets a later file decide alone"). A matcher that could
   not run gives the same nothing; only the run's message tells them
   apart (`license-db-missing`, `license-db-unusable`), and a lookup
   that fails otherwise is `DEBUG` only. Which class that last case
   falls in is open.
4. **The two wrong classes are the matcher's, not the gate's**: optional
   text of the list's templates, and more than one licence text in a
   file. Both went to LicenseID (findings LID-1 and LID-5). **Today:**
   LicenseID 0.10.0 compares a text without its optional parts and
   lists the texts a file holds; an answer in a file of several stands
   only when its text comes first. Pitloom goes its own way on both: an
   Apache 2.0 text without its appendix (requests 2.34.2) ranks
   `Apache-2.0` 1.0 and `Pixar` 0.9963, a near-tie of two families by
   Pitloom's rule, so it is declared only when a licence stated breaks
   the tie, and gives no id otherwise; and a file of several texts
   gives no id even where LicenseID answers (types-setuptools: its own
   `Apache-2.0` text, then `MIT`). Both are open decisions below.

Not chosen for item 1: `exact` only (one file in ten gets an id; every
MIT file becomes a custom text); a score floor alone (no floor parts
`Pixar` from `MIT`). Not chosen for item 3: the nearest id with a mark
(often a wrong id in the declared slot: of the 26 first results under
0.85, the second reading replaces 11 and names none for 15; 0.9.0,
2026-11-19); nothing at all, as today (an element with a licence file
and no declared licence).

### The form of a text match (ruled 2026-11-21: form A)

A match that passes the gate is the originator's declared licence. Two
ways to write the match down, here for tomli 2.5.0 (`licenses/LICENSE`;
LicenseID 0.9.0: `MIT`, `exact` false, `score` 1.0; the metadata states
`MIT`). The quoted `exact` and `score` are left out: their keys are not
named yet. Today the claim is written `Source: LICENSE | Method:
licenseid_detection | Tool: licenseid==0.10.0`.

```text
A  Asserter: originator | Method: matched | Technique: license-text | Tool: licenseid==0.9.0 | Basis: declared
B  Asserter: originator | Written: (the text, by its hash) | Change: (a further step kind) | Tool: licenseid==0.9.0 | Basis: declared
```

| Question | A: the `matched` exception | B: a `Change` step |
| --- | --- | --- |
| What the claim says Pitloom did | `Method: matched`, as the first question of [method.md](method.md) says | `read`, not written; the match is in `Change` |
| Exception needed | one: `matched` on the element's own licence text keeps `originator` and `declared` | one: the first question of method.md does not hold for the element's own licence text |
| New vocabulary | none | a further step kind in a closed list; a form of `Written` for a text |
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
its second reading was not run.) A wrong match that passes (`Pixar` on
0.9.0) is wrong in both forms.

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

## Open decisions for the plan

Where the code of dfa11c14 goes against a ruling above, or goes its own
way where LicenseID 0.10.0 now gives a rule of its own. Questions only;
none is decided here.

1. **Several texts.** Today a file whose reading holds two or more List
   texts gives no id, stated or not, and ends the search, also where
   LicenseID answers the first text (types-setuptools: `Apache-2.0`,
   then `MIT`; mypy by LicenseID's documentation: `MIT`, then two
   more). LicenseID's documentation says to record each text as its own
   `hasDeclaredLicense`, never joined with `AND`. Keep none, declare the
   answer, or declare every text? The same when LicenseID gives no
   answer (numpy 2.5.5)? Does the search still stop there?
2. **The family near-tie against LicenseID's caller rule.** LicenseID
   says to declare the answer when `texts` is exactly it. Pitloom
   refuses a near-tie of two families: requests' Apache 2.0 text with
   nothing stated, and an exact `MPL-2.0` text with its twin in
   `same_text`. Does the gate read `texts`, `exact` and `same_text`, and
   does item 1's "`exact` passes at once" get built?
3. **A notice accepted.** A 12-line Apache header scores 1.0 at
   coverage 0.0564 with no `texts`; Pitloom names `Apache-2.0` (copy of
   the gate, 2026-11-28). LicenseID's rule calls that a notice or a
   pointer. No id, the custom text of item 3, or the id with a mark?
   The same beside a manifest licence?
4. **The unmarked `-only`.** The ruled mark (`Change: expanded`, with
   `variant_stated` quoted) is not built. Built with the gate, or on its
   own? And the clash with option G of `licence-variant-evidence.md`?
5. **The second reading.** On the 15 files run on 0.10.0 it changed no
   first id. Drop it, keep it as a fallback, or keep it? Run the 197
   files again first?
6. **No answer moves on.** A near-tie, a score under 0.85 and a short
   text are all "nothing here", and the next file may decide alone.
   Which of them end the search, now that only "several texts" does?
7. **The stated licence breaks the tie** through `_stated_among`;
   LicenseID has a `hint` option for the same. Which, and does the Hub
   or a manifest text get a stated licence for it (none today)?
8. **The project's second opinion.** Declared with a conflict (the
   ruling), as #569 did for dependencies, and with which message for a
   difference (PIT-18)? The same for `CITATION.cff`, `codemeta.json`
   and `embed-wheel --project-dir`.
9. **C6 in the code.** Where the "not able" outcome is recorded, and
   which class a lookup that fails for another reason gets.

## Not checked

- The 197-file measurement on any LicenseID after 0.9.0: every count
  from it on this page is of 0.9.0, 2026-11-19.
- The real files of mypy, CacheControl, pathspec, bandit, rfc8785 and
  OL-5 of the examples on 0.10.0. The `MPL-2.0`, appendix and notice
  cases of 0.10.0 rest on LicenseID's stored normalised texts and a
  header written for the probe, run through a copy of Pitloom's gate,
  not Pitloom itself.
- `PKG-INFO` against an archived `pyproject.toml`; the Hub card
  against a model file's own licence; the whole fragment merge (read in
  part); whether `embed-wheel --project-dir` compares the version.
- Whether LicenseID's `hint` gives the answers `_stated_among` gives.
