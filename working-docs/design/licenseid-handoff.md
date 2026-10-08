---
Created: 2026-10-08
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Handoff to `licenseid`: what Pitloom needs upstream

Status: prompt to give a session working in the `licenseid` repository
(Pitloom never edits it). Written 2026-10-08 after the #294 reviews.

See also: [canonical-output-followups.md](canonical-output-followups.md)
(C11 to C21, the questions behind this),
[license-layers.md](license-layers.md) (what belongs upstream),
[license-rules.md](license-rules.md).

Decision (user, 2026-10-08): Pitloom waits for `licenseid` for C12 (name to
id) and C18 (URL to id); it does not map them itself.

## Prompt

You work in the `licenseid` repository (version 0.4.3 at the time of
writing; Pitloom requires `licenseid>=0.4.3`). Pitloom, an SBOM generator,
asks it three kinds of question and today gets no useful answer for some of
them. Verify every claim below against the repository before acting; fix
only what is real, and report anything that differs. Do not change the
public API of what Pitloom already calls without keeping it working:
`AggregatedLicenseMatcher`, `DatabaseNotReadyError`, `LicenseMatch`,
`LicenseDatabase`, `get_default_db_path`, `identifiers.normalize_identifier`,
`LicenseDatabase.get_license_by_name`, `get_deprecated_mappings`.

### Checked on 0.4.3 (2026-10-08, default database)

| Input | `normalize_identifier(s, db)` | `db.get_license_by_name(s)` |
|---|---|---|
| `MIT License`, `mit license` | unchanged | the `MIT` record (a `dict`, with `license_id`) |
| `Apache License 2.0` | unchanged | the `Apache-2.0` record |
| `Apache Software License`, `BSD License` (trove classifier names) | unchanged | `None` |
| `https://opensource.org/licenses/MIT` | unchanged | `None` |
| `apache-2.0,mit` | unchanged | `None` |
| `MIT` followed by U+200B | unchanged | `None` |
| `licenseref-foo` | unchanged | `None` |
| `other` | unchanged | `None` |
| `mit or apache-2.0` | `Apache-2.0 OR MIT` | `None` |
| `GPL-2.0+` | `GPL-2.0-or-later` | `None` |
| `Apache-2.0+` | `Apache-2.0+` (unchanged) | `None` |

### What Pitloom needs, in priority order

1. **Licence URL to id** (Pitloom C18). Each SPDX License List entry has
   `crossRef` URLs (visible in the record's `xml_template`) and a
   `reference` page. Offer a lookup from a URL to the candidate ids, with a
   stated folding (scheme, `www.`, trailing `/`, `.html`/`.txt`, a `#L`
   fragment) and a result that says when a URL maps to several ids. On the
   2026-10-07 list, 43 URLs map to several ids, all same-text families
   (GPL-2.0 page: `-only`, `-or-later`, deprecated `GPL-2.0` and `GPL-2.0+`;
   each GFDL text: 7 ids). An ambiguous URL must not be resolved to a guessed
   `-only`; return all candidates and let the caller decide. Say whether
   deprecated ids are candidates. Pure function of the database; no network.
2. **Trove classifier name to id** (Pitloom C12; the real gap). `Apache
   Software License`, `BSD License`, `GNU General Public License v3 (GPLv3)`
   and the other `License :: ...` classifier names give `None`. Provide a
   mapping with data: a name to a candidate id list (many classifiers are
   ambiguous: `BSD License` is several ids; say so, do not pick).
3. **`get_license_by_name` return type.** It returns a `dict` carrying the
   whole XML template. A small typed result (id, name, deprecated, OSI) would
   let Pitloom avoid parsing a template; keep the old call working.
4. **Edge characters and comma lists in `normalize_identifier`** (Pitloom
   C15, C17). Decide and document, in the function's contract: whether
   zero-width and other format characters (U+200B, U+2060, U+FEFF) at the
   ends are stripped (`MIT` plus U+200B is today not `MIT`); that a
   comma-separated list is not an expression and is returned unchanged (do
   not guess AND or OR; Pitloom decides). Add tests either way.
5. **Case of `LicenseRef-` and `DocumentRef-`** (Pitloom C13). `licenseref-foo`
   is returned unchanged and not recognised as a reference. State the rule
   (SPDX matches ids case-insensitively; the idstring case is the user's) and
   test it.
6. **`WITH DocumentRef-d:AdditionRef-x` and `Apache-2.0+` with an exception**
   (Pitloom C14). `normalize_identifier` leaves `Apache-2.0+` unchanged
   though `GPL-2.0+` becomes `GPL-2.0-or-later`; say whether that is
   intended (the deprecated-id table may only hold ids the List marks
   deprecated) and document the grammar it accepts (`+`, `AdditionRef-`,
   `DocumentRef-...:AdditionRef-`, `NOT`).
7. **Stability of output across versions** (Pitloom C21). Pitloom records
   `licenseid`'s answers in SBOMs and needs the same input to give the same
   id for the same database. Offer: a documented determinism guarantee
   (what may change between versions: database content, thresholds); the
   database/List version in a field Pitloom can record (`get_metadata`
   already exists: confirm it is enough); a changelog line whenever a result
   for existing input changes.

### Text matching findings from Pitloom (#286, still open upstream)

- A leading copyright notice hides MIT (PyYAML's licence text gives `Xnet`).
- A near-variant can outrank the verbatim licence (`Pixar` over
  `Apache-2.0`, `JSON` over `MIT`).
Reproduce on the Pitloom side with its fixtures or give a minimal text
sample in a licenseid test.

### Deliver

For each item: reproduce, fix or document, add a test, and a changelog line.
Report which items you did, which you refused and why, and the new API for
each so Pitloom can adopt it behind its adapter
(`src/pitloom/extract/_license_classify.py`). Do not touch Pitloom.
