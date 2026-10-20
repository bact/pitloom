---
Created: 2026-10-18
Last-Modified: 2026-10-19
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Readers that feed a dataset licence

See also: [g7-ai-sbom-coverage.md](g7-ai-sbom-coverage.md) (G7 DP-010),
[g7-honesty-and-non-recordable.md](g7-honesty-and-non-recordable.md),
[roadmap.md](roadmap.md),
[g7-conformance-tests.md](../implementation/g7-conformance-tests.md).

Status 2026-10-19: all three readers and the shared mapping built (see
[Built: readers 1 and 2](#built-readers-1-and-2) and
[Built: reader 3](#built-reader-3)); licence lists and non-prose card
descriptions ruled on and built (see
[Built: licence lists and card descriptions](#built-licence-lists-and-card-descriptions)).

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
  licence, silently. `unknown`, `N/A`, `other` without a real name or link,
  blank or `NOASSERTION`: no relationship (a placeholder is not a claim); if the source
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
list, a JSON-LD `{"@id": ...}` node; a several-item list since the owner's
ruling (see [Built: licence lists and card descriptions](#built-licence-lists-and-card-descriptions)).
A number or a mapping is `None` with one `WARNING:` (`dataset metadata: <src> field <f> is of
type <type>, not text; skipped`): the source stated something not recordable.
`read_croissant` now uses it (before: `str(value)`, so a list became
`"['...']"` and `unknown` was a licence).

**Reader 1: `loom.run` with Croissant.** The four dataset calls
(`add_dataset`, `add_validation_dataset`, `add_input_dataset`,
`add_output_dataset`, on `loom` and on the run object) take keyword-only
`croissant=` (a local file) and `declared_license=` (the caller's own
statement). Local file only: loom has no network switch (it reads no
`offline` key), so there is no gate to mirror; a URL raises `ValueError`
at the call, as do a missing, malformed or nameless Croissant file. The
Croissant file is opened exactly as given (a `link/../c.json` follows the
link, as the OS does); its provenance label is its path from the current
directory when below it, else its bare name (`_loom_caller.cwd_relative_label`,
shared with the caller provenance), so no machine path is recorded. A FIFO or
other non-regular file is refused before the blocking open (`ValueError`), a
non-UTF-8 file names itself in the error, the URL check ignores the scheme's
case and catches `Path("https://...")` (`https:/...`), and a lone surrogate in
a Croissant string is escaped with one `WARNING:` (it crashed the writer).
Written onto the package (through `set_dataset_fields`,
`add_dataset_creator_agent` and `add_dataset_license`, factored out of
`assemble/spdx3/dataset.py` and shared with the model path): version,
description, download URL and its PURL, creator (`publishedBy` Agent),
licence, dataset size, collection process, preprocessing, known bias,
sensitive personal information (the fields `read_croissant` fills). Not
written: Croissant's name and dataset types (the call's win), keywords (no
SPDX 3.0.1 dataset property; the model path does not write them either).
`data_preprocessing=` on the call beats Croissant's, even `[]` (presence,
recorded per package by `LoomElements.declare_preprocessing`, not the
package's list being non-empty). A Croissant creator's name is cut as a
model's (`cap_model_name`), with one over-cap `WARNING:`. Code:
`src/pitloom/_loom_dataset_meta.py`; the package's provenance record is now
written when the run ends (`LoomElements.finish()`), one record holding the
caller and each source field. Its Annotation id is minted when the package
is (`emit_provenance(annotation_spdx_id=...)`), so a run with no sources
keeps the ids it had before these readers (writing at the end first
renumbered them against the model's record); ids are stable within a
version either way. The licence elements, their relationships and their
provenance Annotations are still minted at the end: what a package's
licence is (and so how many elements it needs) is known only once every
declaration is in, so adding a dataset to a script can renumber the licence
ids of the others. Same script, same ids.

**Hostile input, as one class (round 5).** Three boundaries, so no new
input shape crashes a run: `_parse_frontmatter` treats any exception of
the YAML parser as a parse failure (deep nesting raised `RecursionError`);
`loom` reads a directory dataset's card (a source the caller did not name)
through `_loom_dataset_meta._optional_card`, which skips it with one
`WARNING:` on any failure, as `enrich.run_enrichers` does for a model card;
`read_croissant` (a file the caller named) turns any failure into a
`ValueError` naming the file. Inside them: the `dataType` walk uses an
explicit stack (2000 levels raised `RecursionError`); a size or count is at
most `MAX_SAFE_INTEGER` (2^53 - 1, `core.canonical_json`), the largest
integer RFC 8785 writes (`2**53` failed the whole fragment in
`_graph_sort_key` at run end), as one value or as the record sets' sum
(`stated_total`: one `WARNING:` per field, not per record set); a card
`version` must be quoted text (YAML 1.1 reads `1:1:1` as 3661, `0x1F` as
31, `010` as 8, and the source spelling cannot be recovered), while a JSON
integer version stays accepted; card tags and Croissant data types go
through `stated_texts` like Croissant keywords. Lone surrogates are escaped
on the card's resulting metadata, not on its raw values. Checked for the
same integer limit: no other user-controlled integer reaches the loom writer
(hyperparameters and the parameter count are text).

**Value checks.** Every field `read_croissant` returns goes through
`pitloom.extract.dataset.values` (shared with the card readers): text is a
string, a one-item list or a JSON-LD `@value`/`@id` string, else absent with
one `WARNING:` (`description: ["a", "b"]` was written as its Python repr); a
version is text or, in JSON, a whole number (a float such as `1.10` warns); a size is a whole number of zero or more (`-5`, `true`, `1.9` and
`1e400` warn; `-5` crashed the writer at run end and `1e400` raised
`OverflowError`); a creator is text or a node's `name` (blank: none,
silently). Whole numbers over 64 digits warn (`str()` of a 5000-digit int
raises). A card whose YAML raises a bare `ValueError` (an impossible date
`2024-02-30`, an integer over Python's 4300-digit limit) or
`OverflowError` is the existing parse-failure `WARNING:`; on the Hub path
the whole card read is inside the request's `try`, so one bad third-party
card fails only that dataset, never the model SBOM.

**Reader 2: local dataset card.** `pitloom.extract.dataset.read_dataset_card`
reads `README.md` (case-insensitive) in a directory through the frontmatter
reader of `enrich/readme.py`, promoted to public `find_card_file` and
`read_card_frontmatter` with a `CardKind` (`MODEL_CARD`, `DATASET_CARD`)
for the warning wording and cap (1 MiB). Of several spellings of a card name
(`README.md`, `readme.md`), `find_card_file` takes the stem's own spelling,
else the first by name, whatever order the file system lists them in. Mapped: `license` (+
`license_name`/`license_link`), `pretty_name` -> `name` (else the
directory's name, no provenance), `version` (quoted text only; any YAML
number warns and is skipped), `tags` -> `keywords` (texts; other items warn,
a single string is one tag). Not read: prose, `description` and any
other key. `loom.run` reads the card of a dataset that is a directory; no
project scan walks dataset directories, so no other surface reads it. A
UTF-8 BOM before the frontmatter is now dropped (model cards too).

**Precedence.** Field by field: `declared_license=`, then Croissant, then
the card; a placeholder from a source is skipped, so a later source can still
give the field. A `declared_license=` on any declaration of the dataset beats
every Croissant file and card, whichever call came first
(`_loom_dataset_meta.DatasetSources`: declared first, then read, each in
declaration order); of two declared licences the first call's wins. Owner's
rule for the caller's placeholders: an explicit
`declared_license="NOASSERTION"` (any case) is the caller's statement and is
written (as the individual); the caller's `unknown`, blank or bare `other` is
weak as from any source (nothing written; the next source may fill it). A
`declared_license=` that is not a string raises `TypeError` at the call.

**Surfaces.** Library only (`loom.run`). The CLI has no dataset path; the
hook and the Action reach a loom dataset only through its merged fragment,
which keeps the licence (tested through `merge_fragments`).

**Tests.** `tests/extract/dataset/test_licence.py`, `test_card.py`,
`test_croissant.py` (licence rules), `tests/core/test_loom_dataset_sources.py`
(loom run: shapes, weak values, precedence, errors, display controls, byte
identity, fragment merge), `tests/core/test_loom_dataset_sources_rules.py`
(precedence across declarations, caller placeholders, presence, paths opened
as given, no machine path, annotation ids, creator cap). No conformance table cell moved: no conformance
scenario uses `loom.run` or a Croissant file yet.

## Built: reader 3

**Where.** `pitloom.extract.remote.huggingface_dataset.add_hub_dataset_metadata`,
called by `read_huggingface` right after the model card's datasets (card
`datasets:`, else the `dataset:*` tags) are listed. It is the only caller, so
a dataset is looked up exactly when its model is: `--offline` (or
`offline = true`) refuses the Hub model before any request, and
`HF_HUB_OFFLINE` makes `dataset_info()` fail, which warns, as the model's
own requests do. There is no other
switch to mirror.

**Requests, per dataset.** `dataset_info(id)` (owner, commit hash), then the
`README.md` at that commit through `hf_hub_download(repo_type="dataset")`
(the Hub file cache, as `ModelCard.load` uses for the model), read through
`enrich.readme.read_card` (new public helper: text and frontmatter, 1 MiB
cap, the cap and parse warnings of reader 2) with a `CardKind` of its own.
Mocking seam: `_load_dataset_info` / `_load_dataset_card`, patched by the
tests' `_patch_hf_calls(datasets=...)`.

**Mapped, 1:1.** `license` (+ `license_name`/`license_link` for `other`)
through `dataset_licence(..., field_prefix="dataset card ", where=...)`
(two new keyword arguments: the provenance `Field:` prefix, and the name a
warning gives, here `Hugging Face dataset <id>`); description: the card's
first prose paragraph (`_extract_card_description`, the model's helper);
keywords: card `tags` (`card_tags`, promoted from reader 2); version: the
commit hash (`commit_hash`, as for a model); creator: the owner
(`originator_names`, provenance `Method: repository_owner`), written as a
`publishedBy` Agent. Provenance `Source: Hugging Face Hub | Field: dataset
card <field>` / `dataset_info sha` / `dataset_info author`. Keywords have no
SPDX 3.0.1 dataset property: their provenance is now dropped by the writer
for every dataset (`assemble.spdx3.dataset.written_provenance`, shared with
the `loom` path, which dropped it by hand).

**Not looked up.** A name that is not a Hub repository id (`My corpus`;
also `o/d-`, `o/d.` and `o/d.git`, which `huggingface_hub` refuses, so a
lookup only warned); ids
past `MAX_HUB_DATASET_LOOKUPS` (20), with one over-cap `WARNING:` naming the
model and how many were skipped. A dataset listed twice (any letter case or whitespace) is one
reference, so it is requested once (see
[Built: edge-case hardening](#built-edge-case-hardening-2026-10-19)).

**Failure.** A failed `dataset_info()` is one `WARNING:` (`Failed to load
dataset_info() for <id>: ...`), no card request follows, and the dataset keeps
its name and download URL; a failed card download likewise (`Failed to load
dataset card for <id>`); a repository with no `README.md`
(`RemoteEntryNotFoundError`) and a card with no licence are silent. Never
fatal to the model SBOM.

**Seen on the live Hub (manual, not a test).** `allenai/c4` and
`HuggingFaceFW/fineweb` give `odc-by`, owner and commit; `wikipedia` states
its licence as a two-item list (`cc-by-sa-3.0`, `gfdl`), which the shared
rule refused with a `WARNING:`; the first prose paragraph of many dataset
cards is a table of contents, a `**Paper:**` line or HTML, read as the
description as the model helper reads a model card. Both ruled on and built
(next section).

**Not done.** No cap on the bytes `hf_hub_download` writes to the cache (the
read is capped); no request timeout of its own (the model's requests have
none either). Hub dataset `size_categories`, `task_categories` and similar
are not read: they do not map 1:1 onto a dataset property.

**Surfaces.** Library (`generate_model_sbom`, `read_huggingface`), `loom
model` and `loom generate` (tested); the Action runs `loom model`; the
build hook never reads a Hub model.

**Tables.** `hub`: G7 `DP-010`, CISA `COMP-006`/`COMP-008`, FSCT `COMP-002`,
BSI `COMP-003` to `present` (see the increment note in
[g7-conformance-tests.md](../implementation/g7-conformance-tests.md)).

**Tests.** `tests/extract/remote/test_huggingface_dataset.py` (licence
outcomes, every field, unstated fields, tag fallback, plain names and repeats,
cap, request failures, no card, capped read, escaped error, wrong licence
shape, id rule), `test_huggingface_dataset_surfaces.py` (library, `loom
model`, `loom generate`; provenance; byte identity; no request when offline).

## Built: licence lists and card descriptions

Owner rulings 2026-10-18.

**Licence lists.** A `license` that is a list of several texts (Hub
`wikipedia`, `multi_nli`; a local card; a Croissant file) gives one
`hasDeclaredLicense` per licence (SPDX 3 allows several), in the order
stated, once each (letter case ignored), each item by the single-value rules
(weak items dropped silently; an `other` in a several-item list has no text
of its own and is dropped: `license_name`/`license_link` apply to a one-item
list only). Non-text items: dropped with one `WARNING:` for the field
(`stated_texts`). A one-item list is a single value, as before.
`DatasetMetadata.license` stays the first licence (every presence check
unchanged); `further_licenses` (`FurtherLicences`: the rest, and the source
noun) is set only through `apply_dataset_licence` and taken only together
with `license` (`FOLLOWER_FIELDS`: the `loom` merge and the Hub repeat
copy), so `declared_license=` and source precedence move the list whole.
Provenance stays one entry.

**AND or OR.** A card listing several licences does not say whether they
combine as AND (all apply) or OR (a choice). Pitloom does not guess: when
two or more are recorded the dataset package `comment` says "The <dataset
card | Croissant file | Hugging Face dataset card> lists several licences; it
does not say whether they combine as AND or OR." One comment per dataset,
ahead of any provenance comment; none for one licence.

**Card descriptions.** `card_description` (`extract/remote/_card_description.py`,
model and dataset cards, moved out of `huggingface_fetch.py`) takes the first
prose paragraph: a fenced code block, a paragraph starting with an HTML tag,
or one whose every line is a heading, rule, table row, contents title,
link-only list item, image/badge run, or a bold key whose value is not a
sentence is passed over; one prose line keeps the paragraph whole; none
gives no description, silently. Length cap (500) unchanged.

**Not done.** Two licence texts that
normalise to one element (`MIT`, `MIT License`) give two relationships to it;
a comma-separated single string is not split; no Setext headings or
indented code blocks in the description rule.

## Built: edge-case hardening (2026-10-19)

Rulings follow the rules in CLAUDE.md: a source that never had a value is
quiet; one that stated something unrecordable warns.

**Nesting cap.** A Croissant file nests at most `CROISSANT_MAX_NESTING` (64)
levels of arrays and objects (real files: about ten). `fetch_json(max_nesting=)`
counts the levels on the decoded text before `json.loads`
(`json_nests_over`, a regex over strings and brackets, every encoding the
parser accepts), so a file is read or refused the same on every Python:
`json`'s own depth limit differs by release (3.11 fails at 2000 levels, 3.14
parses 100000), and the old test, which accepted either outcome, was skipped.
Over the cap is `ValueError: Croissant source 'f' is larger than the 64-level
Croissant-nesting cap` (a file the caller named is refused, not warned of).
`_data_type_values` stays an explicit stack. Tested at the cap, over it and
far over it (`tests/core/test_loom_dataset_sources_rules.py`), on 3.11 and
3.14 as well.

**Placeholders (`values.is_placeholder`).** `unknown`, `NOASSERTION` and `N/A`
(any case, stripped) state nothing, silently: a dataset version, creator
(also a creator node's `name`), licence (value, `license_name`,
`license_link`, list items) and download location. A name of `other` for an
`other` licence says nothing either; a real name or link is kept as the card
says (owner ruling above). `NONE` stays a statement. Not widened to other
spellings (`n.a.`, `tbd`, `-`): no list can be complete, and a text that is
not a placeholder is the source's claim. The download location (`url`) must
also be a URL (a scheme and a host, no whitespace: `https://`, `s3://`,
`hf://`); other text is dropped with one `WARNING:` (`field url is not a
URL`), since the source did state it. `license_link` is not URL-checked: it
is kept as text, as the Hub does. Description, `pretty_name` and keywords are
not screened for placeholders.

**Hub card warnings.** `read_card(name=)`: a downloaded card is named by its
dataset id, and an `OSError` is given by its reason, not the cache path it
quotes (`Failed to read Hugging Face dataset card o/d: Permission denied`);
`_load_dataset_card` does the same for a failed download. The model's own
Hub requests (`huggingface_fetch.py`) were not touched.

**Dataset names and the `datasets:` cap (`core/dataset_names.py`).** One
reference per dataset: names are stripped, whitespace runs compare as one
space, and a Hub repository id also compares without letter case; the first
spelling is kept, in card order (the Hub lookup's own repeat-copying is
gone: there are no repeats). A card lists at most `MAX_CARD_DATASETS` (1000,
as the per-field cap of the model readers) distinct datasets, with one
over-cap `WARNING:` (`FORMAT=huggingface FILE=<model URL>: larger than the
1000-dataset model-card-datasets cap; the first 1000 kept`; a local model card:
`FILE=<card path>`). Applies to the Hub model card and its `dataset:*` tag
fallback, and to the local model card's enrichment (which also skips a name
the model already has, by the same key). Not done: names from several sources
(model's own extraction vs a card) are matched, but plain names are not
case-folded (`My corpus` and `my corpus` are two).

**YAML 1.1 corner cases** are tabled in `tests/extract/dataset/test_card_yaml.py`
(booleans, octal-looking, dates, `null`, duplicate keys (last wins), merge
keys, tabs, alias fan-out); no code change was needed.

**Generated input.** `tests/extract/dataset/test_reader_fuzz.py`: four seeds
of 25 inputs for each of `read_croissant`, `read_dataset_card`, the Hub card
reader and the local model card (`random.Random(seed)`: odd types, NaN and
huge numbers, BOM, NUL, lone surrogates, truncation, deep nesting, aliases,
merge keys, tabs); each returns a valid, UTF-8-writable result or the
documented `ValueError`. A one-off run of 20,000 inputs found nothing. No
change to `fuzz/` (its harnesses are coverage-guided byte parsers).

## Order (settled)

Readers 1 and 2 (no network) were built first, reader 3 after the Hub gate.
