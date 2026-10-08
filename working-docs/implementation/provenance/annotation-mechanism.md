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
dependency, used for the outer document). Every `Annotation.statement`
is now genuinely canonical, not just key-sorted — no insignificant
whitespace, so every statement also shrank a little for free.
`_sanitize_for_json()`'s fallback for unrecognized types (`np.float32`,
`Decimal`, etc.) changed from relying on `json.dumps`'s `default=str`
hook (which `rfc8785.dumps()` has no equivalent of) to stringifying them
itself before the value ever reaches the serializer.

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
JSON array or object. The GGUF float32 widening is a separate known bug
(see [known-bugs.md](../../design/known-bugs.md)).

**Follow-up rules (2026-10-08, #294 review).**

- *Collection elements* are text spelt as JSON spells them (`true`,
  `false`, `null`, `1`, `0.5`); a top-level scalar stays `str()`. Every
  collection with non-string elements comes from JSON (HDF5 `metrics`,
  PT2 `tags`), and its `properties` text is that JSON (`json.dumps`), so
  "the same text as `properties`" means JSON's spelling there. PT2 `tags`
  property text (comma-joined) now spells its elements the same way, via
  the shared `source_element_text()`. Rejected: `str()` everywhere (gives
  `"True"` beside `properties` `true`); a per-collection "came from JSON"
  flag (every current collection would set it, so one rule is simpler).
- *A key without a value is absent*, never `null` (a GGUF field with no
  parts). A `null` *element* is the text `"null"`, like `true`: elements
  are uniformly text, and the guard test asserts every scalar is a string.
- *Nesting is bounded* at `SOURCE_METADATA_MAX_DEPTH` (32) levels; a
  deeper part becomes its `json.dumps` text, or `<nested over 32 levels>`
  where that raises. The recursive walk raised `RecursionError` from about
  490 levels (two frames a level) and lost the whole model; measured
  without the bound, the rest of the pipeline (`_sanitize_for_json`,
  `rfc8785`) also fails from 491 levels, so 32 leaves a wide margin and
  far exceeds any real metadata.
- *Archive listings* record `archive_member_count` (always, text) beside
  the 20 names, since the `... (N total)` marker lives only in the
  `properties` text, which the SBOM does not carry.
