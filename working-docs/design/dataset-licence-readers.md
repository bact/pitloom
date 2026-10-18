---
Created: 2026-10-18
Last-Modified: 2026-10-18
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Readers that feed a dataset licence

See also: [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md) (G7 DP-010),
[g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md),
[roadmap.md](roadmap.md),
[g7-conformance-tests.md](../implementation/g7-conformance-tests.md).

Status 2026-10-18: readers 1 and 2 and the shared mapping built (see
[Built](#built-readers-1-and-2)); reader 3 not built.

## Where things stand

- The writing side exists: `DatasetMetadata.license` becomes a
  `hasDeclaredLicense` relationship through `add_license_relationships`
  (`assemble/spdx3/dataset.py`), with the provenance the reader recorded.
- Exactly one reader fills it: `read_croissant`
  (`extract/dataset/croissant.py`, the `license` key). It is a library call
  only; no CLI command, project scan, hook or `loom` run calls it.
- The other sources of a dataset reference carry a name and a download URL and
  nothing else: a Hub model card's `datasets:` list, the Hub `dataset:*` tags,
  and a local model card's `datasets:` (`enrich/readme.py`).
- Result: in every Pitloom scenario the datasets have no licence, so G7 DP-010
  is `missing`, and now that every standard follows `trainedOn`/`testedOn`
  the CISA and FSCT licence rules report it too.

## Candidate readers, in the order to build them

| # | Reader | Source of the licence | Cost and risk |
|---|---|---|---|
| 1 | `loom.run` / `add_input_dataset` with a Croissant file or URL | The dataset's own Croissant `license` | Smallest: the extractor and writer exist; only the call site is missing. A URL is a network read, so it follows the existing gate; a local file is not. |
| 2 | Local dataset card in a dataset directory a project ships or a `loom.run` names (`README.md` YAML `license:`) | The card's front matter, the same field the model-card enrichment already reads | Small: reuse the front-matter reader of `enrich/readme.py`. |
| 3 | Hub dataset repository for each dataset a Hub model card lists | The Hub dataset card `license` (and `license_name` / `license_link` for `other`) | One extra request per dataset. Needs the same gate, cache and offline behaviour as the model lookup; the largest of the three. |

Not planned: guessing a licence from a dataset's name, or from the model's
licence. A dataset licence is a statement about the dataset.

## Rules the readers follow

- **Honesty.** The value is the source's claim, recorded as such in
  `provenance["license"]` (`Source: ... | Field: license`). Absent field: no
  licence, silently. `unknown`, `other` without a name or link, blank or
  `NOASSERTION`: no relationship (a placeholder is not a claim); if the source
  states `other` with a licence name or link, that text is the licence (see
  Decided).
- **Shape.** One value goes through `add_license_relationships`, so a valid
  SPDX expression becomes a `LicenseExpression`, any other text a
  `SimpleLicensingText`, exactly as for models. The mapping
  (`g7ai2026-to-spdx30`) needs a `hasDeclaredLicense` to an `AnyLicenseInfo`,
  so a URL and an expression both fit.
- **Declared, not concluded.** A reader fills `hasDeclaredLicense`. Pitloom does
  not conclude a dataset's licence.
- **Determinism.** Same input, same bytes; a network reader writes nothing it
  cannot reproduce from the cached response, as the model lookup does.
- **Gate.** Reader 3 follows the existing Hub-lookup switches and cache, and
  stays off when the model lookup is off. A failed request is a `WARNING:`
  (real disruption); a dataset repository with no licence field is silent.
- **One path.** All three call one function that maps a source value to
  `DatasetMetadata.license` and its provenance, so wording and the weak-value
  list cannot drift.
- **Surfaces.** The CLI, library, hook and Action reach datasets through the
  same extractors; each reader is tested on each surface that can reach it,
  and a surface that cannot (the hook has no `loom.run`) says so in the docs.

## Effect on the conformance tables

- G7 DP-010 flips for the scenarios whose datasets get a licence; the
  `library` scenario gets a Croissant-backed dataset licence first (reader 1),
  `hub` after reader 3 with a mocked dataset card.
- CISA 2026 COMP-006 and FSCT concluded-licence rows report datasets now
  (checker `151460c`); declared licences do not satisfy a concluded-licence
  rule, so check each standard's reading before expecting a flip.
- Regenerate `*-expected.tsv` and the history files with
  `scripts/g7_coverage_report.py --write-expected`, one increment per reader.

## Tests per reader

Compact, parametrised: the source with a licence writes the relationship and
the provenance; no licence field writes nothing and logs nothing; `unknown`,
`other` with and without a name, blank and `NOASSERTION` write nothing or the
named text as above; a URL value and an SPDX expression take their two shapes;
two runs give identical bytes; the table cell flips and nothing else moves;
reader 3: request failure, cache hit, gate off.

## Estimates

Reader 1: 0.5 day. Reader 2: 0.5 day. Reader 3: 1 day. Table, history and
documentation updates: 0.5 day. About 2.5 days in total, one commit per reader.

## Decided (owner, 2026-10-18)

A Hub dataset with `license: other` and only a `license_link` becomes a
`SimpleLicensingText` holding the link (provenance names the card field). With
a `license_name` as well, the text is the name and the link. `other` with
neither stays absent.

## Built: readers 1 and 2

The "Where things stand" section above describes the state before this.

**Shared mapping.** `pitloom.extract.dataset.licence.dataset_licence(value,
source=, name=, link=)` returns the licence text and its provenance, or
`None`. Text or an SPDX expression is kept as read (stripped); absent,
blank, `unknown` or `NOASSERTION` (any case, through the existing
`is_weak_licence`, moved from `extract/project/_field_agreement.py` to
`extract/_license_classify.py`) is `None`; `other` (any case) gives the
name, the link, or `"<name> (<link>)"`, with provenance
`Source: <src> | Field: license, license_name, license_link` naming the
fields used, and `None` with neither. Accepted shapes: a string, a one-item
list, a JSON-LD `{"@id": ...}` node. A number, a mapping or a several-item
list is `None` with one `WARNING:` (`dataset metadata: <src> field <f> is a
<type>, not text; skipped`): the source stated something not recordable.
`read_croissant` now uses it (before: `str(value)`, so a list became
`"['...']"` and `unknown` was a licence).

**Reader 1: `loom.run` with Croissant.** The four dataset calls
(`add_dataset`, `add_validation_dataset`, `add_input_dataset`,
`add_output_dataset`, on `loom` and on the run object) take keyword-only
`croissant=` (a local file) and `declared_license=` (the caller's own
statement). Local file only: loom has no network switch (it reads no
`offline` key), so there is no gate to mirror; a URL raises `ValueError`
at the call, as do a missing, malformed or nameless Croissant file. The
Croissant path is recorded relative to the current directory when below it.
Written onto the package (through `set_dataset_fields`,
`add_dataset_creator_agent` and `add_dataset_license`, factored out of
`assemble/spdx3/dataset.py` and shared with the model path): version,
description, download URL and its PURL, creator (`publishedBy` Agent),
licence, dataset size, collection process, preprocessing, known bias,
sensitive personal information (the fields `read_croissant` fills). Not
written: Croissant's name and dataset types (the call's win), keywords (no
SPDX 3.0.1 dataset property; the model path does not write them either).
`data_preprocessing=` on the call beats Croissant's. Code:
`src/pitloom/_loom_dataset_meta.py`; the package's provenance record is now
written when the run ends (`LoomElements.finish()`), one record holding the
caller and each source field.

**Reader 2: local dataset card.** `pitloom.extract.dataset.read_dataset_card`
reads `README.md` (case-insensitive) in a directory through the frontmatter
reader of `enrich/readme.py`, promoted to public `find_card_file` and
`read_card_frontmatter` with a `CardKind` (`MODEL_CARD`, `DATASET_CARD`)
for the warning wording and cap (1 MiB). Mapped: `license` (+
`license_name`/`license_link`), `pretty_name` -> `name` (else the
directory's name, no provenance), `version` (text or a whole number; a YAML
float such as `1.10` warns and is skipped), `tags` -> `keywords` (strings
only, a single string is one tag). Not read: prose, `description` and any
other key. `loom.run` reads the card of a dataset that is a directory; no
project scan walks dataset directories, so no other surface reads it. A
UTF-8 BOM before the frontmatter is now dropped (model cards too).

**Precedence.** Field by field: `declared_license=`, then Croissant, then
the card; a placeholder from a source is skipped, so a later source can still
give the field. An explicit `declared_license="NOASSERTION"` is the caller's
statement and is written (as the individual).

**Surfaces.** Library only (`loom.run`). The CLI has no dataset path; the
hook and the Action reach a loom dataset only through its merged fragment,
which keeps the licence (tested through `merge_fragments`).

**Tests.** `tests/extract/dataset/test_licence.py`, `test_card.py`,
`test_croissant.py` (licence rules), `tests/core/test_loom_dataset_sources.py`
(loom run: shapes, weak values, precedence, errors, display controls, byte
identity, fragment merge). No conformance table cell moved: no conformance
scenario uses `loom.run` or a Croissant file yet.

## Open question for the owner

Order: build readers 1 and 2 (no network) first, reader 3 after the Hub gate is
reviewed?
