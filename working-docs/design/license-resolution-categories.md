---
Created: 2026-10-26
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Licence resolution categories: what Pitloom needs to know from LicenseID

Status: partly built. LicenseID ships `resolve()` (declared-value
resolution, `Apache2` to `Apache-2.0`), which reads the SPDX License List
packaged with it: Pitloom calls it with `source="packaged"`, so a declared
value needs no database (#437). Pitloom reads a single-line value
through it, quiet at `DEBUG:` for form changes and one `INFO:` per decision,
with `Method`, `Resolution-1`, `Expansion-1` and `Tool` in the provenance (see
[license-pipeline.md](../implementation/license-pipeline.md)). Not built:
reading a compound operand by operand (LicenseID gives `operands`; Pitloom
reads a compound only as one answer), the licence
list version (Q5, in `Resolution["lists"]` but not used), a cross-field
indicator for a concluded licence (Q4). LicenseID 0.8.4 has `alias_name`,
`text_title` and `license_url` (this page's `alias` and `listed_url`, plus
titles); the list is in the note after section 4's table and Pitloom's
decision per category is in `tests/extract/test_license_resolve.py`
(`_DECIDED_BY_CATEGORY`). Decided 2026-11-05: provenance annotations are off by
default and a flag turns them on (deferred); the provenance notes below are
written when it is on.

See also: [license-typing.md](../implementation/license-typing.md) (the one
classifier and element builder),
[license-pipeline.md](../implementation/license-pipeline.md) (sources and
call sites),
[provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md)
(`Method`/`Role` vocabulary), [known-bugs.md](known-bugs.md),
[sbom-format-gaps.md](sbom-format-gaps.md) (FG-6, FG-7),
[licenseid-handoff.md](licenseid-handoff.md) (earlier upstream asks),
[license-rules.md](license-rules.md) (equivalence, provenance keys),
[license-resolution-categories-licenseid.md](license-resolution-categories-licenseid.md)
(sections 2 and 9: LicenseID evidence and requests; split out for size).

## 1. Question and decisions on record

When the resolver turns a declared value into an SPDX expression, which kinds
of change must Pitloom be told about, and how much does each deserve to be
trusted? Decisions (maintainer, 2026-10-26):

1. Pitloom still handles every value the resolver cannot resolve, and should
   get reasonable results in general.
2. A change beyond basic whitespace trimming and basic case normalisation is
   the resolver's decision, not the author's verbatim statement: an `INFO:`
   line and provenance in the SBOM, never silent.
3. `+` to `-or-later`, and calling a bare/deprecated id `-only`, are
   expansions, recorded apart from normalisation.

Scope: fields that hold an SPDX expression only (`project.license`,
`License-Expression`, PyPI `license_expression`, `SPDX-License-Identifier`,
GGUF `general.license`), where an unknown id is text with one `WARNING:`
(#357). Free-text fields: Q1. Licence text
detection (`licenseid_detection`) is out of scope.

## 2. Evidence: LicenseID 0.5.0 on 220-odd declared values

Moved to [license-resolution-categories-licenseid.md](license-resolution-categories-licenseid.md#2-evidence-licenseid-050-on-220-odd-declared-values)
(with 2.1 per-category reporting and 2.2 the upstream defects).

## 3. What SPDX makes equal (family A basis)

- SPDX 3.0.1 Annex "SPDX License Expressions", clause "Case sensitivity":
  licence and exception identifiers should be matched case-insensitively;
  the operators AND, OR and WITH should be matched case-*sensitively*. The
  ABNF's quoted operators are case-insensitive by RFC 5234 section 2.3, so
  parsers accept `or`; folding operator case is a tolerance, not a stated
  identity. It changes no licence, so it stays family A.
- Same annex, ABNF: an `idstring` holds letters, digits, `-` and `.` only, so
  `Apache 2.0` is no id under any case folding; whitespace separates tokens
  and its amount carries nothing; brackets group.
- Same annex, clause "Simple license expressions": a `+` after a List id means
  "or any later version". The List names the deprecated `GPL-2.0+` exactly as
  `GPL-2.0-or-later` (probe: the 12 GPL/LGPL `X`/`X+` ids share names with
  `X-only`/`X-or-later`).
- The List names the deprecated `GPL-2.0` "GNU General Public License v2.0
  only", the name of `GPL-2.0-only`. That is the List's reading of the id; it
  was deprecated (License List 3.0) because declarations did not follow that
  reading, so the successor is a reading, not the author's statement.
- Annex "License matching guidelines and templates" (whitespace,
  capitalisation, punctuation, hyphens and dashes, ...) says when licence
  *text* matches; it is no rule for ids or names, so its hyphen equivalence
  applied to `Apache 2.0` is the resolver's extension (B). No clause defines
  aliases, version completion or name matching.
- `licenses.json` has `isDeprecatedLicenseId` but no successor field: every
  successor beyond the `+` naming is curated data.

## 4. The taxonomy

Families: **A** lexical identity (no decision); **B** the resolver decides
which licence is meant; **C** expansions (the qualifier `-only`/`-or-later`);
**D** no answer. Trust tiers, strongest first: `identity` (A), `list_data`
(the List's own ids, names, URLs, naming), `author_words` (the author wrote
the qualifier), `resolver_rule` (a stated, collision-checked rule or curated
table), `guess`, `none`.

| Category | Fam. | Trust | Definition | Examples | Pitloom |
| - | - | - | - | - | - |
| `exact` | A | identity | Input equals the output. | `MIT`, `Apache-2.0+`, `eCos-2.0` | accept |
| `lexical` | A | identity | Only steps `trim`, `whitespace` (Unicode White_Space at the ends or between tokens), `id_case`, `operator_case`, `ref_prefix_case` (`licenseref-` to `LicenseRef-`; idstring kept), `brackets`, `reorder`, `dedupe`. | `mit`, ` MIT\t`, `(MIT)`, `mit or apache-2.0`, `MIT OR MIT` | accept; `DEBUG:`; `Normalized-From` (today's rule) |
| `separator` | B | resolver_rule | Re-spelling inside one id: space, `_`, `.` or Unicode dash for `-`; a letter-digit boundary; a format character (U+200B) or one trailing `.`/`,` dropped. Never `+`. Valid while the folded List has no collision (3.29.0: only `X`/`X+`, hence no `+`). | `Apache 2.0`, `CC BY 4.0`, `Apache‑2.0`, `MIT.`, `Apache2` (with the next) | accept; `INFO:` |
| `version_spelling` | B | resolver_rule | Version written another way: a `v`/`V`/`Version` prefix, or a shorter number zero-padded (`2` is `2.0`, as PEP 440 pads), only when the padded id is listed. Never picks between listed versions (`LGPLv2` is `LGPL-2.0`, never `LGPL-2.1`). | `Apache-2`, `Apache v2`, `MPL2`, `EUPLv1.2`, `GPLv3+` | accept; `INFO:` |
| `listed_name` | B | list_data | After A folding, equal to the List `name` of exactly one non-deprecated id. | `MIT License`, `Apache License 2.0`, `The Unlicense`, `Boost Software License 1.0` | accept; `INFO:` |
| `alias` | B | resolver_rule | A curated table entry: a string that is neither an id nor a List name, mapped to exactly one id (never an expression), with its source: `spdx-name-part` (a quoted alternate in a List name: `"New"`, `"Simplified"`), `pypi-trove`, `fedora`, `debian`, ... Two targets make it ambiguous. | `New BSD`, `ASL 2.0` (Fedora), `Expat` (Debian), `Python Software Foundation License` (trove), `BSD-3` | accept; `INFO:` with the source |
| `listed_url` | B | list_data | A URL equal (scheme, `www.`, trailing `/`, `.html`/`.txt` folded) to the List `reference` or a `seeAlso` URL of exactly one id. A URL several ids share (the GPL pages) is ambiguous. | `https://spdx.org/licenses/MIT.html`, `https://opensource.org/licenses/MIT` | accept; `INFO:` |
| `deprecated_equal_successor` | B | list_data | A deprecated id whose List `superseded_by` names exactly one id with the same List name: a rename, no change of meaning. | `StandardML-NJ` to `SMLNJ` | accept; `INFO:`; the successor is written into the declared AND the concluded licence; the deprecated id stays in provenance (`Deprecated-License-Id`, `Resolution-n`) |
| `deprecated_ambiguous` | B | list_data or resolver_rule | A deprecated id with no provably equal successor: a successor under another name, an expression (`-with-` ids) or the `-only`/`-or-later` split. Reported as an offer, not applied. | `BSD-2-Clause-FreeBSD`, `GPL-2.0-with-classpath-exception`, `GPL-2.0` | keep as written (valid SPDX); note `Deprecated-License-Id: X (Y)`; quiet |
| `expression_repair` | B | guess | A non-SPDX operator read as one: `/`, `&`, `,`, `Dual X/Y`. | `MIT/Apache-2.0`, `MIT & Apache-2.0`, `MIT, Apache-2.0` | refuse: text + `WARNING:` |
| `fuzzy` | B | guess | Any similarity measure (section 6), opt-in only. | `UNLICENSED` to `Unlicense`, `GPLv2` to `LiLiQ-R-1.1` | refuse; never requested |
| `ambiguous` | B | none | Several candidates survive; the resolver returns them all and chooses none. | `BSD`, `GPL`, `LGPL`, `Apache`, `Apache Software License`, `Public Domain` | text + `WARNING:` naming candidates |
| `plus_to_or_later` | C | list_data | `X+` to `X-or-later` where the List has that id. | `GPL-2.0+`, `LGPL-2.1+`, `GPLv2+` (after `version_spelling`) | accept; `DEBUG:` (decision Q3); key `Expansion-n` is still written |
| `stated_qualifier` | C | author_words | The author's own words in the same value attach a qualifier: "or later", "or any later version", "only". | `GPL-2.0 or later`, `GPL 3.0 only`, `GPLv3 or later`, the trove `... v2 or later (GPLv2+)` | accept; `INFO:`; key `Expansion-n` |
| `assumed_only` | C | guess | A bare deprecated id (`GPL-2.0`, `LGPL-2.1`, `AGPL-3.0`, ..., also inside a `-with-` id) read as `-only` with no indicator. Reported as an offer with both candidates, never applied. | `GPL-2.0`, `GPL-3.0 WITH ...`, `GPL-2` | keep as written; `Deprecated-License-Id` (today) |
| `unresolved` | D | none | No candidate. | `Proprietary`, `llama3.1`, `UNLICENSED`, `licenseref-foo` | text + `WARNING:` (today) |
| `malformed` | D | none | Broken expression syntax, or `+` after `-only`/`-or-later`, or `+` after a `LicenseRef-`. | `MIT OR`, `GPL-2.0-only+` | text + `WARNING:` (today) |

A value's category is its weakest operand's, in this order: `exact`,
`lexical`, `listed_name`, `listed_url`, `plus_to_or_later`,
`stated_qualifier`, `separator`, `version_spelling`, `alias`, then the
refused ones. Acceptance is all or nothing: `Apache2 OR Foo` stays text, as
emitting `Apache-2.0 OR LicenseRef-...` would invent a reference. An accepted
result is checked again by Pitloom's strict parse before it is recorded.

**LicenseID 0.8.4's own categories** (`licenseid.resolvertypes.Category`, in
`CATEGORY_ORDER`): `exact`, `lexical`, `plus_to_or_later`,
`stated_qualifier`, `separator`, `version_spelling`, `listed_name`,
`deprecated_equal_successor`, `prose_form`, `text_title`, `alias_name`,
`license_url`, `trove_name`, `deprecated_ambiguous`, `assumed_only`,
`malformed`, `unresolved`. This page's `alias` is `alias_name` (also
`text_title`, `prose_form`, `trove_name`) and `listed_url` is `license_url`
(trust `resolver_rule`, not `list_data`); `expression_repair`, `fuzzy` and
`ambiguous` are not categories there. Pitloom reads `stated_qualifier`,
`separator`, `version_spelling`, `listed_name`, `deprecated_equal_successor`,
`prose_form`, `license_url`, `text_title`, `alias_name` and `trove_name` as
decided, and `exact`, `lexical`, `plus_to_or_later`, `assumed_only` and
`deprecated_ambiguous` as not decided (`_DECIDED_BY_CATEGORY`).

## 5. The two expansions

**`+` is an equivalent spelling, recorded as an expansion.** The `+` operator
means "or any later version"; `GPL-2.0-or-later` names the same choice and
the List gives `GPL-2.0+` its name. No licence changes, so it is accepted (as
Pitloom does today). It is still a rewrite of what the author wrote (operator
to id), so it gets its own `Expansion-n` key and an `INFO:` (decision 2),
apart from `Resolution-n`. `Apache-2.0+` has no `-or-later` id and stays.

**`-only` needs an indicator; the absence of "or later" is not one.** A
`GPL-2.0` declaration has the List's "only" name, but the List deprecated it
because authors used it for both. Indicators, in the order of their weight:

| Indicator | Gives | Who can see it |
| - | - | - |
| Words in the same value: "only", "or later", "or any later version", `+` | the qualifier stated | LicenseID (`stated_qualifier`) |
| A `License ::` classifier on the same package naming "or later" (`GNU General Public License v2 or later (GPLv2+)`) | `-or-later` | Pitloom (several fields) |
| The classifier without it (`GNU General Public License v2 (GPLv2)`) | nothing: the classifier list has no "only" form | - |
| A source header with the FSF notice "either version 2 of the License, or (at your option) any later version", or a tag `GPL-2.0-only`/`-or-later` | that qualifier | Pitloom (files) |
| The `LICENSE`/`COPYING` text | nothing: both share the text | - |

Cross-field indicators belong to Pitloom and would make a *concluded*
licence (Q4); LicenseID sees one value and reports `assumed_only` as an
offer with both candidates.

## 6. Fuzzy: never in an SPDX-only field

Fuzzy means any similarity measure in place of equality: edit distance over
ids (`ratio`), substring (`partial_ratio`), token set over names
(`token_set_ratio`), all three in 0.5.0's Tier 0 at 0.90 (two words or fewer)
or 0.85; and text similarity over licence bodies (Tiers 1 and 2). Pitloom
should never accept one, in any declared field:

1. A declared field is the author's statement; a near string asserts a
   licence the author did not name.
2. Licence identity is discrete and close strings are different licences:
   `MIT`/`MIT-0`, `Unlicense`/`UNLICENSED` (opposite meanings),
   `GPL-2.0`/`LGPL-2.0`, `Zlib`/`zlib-acknowledgement`.
3. 0.5.0 scores unrelated answers 1.00 on short input (D5), so no threshold
   separates right from wrong.
4. Errors are asymmetric: a wrong id is acted on (compliance, CRA, licence
   scanners); text forces a human to look.
5. The nearest neighbour moves when the List grows, so a fuzzy reading is not
   stable across database versions even with the input unchanged.

Each right answer fuzzy gave (rows 12, 13) is a name or a List name part:
data for `alias`.

## 7. Recording

**Log lines** (`excerpt()` on both values, operand names through
`loggable()`, one per value per process, as `warn_once` but at `INFO`):

Design wording, quoting the result and giving a reason for an ambiguous
value; the built lines are in the provenance docs.

```text
INFO: FIELD=project.license LICENSE='Apache2': read as 'Apache-2.0' (separator, version_spelling)
INFO: FIELD=License-Expression LICENSE='Apache2 OR gpl-2.0+': read as 'Apache-2.0 OR GPL-2.0-or-later' (Apache2: separator, version_spelling; gpl-2.0+: plus_to_or_later)
INFO: FIELD=project.license LICENSE='New BSD': read as 'BSD-3-Clause' (alias: spdx-name-part)
WARNING: FIELD=project.license LICENSE='BSD': not read as an SPDX license expression (ambiguous: 0BSD, BSD-1-Clause, BSD-2-Clause and 43 more); recorded as license text
WARNING: FIELD=project.license LICENSE='MIT/Apache-2.0': not read as an SPDX license expression ('/' is not an SPDX operator); recorded as license text
```

Family A steps are not listed (`DEBUG:` only). `assumed_only` and
`deprecated_ambiguous` change nothing, so no `INFO:`; the note says it. `plus_to_or_later` is logged at `DEBUG:`, and its `Expansion-n` key is always written.

**Provenance** (the comment string, `parse_provenance_value` keys; existing
keys unchanged):

| Key | Meaning |
| - | - |
| `Normalized-From` | The value as written (exists). Kept whenever anything changed. |
| `Method: licenseid_resolution` | New: the resolver's reading of a declared value (not `licenseid_detection`, a text). Absent when only A or `plus_to_or_later` applied. |
| `Resolution-<n>` | New. Operand `n` (1-based, in input order) as written, its result and B steps: `Apache2 -> Apache-2.0 (separator, version_spelling)`; `alias` adds its source. |
| `Expansion-<n>` | New. Operand `n`'s C step, kept apart: `GPL-2.0+ -> GPL-2.0-or-later (plus_to_or_later)`. |
| `Tool` | `licenseid==0.5.1` (exists for detection). |
| `License-List-Version`, `Resolver-Data` | New. The List version and LicenseID's data version (section 9, R11). |
| `Deprecated-License-Id` | Exists; also names the successor a `deprecated_equal_successor` and `deprecated_ambiguous` offer gives. |

One `Method` per value, as the key is single-valued; per-category `Method`
values could not describe `Apache2 OR gpl-2.0+`, whose operands differ. The
shared operand number ties a `Resolution-n` to its `Expansion-n`
(`GPLv2+`: `Resolution-1: GPLv2+ -> GPL-2.0+ (version_spelling)`,
`Expansion-1: GPL-2.0+ -> GPL-2.0-or-later (plus_to_or_later)`). The
`Annotation` statement carries the same as a list of
`{operand, from, to, steps: [{kind, from, to, detail}]}`, which needs the
encoder to take a structured value. A `|` in a value must be escaped (the
comment and the parser split on it; today unreachable, as no value holding
`|` parses).

**The verbatim value stays in the SBOM** (`Normalized-From`, at
`detail = "minimal"`, on the element or the source's relationship as today).
The element states the resolver's reading; the honesty rules ("no silent
deviations") need the reader able to see what the author wrote and who
changed it. Rejected: declared to the verbatim text, concluded to the
resolved expression. Truer to the SPDX words, but checks read declared ids
(`Apache2` would keep failing them), and concluded already means Pitloom's
second opinion (a `LICENSE` file). SPDX 3.0.1 has no property for either
fact: FG-6, FG-7.

## 8. Pipeline, determinism, offline, idempotence

- **Where.** In `_classify`, after the strict and grammar-gap parses fail and
  before text, for an SPDX-only field: one place every surface reaches
  (CLI, hook, library, wheel, sdist, GGUF, Hugging Face). The field kind
  becomes an explicit parameter (the stage-flag rule), which
  `warn_unless_expression` already receives. The Hugging Face path no longer
  folds a card value (`canonicalize_license_id`, deleted in #437).
- **Conflicts.** A resolved `Apache2` agrees with a detected `Apache-2.0`.
- **Determinism.** The result is a function of the input, the field kind,
  the LicenseID version and its data version; record `Tool`,
  `License-List-Version` and `Resolver-Data`. Two databases built at
  different times from one List must answer byte-identically.
- **Offline / no database.**

| Needs | Categories |
| - | - |
| `py-spdx-license`'s bundled List only | `exact`, `lexical`, `plus_to_or_later` (today) |
| List ids, names, URLs (LicenseID's packaged snapshot) | `separator`, `version_spelling`, `listed_name`, `listed_url`, `stated_qualifier`, `deprecated_equal_successor` and `deprecated_ambiguous` |
| Curated tables (to ship in the wheel) | `alias` |
| A built database | `fuzzy` and text detection only |

  Built (#437): resolution reads the packaged List and needs no built
  database. Only when the `licenseid` install has no packaged list is
  nothing read; the value stays text and LicenseID's error is said once.
- **Idempotence.** Resolving an output again gives `exact`; reclassifying it
  gives the same expression and no `Normalized-From`. (0.5.0:
  `normalize_identifier` was idempotent on all 209 corpus outputs.)

## 9. What Pitloom needs from LicenseID 0.5.1

Moved to [license-resolution-categories-licenseid.md](license-resolution-categories-licenseid.md#9-what-pitloom-needs-from-licenseid-051)
(R1 to R11, and "Tool modelling").

## 10. Review of the draft list

- exact: keep.
- Whitespace removal, and case-insensitive: merge into one family-A
  category, `lexical`, with steps; add operator case, brackets, reorder,
  dedupe. None is a decision (section 3).
- Alias: split into `listed_name` (the List's own `name`) and `alias` (a
  curated alternate name of exactly one id, with its source); add
  `listed_url`.
- Separator normalisation: keep, narrowed to re-spelling within one id,
  `+` excluded, checked collision-free; split out `version_spelling` (it
  adds a number).
- Fuzzy: defined (section 6); opt-in in the API, never accepted by Pitloom.
- `+` to `-or-later`: an expansion, accepted (equivalent spelling).
- Bare id to `-only`: an expansion, never applied without an indicator; add
  `stated_qualifier` for the indicator in the value.
- Missing: `deprecated_equal_successor` and `deprecated_ambiguous` (offer), `expression_repair` (refused),
  `ambiguous`, `unresolved`, `malformed`.

## 11. Decisions on the open questions (2026-10-26)

- **Q1, free-text values: yes.** The same resolution applies to short one-line
  values (`License:`, `project.license.text`, `License ::` classifiers, a
  Hugging Face card `license`), quiet when unresolved (free text is not
  declared as SPDX, so no `WARNING:`). Many SBOMs will change: a test per
  field.
- **Q2, reorder and dedupe: family A** (`DEBUG:`, `Normalized-From`).
- **Q3, `plus_to_or_later`: `DEBUG:`.** The `Expansion-n` provenance key is
  still written, so the SBOM says it.
- **Q4, a cross-field indicator: a concluded licence.** A classifier
  `GPLv2+` beside `License-Expression: GPL-2.0` gives declared `GPL-2.0` (as
  resolved) and concluded `GPL-2.0-or-later`, the provenance naming the field
  and the words. It never rewrites the declared value.
- **Q5, the list version: set it, from the data the resolver used.** The
  result carries `license_list_version` (the database's own metadata:
  `get_metadata()` returns `license_list_version`, `release_date`,
  `normalization_version`), and Pitloom copies it into
  `simplelicensing_licenseListVersion`. Pitloom does not read the database
  itself: it could differ from what the resolver read (a database updated in
  between, a `--db` path, the bundled fallback). When the resolver used its
  bundled data, `source: bundled` and that list's version, and Pitloom says
  which; the strict parser's own list (`py-spdx-license`) validates ids and its
  version is not claimed.
- **Q6, aliases: the SPDX License List for now.** An `alias` is a string that
  one named published list maps to exactly one id, and every alias carries its
  `source` and `source_version`. The SPDX License List ships no alias table:
  its data are ids, names, URLs and deprecation with `superseded_by`, which
  give `listed_name`, `listed_url` and the deprecated categories. So with the
  SPDX list alone `alias` is empty, and `Apache2` is resolved by the rules
  (`separator` to `Apache-2`, then `version_spelling` to `Apache-2.0`, listed),
  not by a table. A second list (ScanCode LicenseDB, trove classifiers, Fedora,
  Debian) enters as a new `source` after review, one entry at a time.
- **Q7, an equal successor: replace, keep the deprecated id in provenance.**
  `deprecated_equal_successor` (section 4) writes the successor into the
  declared and the concluded licence, with an `INFO:`, and keeps the deprecated
  id in `Deprecated-License-Id` and `Resolution-n`. "Provably equal" is the
  List's `superseded_by` naming one id with the same List name. Everything else
  stays `deprecated_ambiguous`.
