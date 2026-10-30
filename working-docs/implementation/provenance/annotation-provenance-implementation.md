---
Created: 2026-10-15
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Annotation provenance plan -- implementation, output, tests

See also: [`annotation-provenance.md`](annotation-provenance.md) (goal,
current state, settled design decisions, statement schema -- §1-4) and
[`annotation-provenance-acceptance.md`](annotation-provenance-acceptance.md)
(§8-10). This part holds §5 Implementation, §6 Expected output and §7
Tests; section numbers (§N) are continuous across the parts.

## 5. Implementation

### 5.1 Parser: provenance string → structured dict

Segment key normalization mapping (case-insensitive):

- `Source` → `source`
- `Field` → `location`
- `Method` → `method`
- `Package` → `package`
- anything else → keep lower-cased key as-is
- segment with no `:` → append to `note`

Revised (#402): "anything else" read free text as a key (`pkg @
https://x/p.whl` gave `pkg @ https`). The key set is now closed: the
segment keys `provenance_segment` writes, `Source`, `Evidence`, `Reason` and
the numbered `Resolution-<n>`/`Expansion-<n>` keep their lower-cased key;
any other segment, and a `Note:` segment's value, is appended to `note`, in
order. The snippet below is the original.

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
