---
Created: 2026-07-20
Last-Modified: 2026-10-15
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
see the pointer where §10 used to be, in
`annotation-provenance-acceptance.md`). The Phase 2 native-backfill
checklist (6 of 6 items shipped as of 2026-08-10) is now in
`use-case-catalog.md`; current PR-by-PR status is in
[`phase2-native-backfill-handover.md`](phase2-native-backfill-handover.md).
**Planned with:** Opus 4.8. **Implemented by:** Sonnet 5.
**Related docs:** [`metadata-provenance.md`](metadata-provenance.md),
[`working-docs/design/model-metadata-extraction.md`](../../design/model-metadata-extraction.md).

**See also (parts of this document):**

- [`annotation-provenance-implementation.md`](annotation-provenance-implementation.md)
  -- §5 Implementation, §6 Expected output, §7 Tests.
- [`annotation-provenance-acceptance.md`](annotation-provenance-acceptance.md)
  -- §8 Out of scope / follow-ups, §9 Acceptance criteria, §10
  Security/robustness hardening.

Section numbers (§N) are continuous across the three parts: §1-4 in
[`annotation-provenance.md`](annotation-provenance.md), §5-7 in
[`annotation-provenance-implementation.md`](annotation-provenance-implementation.md),
§8-10 in
[`annotation-provenance-acceptance.md`](annotation-provenance-acceptance.md).

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
split (`deps.py`, `document.py`, `remote/huggingface.py`, `loom.py` each broken
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

- `"Source: pyproject.toml | Field: project.name"` — [`src/pitloom/extract/project/pyproject.py:83`](../../../src/pitloom/extract/project/pyproject.py)
- `"Source: Hugging Face Hub | Field: model card"` — [`src/pitloom/extract/remote/huggingface_field.py:134`](../../../src/pitloom/extract/remote/huggingface_field.py)
- `f"{source} | Field: extra/name"` — [`src/pitloom/extract/ai_model/pytorch_pt2.py:132`](../../../src/pitloom/extract/ai_model/pytorch_pt2.py)

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
