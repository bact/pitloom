---
Created: 2026-10-04
Last-Modified: 2026-11-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Licence handling in three layers

See also: [license-typing.md](../implementation/license-typing.md) (what
PR #276 built), [license-pipeline.md](../implementation/license-pipeline.md)
(sources and call sites), [metadata-quality.md](metadata-quality.md)
(licence follow-ups),
[multi-source-conflict.md](../implementation/provenance/multi-source-conflict.md)
and [role-vocabulary.md](../implementation/provenance/role-vocabulary.md)
(conflict model and roles), [license-rules.md](license-rules.md)
(sources, cascade, conflicts: current rules and open questions).

Pitloom's licence code does three different jobs. Only the last two are
Pitloom's; the first belongs in licence libraries, and Pitloom keeps it
behind one adapter until it moves.

## Layer 1: licence content (string to SPDX meaning)

What a licence string means, independent of where it was read.

Pitloom does today:

- `extract/_license_classify.py`: `classify_license(raw) ->
  ClassifiedLicense` (the adapter seam): the named individuals, long and
  multi-line text left unread, "looks like an expression"
  (`_looks_like_expression`, one `WARNING:`), the notes
  (`tag_license_normalization`, `tag_deprecated_license_ids`). Pitloom's
  own parser over `py-spdx-license` (strict parse, canonical string, the
  `+`/`AdditionRef-` grammar-gap fallback, deprecated `X+` successors,
  `is_listed_name`) was deleted in #440; `extract/_license_names.py`
  keeps the 14 deprecated List names `licenseid.resolve` does not read
  (`same_licence`), held to its packaged List by a drift-guard test.
- `extract/_license_resolve.py`: the declared-value reading
  (`resolve_declared_value`, `licenseid.resolve` on its packaged list), the
  only reader of an expression since #440: every answer with an expression
  is recorded; the `INFO:` line and the `Method`, `Resolution-1`,
  `Expansion-1`, `Tool` and `Deprecated-License-Id` notes come from it.
- `extract/_license_text_match.py`: text to id (`detect_license_from_text`
  over `licenseid`, #438); `extract/_license.py` is the facade
  (`canonicalize_license_id` was deleted in #437: no caller).
- `extract/_license_detect.py`: `_looks_like_spdx_license_id` for
  `CITATION.cff`/`codemeta.json` values.

The rule between the two `licenseid` calls: `resolve()` reads a declared
value (package metadata) and returns the canonical expression; `detect()`
reads licence text. Only `detect()` needs the database.

`py-spdx-license` 0.0.1 offers a strict parser, an AST and
`get_license`/`get_exception` over the bundled SPDX List. It lacks a
canonical form, rejects `+`, `AdditionRef-` and `NOT`, raises `TypeError`
sorting a flat chain with a repeated term, and maps no name to an id.

`licenseid` 0.3.7 (checked interactively, 2026-10-04) offers more than
text to id: `licenseid.identifiers.normalize_identifier(expr, db)`
canonicalises case, operators, sort order and repeats and replaces a
deprecated id (`mit or apache-2.0` is `Apache-2.0 OR MIT`, `GPL-2.0+` is
`GPL-2.0-or-later`; `Apache-2.0+` and `WITH AdditionRef-x` pass through
unchanged); `LicenseDatabase.get_deprecated_mappings()` gives the
`X+` successors; `get_license_by_name()` maps an SPDX List name, any case
(`mit license` and `Apache License 2.0` give `MIT` and `Apache-2.0`). It
does not map a classifier's own name: `Apache Software License` and
`BSD License` give `None`.

The table and the issue list below are the plan of 2026-10-04, written on
`licenseid` 0.3.7. Since #437 and #440, `licenseid` 0.7 reads the canonical
form, the grammar, the successors and the List names (see above).

| Item | Target home |
| --- | --- |
| Canonical form, sorting, repeats | licenseid (already: `normalize_identifier`); py-spdx-license for the repeated-term sort fix |
| `+`, `AdditionRef-`, `DocumentRef-` grammar | py-spdx-license |
| Deprecated id successors | licenseid (already: `get_deprecated_mappings`) |
| "Looks like an expression" diagnosis | py-spdx-license |
| SPDX List name to id (`is_listed_name`) | licenseid (already: `get_license_by_name`) |
| Classifier name to id | licenseid (the real gap) |
| Licence text to id | licenseid (already) |

Upstream issues to file: py-spdx-license grammar (`+`, `AdditionRef-`,
`DocumentRef-...:AdditionRef-`, `NOT`) and the sort `TypeError`;
licenseid classifier-name to id; licenseid text matching (#286, scores
in [license-rules.md](license-rules.md#4-declared-or-concluded)): a leading
copyright notice hides MIT (PyYAML gives `Xnet`), and a near-variant
outranks the verbatim licence (`Pixar` over `Apache-2.0`, `JSON` over
`MIT`). Before filing a canonical-form or
successor issue, check whether `normalize_identifier` already covers
Pitloom's cases (the grammar gaps differ). Whether Pitloom later uses
`normalize_identifier` and `get_license_by_name` behind the adapter is a
content decision, not taken in #276.

Deferred until upstream (no Pitloom feature meanwhile):

- `LicenseRef-a WITH DocumentRef-d:AdditionRef-x` as an expression (today
  text, silent).
- Classifier or licence name to SPDX id: `resolve()` reads a name that names
  one licence (`MIT License`); a family name (`BSD License`, `Apache Software
  License`) stays `SimpleLicensingText`, and several such classifiers are an
  AND of `LicenseRef-pitloom-classifier-` terms (layer 3).
- An unknown-id `WARNING:` in a field that must hold an SPDX expression.
- Names differing only in case give two `LicenseRef-` terms (SPDX matches
  them case-insensitively): needs classifier-to-id knowledge (licenseid).
  The open normalisation questions (names, case, URLs, canonical form):
  C12 to C14, C18 in
  [canonical-output-followups.md](canonical-output-followups.md).
  The one category classifier, `License :: OSI Approved`, is dropped
  already (`license-typing.md`).
- A licence text `licenseid` identifies is the id on a directory and the
  hook but text from an sdist, wheel or installed metadata, whose readers
  run no detection (`metadata-quality.md`).

## Layer 2: licence source (Pitloom)

Where a package states its licence and whose statement it is. Packaging
and provenance knowledge; a licence library cannot do it. Sources, the
cascade per surface, weak and final values, declared vs concluded, the
conflict model and equivalence: [license-rules.md](license-rules.md).

## Layer 3: SBOM shape (Pitloom, PR #276)

- Element classes: `simplelicensing_LicenseExpression`,
  `simplelicensing_SimpleLicensingText`; the `NoAssertionLicense` and
  `NoneLicense` individuals.
- Relationship types `hasDeclaredLicense`/`hasConcludedLicense`; none for
  an absent licence.
- One element per classified value (dedup key: kind and value).
- `profileConformance` derived from the graph.
- Fragment merge treating named individuals as resolved, and checking each
  `customIdToUri` target in the document's own namespace.
- Design note, not built: `customIdToUri` targets are checked at merge
  only in the main document's namespace (none without an `SpdxDocument`,
  e.g. `loom merge` output); a fragment's own namespace is not checked.
- Several `License ::` classifiers: one AND `LicenseExpression`
  ([license-typing.md](../implementation/license-typing.md#the-main-packages-classifiers)).

## Prerequisites: conflict resolution, provenance and taxonomy

Goal (roadmap, "Licence rules, systematic"): explicit rules for licence
sources, normalisation and conflict resolution, applied identically on
every surface. The current rule for each prerequisite (source classes,
roles, weak and final values, cascade order, conflict model,
equivalence, provenance, tie-breaks) and what is open:
[license-rules.md](license-rules.md).

## Findings for the rule design (PR #276 review, R10)

Moved, with the user's leanings, to
[license-rules.md](license-rules.md#open-questions); the full list of
what #276 left open, by group:
[license-pr276-followups.md](license-pr276-followups.md).

## Rule for future work

A change that only alters what a licence string means goes upstream;
Pitloom changes only the adapter.

## Migration

- Upstream fix lands in py-spdx-license or licenseid.
- Pitloom raises its floor and drops the matching workaround.
- `classify_license` shrinks to a call and a mapping to `ClassifiedLicense`;
  its tests stay as the contract.
