---
Created: 2026-10-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Licence resolution provenance: one entry, a segment per operand

See also: [licenseid-0-7-adoption.md](licenseid-0-7-adoption.md) (T13, the
adoption; this is T14),
[license-resolution-categories.md](license-resolution-categories.md)
(categories, `Resolution-n`, Q1 to Q7), [roadmap.md](roadmap.md),
`evidence-levels.md` and `message-catalogue-and-skills.md` in this folder once
merged, [sbom-format-gaps.md](sbom-format-gaps.md) (FG-6 to FG-8).

Status: design, 2026-10-29. Facts were read in the code of `main` b18e2cce
and licenseid `origin/main` 1dd6b38 (T0 to T4 built, T5 onwards not), and
probed with licenseid 0.6.0 and SPDX License List 3.29.0. "Planned" means a
licenseid plan, not code.

## 1. What `resolve()` gives

**Verified** (`origin/main` `src/licenseid/resolvertypes.py`, the same as the
installed 0.6.0): `Resolution` has `input`, `expression` (`None` when no single
reading), `category`, `trust`, `steps`, `expansions`, `candidates`, `resolver`
(`name`, `version`, `url`, `purl`) and `lists` (`id`, `name`, `version`, `url`,
`license`, `provides`, `id_authority`). A `Step` has `kind`, `applied`, `from`,
`to`, `list`, `detail`. `Category` still holds `expression` (a compound: no
expression, so Pitloom records text).

**Planned for 0.7.0** (licenseid `resolver-0-7-plan.md` section 4, tasks T5 to
T9): `schema: 2`; `operands` (per leaf: `text`, `span`, `expression`,
`category`, `trust`, `steps`, `expansions`, `candidates`, `reason`);
`components` (`py-spdx-license` when its parser ran); `reason`; `Step.by`
(always `""` in 0.7.0); `ListInfo.source` (`database` or `packaged`); a
`pypi-trove-classifiers` list; categories `prose_form`, `trove_name`;
`expression` removed; `source="auto"|"database"|"packaged"`, the newer list
winning under `auto`. None of these exists in code yet; every rule below that
reads one is written against the plan and is re-checked at the release.

**What the SBOM must say about one licence decision:** the value as written;
whether the resolver decided anything beyond form; per operand, what it was
read as and by which kinds of step; a qualifier written out (`+`, "or
later"); a deprecated id kept or renamed; which tools read it and their
versions; which list (version and source) the decision rests on; and, for a
value not read, that it was not and why.

## 2. Today (facts)

- One entry per element and field, `{"license": "Key: v | Key: v"}`, read by
  `parse_provenance_value` (`core/provenance.py:107-123`): keys lower-cased,
  **a repeated key keeps the last value** (line 118).
- `tag_license_normalization` (`extract/_license_classify.py:450-466`) writes
  `Normalized-From`, then `resolution_notes` only if Pitloom's own parse failed
  (line 462), then `Normalizer: py-spdx-license==Y`. `resolution_notes`
  (`extract/_license_resolve.py:130-151`) resolves again and writes `Method:
  licenseid_resolution`, `Resolution-1` (whole value), `Expansion-1` (kinds
  only), `Tool: licenseid==X`. `Deprecated-License-Id`: lines 485-491.
  Detection: `Method: licenseid_detection | Tool: ...` (`_license.py:510-532`).
- The created element carries the entry (`_license_elements.py:150-159`); a
  reused one puts a noted source's entry on the relationship
  (`deps_license.py:80-90`); `emit_provenance` writes a `comment`, an
  `Annotation` or both (`assemble/spdx3/provenance.py:421-476`). `minimal`
  (the default) keeps an entry only with a `method`, `normalized-from`,
  `deprecated-license-id`, a classifier field or a non-manifest source
  (`_provenance_encoders.py:59-74`).
- Only `LicenseExpression` and `SimpleLicensingText` are built (no
  `ListedLicense`, `CustomLicense`); `licenseListVersion` is never set.

Probed outcomes (licenseid 0.6.0):

| Value | Recorded entry beyond `Source`/`Field` |
| - | - |
| `MIT` | nothing; dropped in `minimal` |
| `GPL-2.0+` | `Normalized-From`, `Normalizer`; no `Expansion-1` |
| `MIT OR Apache-2.0` | `Normalized-From`, `Normalizer` |
| `Apache2` | all of `resolution_notes` plus `Normalizer` |
| `StandardML-NJ` | nothing: kept as written, not `SMLNJ` |
| `GPL-2.0` | `Deprecated-License-Id: GPL-2.0 (GPL-2.0-only or ...)` |
| two classifiers, one `MIT License` | `MIT` recorded, no note of the reading |
| `Acme-Terms` (`project.license`) | nothing; dropped in `minimal` |

Two gaps follow: a reading inside the classifier `AND`
(`_license_elements.py:164-211` passes the provenance unchanged) and an
unresolved declaration leave no trace in a default SBOM; the `WARNING:` on
stderr is all.

## 3. The mapping

| `Resolution` field | Segment |
| - | - |
| `input` | `Normalized-From` (exists), if the value changed |
| `category` beyond form and `+` | `Method: licenseid_resolution` |
| `operands[n]`, applied B step | `Resolution-<n>` |
| `operands[n]`, applied C step | `Expansion-<n>` |
| `candidates` of a kept deprecated id | `Deprecated-License-Id` (exists) |
| `resolver`, `components` | `Tool` (one segment, a comma list) |
| `lists[*]` cited by a step, `source` | `License-List` |
| `version` of the `id_authority` list | `licenseListVersion` property |
| no expression, SPDX-only field | `Reason: <code>`, blocking operands |

Rules:

1. **One entry.** All segments sit in the source's one `license` entry; no
   per-operand field, no `Count:`. The evidence-levels rule "one entry per
   element and field" holds, operands are visible in `Normalized-From`, and
   size is bounded: only decided operands get a segment, a value is at most
   200 characters (`_license_classify.py:69`).
2. **`n` is the 1-based operand position in the input**, never compacted
   and never the output order, so a change of licenseid's canonical order
   (adoption section 2) changes no segment key. A value of one leaf is
   operand 1; with 0.6.0 (no `operands`) the whole value is operand 1.
3. **Rendering:** `<first applied step's from> -> <last applied step's to>
   (<kinds, applied order, each once>)`, over B steps for `Resolution-n` and
   C steps for `Expansion-n`; A steps are not listed. An operand with no
   expression: `<text> (<category>)`, no arrow.
4. **`Tool` and `License-List` go with `Normalized-From`** when a
   `resolve()` answer produced it. An exact value carries neither, so an `MIT`
   project's SBOM does not depend on licenseid's version. `Tool` lists the
   resolver first, then `components` by name: two `Tool:` segments would lose
   the first (rule above, probed). Read `components`, not `Step.by`.
5. **One writer** renders from the answer that made the value: the
   classification carries the `Resolution`, never a second `resolve()` call.
   It escapes `|` as `\u007c` (the comment's escape spelling);
   unreachable today, as no value holding `|` resolves.

Worked cases, one segment per line after `S` (`Source: pyproject.toml |
Field: project.license`); `N` = `Normalized-From: <value>`, `M` = `Method:
licenseid_resolution`, `T` = `Tool: licenseid==0.7.0`, `L` = `License-List:
spdx-license-list==3.29.0 (packaged)`; versions illustrative. Whether
`py-spdx-license` joins `T` for one leaf depends on `components`
(unverified). Each ran through `parse_provenance_value` (every key once) and
the `minimal` filter.

```text
1 MIT                    S                         (full detail only)
2 GPL-2.0+               S | N | T
    Expansion-1: GPL-2.0+ -> GPL-2.0-or-later (plus_to_or_later)
3 Apache2 OR gpl-2.0+    S | N | M | L
    Resolution-1: Apache2 -> Apache-2.0 (separator, version_spelling)
    Expansion-2: gpl-2.0+ -> GPL-2.0-or-later (plus_to_or_later)
    Tool: licenseid==0.7.0, py-spdx-license==0.0.1
  MIT OR Apache-2.0      S | N | Tool: ... | L      (a reorder only)
4 StandardML-NJ          S | N | M | T | L
    Resolution-1: StandardML-NJ -> SMLNJ (deprecated_equal_successor)
    Deprecated-License-Id: StandardML-NJ (SMLNJ)
5 classifier             Source: pyproject.toml | Field: project.classifiers
  "GNU General Public License v3 or later (GPLv3+)"   N | M | T
    Resolution-1: GNU ... (GPLv3+) -> GPL-3.0-or-later (trove_name)
    License-List: pypi-trove-classifiers==<v>, spdx-license-list==3.29.0
      (packaged)
  several classifiers: n is the position in the sorted names
6 Apache License, Version 2.0 (planned P2)   S | N | M | T | L
    Resolution-1: Apache License, Version 2.0 -> Apache-2.0 (prose_words)
7 Apache2 OR Foo         S | Reason: licence-unresolved
    Resolution-2: Foo (unresolved)
  MIT OR                 S | Reason: licence-malformed
8 LICENSE text matched   Source: LICENSE | Method: licenseid_detection | T
    License-List: spdx-license-list==3.29.0 (database)
```

Case 7 is a declaration, not a missing measurement: the value is recorded
verbatim on `hasDeclaredLicense`, so it is not `not_measured` (that level
means "no value"). What is missing is a derived fact, the SPDX reading: hence
`Reason:` with no `Evidence:`. For licences the relationship type carries the
level: `hasDeclaredLicense` is `declared`, a detected `hasConcludedLicense` is
`measured_read` (case 8; a detection is declared only when the manifest is
silent, `_license.py:557-576`, and then its `Method` says how). A free-text
field (`License:`, Q1) gets no `Reason:`: it never claimed SPDX, so its text is
absent data, quiet. `minimal` drops case 7 today (probed): `_is_high_signal`
must keep an entry with `reason`. The step kinds of cases 5 and 6 and the
trove list's version are planned, unverified.

## 4. Where it attaches

Unchanged: the entry rides on the element the source created, else on its
relationship; a named individual's always on the relationship. One
`LicenseExpression` holds the whole expression, so operand evidence rides as
numbered segments of its entry. Rejected: a `ListedLicense`/`CustomLicense`
per operand: new elements and ids, a declared licence no longer one
expression (Lumina reads `simplelicensing_licenseExpression`,
`backend/app/evidence/reader.py:240`), and still no property for a step. The
classifier `AND`'s `SimpleLicensingText` per unread name keeps the source
entry only. New: `simplelicensing_licenseListVersion` (in the 3.0.1 binding,
probed) on each `LicenseExpression` made from a `resolve()` answer (Q5),
first source wins. The shared-element first-wins bug (known-bugs.md) stays.

## 5. `Resolution-n`

Origin: categories section 7 (operand `n` as written, its result and B steps;
`Expansion-n` its C step), built for `n = 1` only (`_license_resolve.py:144`)
as 0.6.0 gives no operands. It survives, refined by rule 2 and the arrowless
unresolved form. Final names: `Resolution-<n>`, `Expansion-<n>`, `Tool`,
`License-List`, `Reason`; `Normalizer` goes into `Tool`;
`License-List-Version` and `Resolver-Data` are dropped (no data hash in
`ListInfo`).

## 6. Interactions

- **Message catalogue** (proposed codes, licence family, after the
  adoption): `licence-resolved` (`INFO:`, the existing "read as" line),
  `licence-unresolved` and `licence-malformed` (`WARNING:`, SPDX-only
  fields), and reserved `licence-deprecated-id` (no line by decision; a
  `--report` record later) and `licence-assumed-reading` (licenseid 0.8
  `assumed_usage`). The `Reason:` code equals the line's code:

```text
INFO: FIELD=project.license LICENSE='Apache2 OR gpl-2.0+': read as
  Apache-2.0 OR GPL-2.0-or-later (Apache2: separator, version_spelling;
  gpl-2.0+: plus_to_or_later) [licence-resolved]
WARNING: FIELD=project.license LICENSE='Apache2 OR Foo': not read as an SPDX
  license expression (operand not resolved: Foo); recorded as license text
  [licence-unresolved]
```

  (wrapped here; one line each). licenseid's `reason` is the detail,
  through `loggable()`; the provenance holds only the code and the operand.
- **Evidence levels:** `Tool:` names the software that decided the reading,
  `Method:` how; neither is `Evidence:`, which licence entries never write
  (section 3). Write `Reason:` through `evidence_segment` if it exists.
- **Detail levels:** a decided entry has `Normalized-From`, so `minimal`
  keeps it; case 7 needs the `reason` line; case 1 is `full` only.
- **Fragments:** no supersession for licences; `_fragments_generated.py`
  replaces only three `ai_AIPackage` properties (`core/provenance.py:40-44`).
  A fragment licence is unified by `license_key`
  (`_fragments_licenses.py:38-53`, via `classify_license`,
  `_license_elements.py:96`), the dropped element's comment not folded; its
  relationship is added beside the generated one. After T13 that key goes
  through `resolve()`: with the build's `source`, or the known bug "the
  resolver's reading depends on the database" moves into merges.
- **ID registry:** licence and Annotation ids are counters
  (`core/models.py:205-227`), not registry keys; the dedup key stays `(kind,
  canonical value)`, never the list version or provenance. Licence provenance
  does not feed the document uuid (`core/models.py:161-202`).
- **Determinism:** the entry depends on the value, the tool versions and the
  list version and source, all stated (they are inputs). Under `auto` a
  `licenseid update` in HOME changes the list, so two builds of one lock file
  differ. Call `resolve(value, source="packaged")` for declared values
  (decision 4): the answer is then a function of the installed licenseid,
  which a lock pins, and the cache needs no database stamp.
- **Lumina and the checker:** Lumina's evidence code reads relationships,
  properties and `CreationInfo` (`backend/app/evidence/carriers.py:55-73`),
  never Pitloom's provenance (grep, b802223). The checker was not read.

## 7. First step, tasks, order

**Smallest first step** (now, on 0.6.0, no output change): a pure renderer
`licence_notes(found: Resolution, raw: str) -> str` in `_license_resolve.py`
replacing the second `resolve()` of `resolution_notes`, with
`ClassifiedLicense` carrying the answer (one constructor helper); and a
`--provenance` mode in `scripts/licence_adoption_sweep.py` printing each
row's built entry, the before snapshot. T14 is then one function's diff.

| # | Task | Tier |
| - | - | - |
| 1 | Renderer, answer on `ClassifiedLicense`, sweep mode | Sonnet |
| 2 | Operands, `Tool`, `License-List`, list version | Sonnet, Opus review |
| 3 | `Reason:` in SPDX-only fields, `reason` kept | Sonnet |
| 4 | Classifier `AND`: `Resolution-n` per sorted name | Sonnet |
| 5 | Licence family codes, after catalogue step 3a | Sonnet |
| 6 | Licence provenance docs, skills grep, CHANGELOG | Haiku |

Order: catalogue 3a, T13, then 2 to 6; 1 any time before T13. Tests: a
parametrised case per worked case (each key once, `Tool` holds both);
`minimal` keeps 7; a reused element's entry on the relationship; `|` and a
newline escaped; same bytes twice, across processes and `PYTHONHASHSEED`;
doc uuid and fragment unify unchanged; the sweep before (0.21.1) and after
over the 139 parity rows, each changed entry explained (expected: `Tool`
replaces `Normalizer`, `GPL-2.0+` gains `Expansion-1`). Manual checks: the
licence area via `--only`. Risks: the plan's names move (re-check at the
release); churn in every non-exact entry; a second `Tool` writer; `minimal`
silently dropping a new negative entry.

## 8. Conflicts with other documents

- Adoption section 3, Provenance row: "`Tool: licenseid==X` plus `Tool:
  py-spdx-license==Y`" loses the first. Fix: one comma-list `Tool:`.
- Adoption section 4: "depends on the `licenseid` and list versions, not on
  `licenseid update`" is false under `auto` (newer list wins). Fix: pin
  `packaged`, or say `update` can change it.
- Adoption section 3, `_license.py` row (also the licenseid plan's Pitloom
  0.22.0 list): "cache key adds `lists[0].source` and its version": a lookup
  cannot key on its own answer. Fix: key on the requested `source`.
- Categories Q3: "`Expansion-n` is still written" for `+`; today it is not
  for `GPL-2.0+` (`_license_classify.py:462`). After T13 it is: announce.
- Categories section 7: `License-List-Version`, `Resolver-Data` and a
  structured operand list in the Annotation. Fix: `License-List`; the
  structured form waits for 0.23.0 `--report` (catalogue decision 2).
- Evidence levels, "keep any entry that has `evidence`": also `reason`; and
  add that a licence's level is its relationship type, so an unresolved
  declaration is not `not_measured`.
- licenseid: `span` is in raw code points (plan section 4) or of the stripped
  input (`expression-resolution.md`); `by` names py-spdx-license (design 4.4)
  or is always empty (plan). Pitloom records neither.

## 9. Open decisions (recommended answer in brackets)

1. One entry with numbered segments, not a field per operand. [yes]
2. `Tool:` one comma list, resolver first. [yes]
3. `License-List:` segment plus `licenseListVersion` on the element. [yes]
4. `source="packaged"` for declared values; `auto` only behind a future
   `[tool.pitloom]` key. [packaged; a newer id then needs a newer licenseid]
5. `Expansion-n` as `from -> to (kind)`, not kinds only. [yes]
6. `Reason:` only for SPDX-only fields; free text quiet. [yes]
7. Keep `Deprecated-License-Id` beside `Resolution-n` for an equal successor
   (Q7). [keep]
8. `License-List (database)` on detection entries, from the matcher's
   database metadata. [yes, same PR]
9. Structured operands in the provenance Annotation. [no; 0.23.0]
