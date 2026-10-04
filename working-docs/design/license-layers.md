---
Created: 2026-10-04
Last-Modified: 2026-10-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Licence handling in three layers

See also: [license-typing.md](../implementation/license-typing.md) (what
PR #276 built), [license-pipeline.md](../implementation/license-pipeline.md)
(sources and call sites), [metadata-quality.md](metadata-quality.md)
(licence follow-ups).

Pitloom's licence code does three different jobs. Only the last two are
Pitloom's; the first belongs in licence libraries, and Pitloom keeps it
behind one adapter until it moves.

## Layer 1: licence content (string to SPDX meaning)

What a licence string means, independent of where it was read.

Pitloom does today:

- `extract/_license_classify.py`: `classify_license(raw) ->
  ClassifiedLicense` (the adapter seam); strict parse and canonical string
  (`_strict_parse`, `_canonical_string`: listed id case, upper-case
  operators, sorted terms); the sort `TypeError` workaround on a flat chain
  with a repeated term; deprecated `X+` to `X-or-later` (`_successor_id`,
  `_replace_deprecated`); the grammar-gap fallback for `+` and
  `WITH AdditionRef-` (`_gap_term`, `_gap_expression`); "looks like an
  expression" (`_looks_like_expression`, one `WARNING:`); deprecated-id
  notes (`tag_deprecated_license_ids`); the name-vs-id stop-gap
  `is_listed_name`.
- `extract/_license.py`: text to id (`detect_license_from_text` over
  `licenseid`), `canonicalize_license_id`,
  `_looks_like_spdx_license_expression`.
- `extract/_license_detect.py`: `_looks_like_spdx_license_id` for
  `CITATION.cff`/`codemeta.json` values.

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
licenseid classifier-name to id. Before filing a canonical-form or
successor issue, check whether `normalize_identifier` already covers
Pitloom's cases (the grammar gaps differ). Whether Pitloom later uses
`normalize_identifier` and `get_license_by_name` behind the adapter is a
content decision, not taken in #276.

Deferred until upstream (no Pitloom feature meanwhile):

- `LicenseRef-a WITH DocumentRef-d:AdditionRef-x` as an expression (today
  text, silent).
- Classifier or licence name to SPDX id (today `SimpleLicensingText`; several
  classifiers are an AND of `LicenseRef-pitloom-classifier-` terms, layer 3).
- An unknown-id `WARNING:` in a field that must hold an SPDX expression.
- A category classifier (`License :: OSI Approved`) becomes its own AND
  term, and names differing only in case give two `LicenseRef-` terms
  (SPDX matches them case-insensitively): both need classifier-to-id
  knowledge (licenseid).
- A licence text `licenseid` identifies is the id on a directory and the
  hook but text from an sdist, wheel or installed metadata, whose readers
  run no detection (`metadata-quality.md`).

## Layer 2: licence source (Pitloom)

Where a package states its licence and whose statement it is. Packaging
and provenance knowledge; a licence library cannot do it.

- Cascade: `License-Expression`, `License`, `License ::` classifiers, then
  (dependencies) the PyPI JSON API. One rule, `first_license` in
  `extract/_core_metadata.py`.
- `NOASSERTION`/`UNKNOWN` is weak (a later source wins); `NONE` is a
  statement and ends the cascade.
- Field names per format: `project.license`/`project.classifiers`,
  `metadata.license`/`metadata.classifiers`, `setup(license=...)`/
  `setup(classifiers=...)`, Core Metadata headers.
- Core Metadata folding removed; the leading and trailing blank space
  around a licence text dropped as serialisation, once, in the element
  builder.
- Declared (the package's own claim) or concluded (a third-party record)
  by source: `is_license_concluded`.
- G2 two-candidate model: the manifest's value declared, the directory's
  detection concluded, a `conflict` Annotation when they differ.

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
- Several `License ::` classifiers: one `LicenseExpression`, the AND of
  `LicenseRef-pitloom-classifier-<name>` terms (the name reversibly encoded
  as an idstring; sorted by classifier, no repeats), its `customIdToUri`
  mapping each term to the `SimpleLicensingText` of the name as given. No
  mapping to a listed id; AND is assumed, with one `WARNING:`.

## Rule for future work

A change that only alters what a licence string means goes upstream;
Pitloom changes only the adapter.

## Migration

- Upstream fix lands in py-spdx-license or licenseid.
- Pitloom raises its floor and drops the matching workaround.
- `classify_license` shrinks to a call and a mapping to `ClassifiedLicense`;
  its tests stay as the contract.
