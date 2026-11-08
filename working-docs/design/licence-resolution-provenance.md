---
Created: 2026-10-29
Last-Modified: 2026-11-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Licence resolution provenance: one entry, a segment per operand

See also: [implementation/licenseid/](../implementation/licenseid/README.md)
(the LicenseID adoption, built, and its upstream findings),
[license-resolution-categories.md](license-resolution-categories.md)
(categories, `Resolution-n`, Q1 to Q7),
[evidence-levels.md](evidence-levels.md),
[message-catalogue-and-skills.md](message-catalogue-and-skills.md),
[provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md)
(the `Method`/`Role` taxonomy), [sbom-format-gaps.md](sbom-format-gaps.md)
(FG-6 to FG-8) and [roadmap.md](roadmap.md).

Status: design; supersedes PR #384. Facts were read in the code and probed
with LicenseID (SPDX License List 3.29.0, packaged).

Two pieces, on two schedules:

- **Per-operand provenance** (sections 3 to 6, 8 to 10): new segments
  (`Resolution-<n>` per operand, `License-List`, `Reason`) that the planned
  `--provenance` flag adds. It waits for that flag and for the provenance
  taxonomy (roadmap 0.24.0, rulings of 2026-11-05).
- **`licenseListVersion`** (section 7): an SPDX 3 property on the licence
  element, not provenance. It ships independently.

## 1. What `resolve()` gives

`licenseid.resolve(value, db=None, *, source="auto"|"database"|"packaged")`
returns a `Resolution` (typed dict, `schema` 2):

| Field | Content |
| - | - |
| `schema`, `input` | `2`; the value as given |
| `expression` | the canonical SPDX expression, or `None` when no reading |
| `category`, `trust` | the whole value's: the weakest operand's, or `lexical` for a change of form (a reorder) |
| `steps`, `expansions` | applied steps of the whole value; qualifier steps apart |
| `candidates` | the possible successors of a kept deprecated id |
| `operands` | one per leaf, in input order (below) |
| `resolver` | `name`, `version`, `url`, `purl` of LicenseID |
| `components` | other software that read the value (`py-spdx-license` when its parser ran) |
| `lists` | each list the answer rests on (below) |
| `reason` | why there is no expression (`not found: Foo`, `operand not resolved: Foo`), else `None` |

- **`Operand`:** `text`, `span` (start and end in the input), `expression`
  (`None` when that leaf is not read), `category`, `trust`, `steps`,
  `expansions`, `candidates`, `reason`. An unresolved compound keeps the
  readings of its other operands (`Apache2 OR Foo`: `Apache2` is
  `Apache-2.0`, `version_spelling`; `Foo` is `unresolved`, `not found: Foo`).
- **`Step`:** `kind`, `applied`, `from`, `to`, `list` (the list that
  supported it), `detail`.
- **`ListInfo`:** `id` (`spdx-license-list`, `pypi-trove-classifiers`),
  `name`, `version` (`3.29.0`; the trove list `2026.9.21.13`), `source`
  (`database` or `packaged`), `url`, `license`, `provides`, `id_authority`
  (true for the SPDX License List). Every answer, `MIT` included, lists
  the SPDX License List.
- **Categories** (`CATEGORY_ORDER`): `exact`, `lexical`, `listed_name`,
  `deprecated_equal_successor`, `plus_to_or_later`, `stated_qualifier`,
  `separator`, `version_spelling`, `prose_form`, `text_title`, `alias_name`,
  `trove_name`, `deprecated_ambiguous`, `assumed_only`, `malformed`,
  `unresolved`. `text_title` and `alias_name` have trust
  `resolver_rule`. Trust: `identity`, `list_data`, `author_words`,
  `resolver_rule`, `none`.
- **Lexical step kinds** (`LEXICAL_KINDS`, form only): `brackets`,
  `dedupe`, `id_case`, `operator_case`, `reorder`, `trailing_name`, `trim`,
  `trove_path`, `unquote`, `whitespace`.
- `detect()` returns `Detection`s; each carries `lists` in the same shape
  (`source: database`).

**What the SBOM must say about one licence decision:** the value as written;
whether the resolver decided anything beyond form; per operand, what it was
read as and by which kinds of step; a qualifier written out (`+`, "or
later"); a deprecated id kept or renamed; which tools read it, with
versions; which list (version and source) the decision rests on; and, for a
value not read, that it was not and why.

## 2. Today (Pitloom 0.23.0)

- **One reading.** `_resolved` in `src/pitloom/extract/_license_resolve.py`
  calls `resolve(value, source="packaged")` once per value (an LRU cache):
  the answer depends on the installed LicenseID alone, never on a database.
  `resolve_value` reduces it to a `DeclaredResolution` (expression,
  category, step kinds, expansion kinds, `decided`, `tool`, ambiguous
  deprecated ids).
- **The entry.** One entry per element and field, `{"license": "Key: v |
  Key: v"}`, parsed by `parse_provenance_value`
  (`src/pitloom/core/provenance.py`): keys lower-cased, a repeated key keeps
  the last value. `provenance_segment` accepts only the keys of
  `PROVENANCE_SEGMENT_KEYS` and the numbered `Resolution-<n>` and
  `Expansion-<n>`; `Evidence` and `Reason` are written only by
  `evidence_segment` (`src/pitloom/core/evidence.py`), and `Reason` only
  after `Evidence: not_measured`.
- **The segments.** `tag_license_normalization`
  (`src/pitloom/extract/_license_classify.py`) writes `Normalized-From` when
  the value changed, then `resolution_notes`
  (`_license_resolve.py`): `Method: licenseid_resolution` and
  `Resolution-1` (the whole value, `<value> -> <expression> (<kinds>)`) when
  the resolver decided beyond form; `Expansion-1` (kinds only) for a
  qualifier; `Tool: licenseid==X`. `tag_deprecated_license_ids` adds
  `Deprecated-License-Id` for a kept deprecated id with ambiguous successors.
  Detection writes `Method: licenseid_detection | Tool: licenseid==X`
  (`_with_tool_tag` in `src/pitloom/extract/_license.py`).
- **Gone:** the `Normalizer: py-spdx-license==Y` segment of 0.22.x. No
  `components` entry is cited, so `py-spdx-license` appears nowhere.
- **Where.** The element a source creates carries the entry
  (`_get_or_create` in `src/pitloom/assemble/spdx3/_license_elements.py`);
  a reused element puts a noted source's entry on the relationship
  (`src/pitloom/assemble/spdx3/deps_license.py`). `emit_provenance`
  (`src/pitloom/assemble/spdx3/provenance.py`) writes a `comment`, an
  `Annotation` or both. `minimal` keeps an entry with a `method`,
  `normalized-from`, `deprecated-license-id`, `evidence`, a classifier
  field or a non-manifest source (`_is_high_signal` in
  `src/pitloom/assemble/spdx3/_provenance_encoders.py`).
- Only `LicenseExpression` and `SimpleLicensingText` are built; no element
  sets `licenseListVersion`.

**Probed outcomes** (`loom project` on a one-file `pyproject.toml`,
`format = "both"`, `detail = "minimal"`, the defaults; the entry beyond
`Source: pyproject.toml | Field: project.license`):

| Value | Element | Recorded entry |
| - | - | - |
| `MIT` | `MIT` | none (dropped in `minimal`) |
| `GPL-2.0+` | `GPL-2.0-or-later` | `Normalized-From`, `Expansion-1: plus_to_or_later`, `Tool` |
| `MIT OR Apache-2.0` | `Apache-2.0 OR MIT` | `Normalized-From`, `Tool` |
| `Apache2` | `Apache-2.0` | `Normalized-From`, `Method`, `Resolution-1: Apache2 -> Apache-2.0 (separator, version_spelling)`, `Tool` |
| `StandardML-NJ` | `SMLNJ` | `Normalized-From`, `Method`, `Resolution-1: ... (deprecated_equal_successor)`, `Tool` |
| `GPL-2.0` | `GPL-2.0` | `Deprecated-License-Id: GPL-2.0 (GPL-2.0-only or GPL-2.0-or-later)` |
| `Apache2 OR gpl-2.0+` | `Apache-2.0 OR GPL-2.0-or-later` | `Normalized-From`, `Method`, `Resolution-1` (whole value; kinds `separator, version_spelling, id_case`), `Expansion-1: plus_to_or_later`, `Tool` |
| `BSD-3` (`license.text`) | `BSD-3-Clause` | `Normalized-From`, `Method`, `Resolution-1: ... (alias_name)`, `Tool` |
| `Apache2 OR Foo` | text | none; `WARNING:` on stderr only |
| `Acme-Terms` | text | none; `WARNING:` on stderr only |
| classifiers `MIT License` and `Python Software Foundation License` | `MIT AND LicenseRef-pitloom-classifier-...` | `Field: project.classifiers` only; the reading of `MIT License` is on stderr only |
| one classifier `GNU General Public License v3 or later (GPLv3+)` | `GPL-3.0-or-later` | `Normalized-From`, `Method`, `Resolution-1: ... (trove_name)`, `Tool` |
| `LICENSE` file, MIT text, no `license` | `MIT` | `Source: LICENSE | Method: licenseid_detection | Tool` |

Gaps: `Resolution-1` names the whole value and every kind, so a reader
cannot tell which operand was re-spelt; lexical kinds (`id_case`) are
listed beside decided ones; a reading inside the classifier `AND` and an
unread declaration leave no trace in the SBOM; no list version is
recorded.

## 3. Scope: what `--provenance` adds, and what waits for the taxonomy

The rulings of 2026-11-05 (roadmap 0.24.0, "Provenance and source-metadata
flags"): provenance annotations go off by default, behind `--provenance`
(name to settle), because they make the SBOM large and the taxonomy is not
settled. So:

- **A default SBOM carries none of this design.** Not the new segments, nor
  today's `Normalized-From`, `Resolution-1` or `Tool`. What a default SBOM
  says about a licence is the element, its relationship type (declared or
  concluded) and `licenseListVersion` (section 7).
- **With `--provenance`**, the entry gains per-operand `Resolution-<n>` and
  `Expansion-<n>`, `License-List` and, for an unread SPDX-only field,
  `Reason`. Its detail level (`minimal`, `full`) still filters it.
- **Waits for the taxonomy** (`Method` vs `Role`, the source and role
  vocabulary,
  [provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md),
  [license-rules.md](license-rules.md)): whether `licenseid_resolution`
  and `licenseid_detection` stay `Method` values or become a role; whether
  `Tool` and `License-List` are sources, roles or their own keys; and
  whether `Reason` may stand without `Evidence` (today it may not). The
  segment names below are working names; the mapping (which `Resolution`
  field feeds which fact) does not depend on them.
- **Does not wait:** the renderer and the stored answer (section 9, task 1)
  change no output and can land at any time.

## 4. The mapping

| `Resolution` field | Segment |
| - | - |
| `input` | `Normalized-From` (exists), if the value changed |
| `category` beyond form and `+` | `Method: licenseid_resolution` (exists) |
| `operands[n]`, decided step | `Resolution-<n>` |
| `operands[n]`, `expansions` | `Expansion-<n>` |
| `candidates` of a kept deprecated id | `Deprecated-License-Id` (exists) |
| `resolver`, `components` | `Tool` (one segment, a comma list) |
| `lists[*]` cited by a step, with `source` | `License-List` |
| `lists[id_authority].version` | `licenseListVersion` property (section 7) |
| no expression, SPDX-only field | `Reason: <code>`, plus the blocking operands |

Rules:

1. **One entry.** All segments sit in the source's one `license` entry; no
   field per operand, no `Count:`. Operands are visible in
   `Normalized-From`. Size is bounded: only decided operands get a segment,
   and a value read is at most 200 characters
   (`_MAX_EXPRESSION_LENGTH` in `_license_classify.py`).
2. **`n` is the 1-based operand position in the input**, never compacted and
   never the output order, so a change of LicenseID's canonical order
   changes no key. A value of one leaf is operand 1, as today.
3. **Rendering:** `<operand text> -> <operand expression> (<kinds>)`, the
   kinds in applied order, each once, lexical kinds (`LEXICAL_KINDS`) left
   out; `Expansion-<n>` the same over the operand's `expansions`. An
   operand with no expression: `<text> (<category>)`, no arrow.
4. **`Tool` and `License-List` go with `Normalized-From`** when a
   `resolve()` answer produced it; `License-List` names each list a step
   cites (`Step.list`). An exact value carries neither, so an
   `MIT` project's provenance does not depend on LicenseID's version.
   `Tool` lists the resolver first, then `components` by name; two `Tool:`
   segments would lose the first (the parser keeps the last).
5. **One writer** renders from the answer that made the value: the
   classification carries the `Resolution`, never a second `resolve()` call
   (today `resolution_notes` resolves again; the LRU cache hides the cost,
   not the duplication). Every value goes through `provenance_segment`
   (a `|` becomes `/`).

Worked cases with `--provenance`; `S` = `Source: pyproject.toml | Field:
project.license`, `N` = `Normalized-From: <value>`, `M` = `Method:
licenseid_resolution`, `T` = `Tool: licenseid==<version>,
py-spdx-license==0.0.1`
(`py-spdx-license` only when `components` names it), `L` = `License-List:
spdx-license-list==3.29.0 (packaged)`:

```text
1 MIT                    S                          (full detail only)
2 GPL-2.0+               S | N | T | L
    Expansion-1: GPL-2.0+ -> GPL-2.0-or-later (plus_to_or_later)
3 Apache2 OR gpl-2.0+    S | N | M | T | L
    Resolution-1: Apache2 -> Apache-2.0 (separator, version_spelling)
    Expansion-2: gpl-2.0+ -> GPL-2.0-or-later (plus_to_or_later)
  MIT OR Apache-2.0      S | N | T     (a reorder only; no step cites a list)
4 StandardML-NJ          S | N | M | T | L
    Resolution-1: StandardML-NJ -> SMLNJ (deprecated_equal_successor)
5 classifier             Source: pyproject.toml | Field: project.classifiers
  "GNU General Public License v3 or later (GPLv3+)"   N | M | T
    Resolution-1: GNU ... (GPLv3+) -> GPL-3.0-or-later (trove_name)
    License-List: pypi-trove-classifiers==2026.9.21.13 (packaged)
  several classifiers: n is the position in the sorted names
6 BSD-3                  S | N | M | T | L
    Resolution-1: BSD-3 -> BSD-3-Clause (alias_name)
7 Apache2 OR Foo         S | Reason: licence-unresolved
    Resolution-2: Foo (unresolved)          (the blocking operand only)
  MIT OR                 S | Reason: licence-malformed
8 LICENSE text matched   Source: LICENSE | Method: licenseid_detection | T
    License-List: spdx-license-list==3.29.0 (database)
```

Case 3 today writes one `Resolution-1` for the whole value with `id_case`
among its kinds. Case 4 has no `Deprecated-License-Id`: the shipped code
notes only an id with ambiguous successors. Case 7 is a declaration, not a
missing measurement: the value is recorded verbatim on
`hasDeclaredLicense`, so it is not `not_measured`; what is missing is the
SPDX reading. A free-text field (Core Metadata `License`) gets no `Reason`:
it never claimed SPDX. `minimal` drops case 7 today (no key it keeps):
`_is_high_signal` must keep an entry with `reason`.

## 5. Where it attaches

Unchanged: the entry rides on the element the source created, else on its
relationship; a named individual's always on the relationship. One
`LicenseExpression` holds the whole expression, so operand evidence rides
as numbered segments of its entry. Rejected: a `ListedLicense` or
`CustomLicense` per operand (new elements and ids, a declared licence no
longer one expression, and still no property for a step). The classifier
`AND` (`_classifier_and` in `_license_elements.py`) passes the source entry
unchanged to the expression and to each `SimpleLicensingText`; with
`--provenance` its expression gets one `Resolution-<n>` per term read, `n`
the position in the sorted names. The shared-element first-wins bug
([known-bugs.md](known-bugs.md)) stays.

## 6. `Resolution-n`

Origin: categories section 7 (operand `n` as written, its result and decided
steps; `Expansion-n` its qualifier step). Built for `n = 1` as the whole
value; operands are now available. Final names:
`Resolution-<n>`, `Expansion-<n>`, `Tool`, `License-List`, `Reason`.
`License-List-Version` and `Resolver-Data`
([license-resolution-categories.md](license-resolution-categories.md),
section 7) are dropped: the version is the property of section 7 here, and
`ListInfo` has no data hash.

## 7. `licenseListVersion` (ships independently)

**What.** SPDX 3.0.1 `simplelicensing_licenseListVersion`, "the version of
the SPDX License List used in the license expression". In
`spdx_python_model.bindings.v3_0_1` it is a property of
`simplelicensing_LicenseExpression` only: `SimpleLicensingText`,
`expandedlicensing_ListedLicense` and `CustomLicense` reject it
(`ListedLicense` has `expandedlicensing_listVersionAdded`, another fact).
Its value must match a SemVer pattern: `3.29.0` passes, `3.29` and
`v3.29.0` fail.

**Not provenance.** It is a property of the element, read by any SPDX
consumer, so it does not wait for `--provenance` or the taxonomy, and a
default SBOM carries it.

**Value.** The `version` of the `lists` entry with `id_authority` true in
the `Resolution` that made the expression. Pitloom builds every
`LicenseExpression` in `_get_or_create` from a value `classify_license`
read (a detected id is classified too), except the classifier `AND`,
whose terms `license_from_classifiers` (`_core_metadata.py`) reads with
`resolve_value`. Every answer is read on the packaged List, so one run has
one version. Carry it on `DeclaredResolution` and `ClassifiedLicense` (one
constructor helper sets it at every call site), take the classifier
`AND`'s from its terms, and set it in `_get_or_create`. Detection's
database list is the text match's evidence, not the List the expression
uses: it goes to `License-List (database)` under `--provenance`, not here.

**Determinism.** A function of the installed LicenseID (its packaged
List), which a lock file pins; no database, `HOME` or clock. Upgrading
LicenseID to a newer List changes the bytes, as it should: the version is
an input. A fragment's expression unified with a built one
(`license_key`) should keep the built element's version; a fragment that
states another version for the same expression is a conflict to note, not
to overwrite (open decision 7).

**Format-gap ledger.** [sbom-format-gaps.md](sbom-format-gaps.md) FG-6 (the
value as written), FG-7 (how a licence was identified; it names this
property as the nearest) and FG-8 (which `Tool` is the generator) exist
and still say what #384 relied on; FG-6 and FG-7 called the built
segments "design", corrected on 2026-11-07. The property records the List
version precisely, so it needs no new entry; the method and the tool
(FG-7, FG-8) stay gaps.

**Tests.** Per surface (CLI, library, hook, a wheel's `License-Expression`,
a GGUF `general.license`, a dataset card, a detected `LICENSE`, the
classifier `AND`): the property equals
`resolve("MIT", source="packaged")["lists"]` id-authority version; absent on
`SimpleLicensingText` and on the named individuals; schema and SHACL valid;
the same bytes twice and across `PYTHONHASHSEED`; a merge keeps the built
element's value. One test reads the version from LicenseID, never a literal
`3.29.0`. Update the few golden SBOMs and the manual checks' baselines.

**Size: S** (one field through two dataclasses, one setter, about ten
tests; golden SBOMs regenerated).

## 8. Interactions

- **Message catalogue:** the licence family codes come with catalogue PR 18
  ([message-catalogue-migration-plan.md](message-catalogue-migration-plan.md)
  proposes `expression-malformed`, `licence-not-recordable`,
  `licence-ambiguous`); `licence-unresolved` and `licence-malformed` in case
  7 are working names. The `Reason` code equals the code of the stderr line,
  which stays whatever `--provenance` says.
- **Evidence levels:** `Tool` names the software that decided the reading,
  `Method` how; neither is `Evidence`, which licence entries never write.
  A licence's level follows its relationship type, chosen by source
  (`is_license_concluded`): the package's own statement, a `LICENSE` file
  matched by detection included, is `hasDeclaredLicense`; a third-party
  record is `hasConcludedLicense`. `Reason` without `Evidence` needs
  `evidence_segment` (or a sibling writer) to allow it: a taxonomy
  decision.
- **Detail levels:** a decided entry has `Normalized-From`, so `minimal`
  keeps it; case 7 needs the `reason` key; case 1 is `full` only.
- **Fragments:** a fragment licence is unified by `license_key`
  (`_license_elements.py`, via `classify_license`), the dropped element's
  comment not folded; its relationship is added beside the generated one.
- **ID registry:** licence and Annotation ids are counters, not registry
  keys; the dedup key stays `(kind, canonical value)`, never the list
  version or provenance.
- **Determinism:** the entry depends on the value, the LicenseID version and
  the packaged List, all stated inputs; detection entries also on the
  database (`License-List (database)` says which).
- **Upstream** ([upstream-issues.md](../implementation/licenseid/upstream-issues.md)):
  `components` is empty for most answers (finding 8), so `Tool` cites
  `py-spdx-license` only for some values; a no-break space re-spelt without
  a step (finding 10) leaves no `Resolution-n` trace.

## 9. Tasks and order

| # | Task | Waits for |
| - | - | - |
| 1 | Renderer from the stored answer (`ClassifiedLicense` carries the `Resolution`), a sweep mode printing each entry; no output change | nothing |
| 2 | `licenseListVersion` (section 7) | nothing |
| 3 | Per-operand `Resolution-<n>`, `Expansion-<n>`, `Tool` list, `License-List` | the flag, the taxonomy |
| 4 | `Reason` in SPDX-only fields, `minimal` keeps `reason` | 3, catalogue PR 18 |
| 5 | Classifier `AND`: `Resolution-<n>` per sorted name | 3 |
| 6 | Licence provenance docs, skills grep, CHANGELOG | each PR |

Tests for 3 to 5: a parametrised case per worked case (each key once, `Tool`
holds both names); `minimal` keeps case 7; a reused element's entry on the
relationship; `|` and a newline escaped; the same bytes twice, across
processes and `PYTHONHASHSEED`; nothing new without `--provenance`; the
adoption sweep before and after, each changed entry explained. Risks: churn
in every non-exact entry; a second `Tool` writer; `minimal` silently
dropping a new negative entry.

## 10. Open decisions (recommended answer in brackets)

1. Flag name and scope: does `--provenance` also gate today's
   `Normalized-From`, `Resolution-1` and `Tool`? [yes: the ruling turns
   all provenance off by default; the stderr lines stay]
2. `Tool`: one comma list, resolver first, `components` after. [yes]
3. `License-List` segment for each list a step cites, with its source.
   [yes]
4. `Expansion-n` as `from -> to (kind)`, not kinds only as today. [yes]
5. Lexical kinds out of `Resolution-n`. [yes; they are form, which
   `_FORM_ONLY` already keeps out of the `INFO:` line]
6. `Reason` for SPDX-only fields only, free text quiet; whether it may stand
   without `Evidence`. [SPDX-only only; the second waits for the taxonomy]
7. `licenseListVersion` from a fragment that differs from the built one.
   [keep the built value; say the conflict with `INFO:`]
8. `License-List (database)` on detection entries, from `Detection.lists`.
   [yes, with task 3]

Settled since #384 by the shipped code or later rulings: one entry with
numbered segments (built); `source="packaged"` for declared values (built,
no `auto`); no `Deprecated-License-Id` for an equal successor (built:
ambiguous ids only); the cache keyed on the value, not the answer (built);
`Expansion-1` for `GPL-2.0+` (built); structured operands in the Annotation
(no; waits for `--report`); `licenseListVersion` split from the provenance
work (this page).
