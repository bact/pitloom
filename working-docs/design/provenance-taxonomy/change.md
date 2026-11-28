---
Created: 2026-11-14
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Change: how a recorded value differs from what was written

See also: [README.md](README.md) (the claim model), [method.md](method.md),
[license-resolution-categories.md](../license-resolution-categories.md) (the
licence categories, owned by LicenseID),
[licence-resolution-provenance.md](../licence-resolution-provenance.md)
(T14, which waits on this page),
[canonical-output-followups.md](../canonical-output-followups.md)
(normalisation rules themselves),
[resweep-rulings.md](resweep-rulings.md) (C4 and C5, ruled 2026-11-28).

**Status:** draft.

## Definition

A **change** is the difference between the value a source wrote and the
value Pitloom records for the same claim. The asserter stays the same: a
licence written `apache 2` and recorded `Apache-2.0` is still the originator's
statement, with a change. A change that goes beyond what the source
stated is not a change; it is a second claim by `sbom-tool`
([asserter.md](asserter.md), rule 5): picking one of several stated values,
or combining them. A licence text matched to an id is not a change: it
is written as a method, `matched` (ruled 2026-11-21; same page, "The
form of a text match").

Method and change differ: the method gets a value out of a source; a change
re-spells a value already obtained.

## Keys

| Key | Holds | Was |
| --- | --- | --- |
| `Written` | the value as written, whenever a step other than `form` changed it; never on a `matched` claim (below) | `Normalized-From` |
| `Change` | the step kinds applied, in order, comma-joined | (licence only: inside `Resolution-n`) |
| `Tool` | the tool and version that applied a `respelled` or `expanded` step | `Tool` |
| `Resolution-<n>`, `Expansion-<n>` | licence only: operand `n` as written, its result and LicenseID's own category names | same |
| `Superseded` | an identifier the source used that the reference list has retired, with its successor | `Deprecated-License-Id` |

A `matched` claim has no `Written` (ruled 2026-11-23), also when it
carries a step (`expanded`, for a variant the matcher chose). `Written`
holds a value the source wrote; there the source wrote a text, which
`Source` and `Location` name. Not taken: the text's digest in `Written`
(the key would hold two kinds of thing, and which state of a file was
read is for `Location`), and the id without its variant (`GPL-3.0`),
which the source did not write.

## Step kinds

Five kinds, by how much the tool decided. Closed. `escaped` was added,
and the log of `cut` raised to `WARNING:`, on 2026-11-28
([resweep-rulings.md](resweep-rulings.md), C5). Ruling C5 decided only
those two things; the `WARNING:` log, the missing `Written` and the
Trust value of `escaped` below are this page's reading, not ruled.

| Kind | Definition | Decision question | Trust | Log |
| --- | --- | --- | --- | --- |
| `form` | Spelling that the format itself makes equal: case, blank space, brackets, order, duplicates. | Would the format's own comparison rule call the two equal? | as written | `DEBUG:` |
| `respelled` | The tool read a non-canonical spelling as one canonical value, from reference data or by a rule of the tool, with one candidate. | Is there exactly one listed value this can be? | the tool's reading | `INFO:` |
| `expanded` | The tool added a qualifier or an operator the canonical form needs. | Did the value gain meaning it did not spell out? | the tool's reading, kept apart | `INFO:` or `DEBUG:` by rule; `WARNING:` for an operator |
| `cut` | The value was shortened to a limit. | Is part of the written value missing? | incomplete | `WARNING:` |
| `escaped` | The written form cannot hold the text as read, so part of it is written as an escape or a replacement character (`\uXXXX`, U+FFFD). | Does the recorded text differ from the text read only where the format, or a safety rule for display, cannot hold the character? | as written, but not the same text | `WARNING:` |

An `escaped` claim has no `Written` (this page's reading, not ruled):
the raw text is exactly what the written form cannot hold. `Change: escaped` says that the recorded
text is not the text read. `cut` is a `WARNING:` because a value of
which part is missing is a deviation from what the source wrote.

`cut` and `lower-bound` ([basis.md](basis.md)) part by what was
stopped (this page's reading, not ruled): `cut` is a text shortened,
and the part kept is recorded with the step; `lower-bound` is a count
or a size whose read stopped at a limit, and the partial value is never
recorded.

A split by a rule that can be wrong (an author field read "by a
guess") stays the originator's statement, `parsed` (ruled 2026-11-28,
[resweep-rulings.md](resweep-rulings.md), C4). Its doubt is shown by
naming the technique ([method.md](method.md)) and by a `Change` step.
Whether that step is a new kind or one of the five is open (below).

Not changes, so not kinds: a value the tool could not read (`unresolved`,
`malformed`) is recorded as written, with a `WARNING:`. LicenseID has no
category for a guess: a value it will not read gets no expression, and a
`reason`.

## Fields that change today

| Field | Step | Kind |
| --- | --- | --- |
| licence | LicenseID categories | `form`, `respelled`, `expanded` (table below) |
| package name | PEP 503 normalisation | `form` |
| version | PEP 440 normalisation; a version as a URL spelled it | `form` |
| a model name over 1,024 characters | cut (`Note: cut to 1024 characters` today; a related name's cut is said as an `over-cap` `WARNING:`, `assemble/spdx3/_ai_package.py:214-218`, read at dfa11c14) | `cut` |
| source metadata blob | keys dropped to a byte budget (`truncated` in the statement) | `cut` |
| a placeholder spelling (`UNKNOWN` to `NOASSERTION`) | recorded as the format's term | `respelled` |
| display text of a model's or a loom dataset's elements | invisible, bidi or other control characters written as `\uXXXX` (`core/untrusted_text.py:135`, read at dfa11c14) | `escaped` |
| any text of the SBOM, a licence value apart | a lone surrogate written as the six characters `\udXXX` (`export/spdx3_json.py:137`, read at dfa11c14) | `escaped` |
| a licence value | a lone surrogate replaced by U+FFFD (`extract/_license_classify.py:79`, read at dfa11c14) | `escaped` |
| a dependency's stated licence text that LicenseID reads as the licence of its licence files (a `License` header holding the licence body) | recorded as that licence, the text kept as `Normalized-From` (`assemble/spdx3/_deps_license_files.py:146-183`, read at dfa11c14) | not yet mapped: on this page's reading `respelled`, unless the reading is taken as a match, which has no `Written` |
| the location of a GGUF training dataset (on `main`) | a `repo_url` in the model-path form that `gguf-py` writes (`https://huggingface.co/owner/name`), recorded as the dataset's page (`https://huggingface.co/datasets/owner/name`); ruled 2026-11-23 | `respelled`; `Written` holds the stated URL |

## Licence categories

LicenseID owns the category names; Pitloom records them unchanged in
`Resolution-<n>` and `Expansion-<n>` and maps each to a step kind for
`Change`. No renaming: the names are LicenseID's interface.

The categories and the `trust` word of each are LicenseID's, read from
release 0.9.0 (`licenseid.resolvertypes`, `docs/resolve.md`; 2026-11-19).
Release 0.8.4 has the same seventeen. The category of a value is the
weakest of its steps.

| LicenseID category | LicenseID `trust` | Step kind |
| --- | --- | --- |
| `exact` | `identity` | none |
| `lexical` | `identity` | `form` |
| `listed_name`, `deprecated_equal_successor` | `list_data` | `respelled` |
| `separator`, `version_spelling` | `resolver_rule` | `respelled` |
| `prose_form`, `text_title`, `alias_name`, `license_url`, `trove_name` | `resolver_rule` | `respelled` (ruled 2026-11-23) |
| `plus_to_or_later` | `list_data` | `expanded` |
| `stated_qualifier` | `author_words` | `expanded` |
| `deprecated_ambiguous` | `list_data` | none; `Superseded` |
| `assumed_only` | `none` | none; `Superseded`; the id stays as written |
| `malformed`, `unresolved` | `none` | none |

The step kind does not part a reading from list data and one by a rule
of the tool (ruled 2026-11-23): `MIT License` (`listed_name`) and
`New BSD` (`alias_name`) are both `respelled`. LicenseID owns that
line, and its category name is quoted beside each step. Not taken: a
fifth step kind for a rule of the tool, which would state LicenseID's
`trust` again under a word of Pitloom's. Run on 0.9.0 that day:
`Apache License, Version 2.0` is `prose_form`,
`https://opensource.org/licenses/MIT` is `license_url`; no input tried
gave `text_title`, known from the source only.

`trust` says who decided the reading: nothing was decided (`identity`),
a list (`list_data`), the author's own words (`author_words`), a rule of
the tool (`resolver_rule`), or nobody (`none`). It parts two categories
that `expanded` holds together: `stated_qualifier` is the author's "or
later" in words, `plus_to_or_later` a "+" read by the list. The step
kind does not part them (ruled 2026-11-23): both are `expanded`, as a
reading from list data and one by a rule of the tool are both
`respelled`; the category name beside the step says which.

A variant the tool chose for a licence text is `expanded` too (ruled
2026-11-19): a bare GPL text recorded as `GPL-3.0-only` gained a
qualifier it does not spell out. `expanded` alone does not say "guess",
so LicenseID's `variant_stated` (false here) is quoted beside it
([asserter-licence-points.md](asserter-licence-points.md),
"The points").

An operator the tool chose is `expanded` as well (ruled 2026-11-23):
several licence classifiers recorded as one expression joined by
`AND` gained an operator the source does not spell out. `Written`
holds the classifiers as written. This step is Pitloom's own, not a
LicenseID category.

LicenseID's category names are snake_case. They stay so inside
`Resolution-<n>`: they are another tool's vocabulary, quoted.

## Mappings (loose)

| Kind | SEMAPV | PAV | Wikidata |
| --- | --- | --- | --- |
| `form` | `semapv:Normalization`, `semapv:CaseNormalization`, `semapv:BlankNormalisation` | `pav:importedFrom` (meaning kept) | - |
| `respelled` | `semapv:LexicalMatching` | `pav:importedFrom` | P459 determination method or standard |
| `expanded` | `semapv:BackgroundKnowledgeBasedMatching` | `pav:derivedFrom` (meaning added) | P887 based on heuristic |
| `cut` | - | - | - |
| `escaped` | - | - | - |

SSSOM's `subject_preprocessing` slot is the nearest existing home for a
list of step kinds.

In PROV-O the recorded value is a `prov:wasRevisionOf` the value as
written ("a derivation that revises an entity into a revised version").
PROV-O does not name kinds of revision; the step kinds stay Pitloom's own
([alignment.md](alignment.md), "Limits"). SIO's `is subsequent version
of` is a loose match.

## Open points

1. Under C4 (ruled 2026-11-28,
   [resweep-rulings.md](resweep-rulings.md)): the `Change` step that
   marks a split by a rule that can be wrong, a new kind or one of the
   five. The technique names go to [method.md](method.md). Not built:
   the author split was read in the code on 2026-11-28, see the
   paragraph on the author split in [method.md](method.md).
2. The line between `cut` and `lower-bound` above is this page's
   reading, not ruled.
3. The kind of a stated licence text read as its licence file's licence
   (the row above): `respelled`, or a match.
4. For `escaped`, three things on this page are its reading and not
   ruled: that it logs at `WARNING:`, that such a claim has no
   `Written`, and its trust.
