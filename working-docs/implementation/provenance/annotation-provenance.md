---
Created: 2026-07-20
Last-Modified: 2026-08-25
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Implementation plan: metadata provenance via SPDX 3 Core/Annotation

**Status:** implemented and merged
(PR [#102](https://github.com/bact/pitloom/pull/102)) --
see §9 for what shipped vs. deferred, and §10 for security/robustness
hardening. The boundary-refinement work (non-native / high-signal only,
config-gated) that used to live in this file's own §10 is now split
across [`annotation-mechanism.md`](annotation-mechanism.md),
[`role-vocabulary.md`](role-vocabulary.md),
[`use-case-catalog.md`](use-case-catalog.md), and
[`multi-source-conflict.md`](multi-source-conflict.md) (2026-08-25 split,
see the pointer where §10 used to be, below). The Phase 2 native-backfill
checklist (6 of 6 items shipped as of 2026-08-10) is now in
`use-case-catalog.md`; current PR-by-PR status is in
[`phase2-native-backfill-handover.md`](phase2-native-backfill-handover.md).
**Planned with:** Opus 4.8. **Implemented by:** Sonnet 5.
**Related docs:** [`metadata-provenance.md`](metadata-provenance.md),
[`working-docs/design/model-metadata-extraction.md`](../../design/model-metadata-extraction.md).

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

**Historical snapshot.** §2.1-2.4 describe the pre-migration
`comment`-string state as it stood on 2026-07-20, before this plan's own
Annotation migration (§5.5) landed and before the later 4-file source
split (`deps.py`, `document.py`, `_huggingface.py`, `loom.py` each broken
into a smaller facade plus siblings). Paths/lines have been updated below
to point at where the equivalent code lives today, but the described
mechanism (writing directly into `comment`) is itself superseded by the
Annotation-based `emit_provenance()` calls those locations now contain.
`_build_provenance_comment` (§2.2 row 1) no longer exists under that
name.

### 2.1 Provenance data model

Provenance is a `dict[str, str]` field on each format-neutral metadata object,
keyed by SBOM field name, value already semi-structured as pipe-delimited
`"Key: value | Key: value"` segments:

- `ProjectMetadata.provenance` — [`src/pitloom/core/project.py:77`](../../../src/pitloom/core/project.py)
- `AiModelMetadata.provenance` — [`src/pitloom/core/ai_metadata.py:201`](../../../src/pitloom/core/ai_metadata.py)
- `DatasetMetadata.provenance` — [`src/pitloom/core/dataset_metadata.py:89`](../../../src/pitloom/core/dataset_metadata.py)

Example values produced by extractors:

- `"Source: pyproject.toml | Field: project.name"` — [`src/pitloom/extract/_pyproject.py:83`](../../../src/pitloom/extract/_pyproject.py)
- `"Source: Hugging Face Hub | Field: model card"` — [`src/pitloom/extract/_huggingface_fields.py:134`](../../../src/pitloom/extract/_huggingface_fields.py)
- `f"{source} | Field: extra/name"` — [`src/pitloom/extract/_pytorch_pt2.py:132`](../../../src/pitloom/extract/_pytorch_pt2.py)

The pipe/`Key: value` convention is consistent enough to parse. Anything that
does not fit `Key: value` must be preserved (see parser rules in §5.1).

### 2.2 Where provenance is written into `comment` today (all call sites to migrate)

| Subject element | Location |
| --- | --- |
| Main Python package (post-migration: `emit_provenance()` call) | [`src/pitloom/assemble/spdx3/document.py:220`](../../../src/pitloom/assemble/spdx3/document.py) |
| AI `ai_AIPackage` | [`src/pitloom/assemble/spdx3/ai.py:193`](../../../src/pitloom/assemble/spdx3/ai.py) (`_build_ai_package`) |
| Dataset package | [`src/pitloom/assemble/spdx3/dataset.py:160`](../../../src/pitloom/assemble/spdx3/dataset.py) |
| Dependency packages / license text / relationships | [`src/pitloom/assemble/spdx3/deps.py:492,566`](../../../src/pitloom/assemble/spdx3/deps.py), [`deps_license.py:79`](../../../src/pitloom/assemble/spdx3/deps_license.py), [`deps_originator.py:358`](../../../src/pitloom/assemble/spdx3/deps_originator.py) |
| pipdeptree deps | [`src/pitloom/assemble/spdx3/_document_deployed.py:89,158`](../../../src/pitloom/assemble/spdx3/_document_deployed.py) |
| Loom SDK fragments | [`src/pitloom/_loom_active_run.py:295,341,367`](../../../src/pitloom/_loom_active_run.py) |

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
  [`src/pitloom/core/models.py:234`](../../../src/pitloom/core/models.py). Per
  `(doc_uuid, prefix)` counter. Use prefix `"Annotation"`.
- Shared `CreationInfo` (carries pitloom `Agent` via `createdBy` and `Tool`
  via `createdUsing`) — [`src/pitloom/assemble/spdx3/creation_info.py`](../../../src/pitloom/assemble/spdx3/creation_info.py).
- Exporter collectors (`add_package`, `add_relationship`, …) —
  [`src/pitloom/export/spdx3_json.py:219-302`](../../../src/pitloom/export/spdx3_json.py).
  A new `add_annotation` follows the same pattern.
- `require_spdx_id(element)` — [`src/pitloom/export/spdx3_json.py:32`](../../../src/pitloom/export/spdx3_json.py).

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
  [`src/pitloom/assemble/spdx3/fragments.py`](../../../src/pitloom/assemble/spdx3/fragments.py).

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

In [`src/pitloom/export/spdx3_json.py`](../../../src/pitloom/export/spdx3_json.py),
mirror `add_relationship` (`:286`): a thin collector that appends the
`Annotation` to the same element list that feeds the graph / SBOM
`element` set. Ensure annotations are included wherever relationships are when
building the final `SpdxDocument` / `software_Sbom`.

### 5.4 Config toggle

Add to config model ([`src/pitloom/core/config.py`](../../../src/pitloom/core/config.py))
under `[tool.pitloom.provenance]`:

- `format` enum, default `"both"` (`"annotation" | "comment" | "both"`),
  validated eagerly at config-load time (`ValueError` on an unknown value).
- `schema` string, default `"pitloom/1"` — resolved via `resolve_encoder`
  (§5.2). **As implemented:** *not* validated at config-load time, because
  `core` must not import the `assemble`-layer encoder registry (see the
  layering rule enforced elsewhere in this file, e.g.
  [`creation_info.py`](../../../src/pitloom/assemble/spdx3/creation_info.py)).
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

- **New** `tests/test_annotation_provenance.py` (since moved and split
  into `tests/assemble/test_annotation_provenance_core.py`/`_emit.py`/
  `_annotations.py` -- see `cli-test-coverage-roadmap.md`):
  - `parse_provenance_value` round-trips each real extractor string form
    (`Source: X | Field: Y`, `{source} | Field: extra/name`, note-only, empty).
  - `build_provenance_statement` is deterministic (`sort_keys`), valid JSON,
    contains the schema marker.
  - `build_provenance_annotation` returns `None` on empty; sets
    `annotationType=other`, `contentType=application/json`, correct `subject`,
    and a minted `spdxId`.
- **Update** [`tests/assemble/test_provenance.py`](../../../tests/assemble/test_provenance.py): keep
  the `dict` provenance assertions (those test extraction, unchanged); add a
  path asserting an Annotation is emitted when `format="annotation"`/`"both"`.
- **Update** [`tests/assemble/test_spdx3_compliance_shacl.py`](../../../tests/assemble/test_spdx3_compliance_shacl.py):
  assert emitted `Annotation` elements validate (required `subject`,
  `annotationType`, valid `contentType` regex, resolvable `subject` id).
- **Update** [`tests/extract/test_jcs.py`](../../../tests/extract/test_jcs.py) / any golden-output
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
    ([`src/pitloom/extract/_croissant.py`](../../../src/pitloom/extract/_croissant.py));
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
  ([`tests/assemble/test_annotation_provenance_core.py`](../../../tests/assemble/test_annotation_provenance_core.py)).
- [x] `exporter.add_annotation` and inclusion in graph/SBOM output.
- [x] `[tool.pitloom.provenance] format` (default `"both"`, validated at
  config-load time) and `schema` (default `"pitloom/1"`, validated at first
  SBOM generation — see §5.4's "as implemented" note) config.
- [x] All six call sites (§2.2) migrated behind the toggle.
- [x] Emitted annotations pass SPDX 3 compliance tests
  ([`tests/assemble/test_spdx3_compliance_shacl.py::test_spdx3_provenance_annotations_are_compliant`](../../../tests/assemble/test_spdx3_compliance_shacl.py)).
- [x] Output is byte-stable across two generations (determinism preserved) —
  verified cross-process with a fixed `creation_datetime`, both for
  `generate_project_sbom()` and the `pitloom.loom` SDK path.
- [x] Existing `test_provenance.py` extraction assertions still pass.
- [x] A second (stub) encoder can be registered without editing call sites —
  demonstrated by
  [`test_swapping_encoder_changes_output_without_changing_wiring`](../../../tests/assemble/test_annotation_provenance_core.py)
  and [`test_build_provenance_annotation_uses_given_encoder`](../../../tests/assemble/test_annotation_provenance_core.py).

### Found and fixed during implementation review

- `emit_provenance` originally matched neither `if` branch for an
  unrecognized `provenance_format`, silently dropping the provenance with no
  comment, no Annotation, and no error — contradicting its own docstring's
  claim of a `"both"` fallback. Fixed to raise `ValueError` (matching
  `resolve_encoder`'s fail-fast pattern); regression test:
  `test_emit_provenance_unknown_format_raises`. The `pyproject.toml`-driven
  path was never affected (`core/config.py` already validated `format`
  eagerly) — this only mattered for direct API/library callers.
- [`metadata-provenance.md`](metadata-provenance.md)
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
  `src/pitloom/loom.py`'s `_LOOM_PROVENANCE_CONFIG`.
- Demo/example SBOM fixtures under `examples/sentimentdemo-aibom/` were not
  regenerated (no test depends on their exact content; they now simply show
  the pre-Annotation output format).
- §8 follow-ups (external schema encoders, per-field granular annotations,
  moving `known_biases` out of `comment`, flipping the default format) —
  unchanged, still future work.

---

## (Former §10) Boundary refinement, role vocabulary, use-case catalog, and G2 -- moved 2026-08-25

This section originally covered non-native/high-signal Annotation
boundaries, the `role` vocabulary, the G1-G4/A1-A2/E1-E2/P1 use-case
catalog, and the Phase 2 native-first backfill checklist -- it grew past
this file's own 800-line size cap and was split into four sibling files
in this directory:

- [`annotation-mechanism.md`](annotation-mechanism.md) -- when/how to use
  the Annotation mechanism at all (boundary principle, extrinsic-assertion
  test, high-signal test, config, statement-envelope convention).
- [`role-vocabulary.md`](role-vocabulary.md) -- the `role` vocabulary
  (`declared`/`detected`/`externalReported`/`inferred`/`sbomAuthorSupplied`),
  decision rule, source-recording convention, role-to-native mapping.
- [`use-case-catalog.md`](use-case-catalog.md) -- the G1-G4/A1-A2/E1-E2/P1
  catalog and the Phase 2 N1-N6 backfill checklist.
- [`multi-source-conflict.md`](multi-source-conflict.md) -- G2's own
  implementation depth (license-conflict schema, normalization logic,
  what's built, real-world validation, future candidate sources).

## 10. Security/robustness hardening (2026-07-21)

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

Also documented (`use-case-catalog.md`, P1 Preservation bullet): the P1 blob has no size cap, so a
production-scale model's large arrays (e.g. a 32K+ entry GGUF vocab table)
could produce a multi-megabyte `Annotation.statement`. Not a spec violation
(`statement` is unbounded `xsd:string`), not exercised by the small test
fixtures, and deliberately not truncated (silently cutting array data would
make "verbatim preservation" dishonest) -- `preserve-source-metadata = "never"`
is the escape hatch for large models today.
