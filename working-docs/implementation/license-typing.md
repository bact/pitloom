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
call sites), [license-layers.md](../design/license-layers.md) (content,
source and shape: what moves upstream; its
[prerequisites](../design/license-layers.md#prerequisites-conflict-resolution-provenance-and-taxonomy)
list what is still to settle),
[recurring-bug-patterns.md](recurring-bug-patterns.md) (the
weak-placeholder lesson) and the user-facing
`docs/metadata-provenance.md` (provenance keys).

## Scope: shape and source here, licence content upstream

Pitloom owns the SBOM shape (element classes, individuals, declared vs
concluded relationships, dedup, profiles, merge) and the licence source
(the Core Metadata/`pyproject.toml`/`setup.cfg`/`setup.py` cascade, field
names, folding, whose statement). What a licence string means is frozen
behind `classify_license(raw) -> ClassifiedLicense` and is to move to
`py-spdx-license` (grammar, canonical form, deprecated ids) and `licenseid`
(text, name or classifier to id); no new content features meanwhile.
`is_listed_name` is the minimal stop-gap for the false name-vs-id conflict
below. Deferred: `WITH DocumentRef-d:AdditionRef-x`, name/classifier to
id, an unknown-id warning. Detail: [license-layers.md](../design/license-layers.md).

## One classifier, one builder

`classify_license(raw, *, warn=True)` in `extract/_license_classify.py`
(re-exported by `extract/_license.py`) returns
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
| `expression` (grammar gap) | valid SPDX the parser cannot read: `Apache-2.0+`, `WITH AdditionRef-x` (also after `LicenseRef-`/`DocumentRef-`); canonicalised like any expression (see below) | `LicenseExpression` |
| `text` | everything else; newline or over 200 characters is text without parsing; kept as written (stripped only to classify) | `simplelicensing_SimpleLicensingText` |

Details that were decided, not obvious:

- **Canonical form.** Listed id case, operators upper-case, terms sorted
  (`mit and apache-2.0` is `Apache-2.0 AND MIT`). The raw value is kept in
  provenance, never lost.
- **Operand order and repeats.** Operands are reordered
  (`MIT OR Apache-2.0` becomes `Apache-2.0 OR MIT`) and repeats collapse
  (`MIT OR MIT` becomes `MIT`); both record `Normalized-From`. Canonical order
  holds for flat lists of one operator. A nested mixed AND/OR tree can have
  more than one equivalent spelling: the library's absorption step is not
  confluent, so two such spellings may stay two elements.
- **Library workaround.** `py-spdx-license` 0.0.1 `Node.sort()` raises
  `TypeError` on a flat chain with a repeated term (`MIT OR ISC OR MIT`).
  The chain is deduplicated by identical terms and sorted again; any other
  shape that cannot be sorted keeps the parser's own spelling. Never text,
  never a `WARNING:`.
- **Grammar gap.** Each `X+`/`WITH AdditionRef-` term is checked (a listed
  id with no `+` after `-only`/`-or-later`, or a `LicenseRef-`/`DocumentRef-`
  the parser accepts, with no `+` at all; a listed exception otherwise),
  stands in as a placeholder while the rest is parsed, sorted and
  deduplicated, then is put back: so spacing, order and identical repeats are
  canonical as for any expression. `MIT+` and `MIT` are different terms and
  are not merged. The placeholder prefix is lengthened until the input does
  not contain it, and is restored by a bounded match: a user's own
  `LicenseRef-pitloom-gap-000` was once dropped or merged into a neighbour by
  a plain substring replace.
- **Text as written, less leading blank space and final line breaks.**
  Leading blank lines, spaces and tabs, and every final `\n`, `\r\n` or `\r`, are
  serialisation: a file or a TOML string keeps them, a wheel's `METADATA`
  drops them (the email parser strips a header value's leading blanks, the
  writer its final breaks). Keeping one final break (the first rule) still
  left `"...\n\n"` differing between a directory and its wheel, and
  leading spaces did the same. They are dropped once, in the element
  builder (`_without_blank_ends`: string methods, as an end-anchored
  regular expression was quadratic on a long inner run of line breaks),
  before classification, and readers
  no longer strip a licence value themselves (PyPI, `setup(license=...)`
  and a PEP 639 string were stripped at read time), so no surface can drop
  more than another. Inner text stays as written. The dedup key is the
  stripped text and the first seen spelling is stored (deterministic:
  first-seen order is). `name` is the first
  line of the stripped text. Internal NBSP or CRLF is text, silently; only the
  edge whitespace is stripped for classification.
- **Lone surrogates.** A value not UTF-8 encodable would fail serialisation
  (`CanonicalizationError`); each lone surrogate becomes U+FFFD with one
  `WARNING:` per value.
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

## The main package's classifiers

The package's own `License ::` classifiers are the next weak-cascade source
after its licence field, by one rule, `license_or_classifier` in
`extract/_core_metadata.py`, on every surface: `pyproject.toml`
(`project.license`, then `project.classifiers`), `setup.cfg` (`license`,
then `classifiers`, inline or `file:`), a wheel (`loom wheel`,
`wheel --embed`, `embed-wheel`), an sdist and installed metadata
(`License-Expression`/`License`, then `Classifier`), `setup.py`
(`setup(license=...)`, then `setup(classifiers=...)`) and the Hatchling
build hook (`core.classifiers`). A blank or weak `UNKNOWN`/`NOASSERTION`
field loses to a classifier, `NONE` ends it, and none gives no
relationship. The order is one function, `first_license`, over the
candidates in order, so `License-Expression: UNKNOWN` then
`License: Apache-2.0` records `Apache-2.0` on every Core Metadata reader.
Provenance names the field: `project.classifiers`, `metadata.classifiers`,
`setup(classifiers=...)`, or `Field: Classifier` added to a METADATA label.

A trove parent (`License :: OSI Approved`) is dropped when another
classifier in the same set extends it by `::` (`_licence_classifiers`): it
adds nothing the child does not say. Alone it is kept, as a name.

Several licence classifiers are one `LicenseExpression`: the AND of
`LicenseRef-pitloom-classifier-<name>` terms, sorted by classifier and
without repeats, so Hatchling sorting them and the source not doing so give
one value. `customIdToUri` maps each term to the `SimpleLicensingText` of
its name as written (the element any other use of that text shares). The
name is encoded reversibly as an idstring (letters and digits kept, a space
`-`, any other byte `.XX`), so the builder recovers the names from the
expression alone, identically for a dependency's installed copy and its
PyPI record; it builds the expression directly, without the parser or the
200-character limit. AND is assumed, as for a dataset list, with one
`WARNING:` naming the classifiers: they may offer a choice. Rejected: the
first classifier in source order (Hatchling's sort made the directory and
its wheel differ) and the sorted-first one alone (drops a stated licence).
A user's own expression spelled exactly like this form is read as one; any
other `LicenseRef-pitloom-classifier-` spelling is left alone. Against a
detected id an AND is a conflict unless equal: the name match below is
for one name. A `customIdToUri` target in the document's own namespace
that names no element is a dangling reference at fragment merge.
A Poetry project's classifiers are not read: `poetry-core` writes the
licence classifier from `license` itself.

`setup.cfg`'s `file:` directive (`extract/project/_setup_cfg_directives.py`)
reads a comma-separated list as setuptools' `read_files` does: each path
stripped, a missing one skipped, the texts joined with a newline. An
existing file that cannot be read (`OSError`, `UnicodeDecodeError`) is left
out with one `WARNING:` naming the file and the field
(`metadata.classifiers`, `metadata.long_description`); it no longer ends the
read.

`license = "UNKNOWN"` with a `License ::` classifier fails
`pyproject-metadata`'s PEP 639 check; the reader drops the placeholder
`license` (the classifier wins the cascade anyway), silently, instead of
dropping the classifiers with a `WARNING:` as for a real SPDX string.

Core Metadata folds a multi-line `License` with a continuation indent
(8 spaces from setuptools and hatchling, setuptools adding one more indent
line when the text ends in a newline; 7 spaces and `|` in the older
`Description` convention; a tab per RFC 5322).
`core_metadata_license_with_source`, the one Core Metadata reader, removes
exactly that marker from each continuation line, so the text equals
the directory's and inner indentation is kept.

Parity, as checked live on hatchling and setuptools projects: the
directory (CLI and library), its sdist, its wheel and the build hook record
the same declared licence, except a `license.file`/`license.text` that
`licenseid` identifies: the directory and the hook record the id, an sdist,
a wheel or installed metadata the text, since their readers run no text
detection (content, predates #276;
[metadata-quality.md](../design/metadata-quality.md)). The concluded G2
second opinion exists only where a directory is scanned (CLI/library on a
directory, the hook); an sdist or wheel SBOM has no detection step, which
predates #276
([metadata-quality.md](../design/metadata-quality.md)). A
dependency (installed, then PyPI) goes through the same helper, so a
blank-but-folded `License:` header or an NBSP `License-Expression` reaches
the classifier there too (a blank header counts as empty). Before, a
`pyproject.toml` classifier was read only to be dropped as redundant, so the
directory and its wheel disagreed.

## Declared or concluded: whose statement

`is_license_concluded` (`assemble/spdx3/_provenance_encoders.py`) decides a
single value by its source alone. The package's own statement is declared,
however it was read: a manifest, an in-package file (`LICENSE` detection,
`CITATION.cff`, `codemeta.json`), a model card (local front matter or the
Hugging Face card and repository files), an AI model file's own metadata,
the package's own installed metadata (the installed-project reader, and a
`loom env` package, labelled `deployed package metadata`). A third-party
record is concluded: the PyPI JSON API and a dependency's installed copy in a
project SBOM (`installed metadata`), whose environment need not hold the
artifact the SBOM describes. No source at all is concluded.

Two-candidate mode is unchanged: when the manifest states a licence it
stays declared, and the directory's detection is the concluded second
opinion. So `detect_license_for_project` no longer replaces a stated
licence text it cannot identify with a directory value; it returns the
text as written. A `Method` is recorded only when `licenseid` identified
the text: `license = {text = "MIT License\n"}` once gained a false
`Method: licenseid_detection` (and so a concluded relationship) because the
stripped fallback differed from the hint.

Rejected: a `Method` making a value concluded (the old rule) -- `licenseid`
reading the package's own `LICENSE` file does not make it Pitloom's opinion;
and a per-call-site flag -- the label already says whose record it is, and
one rule keeps every surface in step. The Hugging Face repository's
`LICENSE` detection is declared by the same reasoning (the repository is the
model's package), and a model card's licence enrichment records
`role: "declared"` (dataset entries stay `detected`).

A library caller's `ProjectMetadata(license_concluded=...)` with no
`license_name` is always `hasConcludedLicense`: the caller named the slot.

## Known deviation: licence names stay text

A licence name or a listed licence's full text (`MIT License`,
`Apache 2.0`, a classifier's `BSD License`) is recorded as
`SimpleLicensingText`, though the spec reserves it for a licence not on the
SPDX List. Mapping names and texts to list ids precisely needs a newer
`licenseid` and is deferred (user, 2026-10-04); not in #276.

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

A per-file tag is not a cascade: a stated value is emitted at once. The main
package's cascade is its field, then its classifiers (above).

## Two-candidate mode and conflicts

The main package has a declared value (`license_name`) and an independently
detected one (`license_concluded`). Both go through the same classification, so
spelling differences (`mit` vs `MIT`, `GPL-2.0+` vs `GPL-2.0-or-later`, `MIT AND
MIT` vs `MIT`) are one element and no conflict. Both relationships are always
built, each for its own role. A G2 `conflict` Annotation is added when the
values differ, except that a licence name equal to the SPDX List name of the
other's listed id (a classifier's `MIT License` against a detected `MIT`;
`is_listed_name`, case-insensitive) is the same licence, and a
`NoAssertionLicense` candidate never conflicts (it only says "unknown"; the real
licence is the only one with content). `NONE` against a real licence is a
conflict. One rule, `same_licence` (`extract/_license_classify.py`), decides
"same licence" here and when a static manifest is reconciled with installed
metadata (`_installed_reconcile.py`), where a weak static value also gives way:
a real installed licence replaces it, with its provenance. Rejected: dropping
the NoAssertion relationship when the other side is real (it loses that source's
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

Cross-surface table (`tests/assemble/test_license_elements_surfaces.py`:
16 values x 9 surfaces, the hook included), cascade tests
(`test_license_cascade.py`), individuals and network `spdx3-validate`
(`test_license_individuals.py`), classifier table, table-vs-bindings
(`tests/core/test_license_individuals.py`), classifier parity across eight
surfaces (`test_license_elements_classifier.py`), several classifiers
(`test_license_classifiers_and.py`), a text's blank ends on nine surfaces
(`test_license_text_line_breaks.py`), declared vs concluded on the real
surfaces, the hook included (`test_license_declared_sources.py`) and the
four core-metadata readers end to end
(`tests/extract/test_core_metadata_license.py`).
`scripts/check_sbom_license.py` reads an individual target as its name.
Output bytes change (no NOASSERTION licence element; License-N ids shift);
no golden fixture held one.
