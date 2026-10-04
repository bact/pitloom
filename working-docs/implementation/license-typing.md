---
Created: 2026-10-04
Last-Modified: 2026-10-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Licence element typing

What was built in PR #276 (0.20.0) and why: how a licence value becomes an
SPDX 3 licence element, relationship or named individual. Before it, every
value -- `MIT`, `MIT AND Apache-2.0`, `NOASSERTION` -- became a
`simplelicensing_SimpleLicensingText`, which the spec reserves for a licence
"not listed on the SPDX License List".

See also: [license-pipeline.md](license-pipeline.md) (sources, data flow,
call sites), [recurring-bug-patterns.md](recurring-bug-patterns.md) (the
weak-placeholder lesson) and the user-facing
`docs/metadata-provenance.md` (provenance keys).

## One classifier, one builder

`classify_license(raw, *, warn=True)` in `extract/_license.py` returns
`ClassifiedLicense(kind, value, raw)` or `None` (absent or blank). Every
surface -- dependencies, main package, wheel, sdist, AI models (local and
Hugging Face), per-file `SPDX-License-Identifier` -- reaches it through
`assemble/spdx3/_license_elements.py`, the one element builder
(`get_or_create_license_element`). Surfaces never classify on their own.

| `kind` | Rule | Element |
| :--- | :--- | :--- |
| `noassertion` | `NOASSERTION` or `UNKNOWN`, any case | none; individual `NoAssertionLicense` |
| `none` | `NONE`, any case | none; individual `NoneLicense` |
| `expression` | strict `py-spdx-license` parse succeeds, every id listed | `simplelicensing_LicenseExpression`, canonical form |
| `expression` (grammar gap) | valid SPDX the parser cannot read: `Apache-2.0+`, `WITH AdditionRef-x`; kept as written, ids in listed case, operators upper-case | `LicenseExpression` |
| `text` | everything else; newline or over 200 characters is text without parsing; stripped | `simplelicensing_SimpleLicensingText` |

Details that were decided, not obvious:

- **Canonical form.** Listed id case, operators upper-case, terms sorted
  (`mit and apache-2.0` is `Apache-2.0 AND MIT`). The raw value is kept in
  provenance, never lost.
- **Deprecated `X+` ids.** A deprecated id ending `+` becomes `X-or-later`,
  found in the SPDX List bundled with `py-spdx-license`, not a hard-coded
  table. `+` is replaced only when no second `+` follows, and `+` after
  `-only`/`-or-later` is invalid, so `GPL-2.0++` and `GPL-2.0-only+` are text.
  A bare deprecated `GPL-2.0` stays as written (the holder's intent, `-only`
  or `-or-later`, is unknown) with a `Deprecated-License-Id` note.
- **Warning rule.** Text with an operator or parenthesis and a known id
  looks like a broken expression: text plus one `WARNING:` per value per
  process (`warn_once`; any-case operators). The parser's message quotes the
  input, so it is escaped. A pure comparison passes `warn=False`
  (installed-metadata reconcile), because comparing is not recording.
- **Unknown id alone** (`Apache2`) is text and silent; warning on a field that
  must hold an SPDX expression is a 0.21.0 follow-up.

## Absent is not NOASSERTION

SPDX 3 Licensing: a missing `hasDeclaredLicense` is not a
`NoAssertionLicense`; "no assumptions can be made". So an absent or blank
licence creates **no relationship** on any surface, declared or concluded,
and a document with no licence relationship has no licensing profile.
Pitloom's earlier own fallback (a NOASSERTION element on every dependency
and project with no licence) was removed. Copyright keeps its
`NOASSERTION` text, a plain string field.

`NOASSERTION`/`UNKNOWN` is emitted only when a source literally said so. The
individual cannot carry a comment or Annotation, so that source's note
(`Normalized-From: UNKNOWN`) goes on the relationship.

## Dependency cascade: NoAssertion is weak

Order: installed `License-Expression`/`License`, installed `License ::`
classifiers, then the PyPI record. `UNKNOWN`/`NOASSERTION` does not end it:

- `WeakLicense` holds the first one stated; `_apply_license(weak=...)` holds
  instead of emitting; `emit_weak_license` emits it after the last source,
  with the first source's provenance, only if no source stated a licence.
- `NONE` is a statement and ends the cascade (PyPI is not asked).
- One PyPI record (`_extract_pypi_license`): placeholders are skipped in
  `license_expression` and `license` while looking for a better value
  (expression, license, classifiers); the first one seen is returned if
  nothing better exists.
- The held state is per dependency, created in
  `_finish_dependency_enrichment` (a test runs two dependencies in one call).

The first build treated an installed `License: UNKNOWN` (legacy setuptools
placeholder) as final, which stopped the PyPI lookup that used to find the
licence; the review caught it. Rejected: treating `UNKNOWN` as absent (loses
"the source says it does not know"), and ending the cascade on it.

Main package and per-file tags are not cascades: a stated value is emitted at
once.

## Two-candidate mode and conflicts

The main package has a declared value (`license_name`) and an independently
detected one (`license_concluded`). Both go through the same classification,
so spelling differences (`mit` vs `MIT`, `GPL-2.0+` vs `GPL-2.0-or-later`,
`MIT AND MIT` vs `MIT`) are one element and no conflict. Both relationships
are always built, each for its own role. A G2 `conflict` Annotation is added
when the values differ, except that a `NoAssertionLicense` candidate never
conflicts (it only says "unknown"; the real licence is the only one with
content). `NONE` against a real licence is a conflict. Rejected: dropping the
NoAssertion relationship when the other side is real (it loses that source's
statement and provenance for no gain).

## Hugging Face `license: unknown`

Card values `other`, `custom`, `proprietary`, `unlicensed` stay "vague": file
detection runs and nothing is emitted if it finds nothing. `unknown` is the
card saying it does not know: file detection still runs first, and if it
finds nothing the raw value is returned with card provenance, so it becomes a
`NoAssertionLicense`.

## Individuals live in one table

`core/license_individuals.py` holds `LicenseIndividual(iri, compact_name,
spdx_name)` and lookups by kind, compact name and either reference. The
element builder, the exporter's relationship `description` (shows `NOASSERTION`
/ `NONE`, not the IRI), `scripts/check_sbom_license.py` and the test helpers
read it; matching is exact (a `#Foo_NoneLicense` is no individual). The
exporter needs only the compact name, since the serialiser never writes the
full IRI. Earlier there were four hand copies.

## `profileConformance` from the graph

`assemble/spdx3/_licensing_profiles.py` derives the licensing profiles from the
graph: `simpleLicensing` for any `LicenseExpression`/`SimpleLicensingText` or
declared/concluded licence relationship, `expandedLicensing` for any
`expandedlicensing_*` element or a reference to one of its individuals (which
implies `simpleLicensing`); a graph with no licence needs neither. It replaced
five hand-maintained computations, so a direct build and a fragment merge of
the same content agree, in one fixed profile order.

## Fragment merge

A fragment relationship or annotation to `NoAssertionElement`, `NoneElement`,
`SpdxOrganization` or a licence individual is not dangling
(`_fragments_refs.py`, `NAMED_INDIVIDUAL_IDS` read from the bindings);
before, merging a document that used a named individual raised
`FragmentMergeError`.

## Provenance

`Normalized-From` (raw value when recording changed it), `Normalizer`
(`py-spdx-license==x`, only when a parse took place -- not for
`UNKNOWN`/`NONE`) and `Deprecated-License-Id` are high-signal, so kept at
`detail = "minimal"`. On the element when this source created it; on the
source's own relationship when the element already existed (per-source note
on a shared element) and always for an individual.

## Tests and checks

Cross-surface table (`tests/assemble/test_license_elements_surfaces.py`: 16
values x 8 surfaces), cascade tests (`test_license_cascade.py`), individuals
and network `spdx3-validate` (`test_license_individuals.py`), classifier
table, table-vs-bindings (`tests/core/test_license_individuals.py`).
`scripts/check_sbom_license.py` reads an individual target as its name.
Output bytes change (no NOASSERTION licence element; License-N ids shift);
no golden fixture held one.
