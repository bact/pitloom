---
Created: 2026-11-26
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Licence resolution categories: LicenseID evidence and requests

See also: [license-resolution-categories.md](license-resolution-categories.md)
(the taxonomy and decisions; "section n" below refers to its numbering),
[licenseid-handoff.md](licenseid-handoff.md) (earlier upstream asks),
[licence-resolution-provenance.md](licence-resolution-provenance.md).

Sections 2 (what LicenseID 0.5.0 reported on a declared-value corpus) and 9
(what Pitloom asked of LicenseID 0.5.1, R1 to R11, and the proposed Tool
modelling), split out of the categories page for size.

## 2. Evidence: LicenseID 0.5.0 on 220-odd declared values

Database: SPDX License List 3.29.0, `normalization_version` 2, 740 rows (32
deprecated). Each value was read four ways: `normalize_identifier(v, db)`;
`match(license_id=v)` (`InvalidInputError` for all but one id);
`match(text=v)`; and the field path, `match(file_path=...)` on a
`pyproject.toml` with `[project] license = "<v>"`. Columns: field path
result; text path top as `id/method[E]score` (`E`: `exact: True`; method
`i`d, `n`ame, `t`ext, `f`ield); category (section 4).

| # | Inputs | Field path | Text path top | Category |
| - | - | - | - | - |
| 1 | 39 listed ids and expressions: `MIT`, `Apache-2.0`, `0BSD`, `X11`, `MIT-0`, `CC0-1.0`, `PSF-2.0`, `Zlib`, `EUPL-1.2`, `GPL-2.0-only`, `LGPL-2.1-or-later`, `AGPL-3.0-or-later`, `LicenseRef-foo`, `DocumentRef-x:LicenseRef-y`, `Apache-2.0 WITH LLVM-exception`, `Apache-2.0 OR MIT`, `MIT AND Zlib`, ... | same, `f`E | same, `i`E 1.00; an expression gets text noise (`Pixar` t0.73) | exact |
| 2 | `mit`, `MIT `, `apache-2.0 `, `BSD-3-clause`, `unlicense`, `cc-by-4.0`, `zlib`, `wtfpl`, `(MIT)`, `  MIT\t`, `MIT\n` | listed case, `f`E (last two: none, see D8) | listed case, `i`E | lexical |
| 3 | `mit or apache-2.0`, `MIT and Zlib`, `Apache-2.0 with LLVM-exception`, `MIT  OR   Apache-2.0`, `mit\tor\napache-2.0`, `MIT OR Apache-2.0`, `MIT OR MIT`, `MIT OR ISC OR MIT`, `((MIT OR ISC))`, `Apache-2.0 AND MIT AND MIT`, `(MIT OR Apache-2.0) AND BSD-3-Clause` | canonical form (`Apache-2.0 OR MIT`, `MIT`, `ISC OR MIT`, `BSD-3-Clause AND (Apache-2.0 OR MIT)`), `f`E | text noise | lexical |
| 4 | `Apache 2.0`, `BSD 3-Clause`, `BSD 3 Clause`, `BSD 2-Clause`, `CC0 1.0`, `CC BY 4.0`, `CC BY-NC 4.0`, `EPL 1.0`, `EUPL 1.2`, `MPL 2.0`, `Artistic 2.0`, `MIT.`, `MIT,` | the id, `f`E | the id, `i`**E** 1.00 | separator |
| 5 | `Apache‑2.0` (U+2011), `Apache–2.0` (U+2013), `MIT` + U+200B | none | the id, `i`E | separator |
| 6 | `Apache2`, `Apache2.0`, `GPL2`, `MPL2`, `AGPL3`, `BSD3`, `CC-0`, `EUPLv1.2`, `MPLv2`, `AGPLv3` | none | none | separator, version_spelling |
| 7 | `Apache-2`, `Apache 2` | none | `Apache-2.0` n1.00, not E | version_spelling |
| 8 | `Apache v2`, `Apache-v2.0`, `GPL-2`, `GPL-3`, `GPLv2`, `GPLv3`, `GPL v2`, `LGPLv2.1`, `GNU GPL v3`, `GNU GPLv3` | none | wrong: `Apache-1.1` t0.82, `SimPL-2.0` t1.00 (for `GPL-2`), `LiLiQ-R-1.1` t1.00 | version_spelling (GPL: then ambiguous) |
| 9 | `Apache-2+`, `MPL-2+`, `CC-BY-4+`, `BSD-3+` | `Apache-2.0+`, `MPL-2.0+`, `CC-BY-4.0+`, `BSD-3-Clause+`, `i`E | same | version_spelling (`BSD-3`: alias) |
| 10 | `GPL-2+` | `GPL-2.0-only+`, `f`E, `is_spdx: true` | same | version_spelling then plus_to_or_later; 0.5.0 wrong (D1) |
| 11 | `MIT License`, `mit license`, `MIT` NBSP `License`, `MIT No Attribution`, `Apache License 2.0`, `ISC License`, `The Unlicense`, `Zlib License`, `Eclipse Public License 2.0`, `Boost Software License 1.0` | the id, `f`E (NBSP: none) | the id, `n`E | listed_name |
| 12 | `The MIT License`, `Apache License, Version 2.0`, `Apache License Version 2.0`, `Apache Software License 2.0`, `Apache 2.0 license`, `Licensed under the Apache License, Version 2.0`, `Mozilla Public License 2.0 (MPL 2.0)`, `ISC License (ISCL)`, `Python Software Foundation License` | none | right id, `n`1.00 not E (token-set fuzzy) | alias |
| 13 | `New BSD`, `New BSD License`, `Revised BSD`, `Simplified BSD` | none | `BSD-3-Clause` / `BSD-2-Clause` n1.00 | alias (List name part) |
| 14 | `Modified BSD`, `3-Clause BSD`, `BSD-3`, `BSD-2`, `FreeBSD`, `zlib/libpng`, `Boost`, `CC0`, `Perl` | none | `any-OSI-perl-modules` t1.00; `BSD-3-Clause` first of 27 ties; `FreeBSD-DOC`; `zlib-acknowledgement` (wrong, D6); `BSL-1.0` n1.00; `CC0-1.0` t1.00 | alias or ambiguous |
| 15 | `ASL 2.0`, `ASL-2.0`, `AL2`, `Expat`, `MIT/X11`, `PSF`, `PSFL` | none | none or noise (`PSF`: `Info-ZIP` t1.00) | alias |
| 16 | `Apache`, `BSD`, `BSD License`, `GPL`, `LGPL`, `AGPL`, `MPL`, `Public Domain`, `Apache Software License`, `GNU General Public License v3 (GPLv3)`, `GNU Lesser General Public License v3 (LGPLv3)`, `LGPLv2` | none | first of a tie at 1.00: `Apache-1.0`, `0BSD`, `GPL-3.0-only` (for `LGPL`), `CC-PDDC`; `Vim` t0.90 | ambiguous |
| 17 | `GPL-2.0`, `GPL-3.0`, `LGPL-2.1`, `LGPL-3.0`, `AGPL-1.0`, `AGPL-3.0`, `GFDL-1.3`, `GPL-2.0 or GPL-3.0` | `-only` ids, `f`E | `-only`, `i`E | assumed_only (applied silently) |
| 18 | `GPL-2.0 WITH Classpath-exception-2.0`, `GPL-2.0-with-classpath-exception` | `GPL-2.0-only WITH Classpath-exception-2.0`, E | same | assumed_only; deprecated_equal_successor` and `deprecated_ambiguous + assumed_only |
| 19 | `GPL-2.0+`, `GPL-3.0+`, `LGPL-2.0+`, `LGPL-2.1+` | `-or-later`, E | same | plus_to_or_later |
| 20 | `Apache-2.0+`, `Apache-1.0+`, `CDDL-1.0+`, `MIT+` | unchanged, E | same | exact (valid `+`, no `-or-later` id) |
| 21 | `GPL-2.0 or later`, `GPL 2.0 or later`, `GPL-2.0 only`, `GPL 3.0 only`, `MIT OR GPL-2.0 or later` | `GPL-2.0-or-later`, ...; last: `GPL-2.0-or-later OR MIT`, E | same; last: `GPL-2.0-or-later`, MIT dropped (D3) | stated_qualifier |
| 22 | `GPLv2 or later`, `GPLv3 or later`, `GPL v2+`, `GPLv2+`, `GPLv3+`, `LGPLv2.1+`, `AGPLv3+`, `GNU General Public License v2 or later (GPLv2+)` | none | noise: `LPPL-1.2` t0.74, `LiLiQ-R-1.1` t1.00, `GPL-3.0-or-later` t0.86 | version_spelling + stated_qualifier or plus_to_or_later |
| 23 | `eCos-2.0`, `Nunit`, `wxWindows`, `StandardML-NJ`, `BSD-2-Clause-FreeBSD` | unchanged, E (successor rows exist for 6 ids only) | same | exact (deprecated; successor offered) |
| 24 | `MIT/Apache-2.0`, `MIT / Apache-2.0`, `Apache-2.0/MIT`, `MIT & Apache-2.0`, `MIT, Apache-2.0`, `Dual MIT/Apache` | none (`/` is OR in `Cargo.toml` only) | noise (`Pixar`, `ECL-2.0` t0.86) | expression_repair |
| 25 | `MIT or Apache 2.0` | none; `normalize_identifier`: `MIT OR Apache 2.0` | noise | lexical + separator |
| 26 | `https://spdx.org/licenses/MIT.html`, `https://opensource.org/licenses/MIT`, `http://www.apache.org/licenses/LICENSE-2.0` | `MIT`, `MIT` (last path segment); none | noise; `Apache-2.0` n1.00 | listed_url |
| 27 | `Proprietary`, `proprietary`, `Commercial`, `Other`, `other`, `Other/Proprietary License`, `All rights reserved`, `See LICENSE`, `see LICENSE file` | none | noise at t1.00 (`GFDL-1.1-only`, `APSL-1.2`, `Aladdin`) | unresolved |
| 28 | `UNLICENSED`, `UNKNOWN`, `NONE`, `NOASSERTION` | none | `Unlicense` t0.90 (npm's keyword for *no* licence); `CC0-1.0` t1.00; GFDL t1.00; none | unresolved (Pitloom reads the last three first) |
| 29 | `llama3.1`, `llama2`, `Llama 3.1 Community License`, `gemma`, `OpenRAIL`, `openrail`, `openrail++`, `creativeml-openrail-m`, `bigscience-openrail-m`, `licenseref-foo` | none (`normalize_identifier('openrail++')` = `openrail+ +`) | none or noise (`ECL-1.0` t0.74) | unresolved |
| 30 | `MIT OR`, `GPL-2.0-only+`, a sentence of MIT text | none; `GPL-2.0-only+` E (D2); none | noise; same; `Clips` t1.00 | malformed; malformed; text detection |

### 2.1 What 0.5.0 can report, per category

| 0.5.0 | Categories |
| - | - |
| Reported, distinguishable | `listed_name` (method `name`, `exact: True`: the one clean signal) |
| Produced, but reported as `exact`/`id` | `lexical`, `separator` (ASCII only, no letter-digit split), `plus_to_or_later`, `assumed_only` (silent), `stated_qualifier` (listed id plus a grant phrase only) |
| Partly, by other means | `version_spelling` (before a `+` by shortest prefix; `Apache 2` by fuzzy name), `alias` (token-set fuzzy, indistinguishable from wrong hits), `listed_url` (field path: last segment of any `/licenses/` URL), `deprecated_equal_successor` and `deprecated_ambiguous` (6 rows plus a `-with-` table), `expression_repair` (`/` in `Cargo.toml`) |
| Always on, unlabelled | `fuzzy` (text input; 1.00 on unrelated licences) |
| Not reported | `ambiguous` (a ranked tie with a first entry), `unresolved`, `malformed` (empty on the field path, noise on the text path) |

Every decision in families B and C is hidden behind `exact: True` or a score.

### 2.2 Defects found (upstream report)

| Id | Defect |
| - | - |
| D1 | `GPL-2+` gives `GPL-2.0-only+` (`is_spdx: true`): the shortest-prefix lookup picks `-only`, then re-attaches `+`. |
| D2 | `GPL-2.0-only+` is accepted as an exact id (`+` after `-only`/`-or-later` is meaningless). |
| D3 | `MIT OR GPL-2.0 or later`: `normalize_identifier` and the text path give `GPL-2.0-or-later` (MIT dropped); the field path is right. |
| D4 | `normalize_identifier` mangles tokens it does not know: `openrail++` to `openrail+ +`; `GPLv2 or later` to `GPLv2 OR later` (prose "or" made an operator). |
| D5 | Few-word text input scores 1.00 for unrelated licences (`Proprietary`, `UNKNOWN`, `GPLv2`); `UNLICENSED` gives `Unlicense` 0.90. |
| D6 | `zlib/libpng` gives `zlib-acknowledgement`, a different licence (`Zlib` is meant). |
| D7 | A tie at score 1.00 is a ranked list with a first entry (`Apache` gives `Apache-1.0` first). |
| D8 | The TOML manifest reader skips a basic string with an escape (`"  MIT\t"`). |
| D9 | `exact: True` is reported for rewritten values (separator, `-only`). |

Pitloom finding (fixed): a Hugging Face card's `license: gpl-3.0` went
through `canonicalize_license_id` and was recorded as `GPL-3.0-only`, with no
`Normalized-From` or `Deprecated-License-Id` (the raw value never reached the
builder); without a database it was `GPL-3.0` plus the note. A silent
`assumed_only` on one surface. The Hugging Face route now records the card
value as stated; the builder's classification does the rest.

## 9. What Pitloom needs from LicenseID 0.5.1

R1. `resolve(value, *, field_kind="spdx", allow_fuzzy=False)`, never raising
on content (an unresolvable value is a category), returning: `input`;
`expression` (canonical, or `None` unless every operand is accepted);
overall `category` and `trust`; `operands` in input order, each with its
span, text, result, category, `steps` (A and B, applied order),
`expansions` (C, applied or offered) and `candidates` (sorted by id); and
`resolver` and `lists` (R1a). A step is `{kind, applied, from, to, detail}`, `detail` holding
the rule, alias source, matched name or score.

R1a. Who resolved it, from which lists. `resolver`: `{name, version, url,
purl}` (`LicenseID`, `0.5.1`, the release tag URL, `pkg:pypi/licenseid@0.5.1`).
`lists`: every list the data was built from, sorted by `id`, each `{id, name,
version, url, license, provides, id_authority, data_sha256}`: `id` a stable
slug (`spdx-license-list`, `scancode-licensedb`); `version` the list's own
(`3.29.0`, `2026-06-20`); `url` a versioned, permanent one where the list has
one (the release tag), else its index plus `data_sha256` of the snapshot read;
`license` the data's licence (an attribution duty is Pitloom's to carry);
`provides` a subset of `ids`, `names`, `urls`, `deprecation`, `aliases`;
`id_authority` true for the list whose ids the result's expression uses (the
SPDX License List: its version is the `simplelicensing_licenseListVersion`; a
ScanCode key is no SPDX id, it would be a `LicenseRef-`). Beside them
`data`: `{source: "database" | "bundled", normalization_version, sha256}` (the
database file, or the packaged snapshot, actually read). Each step, alias
and candidate names the list that supported it (`list`: an `id` above), so a
result says which list made which decision, not only which lists were loaded.
`provides` is a closed vocabulary (decided 2026-10-26: `ids`, `names`, `urls`, `deprecation`,
`aliases`, `texts`), owned by the LicenseID spec and extended with a release;
a consumer ignores a value it does not know, and a step that cites a list
for a kind it does not provide is a bug in the resolver (each step kind needs
one: `listed_name` `names`, `listed_url` `urls`, `deprecated_*` `deprecation`,
`alias` `aliases`, `separator` and `version_spelling` `ids`). Deterministic; no
clock. Pitloom writes `resolver` and `lists` once per SBOM and per-field
provenance cites list ids.

R1b. Alias review. An alias is a claim that a string means exactly one
licence, so a wrong one writes a wrong licence into SBOMs. (1) A list's own
data is its owner's to review. (2) An entry LicenseID adds itself comes by
pull request with its evidence (the source list entry, or real usage in
package metadata), an automated uniqueness check (one id; no clash with any
id, name or other alias), a corpus regression test and a second reviewer. (3)
A list version bump is reviewed as a diff report (aliases added, removed,
changed). (4) Pitloom decides which `source` it accepts for each category
(an allow-list in Pitloom): a new list changes no SBOM until Pitloom adds it.

### Tool modelling (proposed 2026-10-26)

Only the generator in `createdUsing`; the licence resolver as a second
`Tool`, linked `Pitloom usesTool LicenseID`. The `LicenseID` Tool carries
`name`, the version in `summary` (as for Pitloom), `pkg:pypi/licenseid@...` in
`externalIdentifier` and the release URL in `externalRef`; it is minted only
when the resolver contributed to a recorded value; per-field provenance cites
it. Why: every consumer and checker that reads `createdUsing` (CISA's tool name
and version, FSCT) still finds exactly one generator, and the helper's role is
structural, not a convention in a comment. A caller who sets `tools` (Lumina)
keeps its Tools in `createdUsing` and Pitloom hangs under them by the same
relationship. `usesTool` exists in the v3.0.1 bindings; its from/to
constraints in the spec text were not re-read here. Experiment (2026-10-26,
spdx3-validate 0.0.7 with the vendored 3.0.1 model, schema plus SHACL): a
`Relationship` with `usesTool`, `from` a `Tool` and `to` a `Tool`, both
Tools in `@graph`, validates with no finding; a negative control (an unknown
`relationshipType`) is rejected, so the pass is not vacuous. The same
relationship with `to` an `Agent` also validates: SHACL does not constrain
the `to` class for `usesTool`, so validity does not prove the Tool-to-Tool
reading; consumers rely on the convention. Gap: FG-8 in
[sbom-format-gaps.md](sbom-format-gaps.md).

R2. Step kinds, stable string values: A `trim`, `whitespace`, `id_case`,
`operator_case`, `ref_prefix_case`, `brackets`, `reorder`, `dedupe`; B
`separator`, `version_spelling`, `listed_name`, `alias`, `listed_url`,
`deprecated_equal_successor`, `deprecated_ambiguous`, `expression_repair`, `fuzzy`; C `plus_to_or_later`,
`stated_qualifier`, `assumed_only`. Categories add `exact`, `lexical`,
`ambiguous`, `unresolved`, `malformed`.
R3. Expansions never in `steps`; `assumed_only` and `deprecated_ambiguous`
only ever `applied: False` with both or all candidates.
R4. On ambiguity, all candidates (sorted by id, with a total) and
`expression: None`; no first choice, no shortest prefix.
R5. `alias` from data, one row per (string, id, source), shipped in the
wheel; a string with two targets is ambiguous.
R6. `separator` rules checked at build time to cause no collision on the
List; `+` never folded.
R7. `fuzzy` only with `allow_fuzzy=True`: algorithm, score, threshold and the
matched name in `detail`; never `exact`.
R8. `exact` means input equals output; `lexical` means A steps only.
R9. Per-operand results for expressions; never drop an operand (D3).
R10. Declared-value resolution from the packaged data, no built database.
R11. `versions`: LicenseID version, List version, and a `data_version` hash
of the List snapshot, normalisation version and tables; no network, no
clock, no randomness; same input and versions give the same bytes.
R12. Idempotent: `resolve(r["expression"])["category"] == "exact"`.
R13. Fix D1 to D9, each with a test.

**Do not:** apply `-only` anywhere (bare or `-with-` ids, prefix
completion, `+` re-attach); read `/`, `&`, `,` as operators outside a
manifest that defines them; run the text tier on an id- or
expression-shaped value; map `UNLICENSED`, `UNKNOWN`, `NONE`, `Other`,
`Proprietary`; rewrite an unknown token; put an expression in a field typed
as one id.
