---
Created: 2026-08-25
Last-Modified: 2026-08-26
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
verbatim from a transparent, re-readable manifest
(`_TRANSPARENT_SOURCES` = pyproject.toml / hatchling build backend / setup.cfg
/ setup.py / wheel metadata / Hugging Face Hub) with no extraction `method`.
Everything else is kept: any recorded `method` (inferred/detected/dynamic/
caller/directive/inference), a non-manifest source (a pipdeptree scan, a
binary artifact's internal key, a synthesized phantom package), or the raw
PEP 508 `declared_constraint`.

### Config (`[tool.pitloom.provenance]`)

- `detail = "minimal" | "full"` — default `"minimal"`.
- `preserve-source-metadata = "auto" | "always" | "never"` — default
  `"auto"` (preserve an AI model's verbatim metadata only when the artifact is
  not shipped in the distribution and can't be re-extracted).
- `max-source-metadata-bytes = <int>` — default `0` (unlimited). Byte
  budget for the serialized artifact-metadata `Annotation.statement`
  (2026-08-26); unlike its siblings, also has a `--max-source-metadata-bytes`
  CLI flag / `action.yml` input, resolved at the CLI layer via
  `cli/commands/utils.resolve_effective_provenance()` rather than a new
  per-hop parameter — see "Size-bounded artifact-metadata preservation"
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
can inflate it into the multi-megabyte range (previously an open,
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

A negative or too-small-to-hold-data value (below `_MIN_EFFECTIVE_
MAX_SOURCE_METADATA_BYTES`, 8 bytes — the smallest possible JCS-encoded
JSON object, e.g. `{"a":""}`) is normalized to `0` (unlimited) with a
logged `WARNING`, via `core/provenance.normalize_max_source_metadata_bytes()`
— called from both the TOML reader and the CLI-override path, so every
construction route gets the same treatment.

Unlike every other `[tool.pitloom.provenance]` key, this one also has a
`--max-source-metadata-bytes` CLI flag and `action.yml` input — a byte
cap is judged an operational knob worth overriding per-run, unlike the
project-level policy choices the other keys represent. Resolved at the
CLI layer (`cli/commands/utils.resolve_effective_provenance()`, composing
a `dataclasses.replace()` onto the config-sourced `ProvenanceConfig`
before it's ever passed into the assembly pipeline) rather than adding a
new parameter at every hop the way `content_type_method` does — since
`ProvenanceConfig` already flows through `generate_project_sbom()` →
`build()` → `add_ai_models()` as one opaque object, no per-hop threading
was needed.

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
