---
Created: 2026-08-25
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Annotation mechanism: when and how to use it

See also [annotation-provenance.md](annotation-provenance.md) (canonical
design rationale, start here), [role-vocabulary.md](role-vocabulary.md),
[use-case-catalog.md](use-case-catalog.md),
[multi-source-conflict.md](multi-source-conflict.md).

This file covers *when/how to use the `Annotation` mechanism at all*,
independent of what vocabulary or use case ends up inside one. See the
sibling files above for the `role` vocabulary and the specific use
cases that make use of this mechanism.

## Boundary refinement (2026-07-20): non-native, high-signal only

The first cut emitted a field-source Annotation for *every* field on *every*
element, much of it shadowing what SPDX already stores natively (a `name`
annotation on an element whose `name` is the native `Element.name`). This
refinement limits Annotations to what SPDX 3 **cannot** record natively, and
adds two new Annotation roles. Config-gated so an exhaustive audit is still
available.

### Extrinsic-assertion test (2026-08-10, supersedes "high-signal" as the stated rationale)

Annotation serves exactly one purpose in Pitloom: **provenance** — an
extrinsic assertion Pitloom (or an agent) makes *about* an element from
outside, never a restatement of the element's own intrinsic data. SPDX 3's
own `Annotation` definition backs this: an assertion in relation to an
element, explicitly *not part of the element's own definition*.

A second, rejected use would be treating Annotation as an extension slot
for intrinsic properties SPDX has no native field for (e.g. a dataset's
image count — SPDX 3.0.1/3.1 only has byte size). That is out of scope
here: if SPDX is missing a real field, the fix is a spec change or a
documented lossy fallback (`description`/`summary`), not an Annotation.
Annotation cannot fix a native-model gap because doing so would make it
represent an intrinsic characteristic, which contradicts its own
definition.

**The test:** does the Annotation's *role* stay extrinsic — an assertion
about the element from outside — even when its *payload* looks
data-shaped? Role, not payload shape, decides. Most entries pass trivially
(a `{source, method}` string is obviously an outside assertion). One
existing case is genuinely borderline and its justification is written
out explicitly at its definition below rather than left implicit: **P1**
(artifact-metadata preservation) embeds a verbatim metadata blob, which
looks intrinsic — see the P1 bullet in
[use-case-catalog.md](use-case-catalog.md) for why it still passes.

**Burden of proof:** any new Annotation use that looks even slightly
data-shaped must carry this same kind of explicit written justification
at its point of use. Silence is not an acceptable state for a borderline
case.

### Boundary principle (native-first)

1. Never put a value in an Annotation that has a native SPDX home; the
   Annotation only describes *how the value came to be*.
2. Never annotate a native relationship redundantly — the `dependsOn` edge is
   itself the record. (Removed the two relationship annotations in
   `deps.py add_dependencies` and `document.py build_deployed`.)
3. Field-level Annotations only when they add signal the native value can't
   convey (minimal mode). `full` mode keeps all field sources.
4. Process-level facts with no native anchor (fragment unification; enrichment
   override) are the highest-value Annotation content.

### High-signal test (`provenance.py _is_high_signal`)

A parsed field entry is dropped in minimal mode **only** when it was read
verbatim from a transparent, re-readable manifest (`_TRANSPARENT_SOURCES` =
pyproject.toml / hatchling build backend / setup.cfg / setup.py / wheel metadata
/ sdist PKG-INFO / Hugging Face Hub) with no extraction `method`. Everything
else is kept: any recorded `method` (inferred/detected/dynamic/
caller/directive/inference), a non-manifest source (a pipdeptree scan, a binary
artifact's internal key, a synthesized phantom package), or the raw PEP 508
`declared_constraint`.

### Config (`[tool.pitloom.provenance]`)

- `detail = "minimal" | "full"` — default `"minimal"`.
- `preserve-source-metadata = "auto" | "always" | "never"` — default
  `"auto"` (preserve an AI model's verbatim metadata only when the artifact is
  not shipped in the distribution and can't be re-extracted).
- `max-source-metadata-bytes = <int>` — default `0` (unlimited). Byte
  budget for the serialized artifact-metadata `Annotation.statement`
  (2026-08-26); unlike its siblings, also has a `--max-source-metadata-bytes`
  CLI flag / `action.yml` input, passed as the field-level override
  `ConfigOverrides.max_source_metadata_bytes` (normalised once in
  `apply_overrides()`) — see "Size-bounded artifact-metadata preservation"
  below.

All parsed/validated in `core/_config_parse.py` (`_read_provenance_settings`),
threaded through `build`/`build_model` and the `generate_*` / hatch-hook
entry points exactly as `provenance_format`/`schema` already were.

### Statement envelope convention (2026-08-10)

Every Pitloom statement schema shares the same two leading keys, so a
consumer can dispatch mechanically without pattern-matching prose:

- `"schema"` — the full versioned URL (`https://pitloom.dev/provenance/
  <kind>/<version>`, or `.../fields/<version>` for the default field-level
  schema).
- `"kind"` — a short string, always equal to the schema URL's own `<kind>`
  path segment (`"fields"`, `"unification"`, `"artifact-metadata"`,
  `"conflict"`).

Compound JSON keys use `camelCase`, matching the surrounding SPDX 3
JSON-LD style already used everywhere in the same document (`spdxId`,
`creationInfo`, `annotationType`). G2's `candidates` list settled on flat,
single-word fields (`value`/`role`/`source`/`ref`) once it moved to an
open candidate-list design instead of fixed `declaredLicenseId`-style
pairs, so none of the original four schemas needed a compound key at
first — but the convention was stated explicitly so the next schema that
*does* need one doesn't have to re-derive it. P1 (artifact-metadata) is
that schema: its optional truncation marker fields (`truncated`,
`truncatedKeys`, `truncatedKeyCount`, `maxMetadataBytes`) are the first
to use it, added 2026-08-26 — see below. Established retroactively
across all four original schemas in an earlier session (none had shipped
in a release yet, so no compatibility constraint).

### Size-bounded artifact-metadata preservation (2026-08-26)

P1's `Annotation.statement` embeds an AI model's raw metadata verbatim
with no inherent size limit — a real GGUF model's tokenizer vocab array
could inflate it into the multi-megabyte range (arrays are now recorded
as their length only) (previously an open,
unimplemented gap — `working-docs/design/provenance-enrichment-vocabulary.md`
open question #7). `max-source-metadata-bytes` (`ProvenanceConfig` field
`max_source_metadata_bytes`, default `0` = unlimited) caps this.

Truncation happens at the dictionary level only — whole `metadata` keys
are dropped, largest-serialized-size first, never a value cut
mid-string (which would produce invalid JSON). This is implemented in
`assemble/spdx3/provenance.py`'s `_truncate_metadata_for_budget()`,
re-checking the real RFC 8785-serialized byte length of the candidate
envelope after each drop rather than approximating it — cheap at the
realistic key counts here (a model's own KV/metadata table: dozens of
keys, not thousands). When triggered, the envelope gains
`truncated: true`, `truncatedKeys` (sorted alphabetically, regardless of
drop order), `truncatedKeyCount`, and `maxMetadataBytes` — an explicit,
visible marker, never a silent size reduction. Two edge cases: if
dropping every key still leaves the envelope's own fixed overhead
(schema/kind/format/markers) over budget, no Annotation is emitted at
all (`build_source_metadata_annotation()` returns `None`, same as
today's "empty original metadata" case); if the overhead fits but every
key had to go, the Annotation is emitted with `metadata: {}`. Both log a
`WARNING`.

**Entry-cap marker (2026-10-08, #294).** `cap_entries()` keeps the first
`MAX_MODEL_ENTRIES` (1000) `raw_metadata` keys; the cut used to be
announced only by the scanner's `WARNING:`, so the annotation itself
looked complete. `AiModelMetadata.raw_metadata_dropped` (default `0`)
counts the keys left out: `cap_entries()` adds its cut, and the
Safetensors reader its own pre-cut (`_stable_metadata()` keeps
`MAX_MODEL_ENTRIES + 1` keys so the cap still fires), so the sum is the
true count. The envelope then gains `truncated: true`,
`truncatedKeyCount` and `maxEntries` -- no key list: naming up to
millions of keys would cost what the cap saves. Both truncations merge
in one envelope: `truncatedKeys`/`maxMetadataBytes` stay the byte
budget's, `truncatedKeyCount` counts both (so it exceeds
`len(truncatedKeys)` by exactly the entry-cap count when `maxEntries` is
present), and the budget check sizes the envelope with the entry-cap
markers in it. `MAX_MODEL_ENTRIES` moved to `core/ai_metadata.py` (still
importable from `extract/ai_model/limits.py`) so `assemble` names it
without importing the readers.

Only `0` or at least `MIN_SOURCE_METADATA_BYTES` (8 bytes — the smallest
possible JCS-encoded JSON object, e.g. `{"a":""}`) is valid; a negative,
non-integer or 1-to-7 value is a `ValueError`, via
`core/provenance.require_max_source_metadata_bytes()` — called from the
TOML reader, the CLI flag's argparse type, `ConfigOverrides`,
`ProvenanceConfig` and the embed path, so every construction route gets the
same check. (An earlier version collapsed such a value to `0`, unlimited,
with a `WARNING`: a typo silently removed the cap.)

Unlike every other `[tool.pitloom.provenance]` key, this one also has a
`--max-source-metadata-bytes` CLI flag and `action.yml` input — a byte
cap is judged an operational knob worth overriding per-run, unlike the
project-level policy choices the other keys represent. Originally
resolved at the CLI layer (a `dataclasses.replace()` onto the
config-sourced `ProvenanceConfig`); now the field-level override
`ConfigOverrides.max_source_metadata_bytes`, layered in
`apply_overrides()` onto whatever provenance settings the config (or a
`provenance=` object) gave, and a `max_source_metadata_bytes=` parameter
on every generator, so the library and every CLI command apply it the
same way (see [config-sources.md](../config-sources.md)). Below the
generators no per-hop threading is needed: `ProvenanceConfig` flows
through `build()` → `add_ai_models()` as one opaque object.

**Also 2026-08-26**: `_build_json_annotation()` (shared by all four
schemas) switched from plain `json.dumps(..., sort_keys=True)` to true
RFC 8785 (JCS) canonicalization (`rfc8785.dumps()`, already a project
dependency, used for the outer document). The statements it builds
became genuinely canonical, not just key-sorted — no insignificant
whitespace, so every statement also shrank a little for free.
`_sanitize_for_json()`'s fallback for unrecognized types (`np.float32`,
`Decimal`, etc.) changed from relying on `json.dumps`'s `default=str`
hook (which `rfc8785.dumps()` has no equivalent of) to stringifying them
itself before the value ever reaches the serializer.

**2026-10-08 (#294): one helper for every embedded JSON text.** The
2026-08-26 switch missed the `fields` statement (`PitloomV1Encoder.encode()`
kept `json.dumps(sort_keys=True)`, spaced), and JSON texts outside
annotations were spaced too: `ai_informationAboutApplication`, fastText
and CRFsuite `labels`, HDF5 `loss`/`metrics`, and the JSON text of a
collection nested past the 32-level bound. All now go through
`pitloom.core.canonical_json.canonical_json()` (the sanitizer moved there
as `json_safe()`), so every `Annotation.statement` and every other JSON
text in an SBOM string is RFC 8785. `json_safe()` makes a string of what
RFC 8785 rejects: NaN and the infinities as `scalar_text()` spells them
(`NaN`, `INF`, `-INF`; the sanitizer used to write `Infinity`, a second
spelling of one value), and an integer beyond +-(2^53 - 1) as its full
decimal (`rfc8785` raises `IntegerDomainError`; a float would lose
digits). Artifact-metadata values are already `scalar_text()` strings, so
these cases reach the helper only from a collection's elements as read
(HDF5 `training_config` JSON, which `json.loads()` lets hold `NaN`) and
from enrichment/conflict values. `json_safe()` takes one stack frame per
nesting level (loops, not comprehensions), as the parser and `rfc8785` do;
an HDF5 `loss`/`metrics` the parser held but the serialiser cannot is a
`training_config` problem (`WARNING:`, that field left out), not a crash.
Guard: `test_every_embedded_json_text_is_canonical` walks every string of
every fixture model's SBOM and checks each JSON-object/array text equals
its RFC 8785 form. RFC 8785 sorts keys by UTF-16 code unit, unlike
`sort_keys` (code point) for a non-BMP key; canonical wins.

### Value types in artifact-metadata `metadata` (2026-10-08)

**Decision (user, #294).** In `metadata`, every *collection* is a real JSON
array (or object, where the file has a mapping) and every *scalar* is
*text*: the same text as the model's `properties` map. No JSON numbers or
booleans. Every model format follows it, so a consumer handles all
formats the same way: parse a string if you need a number.

**Why a collection is an array.** A list stored as a string (fastText
`labels` as `"[\"a\", \"b\"]"`, PT2 `tags` as `"a, b"`) forces a second
parse and an ambiguous separator (a label may contain `,`). Found in the
#294 review: fastText gave a JSON-in-a-string while CRFsuite (native
`raw_metadata`) gave an array, so one key had two types.

**Why a scalar is text, not a number.**

- *Precision.* RFC 8785 (JCS, how `statement` is canonicalised) serialises
  every number as an IEEE-754 double (ECMAScript rules), so an integer
  above 2^53 cannot round-trip, and many consumers (JavaScript, `jq`,
  databases) parse JSON numbers into doubles. A float32 stored in a file is
  widened on the way in: GGUF's `1e-6` was recorded as
  `9.999999974752427e-07`. Text carries exactly what Pitloom read.
- *No computation.* Nothing in Pitloom reads the annotation back, and
  nobody is expected to calculate on these values; they are provenance.
- *Same as SPDX.* The typed SPDX 3 fields Pitloom fills from the same data
  (`ai_hyperparameter`, `DictionaryEntry.value`) are strings. The
  annotation matches them, so one value has one spelling everywhere.
- *No int/float ambiguity.* `1`, `1.0` and `"1"` are three different
  facts to a typed consumer; text keeps the reader's own spelling.

**Alternatives rejected.**

- Native numbers where the file stores a number (GGUF's old behaviour):
  keeps types but carries the precision hazards above, and needs a rule
  per format for which values are "the file's own".
- Decoding JSON-looking strings in the annotation builder: a GGUF string
  that merely looks like an array would be converted silently.
- Leaving the formats inconsistent and documenting it: every consumer would
  need a per-format decoder.

**Consequences.** The `properties` map, hyperparameters and provenance are
unchanged; only the annotation's `metadata` values change type, for the
formats that had flattened collections or native scalars. A new reader
sets `raw_metadata` through the shared helper; the guard test that runs
every fixture fails on a number, a boolean or a string that parses as a
JSON array or object. The GGUF float32 widening was fixed with the one
spelling below.

**Follow-up rules (2026-10-08, #294 review).**

- *Collection elements* are text spelt as JSON spells them (`true`,
  `false`, `null`, `1`, `0.5`); a top-level scalar stays `str()`. Every
  collection with non-string elements comes from JSON (HDF5 `metrics`,
  PT2 `tags`), and its `properties` text is that JSON (`canonical_json()`), so
  "the same text as `properties`" means JSON's spelling there. PT2 `tags`
  property text (comma-joined) now spells its elements the same way, via
  the shared `source_element_text()`. Rejected: `str()` everywhere (gives
  `"True"` beside `properties` `true`); a per-collection "came from JSON"
  flag (every current collection would set it, so one rule is simpler).
- *A key without a value is absent*, never `null` (a GGUF field with no
  parts). A `null` *element* is the text `"null"`, like `true`: elements
  are uniformly text, and the guard test asserts every scalar is a string.
- *Nesting is bounded* at `SOURCE_METADATA_MAX_DEPTH` (32) levels; a
  deeper part becomes its `canonical_json()` text, or `<nested over 32 levels>`
  where that raises. The recursive walk raised `RecursionError` from about
  490 levels (two frames a level) and lost the whole model; measured
  without the bound, the rest of the pipeline (`_sanitize_for_json`,
  `rfc8785`) also fails from 491 levels, so 32 leaves a wide margin and
  far exceeds any real metadata.
- *Archive listings* record `archive_member_count` (always, text) beside
  the 20 names, since the `... (N total)` marker lives only in the
  `properties` text, which the SBOM does not carry.

**One spelling and `valueTypes` (2026-10-08, #294; schema `/2`).** Built
from [scalar-text-spelling.md](../scalar-text-spelling.md)
(option D), which supersedes the `str()` rule above for top-level
scalars:

- *Spelling.* `pitloom.core.scalar_text.scalar_text()` is the only way a
  scalar becomes text, in `properties`, in `ai_hyperparameter` (via
  `value_text()` in `_populate_ai_pkg_hyperparameters`) and in the
  annotation, top level and collection elements alike: `true`/`false`;
  integers in decimal, never through `rfc8785`; floats as
  `rfc8785.dumps(float(x))`; NaN, +inf, -inf as `NaN`, `INF`, `-INF`;
  `-0.0` as `0` (the one documented loss). `bool` is tested first (it is an
  `int`); NumPy scalars are recognised through the `numbers` ABCs and
  `numpy.bool_` through `sys.modules`, so NumPy is never imported.
- *GGUF float32.* `_field_value` narrows a `FLOAT32` field to
  `float(numpy.format_float_scientific(x, unique=True))` (`str(x)` follows
  `numpy.set_printoptions`: `legacy="1.13"` prints `1.0000001` as `1`);
  a `FLOAT64` keeps its value. Only GGUF declares a float32; an HDF5
  float32 attribute is spelt as the double it widens to. That fixed
  the widening bug (stored `1e-5` is now `0.00001`, not
  `9.999999747378752e-06`). fastText `lr`/`t` are C++ `double`s
  (`0.05` reads back exact), so nothing is narrowed there.
- *`valueTypes`.* An envelope object, top-level `metadata` key ->
  `integer` | `float` | `boolean`, only for non-string scalars, emitted
  only when non-empty; elements inside a collection are not typed. The
  reader supplies it: `source_metadata(items, natives)` returns the
  `SourceMetadata` TypedDict keyed `raw_metadata`/`raw_metadata_types`,
  which every reader splats into `AiModelMetadata(...)` (a test fails any
  call that sets either keyword by hand), typing each key from its native
  value (`scalar_type()`), so a reader hands over the native value of a
  property it holds as text (`record_scalar_property()`: ONNX `opset.*`,
  CRFsuite `num_*`, HDF5 `layer_count` and a non-string `loss`/`metrics`,
  archive `archive_member_count`; HDF5 a numeric `backend` or
  `model_config` root attribute). GGUF `general.name`/`description`/
  `version`/`architecture` use `value_text()`, so the package field
  spells a non-string value as `properties` does.
  The types ride on `AiModelMetadata.raw_metadata_types`; `cap_entries()`
  and the byte-budget truncation drop a dropped key's type with it, and a
  type counts towards the budget.
- *SPDX layers.* SPDX 3.0.1 canonical serialisation fixes JSON tokens
  (`true`, base-10 integers) for typed properties; our text sits inside
  `xsd:string` values (`DictionaryEntry.value`, `Annotation.statement`),
  which it does not cover, so `true` follows JSON and `xsd:boolean`, and the
  float spelling follows RFC 8785.
- *Hugging Face.* The fallback blob (no model file: `properties`,
  `extra_data`, `extra_lists`) goes through the same `source_metadata()`,
  so `/2` holds for every annotation (an `hf.tokenizer_max_length` past
  2^53 is text, not an `rfc8785` `IntegerDomainError`).
- *HDF5 `loss`/`metrics`.* A string is kept as is (`metrics` was
  `json.dumps`, so `"acc"` was `"\"acc\""`); a number or boolean is its
  scalar text, typed; a list or object is JSON text in `properties` and
  the collection in the annotation.
- *Collection JSON text.* The JSON text of a collection in `properties`
  (HDF5 `loss`/`metrics`, fastText/CRFsuite `labels`) goes through
  `canonical_json()`, so a float element there is spelt as RFC 8785 does,
  like the annotation element.

### Untrusted model text: annotation as read, display escaped (2026-10-08)

#294 review. Bidi controls (U+202E reorders `txt.exe` to `exe.txt` on
screen) and zero-width characters read from a model file reached the
package `name`, `description` (the CRFsuite labels) and hyperparameters
raw. Decided: one helper, `core/untrusted_text.escape_display_controls()`
(17 code points: U+061C, U+200B-U+200F, U+202A-U+202E, U+2060,
U+2066-U+2069, U+FEFF, each written as the text `\uXXXX`, lowercase
hex as JCS spells its own `\u00xx`), applied once
per AI package by `_ai_package.finish_ai_package()` after the provenance
`comment` is written, on both the project-scan and the `loom model` path,
with one `WARNING:` listing the properties changed. Not per reader: one
choke point covers every format and Hugging Face. The `spdxId` keeps the
resolved name (the IRI percent-encodes these controls), so ids and the
registry agree across surfaces. The JSON text of
`ai_informationAboutApplication` is escaped in place
(`escape_display_controls_in_json()`, `\\uXXXX`): equal to escaping each
string before RFC 8785 serialisation, which writes these code points raw.

The artifact-metadata annotation `metadata` stays as read: it is data
(JSON strings for a program), and it is where the original text survives.
The escape is not reversible on its own: a `\u202e` the file wrote as six
characters is kept as is; escaping `\` too would have changed every
backslash in display text with no control in it. Rejected: stripping the
controls (silent loss), escaping in each reader (drifts, and the honest
field rule keeps read values as read).

Extended in the same PR to every element a model brings in: the
base-model package and its relationship, dataset packages, their creators
and relationships, `externalRef`/`externalIdentifier` text, through one
generic `_display_text.escape_element_display_text()` (a property table
applied where the element's class has the property). The warning stays one
per model: `finish_ai_package()` runs after datasets are added and takes
the related elements, labelled (`base model name`, `dataset name`). A URL
is percent-encoded instead (`escape_display_controls_in_iri()`): a `\` is
not valid in one. The base-model lookup also matches an already escaped
package name, so a later model whose base is an earlier one still links to
it. One set, `DISPLAY_CONTROLS`, is shared by `iri_segment()` (which now
percent-encodes the isolates, zero-width characters and BOM too, beyond RFC
3987's list) and `sanitize_provenance_text()`; `loggable()` and
`escape_file_name_part()` cover it as non-printable / category `C*`. A
drift-guard test checks all six. Consumer-facing layering:
`docs/metadata-reading-back.md`.

Same review, same shape of cap: a name over 1024 code points is cut
(`cap_model_name()`, in `own_name`/`file_name_stem`, so the registry
candidates and `resolve_name()` see one cut name), its provenance gets
`Note: cut to 1024 characters`, one warning from `cap_and_warn()`
(`settle_read_text()`; `read_huggingface()` for a Hub model). The cap was
256 at first; a later round raised it to 1024 and ended the cut name with
`...~` and 8 hex digits of the SHA-256 of the whole name, after two long
names sharing their first 256 characters got one `SpdxDocument` and one
package id under `loom model`, and an enrichment fragment targeted the
wrong model. Base-model, dataset and dataset-creator names are cut the
same way at assembly (`cap_related_name()`), each with its own warning
label. The worst-case `spdxId` from a cut name (1024 non-`ucschar` 4-byte
code points, each percent-encoded to 12 characters) is about 12 KB per
occurrence; a test pins the bound. A lone surrogate (`json.loads` and
YAML accept `"\ud800"`) aborted the whole SBOM (`UnicodeEncodeError` in
`uuid5`, JCS key sorting, the file write); `settle_read_text()` (and the
README enricher for its front matter) now writes each as `\udXXX` text
where the model is read, before any id is derived, with one warning,
rather than at each consumer. A label over
4 KiB (`Limits.max_label_bytes`) drops every label of a CRFsuite or
fastText model with one warning, the counts kept
(`limits.recordable_labels()`). The CRFsuite labels chunk bound stays
1 MiB, renamed `max_crfsuite_labels_chunk_bytes`: it bounds the whole
chunk (hash tables included, about 2 KiB empty), not one label.
