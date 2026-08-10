---
Created: 2026-07-20
Last-Modified: 2026-08-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Implementation plan: metadata provenance via SPDX 3 Core/Annotation

**Status:** implemented and merged
(PR [#102](https://github.com/bact/pitloom/pull/102)) --
see §9 for what shipped vs. deferred, and **§10 for the boundary
refinement** (non-native / high-signal only, config-gated) plus the Phase 2
native-backfill checklist (5 of 6 items shipped as of 2026-08-08; N3 still
blocked -- see
[`phase2-native-backfill-handover.md`](phase2-native-backfill-handover.md)
for current status).
**Planned with:** Opus 4.8. **Implemented by:** Sonnet 5.
**Related design docs:** [`working-docs/design/metadata-provenance.md`](../design/metadata-provenance.md),
[`working-docs/design/model-metadata-extraction.md`](../design/model-metadata-extraction.md).

This is a self-contained handover. An implementing agent should be able to
work from this file plus the cited source locations without re-deriving the
design.

---

## 1. Goal

Today Pitloom records *metadata provenance* (where each SBOM field was
collected/extracted from) by flattening a per-field `dict[str, str]` into the
SPDX `comment` attribute as a string like:

```text
Metadata provenance: name: Source: pyproject.toml | Field: project.name; license: Source: Hugging Face Hub | Field: model card
```

Good for humans, but error-prone to parse and unable to carry richer or
structured provenance.

Replace this with **SPDX 3 Core/`Annotation`** elements that record provenance
systematically and machine-readably, including for **AI model** provenance.
Keep a human-readable path for back-compat during migration.

Spec references:

- Annotation class: <https://spdx.github.io/spdx-spec/v3.0.1/model/Core/Classes/Annotation/>
- Model TTL: <https://spdx.org/rdf/3.0/spdx-model.ttl>

---

## 2. Current state (verified against code, 2026-07-20)

### 2.1 Provenance data model

Provenance is a `dict[str, str]` field on each format-neutral metadata object,
keyed by SBOM field name, value already semi-structured as pipe-delimited
`"Key: value | Key: value"` segments:

- `ProjectMetadata.provenance` — [`src/pitloom/core/project.py:77`](../../src/pitloom/core/project.py)
- `AiModelMetadata.provenance` — [`src/pitloom/core/ai_metadata.py:201`](../../src/pitloom/core/ai_metadata.py)
- `DatasetMetadata.provenance` — [`src/pitloom/core/dataset_metadata.py:89`](../../src/pitloom/core/dataset_metadata.py)

Example values produced by extractors:

- `"Source: pyproject.toml | Field: project.name"` — [`src/pitloom/extract/pyproject.py:81`](../../src/pitloom/extract/pyproject.py)
- `"Source: Hugging Face Hub | Field: model card"` — [`src/pitloom/extract/_huggingface.py:453`](../../src/pitloom/extract/_huggingface.py)
- `f"{source} | Field: extra/name"` — [`src/pitloom/extract/_pytorch_pt2.py:132`](../../src/pitloom/extract/_pytorch_pt2.py)

The pipe/`Key: value` convention is consistent enough to parse. Anything that
does not fit `Key: value` must be preserved (see parser rules in §5.1).

### 2.2 Where provenance is written into `comment` today (all call sites to migrate)

| Subject element | Location |
| --- | --- |
| Main Python package | [`src/pitloom/assemble/spdx3/document.py:45`](../../src/pitloom/assemble/spdx3/document.py) (`_build_provenance_comment`), applied at `:102` |
| AI `ai_AIPackage` | [`src/pitloom/assemble/spdx3/ai.py:193`](../../src/pitloom/assemble/spdx3/ai.py) (`_build_ai_package`) |
| Dataset package | [`src/pitloom/assemble/spdx3/dataset.py:160`](../../src/pitloom/assemble/spdx3/dataset.py) |
| Dependency packages / license text / relationships | [`src/pitloom/assemble/spdx3/deps.py:211,291,308,346`](../../src/pitloom/assemble/spdx3/deps.py) |
| pipdeptree deps | [`src/pitloom/assemble/spdx3/document.py:537,571`](../../src/pitloom/assemble/spdx3/document.py) |
| Loom SDK fragments | [`src/pitloom/loom.py:249,307`](../../src/pitloom/loom.py) |

### 2.3 SPDX Annotation binding (verified)

`spdx3.Annotation` (subclass of `Element`) in
`spdx_python_model.bindings.v3_0_1`:

- `annotationType` — **required**, enum with only two members:
  `AnnotationType.other` and `AnnotationType.review`. **There is no
  `provenance` value.** Provenance annotations use `other`.
- `contentType` — optional MIME string, constrained by regex `^[^/]+/[^/]+$`
  (exactly one slash; no slash inside either part). `application/json` and
  `application/ld+json` both match; anything with two slashes does not. Use
  `application/json`.
- `statement` — optional free string (the annotation body).
- `subject` — **required**, an `Element` reference (serialized as the subject's
  `spdxId`).
- Inherited from `Element`: `spdxId`, `creationInfo` (**required**), `name`,
  `comment`, etc.

### 2.4 Supporting infrastructure to reuse

- ID minting: `generate_spdx_id(prefix, doc_name, doc_uuid)` —
  [`src/pitloom/core/models.py:234`](../../src/pitloom/core/models.py). Per
  `(doc_uuid, prefix)` counter. Use prefix `"Annotation"`.
- Shared `CreationInfo` (carries pitloom `Agent` via `createdBy` and `Tool`
  via `createdUsing`) — [`src/pitloom/assemble/spdx3/creation_info.py`](../../src/pitloom/assemble/spdx3/creation_info.py).
- Exporter collectors (`add_package`, `add_relationship`, …) —
  [`src/pitloom/export/spdx3_json.py:219-302`](../../src/pitloom/export/spdx3_json.py).
  A new `add_annotation` follows the same pattern.
- `require_spdx_id(element)` — [`src/pitloom/export/spdx3_json.py:32`](../../src/pitloom/export/spdx3_json.py).

### 2.5 Determinism constraints (do not break)

From prior work (SBOM unification): output must be byte-stable for
reproducible builds.

- Emit annotations in a **deterministic order** (sort subjects before
  emitting, so the `Annotation-N` counter is stable).
- JSON statement must use `sort_keys=True`.
- Content signatures / unification must continue to exclude `_id`. Annotations
  are new leaf elements keyed by subject; they should not participate in
  fragment unification (they are document-local provenance, not shared
  identity). Confirm they are excluded from any dedup pass in
  [`src/pitloom/assemble/spdx3/fragments.py`](../../src/pitloom/assemble/spdx3/fragments.py).

---

## 3. Design decisions (settled — do not relitigate)

1. **One Annotation per subject Element**, not one per field. The `statement`
   is a JSON object keyed by field name. Rationale: avoids element explosion,
   keeps the graph small, and mirrors the existing `provenance` dict 1:1.

2. **`contentType = "application/json"`**, `statement` = a JSON string.
   *Serialization limit, accepted:* in both JSON-LD and Turtle the `statement`
   is a single string literal — the JSON is opaque text to SPARQL, parseable
   only after string extraction. This is acceptable now. If a consumer later
   needs field-level SPARQL, revisit with per-field `text/plain` annotations
   (heavier). Documented as a known tradeoff, not a blocker.

3. **`annotationType = other`.** The spec enum has no provenance member.
   Disambiguation comes from `contentType` + a `schema` marker inside the JSON
   envelope (see §5.2), never from the enum.

4. **"Who/when extracted" lives in the Annotation's own `creationInfo`**
   (`createdBy` = pitloom Agent, `createdUsing` = pitloom Tool, `created` =
   timestamp), reusing the shared `CreationInfo`. Do **not** duplicate tool
   identity inside the statement.

5. **AI model provenance keeps two axes separate:**
   - *Metadata provenance* — where pitloom read each AI field (HF Hub, model
     card, safetensors header, GGUF kv, PT2 `extra/*`, commit SHA). → goes in
     the Annotation.
     `known_biases` is **not** provenance — leave it in `comment` (or move to
     a proper `ai_*` property later; out of scope here).
   - *Model lineage* (base model, training datasets) — already modeled by
     relationships / dataset packages. Do **not** fold lineage into the
     Annotation.

6. **Migration via config toggle**, not a hard cut:
   `[tool.pitloom.provenance] format = "annotation" | "comment" | "both"`.
   Default `"both"` on first ship, then flip default to `"annotation"` in a
   later change once downstream consumers are updated. Keeps existing tests
   green during transition.

7. **Statement schema is pluggable.** Ship Pitloom's own simple schema now
   (`https://pitloom.dev/provenance/1`), but do **not** hard-code it into the
   annotation builder. Provenance is produced by a small **statement encoder**
   interface, selected by a schema id, so a future external AI-model-provenance
   schema (see §8 candidates) can be added as another encoder without touching
   the call sites. Requirements this imposes on the design:
   - The `schema` id (a URL) is self-describing and lives inside the statement
     payload, so a reader can always tell which encoder produced it.
   - The encoder owns **both** the `contentType` and the serialized
     `statement` — a future schema may need a different MIME (e.g.
     `application/ld+json`) or a non-JSON body. The builder must not assume
     `application/json`.
   - Selection is config-driven: `[tool.pitloom.provenance] schema = "pitloom/1"`
     (default), resolvable to the registered encoder. Unknown id → clear error
     listing registered schemas.
   - The internal `provenance: dict[str, str]` (field → source string) stays
     the single input contract; encoders translate from it. Extractors do not
     change when the schema changes.

---

## 4. Statement schema (pluggable; default = pitloom/1)

A **statement encoder** turns the internal `provenance: dict[str, str]` into a
`(content_type, statement)` pair. Encoders are registered by schema id; the
active one is chosen by config (decision §3.7). Interface:

```python
class ProvenanceEncoder(Protocol):
    schema_id: str  # e.g. "pitloom/1"; the self-describing URL form
    content_type: str  # MIME for the Annotation.contentType

    def encode(self, provenance: dict[str, str]) -> str:
        """Return the serialized Annotation.statement body."""
```

A tiny registry maps `schema_id -> encoder`; `resolve_encoder(id)` raises a
clear error listing known ids when unknown. Only `pitloom/1` ships now.

### 4.1 Default schema: `pitloom/1`

`content_type = "application/json"`. Envelope (self-describing via the
`schema` URL, byte-stable via `sort_keys`):

```json
{
  "schema": "https://pitloom.dev/provenance/1",
  "fields": {
    "<field name>": {
      "source": "<where, e.g. 'Hugging Face Hub'>",
      "location": "<optional, e.g. 'model card' or 'project.name'>",
      "method": "<optional, e.g. 'extraction'>",
      "note": "<optional; catches any unparseable segment>"
    }
  }
}
```

Field sub-keys are all optional except that each field maps to a non-empty
object. Unknown pipe segments are preserved under `note` so no information is
lost. Keys within objects are lower-cased parse keys (`source`, `field`→
`location`, etc. — see mapping in §5.1).

### 4.2 Future schemas

Adding an external AI-model-provenance schema = one new `ProvenanceEncoder`
implementation + registry entry (+ possibly a mapping from Pitloom's internal
`dict` to that schema's shape). No change to call sites, extractors, or the
`Annotation`-building glue. See §8 for candidate schemas.

---

## 5. Implementation

### 5.1 Parser: provenance string → structured dict

Segment key normalization mapping (case-insensitive):

- `Source` → `source`
- `Field` → `location`
- `Method` → `method`
- `Package` → `package`
- anything else → keep lower-cased key as-is
- segment with no `:` → append to `note`

### 5.2 New module `src/pitloom/assemble/spdx3/provenance.py`

The builder is schema-agnostic: it asks the active **encoder** for
`content_type` + `statement`. Ship one encoder (`pitloom/1`); future schemas
register alongside it (§4).

```python
# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Build SPDX 3 Core/Annotation elements recording metadata provenance.

Provenance answers "where did Pitloom collect this field from". The *who/when*
(pitloom Agent + Tool + timestamp) is carried by the Annotation's own
``creationInfo``. The *what/where* (per-field source) is carried by the
``statement``, whose shape and ``contentType`` are decided by a pluggable
:class:`ProvenanceEncoder` selected by schema id -- so an external AI-model
provenance schema can be adopted later without touching call sites.
"""

from __future__ import annotations

import json
from typing import Protocol

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.models import generate_spdx_id

#: Segment-key normalization for the ``"Key: value | Key: value"`` strings.
_KEY_MAP = {
    "source": "source",
    "field": "location",
    "method": "method",
    "package": "package",
}


def parse_provenance_value(value: str) -> dict[str, str]:
    """Parse ``"Source: X | Field: Y"`` into a structured dict.

    Segments without a ``:`` and segments with unknown keys are preserved so
    that no information is silently dropped. Shared by any encoder that wants
    the pre-parsed form; encoders are free to consume the raw string instead.
    """
    parsed: dict[str, str] = {}
    notes: list[str] = []
    for raw in value.split("|"):
        segment = raw.strip()
        if not segment:
            continue
        key, sep, val = segment.partition(":")
        if sep:
            norm = _KEY_MAP.get(key.strip().lower(), key.strip().lower())
            parsed[norm] = val.strip()
        else:
            notes.append(segment)
    if notes:
        parsed.setdefault("note", " | ".join(notes))
    return parsed


class ProvenanceEncoder(Protocol):
    """Turns Pitloom's ``field -> source string`` map into an SPDX statement."""

    schema_id: str  # short id used in config, e.g. "pitloom/1"
    content_type: str  # value for Annotation.contentType

    def encode(self, provenance: dict[str, str]) -> str:
        """Return the serialized ``Annotation.statement`` body."""
        ...


class PitloomV1Encoder:
    """Pitloom's own simple JSON schema (the default)."""

    schema_id = "pitloom/1"
    schema_url = "https://pitloom.dev/provenance/1"
    content_type = "application/json"

    def encode(self, provenance: dict[str, str]) -> str:
        fields = {
            field: parse_provenance_value(src) for field, src in provenance.items()
        }
        envelope = {"schema": self.schema_url, "fields": fields}
        # sort_keys keeps output byte-stable for reproducible builds.
        return json.dumps(envelope, ensure_ascii=False, sort_keys=True)


#: Registry of available encoders, keyed by ``schema_id``. Future external
#: schemas add themselves here.
_ENCODERS: dict[str, ProvenanceEncoder] = {
    PitloomV1Encoder.schema_id: PitloomV1Encoder(),
}

DEFAULT_SCHEMA_ID = PitloomV1Encoder.schema_id


def resolve_encoder(schema_id: str | None = None) -> ProvenanceEncoder:
    """Return the encoder for ``schema_id`` (default when ``None``)."""
    key = schema_id or DEFAULT_SCHEMA_ID
    try:
        return _ENCODERS[key]
    except KeyError:
        known = ", ".join(sorted(_ENCODERS))
        raise ValueError(f"Unknown provenance schema {key!r}; known: {known}") from None


def build_provenance_annotation(
    subject_spdx_id: str,
    provenance: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    encoder: ProvenanceEncoder | None = None,
) -> spdx3.Annotation | None:
    """Return an Annotation recording where each metadata field came from.

    Returns ``None`` when ``provenance`` is empty (nothing to record).
    ``encoder`` defaults to the configured/registered default schema.
    """
    if not provenance:
        return None

    enc = encoder or resolve_encoder()

    ann = spdx3.Annotation()
    ann.spdxId = generate_spdx_id("Annotation", doc_name, doc_uuid)
    ann.creationInfo = creation_info
    ann.annotationType = spdx3.AnnotationType.other
    ann.contentType = enc.content_type
    ann.subject = subject_spdx_id
    ann.statement = enc.encode(provenance)
    return ann
```

> Implementing agent: confirm the exact enum access — it may be
> `spdx3.AnnotationType.other` or a module-level constant. Check the binding
> (`grep -n "class AnnotationType" model.py`) and adjust.

### 5.3 Exporter: add `add_annotation`

In [`src/pitloom/export/spdx3_json.py`](../../src/pitloom/export/spdx3_json.py),
mirror `add_relationship` (`:286`): a thin collector that appends the
`Annotation` to the same element list that feeds the graph / SBOM
`element` set. Ensure annotations are included wherever relationships are when
building the final `SpdxDocument` / `software_Sbom`.

### 5.4 Config toggle

Add to config model ([`src/pitloom/core/config.py`](../../src/pitloom/core/config.py))
under `[tool.pitloom.provenance]`:

- `format` enum, default `"both"` (`"annotation" | "comment" | "both"`),
  validated eagerly at config-load time (`ValueError` on an unknown value).
- `schema` string, default `"pitloom/1"` — resolved via `resolve_encoder`
  (§5.2). **As implemented:** *not* validated at config-load time, because
  `core` must not import the `assemble`-layer encoder registry (see the
  layering rule enforced elsewhere in this file, e.g.
  [`creation_info.py`](../../src/pitloom/assemble/spdx3/creation_info.py)).
  An unknown schema id instead fails fast the first time an SBOM is
  generated, since `build()`/`build_deployed()`/`build_model()` all call
  `resolve_encoder(provenance_schema)` unconditionally up front.

Thread both to the assemble layer. Helper:

```python
def emit_provenance(
    subject_spdx_id,
    provenance,
    creation_info,
    doc_name,
    doc_uuid,
    exporter,
    fmt,
    encoder,
    *,
    comment_target=None,
):
    """Write provenance as annotation, comment, or both per config.

    ``encoder`` is the resolved schema encoder used for the annotation path.
    ``comment_target`` is the element whose ``.comment`` receives the legacy
    human-readable string when ``fmt`` includes comments.
    """
```

Keep the existing comment builders (`_build_provenance_comment`, the inline
`"Metadata provenance: ..."` joins) as the `"comment"`/`"both"` path.

### 5.5 Migrate call sites (§2.2), one file per commit

For each subject: after the subject element has an `spdxId` and is added to the
exporter, call the new `emit_provenance` (or `build_provenance_annotation`
directly) instead of / in addition to setting `.comment`. Order:

1. Main Python package — `document.py`
2. AI `ai_AIPackage` — `ai.py`
3. Dataset package — `dataset.py`
4. Dependencies / license / relationships — `deps.py`
5. pipdeptree deps — `document.py`
6. Loom SDK fragments — `loom.py`

---

## 6. Expected output

### 6.1 SPDX 3 JSON-LD

```json
{
  "type": "Annotation",
  "spdxId": "https://spdx.org/spdxdocs/sentimentdemo-4f...#Annotation-1",
  "creationInfo": "_:creationinfo",
  "annotationType": "other",
  "contentType": "application/json",
  "subject": "https://spdx.org/spdxdocs/sentimentdemo-4f...#ai_AIPackage-1",
  "statement": "{\"fields\":{\"description\":{\"location\":\"model card\",\"method\":\"extraction\",\"source\":\"Hugging Face Hub\"},\"license\":{\"location\":\"model card\",\"source\":\"Hugging Face Hub\"},\"type_of_model\":{\"source\":\"safetensors header\"}},\"schema\":\"https://pitloom.dev/provenance/1\"}"
}
```

The referenced `CreationInfo` already carries the extractor identity:

```json
{
  "type": "CreationInfo",
  "@id": "_:creationinfo",
  "created": "2026-07-20T00:00:00Z",
  "createdBy": ["...#Agent-pitloom"],
  "createdUsing": ["...#Tool-pitloom"]
}
```

### 6.2 RDF/Turtle

```turtle
@prefix core: <https://spdx.org/rdf/3.0.1/terms/Core/> .

<...#Annotation-1> a core:Annotation ;
    core:annotationType core:AnnotationType/other ;
    core:contentType "application/json" ;
    core:subject <...#ai_AIPackage-1> ;
    core:creationInfo _:ci ;
    core:statement "{\"fields\":{\"license\":{\"source\":\"Hugging Face Hub\",\"location\":\"model card\"},\"type_of_model\":{\"source\":\"safetensors header\"}},\"schema\":\"https://pitloom.dev/provenance/1\"}" .
```

`statement` is a single `xsd:string` literal in both formats — the JSON is
opaque to SPARQL except as text (accepted tradeoff, decision §3.2).

---

## 7. Tests

- **New** `tests/test_annotation_provenance.py`:
  - `parse_provenance_value` round-trips each real extractor string form
    (`Source: X | Field: Y`, `{source} | Field: extra/name`, note-only, empty).
  - `build_provenance_statement` is deterministic (`sort_keys`), valid JSON,
    contains the schema marker.
  - `build_provenance_annotation` returns `None` on empty; sets
    `annotationType=other`, `contentType=application/json`, correct `subject`,
    and a minted `spdxId`.
- **Update** [`tests/test_provenance.py`](../../tests/test_provenance.py): keep
  the `dict` provenance assertions (those test extraction, unchanged); add a
  path asserting an Annotation is emitted when `format="annotation"`/`"both"`.
- **Update** [`tests/test_spdx3_compliance.py`](../../tests/test_spdx3_compliance.py):
  assert emitted `Annotation` elements validate (required `subject`,
  `annotationType`, valid `contentType` regex, resolvable `subject` id).
- **Update** [`tests/test_jcs.py`](../../tests/test_jcs.py) / any golden-output
  test: regenerate goldens under the new default; verify byte-stability across
  two runs.
- Run the full determinism check (generate twice, diff) using the pyenv
  `pitloom310` env per the dev-environment memory.

---

## 8. Out of scope / follow-ups

- **Adopting an external AI-model / general provenance schema** as an
  additional `ProvenanceEncoder` (§4.2). The plumbing lands now; a concrete
  second encoder is a later change. Candidate schemas to evaluate when we do:
  - **W3C PROV-O** — general provenance ontology (`prov:wasDerivedFrom`,
    `prov:wasGeneratedBy`, `prov:Activity`); maps naturally to RDF/Turtle and
    would let `contentType = "application/ld+json"`.
  - **SLSA provenance / in-toto attestations** — build/supply-chain focused;
    strong for "how was this produced" attestation.
  - **Croissant** provenance fields — already partly consumed for datasets
    ([`src/pitloom/extract/_croissant.py`](../../src/pitloom/extract/_croissant.py));
    natural fit for dataset subjects.
  - **Hugging Face model-card / model-index** metadata as a first-class
    encoder for AI subjects (source SHA, author, repo URL).
  When choosing, prefer one whose id maps cleanly onto Pitloom's internal
  `field -> source` map and can round-trip through the `Annotation.statement`
  string (or an `application/ld+json` body).
- Per-field granular annotations for SPARQL queryability (only if a consumer
  needs it).
- Moving `known_biases` out of `comment` into proper `ai_*` properties.
- Flipping the config default from `"both"` to `"annotation"` (separate change
  after downstream consumers updated).

---

## 9. Acceptance criteria

- [x] `provenance.py` module: parser, `ProvenanceEncoder` protocol + registry +
  `resolve_encoder`, `PitloomV1Encoder`, annotation builder — with unit tests
  ([`tests/test_annotation_provenance.py`](../../tests/test_annotation_provenance.py)).
- [x] `exporter.add_annotation` and inclusion in graph/SBOM output.
- [x] `[tool.pitloom.provenance] format` (default `"both"`, validated at
  config-load time) and `schema` (default `"pitloom/1"`, validated at first
  SBOM generation — see §5.4's "as implemented" note) config.
- [x] All six call sites (§2.2) migrated behind the toggle.
- [x] Emitted annotations pass SPDX 3 compliance tests
  ([`tests/test_spdx3_compliance.py::test_spdx3_provenance_annotations_are_compliant`](../../tests/test_spdx3_compliance.py)).
- [x] Output is byte-stable across two generations (determinism preserved) —
  verified cross-process with a fixed `creation_datetime`, both for
  `generate_project_sbom()` and the `pitloom.loom` SDK path.
- [x] Existing `test_provenance.py` extraction assertions still pass.
- [x] A second (stub) encoder can be registered without editing call sites —
  demonstrated by
  [`test_swapping_encoder_changes_output_without_changing_wiring`](../../tests/test_annotation_provenance.py)
  and [`test_build_provenance_annotation_uses_given_encoder`](../../tests/test_annotation_provenance.py).

### Found and fixed during implementation review

- `emit_provenance` originally matched neither `if` branch for an
  unrecognized `provenance_format`, silently dropping the provenance with no
  comment, no Annotation, and no error — contradicting its own docstring's
  claim of a `"both"` fallback. Fixed to raise `ValueError` (matching
  `resolve_encoder`'s fail-fast pattern); regression test:
  `test_emit_provenance_unknown_format_raises`. The `pyproject.toml`-driven
  path was never affected (`core/config.py` already validated `format`
  eagerly) — this only mattered for direct API/library callers.
- [`working-docs/design/metadata-provenance.md`](../design/metadata-provenance.md)
  described only the pre-Annotation `comment`-based mechanism; updated to
  document Annotation as the primary mechanism with `comment` as the
  back-compat path.

### Deliberately out of scope (not attempted)

- CLI flags (`--provenance-format` / `--provenance-schema` / `--provenance-detail`
  / `--provenance-preserve-source-metadata`) mirroring
  `--describe-relationship`'s per-command precedence/diagnostics table in
  `__main__.py`. None of the four `[tool.pitloom.provenance]` keys has a CLI
  flag; all are reachable only via `pyproject.toml` or explicit keyword
  arguments to the library API. Not required by these acceptance criteria; the
  `pyproject.toml` config path is fully wired end to end (CLI, Hatchling
  build hook, and library API all honor `[tool.pitloom.provenance]` or
  explicit keyword arguments).
- `pitloom.loom` always uses `provenance_format = "both"` (hardcoded, not
  config-driven) — it is a standalone SDK invoked from ad hoc scripts, not
  through a `pyproject.toml`-based config; see the comment at
  `src/pitloom/loom.py`'s `_LOOM_PROVENANCE_FORMAT`.
- Demo/example SBOM fixtures under `examples/sentimentdemo-aibom/` were not
  regenerated (no test depends on their exact content; they now simply show
  the pre-Annotation output format).
- §8 follow-ups (external schema encoders, per-field granular annotations,
  moving `known_biases` out of `comment`, flipping the default format) —
  unchanged, still future work.

---

## 10. Boundary refinement (2026-07-20): non-native, high-signal only

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
looks intrinsic — see the P1 bullet under "Use-case catalog" for why it
still passes.

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

Both parsed/validated in `core/config.py` (`_read_provenance_settings`),
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
`creationInfo`, `annotationType`). None of the four current schemas ends
up needing a compound key — G2's `candidates` list settled on flat,
single-word fields (`value`/`role`/`source`/`ref`) once it moved to an
open candidate-list design instead of fixed `declaredLicenseId`-style
pairs — but the convention is stated explicitly so the next schema that
*does* need one (E1/E2, whenever `enrich/` lands) doesn't have to
re-derive it. Established retroactively across all four schemas this
session (none had shipped in a release yet, so no compatibility
constraint).

### Use-case catalog (why the Annotation earns its place)

- **Generation** — G1 inferred/detected/AI-generated qualifier (necessary,
  **implemented**: `licenseid_detection`, `inferred_from_authors` have no
  native assertedness marker); **G2 multi-source disagreement** (necessary
  on conflict, **implemented for license**, generalized beyond license — see
  the dedicated subsection below); G3 declared constraint vs resolved
  version (useful, **implemented** — SPDX keeps only the resolved version);
  G4 sub-file location in opaque AI formats (useful, **implemented**).
- **Aggregation** — A1 unification rationale (necessary, **implemented**):
  `_merge_fragment_set` records `(survivor, criterion, dropped_id, fragment)`
  for a **SHA-256 content-equality** match — a genuinely distinct id folded
  into the survivor, which SPDX cannot express — and emits a
  `provenance/unification/1` Annotation on the survivor. A same-id registry
  match carries no such fact (nothing distinct was folded) and is not
  annotated; its fragment origin is Phase-2 `SpdxDocument.imports` territory
  (see N1 below). A2 superseded identity across builds (useful,
  **not implemented — design only**): when file content changes,
  [`ids.py`](../../src/pitloom/ids.py) `register_file` mints a fresh
  `spdxId` and the old one is simply discarded — no supersedes/replaces
  record survives anywhere. Lower priority than A1: it's a cross-build fact
  (comparing this SBOM to a previous one), not something expressible within
  one SBOM generation.
- **Enrichment** — E1 override lineage, E2 AI-inferred-vs-non-inferred
  marker (both necessary; design-only — the `enrich/` subpackage is
  unbuilt). E2's "non-inferred" pole is any of G2's `declared`/`detected`/
  `externalReported` roles below — same vocabulary, reused rather than a
  separate "extracted" word (which would have collided with `extract/`,
  Pitloom's own name for the whole read-a-value pipeline stage).
- **Preservation** — P1 verbatim original AI-model metadata
  (`provenance/artifact-metadata/1`), config-gated, complements the lossy
  native mapping when the artifact isn't shipped. `raw_metadata` captured
  verbatim by the safetensors & GGUF extractors; HF/others fall back to the
  retained `properties`/`extra_data`. **Extrinsic-assertion justification**
  (this is the one borderline case per the test above): the blob payload
  looks intrinsic, but P1's role stays extrinsic — it is Pitloom witnessing
  and recording "here is what the source artifact's own header said at
  generation time," not Pitloom declaring a new native characteristic of
  the model. It exists precisely because the artifact won't travel with the
  SBOM and can't be re-read later to re-derive this; a shipped, re-extractable
  artifact gets no P1 blob at all (`preserve-source-metadata = "auto"`),
  which is itself evidence the role is "preserve what would otherwise be
  lost," not "hold a property."

  **Known limitation (unbounded statement size):** the P1 blob embeds
  `raw_metadata` verbatim with no size cap. Pitloom's own GGUF/safetensors
  test fixtures are small ("vocab-only" stubs, ~4 KB statements), but a
  production LLM's GGUF kv-store can carry a 32K–128K-entry tokenizer vocab
  (plus parallel `scores`/`token_type` arrays) in the same field, which would
  inflate a single `Annotation.statement` into the multi-megabyte range.
  SPDX 3.0.1's `statement` is a plain `xsd:string` with no spec-mandated
  limit, so this isn't a compliance violation, just a real scale gap not
  exercised by the current test suite. No truncation heuristic is applied
  here deliberately — silently cutting array data would make "verbatim
  preservation" dishonest about what was actually preserved, which defeats
  P1's purpose more than the size cost does. For large models, set
  `preserve-source-metadata = "never"` (or leave the default `"auto"`, which
  already skips preservation for any model that *is* shipped and thus
  re-extractable). A future fix, if needed, should truncate with an explicit,
  visible marker (e.g. `"_truncated": true`) rather than cutting silently.

### G2 — multi-source disagreement (2026-08-10, generalized, license implemented)

License is the first field this fires for, but the *mechanism* — several
sources reporting different values for the same field — applies to any
field. Built as a generic schema from the start so a future field or
candidate source never requires another schema redesign.

**Where it lives.** [`provenance.py`](../../src/pitloom/assemble/spdx3/provenance.py)
`ConflictCandidate` (a `TypedDict`) + `build_conflict_annotation`. Schema
URL `https://pitloom.dev/provenance/conflict/1`, envelope:

```json
{
  "schema": "https://pitloom.dev/provenance/conflict/1",
  "kind": "conflict",
  "field": "license",
  "candidates": [
    {"value": "MIT", "role": "declared", "source": "Source: pyproject.toml | Field: project.license", "ref": "<spdxId of hasDeclaredLicense target>"},
    {"value": "Apache-2.0", "role": "detected", "source": "Source: LICENSE | Method: licenseid_detection | Tool: licenseid==0.3.0", "ref": "<spdxId of hasConcludedLicense target>"}
  ]
}
```

Only emitted when candidates actually disagree after normalization
(`_license.py` `normalize_license_expression`, built on the
[`py-spdx-license`](https://github.com/JPEWdev/py-spdx-license) parser —
a plain `.strip()` comparison alone would false-positive not just on
casing differences (declared `"mit"` vs. detected `"MIT"`) but on
equivalent-yet-differently-spelled compound expressions too (`"MIT AND
MIT"` vs. `"MIT"`; `"MIT OR Apache-2.0"` vs. `"Apache-2.0 OR MIT"`) — so
both candidate values are parsed, deduplicated, and canonically reordered
before both the comparison and the license-element lookup/creation. A
value that fails to parse as a valid SPDX expression at all falls back to
`canonicalize_license_id`'s bare-id casing lookup, then to the raw string
unchanged. Full agreement emits no Annotation — both native relationships
still get built, just pointing at the same license element, and there's nothing
extrinsic left to assert.

**`role` vocabulary** — an epistemic-process label (*whose* determination
this is), deliberately not "which native SPDX slot it maps to" (that
would have overloaded SPDX's own `hasConcludedLicense` meaning, "the
SBOM creator's final determination," a graph-placement outcome, not a
method category):

- `declared` — the subject's own stated claim, however observed (read
  locally, or relayed unedited by a third party).
- `detected` — Pitloom's own independent-verification *procedure*'s
  determination, whatever the input's origin (locality of the *input*
  never matters; locality of the *determination* does — Pitloom fetching a
  remote file and running its own `licenseid` match on it is still
  `detected`). "Procedure," not "algorithm ran": the license implementation
  (`detect_independent_license`) is a multi-step search — `CITATION.cff`,
  then `codemeta.json`, then license files, applying `licenseid` text
  matching only where a value isn't already a bare SPDX id — and a step
  that resolves via a direct bare-id read still counts as `detected`,
  because it was Pitloom's own independently-consulted secondary source,
  not a re-read of the subject's primary declared field. What decides the
  role is *whose search procedure* produced the value, not whether every
  individual step needed fuzzy text matching. Not named "extracted":
  `extract/` is already Pitloom's own name for the whole read-a-value
  pipeline stage, and `declared` is also extracted in that sense —
  "extracted" would have collided with `declared` instead of contrasting
  with it.
- `externalReported` — some *other* party's own determination or opinion,
  relayed without Pitloom re-deriving it, and not the subject's own claim
  either (a paper's interpretation, an unrelated org's assessment, or
  another system's own algorithmic conclusion — GitHub's own
  license-detector badge is still GitHub's determination, not Pitloom's,
  even though GitHub's detector is itself rule-based internally —
  "rule-based" was never the right test, "whose algorithm" is). No native
  slot exists for this role by nature, not because it lost a priority
  race against a local `declared` candidate.
- `inferred` — an AI agent's non-deterministic reasoning/judgment. Same
  word E2 already reserves for this.

**Decision rule:** ask "whose determination is this," never "was the
data local or remote" and never "was a rule-based algorithm involved
somewhere" (a third-party service's own rule-based detector is still
`externalReported`, because the algorithm wasn't Pitloom's).

**Source-recording convention, per role** — each role's `source` string
records identity appropriate to *that* answerer, using the existing
generic `"Key: Value | Key: Value"` parser (no parser change needed for
any of these):

- `declared` — unchanged: `"Source: <file> | Field: <field>"`.
- `detected` — **implemented**: gains a `Tool:` segment with the
  detection library's version (`importlib.metadata.version("licenseid")`),
  e.g. `"Source: LICENSE | Method: licenseid_detection | Tool:
  licenseid==0.3.0"` — a detection result is only as reproducible as the
  library version that produced it.
- `externalReported` (future convention, not built) — `"Source: <service
  name> | Endpoint: <API path/version> | Retrieved: <ISO 8601 date>"`.
  Fits API-style sources (HF Hub, GitHub API); a non-API external source
  (a paper, a scraped webpage) will need its own, less endpoint-centric
  shape, worked out when that source type is actually built.
- `inferred` (future convention, not built) — the answerer isn't Pitloom
  at all; inference happens in an agent process entirely outside
  Pitloom's own Python code, so it has to be the *agent's own
  self-reported* identity: `"Source: <agent name> (<vendor>) | Method:
  inference | Date: <ISO 8601 date>"`, e.g. `"Source: Claude Code
  (Anthropic) | Method: inference | Date: 2026-08-10"`. Pitloom cannot
  verify this at merge time — same trust model the `enrich` skill's
  existing generic `"Source: AI agent | Method: inference"` marker
  already has, just more specific when the agent knows its own identity.

**Role → native relationship mapping is today's default policy, not an
inherent law.** For license: `declared` → `hasDeclaredLicense`,
`detected` → `hasConcludedLicense` (the only place the word "concluded"
appears — as SPDX's own relationship-type name, applied to the `detected`
candidate). This is a policy choice made *because* Pitloom's detector has
no confidence score today — its one output is the only candidate
determination available to call "concluded," not because a detected
value is inherently more trustworthy than a declared one. A bad/spurious
detection can and does produce a wrong `hasConcludedLicense` — a
pre-existing limitation of the single detector itself, not something G2
introduces. Once multiple detectors or confidence scoring exist, this
mapping is where a smarter policy would plug in (e.g. falling back to
`declared` when `detected` confidence is low) — future work, not built.
`externalReported` and `inferred` never map to a native relationship for
license (no 3rd/4th native slot exists).

**What's actually built (v1, license only).**
[`_license.py`](../../src/pitloom/extract/_license.py)
`detect_independent_license` — independently scans the project directory
(`CITATION.cff`, `codemeta.json`, license files), *ignoring* any declared
value, so there's a genuine second opinion to compare against. Previously,
a declared value that already looked like a valid SPDX id short-circuited
before the `LICENSE` file was ever read, so there was nothing to disagree
with; now the independent scan always runs alongside it.

`resolve_license_concluded` (also in `_license.py`) is the single, shared
G2 entry point every project-metadata extractor calls — not just
`pyproject.py`'s `[project]` path. It exists because the four extraction
paths (CLI's [`pyproject.py`](../../src/pitloom/extract/pyproject.py)
`read_pyproject`, the [`hatchling.py`](../../src/pitloom/extract/hatchling.py)
build-hook path, the poetry-only
[`poetry.py`](../../src/pitloom/extract/poetry.py) `read_poetry`, and the
setuptools-only [`setuptools.py`](../../src/pitloom/extract/setuptools.py)
`read_setuptools`) were each written and evolving independently. G2 first
shipped wired only into the CLI path; a later review found the Hatchling
build hook called `detect_license_for_project` directly and never ran the
independent scan at all, so G2 silently never fired for any Hatchling-built
project. Rather than patch that one path, all four now call the same
`resolve_license_concluded` (and, for the poetry-only and setuptools-only
paths, the same directory-detection fallback when nothing is declared) so
a future fifth extraction path can't reintroduce the same gap by omission.
Cross-path regression tests
(`test_metadata_from_hatchling_matches_read_pyproject_for_license_conflict`
in `tests/test_hatch_hook.py`,
`test_read_poetry_matches_read_pyproject_fallback_for_license_conflict` in
`tests/test_poetry.py`) assert the paths agree on the same project. The
same review also found the Hatchling and CLI paths each hand-listed their
own `[tool.poetry]`-gap-fill field merge (`_merge_with_poetry` in
`pyproject.py`, `merge_metadata` in `setuptools.py`); both were replaced
by [`core/project.py`](../../src/pitloom/core/project.py)'s
`merge_project_metadata`, which iterates `dataclasses.fields()` instead of
naming every field by hand, so a newly added `ProjectMetadata` field
merges automatically without a call site needing to be updated (see its
own docstring for the field-drift history that motivated this).
[`deps.py`](../../src/pitloom/assemble/spdx3/deps.py)
`build_license_elements` gained `concluded_license_id`/
`concluded_license_provenance` params (`None` default — the three other
call sites, dependency and AI-model licenses, are unaffected, since
neither has a local second source to detect from today): when given, both
candidates are run through `normalize_license_expression` before both the
comparison and the license-element lookup/creation, then both
`hasDeclaredLicense` and `hasConcludedLicense` are always built, and a G2
conflict Annotation is added on disagreement.

`normalize_license_expression` (also in `_license.py`) is the new,
stronger canonicalization step: operator casing (`AND`/`OR`/`WITH`/`NOT`)
is normalized first — but only when the operator stands alone as its own
whitespace/paren-delimited token, never when it's hyphen-glued into an
identifier (`GPL-2.0-or-later`, a custom `LicenseRef-my-or-license`) —
then the result is parsed and canonically sorted via `py-spdx-license`
(a new base dependency). This both canonicalizes bare-id casing (same as
`canonicalize_license_id`, which it falls back to on a parse failure) and
dedupes/reorders compound expressions, which `canonicalize_license_id`
alone never handled.

**Real-world validation.** This is not a hypothetical gap:
[Trivy discussion #10139](https://github.com/aquasecurity/trivy/discussions/10139)
reports scanning the same package and getting the same license expression
back with and without a redundant outer paren
(`GPL-3.0-or-later WITH GCC-exception-3.1` vs.
`(GPL-3.0-or-later WITH GCC-exception-3.1)`), breaking policy rules that
compare against one fixed string. Checked `normalize_license_expression`
against all four of that report's example pairs — every pair normalizes
to an identical string. Separately verified the harder case, where a
paren is *not* redundant: for mixed `AND`/`OR` expressions,
`MIT AND Apache-2.0 OR BSD-3-Clause` (no parens, relies on `AND` binding
tighter than `OR` per the SPDX spec) and
`(MIT AND Apache-2.0) OR BSD-3-Clause` (explicit parens matching that
same default precedence) both normalize to `Apache-2.0 AND MIT OR
BSD-3-Clause`, while `MIT AND (Apache-2.0 OR BSD-3-Clause)` (parens
*overriding* default precedence, semantically different) correctly stays
distinct and keeps its now-necessary paren. So the normalization strips
parens exactly when they're redundant and keeps them exactly when they're
load-bearing — not a blanket strip-all-parens heuristic.

**Future candidate sources (not built — `enrich/`-territory network or
agent work, cross-referenced to
[`sbom-enrichment.md`](../design/sbom-enrichment.md)'s existing source
table):** HF Hub API (`externalReported`), GitHub via `ExternalRef`
(`detected` if Pitloom runs its own scan on the fetched file,
`externalReported` if relaying GitHub's own license badge), a linked
paper (`externalReported`), README/source-comment agent inference
(`inferred`). The schema already has the `role` slots waiting for all of
these — no further schema change needed when they land.

### Phase 2 (documented; built after this Annotation work): native-first backfill

Several facts still live only in an Annotation/comment but have a real SPDX
home Pitloom does not yet populate. Build the native construct, then **trim
the corresponding Annotation to the residual**. Track here so it is not
forgotten:

- [x] **N1 — Fragment origin** → `SpdxDocument.imports` + `ExternalMap` (per
  source fragment). Residual in Annotation: the unification *criterion* only. (PR [#108](https://github.com/bact/pitloom/pull/108))
- [x] **N2 — Declared vs. concluded license** → distinct `hasDeclaredLicense`
  (author-stated) / `hasConcludedLicense` (Pitloom-detected). Originally
  shipped mirrored (single winning value classified as one or the other,
  "no inference yet") in PR [#105](https://github.com/bact/pitloom/pull/105);
  the main project package now populates both independently when a second,
  directory-detected opinion exists (G2, above), across all four
  project-metadata extraction paths (CLI, Hatchling build hook,
  poetry-only, setuptools-only) — dependency and AI-model license paths
  remain single-value/mirrored, no local second source to detect from.
  Residual: the detection evidence.
- [ ] **N3 — Who/when enriched** → a second `CreationInfo` per enrichment run.
  Residual: which field + before/after value + inferred marker (E1/E2). (Blocked on `enrich/` subpackage)
- [x] **N4 — External identifiers** (DOI, arXiv, repo / model-card URL) →
  `ExternalIdentifier` / `ExternalRef` on the AI package (today only in
  `extra_data`/provenance). Residual: none once mapped. (PR [#106](https://github.com/bact/pitloom/pull/106))
- [x] **N5 — Base-model lineage** (HF `base_model`) → `descendantOf`
  `Relationship`. Residual: raw relation subtype in comment. (PR [#109](https://github.com/bact/pitloom/pull/109))
- [x] **N6 — Dataset `creator`** → `Agent` + `publishedBy` relationship on the
  dataset package (extracted but not wired). Residual: none once mapped. (PR [#107](https://github.com/bact/pitloom/pull/107))

Every use case splits into a **native part** (Phase 2) and an **Annotation
part** (this phase); e.g. G2 license = N2 relationships + Annotation evidence,
A1 unification = N1 `imports` + Annotation criterion.

An end-to-end integration test exercising N1/N2/N4/N5/N6 together on one
representative model -- all five native constructs present at once, no
Annotation duplicating a now-native value, byte-identical output across two
runs, and round-trip through `spdx-python-model` -- shipped in
[`tests/test_provenance_integration.py`](../../tests/test_provenance_integration.py)
(PR [#112](https://github.com/bact/pitloom/pull/112)).

---

## 11. Security/robustness hardening (2026-07-21)

Agent-driven adversarial review of the provenance-string construction and
JSON-serialization paths (`record_dict_field_provenance`, `_sanitize_for_json`)
found and fixed two real gaps:

- **Provenance-string delimiter injection.** Both a dict key from an
  untrusted binary artifact (a GGUF kv key, a safetensors `__metadata__`
  key, ...) *and* the model's filename (`f"Source: {model_path.name}"`,
  built independently in all nine AI-model extractors) flow unescaped into a
  `"Source: X | Field: Y"` provenance string. A crafted value containing
  `"| Source: pyproject.toml"` would inject a fake segment that
  `parse_provenance_value` re-parses as if the field came from a transparent
  manifest -- misattributing the source and, in the default minimal-detail
  mode, silently dropping the entry entirely. Fixed with a shared
  `sanitize_provenance_text()` (`_extract_utils.py`) that escapes `|`,
  applied both inside `record_dict_field_provenance` (the key) and at every
  `source = f"Source: {model_path.name}"` construction site (the filename) --
  the first fix (key-only) was caught as incomplete by a follow-up
  adversarial audit before this file was updated.
  **Scope boundary, not fixed:** `_croissant.py`/`pyproject.py`/
  `setuptools.py`/`_license.py` build `"Source: {path}"` strings with the
  identical unescaped pattern, but never call `record_dict_field_provenance`
  and were outside the audited AI-extractor scope; their inputs (project-local
  paths, PEP 621 field values) are a different, generally lower trust
  boundary than an arbitrary downloaded binary model file. Worth revisiting
  with the same `sanitize_provenance_text()` if that trust assumption changes.
- **Non-deterministic/invalid JSON in the P1 preservation blob.**
  `json.dumps`'s `default=` hook is never called for a `float`, so a
  malformed model's NaN/Infinity metadata value round-tripped into the
  non-standard `NaN`/`Infinity` JSON tokens (RFC 8259 forbids them); a `set`
  value fell back to `str()`, whose iteration order is
  `PYTHONHASHSEED`-dependent. Fixed with `_sanitize_for_json()`, a recursive
  pre-pass that converts NaN/±Infinity to string tokens and orders set
  elements by their *canonical JSON form* rather than Python's native `<` --
  ordering by `<` was tried first and rejected: `sorted()` can silently
  succeed without raising `TypeError` for types whose `<` isn't a total order
  (e.g. `frozenset`, where `<` means "is a proper subset of"), so a
  set-of-frozensets stayed input-order-dependent even after the first
  attempt.
  **Known-dormant, not fixed:** extractors are expected to normalize
  numpy/library-native scalars (via `.tolist()`/`.item()`) before they reach
  `raw_metadata` -- confirmed true of every current extractor against real
  fixtures -- so `_sanitize_for_json` doesn't special-case numpy types. A
  future extractor that skips that normalization would silently mis-serialize
  (e.g. a `numpy.int64` becoming a JSON string via the generic `default=str`
  fallback); noted in the function's docstring as an assumption, not guarded
  against, since guarding it well requires a numpy dependency this module
  doesn't otherwise need.

Also documented (§10, Preservation bullet): the P1 blob has no size cap, so a
production-scale model's large arrays (e.g. a 32K+ entry GGUF vocab table)
could produce a multi-megabyte `Annotation.statement`. Not a spec violation
(`statement` is unbounded `xsd:string`), not exercised by the small test
fixtures, and deliberately not truncated (silently cutting array data would
make "verbatim preservation" dishonest) -- `preserve-source-metadata = "never"`
is the escape hatch for large models today.
