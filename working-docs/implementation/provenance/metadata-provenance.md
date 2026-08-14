---
Created: 2026-02-07
Last-Modified: 2026-08-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Metadata provenance and CreationInfo usage: implementation

See [annotation-provenance.md](annotation-provenance.md) for the full
design history and [provenance-enrichment-vocabulary.md](../../design/provenance-enrichment-vocabulary.md)
for still-open questions (CreationInfo future enhancements, the unbounded
artifact-metadata-blob question). The user-facing explainer lives at
[docs/metadata-provenance.md](../../../docs/metadata-provenance.md) and
[docs/creation-metadata.md](../../../docs/creation-metadata.md).

This document describes how Pitloom implements metadata provenance
tracking and uses SPDX 3 CreationInfo for transparency and auditability.

> **Status (2026-08):** Provenance is now recorded as SPDX 3 Core
> `Annotation` elements -- systematic and machine-readable -- with the
> original `comment`-based format kept for back-compat. The native-first
> backfill (Phase 2) has also landed for five of six items -- declared vs.
> concluded license, external identifiers (DOI/arXiv/URL), base-model
> lineage, dataset creator, and fragment-origin `imports` are now emitted
> as native SPDX constructs with no provenance residual for the value
> itself; only enrichment `CreationInfo` (N3) remains, blocked on the
> unbuilt `enrich/` subpackage. G2 (multi-source disagreement detection)
> is now implemented for license, and generalized to any field for when
> future candidate sources land. A2 (superseded identity across builds)
> remains design-only. See
> [`annotation-provenance.md`](annotation-provenance.md)
> §10 for the full design, current status, and code citations for all
> pending items, and
> [`phase2-native-backfill-handover.md`](phase2-native-backfill-handover.md)
> for current status.

## Provenance tracking implementation

### 1. Core/Annotation elements (primary mechanism)

Each element with tracked provenance gets one `Annotation` (per
[`pitloom.assemble.spdx3.provenance`](../../../src/pitloom/assemble/spdx3/provenance.py)):
`annotationType = "other"` (the SPDX 3.0.1 enum has no dedicated provenance
value), `subject` pointing at the element's `spdxId`, and a JSON `statement`
(`contentType = "application/json"`) keyed by field name:

```json
{
  "type": "Annotation",
  "spdxId": "https://spdx.org/spdxdocs/mypackage-.../#Annotation-1",
  "annotationType": "other",
  "contentType": "application/json",
  "subject": "https://spdx.org/spdxdocs/mypackage-.../#Package-1",
  "statement": "{\"schema\":\"https://pitloom.dev/provenance/fields/1\",\"fields\":{\"version\":{\"source\":\"src/mypackage/__about__.py\",\"method\":\"dynamic_extraction\"}}}"
}
```

The *who/when* (which tool/agent extracted the data, and at what time) is
carried by the Annotation's own `creationInfo`, not duplicated in the
statement. The statement schema is pluggable -- `"pitloom/1"` (shown above)
is the default; see the implementation plan for how an external AI-model
provenance schema could be adopted later without changing call sites.

**Native-first boundary (2026-07).** An Annotation must never restate a value
that SPDX already stores natively (the license lives in `hasDeclaredLicense`,
the version in `software_packageVersion`, a dependency edge in `dependsOn`);
it only records *how the value came to be*. In the default `detail = "minimal"`
mode a field-source Annotation is emitted **only** when it adds something the
native value cannot convey -- the value was inferred/detected (not read
verbatim), came from a specific sub-file region of an opaque binary format, or
is the raw dependency constraint. Trivial "read from `pyproject.toml`" sources
are dropped (available under `detail = "full"`). Two process-level roles have
no native home at all and are always recorded: **fragment-unification**
rationale (which criterion merged two elements) and **artifact-metadata
preservation** (an AI model's verbatim original metadata, config-gated to when
the model is not shipped and can't be re-extracted). See §10 of the
implementation plan for the use-case catalog and the Phase 2 native-backfill
checklist.

**Known limitation, not yet fixed:** artifact-metadata preservation
(`_source_metadata_blob()`/`_emit_source_metadata()` in
`src/pitloom/assemble/spdx3/ai.py`) embeds an AI model's raw metadata
**verbatim, with no size cap**, into a single `Annotation.statement`. For
the small fixtures this repo tests against, that's a few KB at most; for
a real production model with a large vocabulary (e.g. a GGUF LLM's
32K-128K+ token list), the same field could inflate a single Annotation
into the multi-megabyte range. SPDX 3.0.1's `statement` is plain
`xsd:string` with no spec-mandated limit, so this isn't a spec
violation, but it's an untested scalability gap for realistic models
(found by independent review). The right behavior (drop oversized fields
entirely? truncate with a marker? move to an external reference?) is
still an open design question -- see
[provenance-enrichment-vocabulary.md](../../design/provenance-enrichment-vocabulary.md)'s
"Open questions" list.

Controlled by `[tool.pitloom.provenance]` in `pyproject.toml`:

```toml
[tool.pitloom.provenance]
format = "both"                    # "annotation" | "comment" | "both" (default)
schema = "pitloom/1"               # statement schema id
detail = "minimal"                 # "minimal" (default) | "full"
preserve-source-metadata = "auto"  # "auto" (default) | "always" | "never"
```

### 2. Comment attribute in SPDX elements (legacy / back-compat)

SPDX 3 defines a `comment` attribute for all Element classes. Before
Annotation support, and still today when `format` includes `"comment"`
(the default `"both"` does), Pitloom also writes a human-readable summary
into this attribute:

```python
class SoftwarePackage:
    def __init__(
        self,
        name: str,
        # ... other parameters
        comment: str | None = None,
    ) -> None:
        self.comment = comment
```

### 3. Provenance format pattern

Both the comment text and each Annotation field's source string share one
consistent, machine-parsable pattern
(parsed by `pitloom.assemble.spdx3.provenance.parse_provenance_value`):

**Format**: `Source: [location] | Field: [field_name]` or
           `Source: [location] | Method: [method_name]`

**Examples**:

- Static extraction: `Source: pyproject.toml | Field: project.name`
- Dynamic extraction: `Source: src/pkg/__about__.py | Method: dynamic_extraction`
- Inferred data: `Source: Pitloom generator | Method: inferred_from_authors`
- Tracking SDK:
  `Source: src/eval.py | Method: inspect_caller (tool: pitloom.loom, function: evaluate)`

### 4. Tracked metadata fields

Pitloom tracks provenance for the following metadata fields:

#### Package metadata

- **name**: Package name
  - Source: `pyproject.toml` -> `project.name`
- **version**: Package version
  - Source: `pyproject.toml` -> `project.version` (static)
  - Source: `__about__.py` or `__version__.py` (dynamic)
- **description**: Package description
  - Source: `pyproject.toml` -> `project.description`
- **dependencies**: Package dependencies
  - Source: `pyproject.toml` -> `project.dependencies`
- **urls**: Project URLs (homepage, source, etc.)
  - Source: `pyproject.toml` -> `project.urls`
- **authors**: Package authors
  - Source: `pyproject.toml` -> `project.authors`
- **license**: License information
  - Source: `pyproject.toml` -> `project.license`
- **copyright_text**: Copyright information
  - Source: Pitloom generator (inferred from authors)

#### Relationship metadata

- **dependsOn relationships**: Package dependencies
  - Source: Same as dependencies field

## Machine-readable format

The Annotation `statement` (JSON, per field) is the primary machine-readable
form -- parse it with a standard JSON decoder, no bespoke parsing needed.
The `comment` string (kept for `format = "comment"`/`"both"`) uses the
`"Source: X | Field: Y"` pattern above; Pitloom's own parser for that pattern
is `pitloom.assemble.spdx3.provenance.parse_provenance_value`, reproduced here
for reference:

```python
def parse_provenance_value(value: str) -> dict[str, str]:
    """Parse "Source: X | Field: Y" into a structured dict."""
    parsed: dict[str, str] = {}
    notes: list[str] = []
    for raw in value.split("|"):
        segment = raw.strip()
        if not segment:
            continue
        key, sep, val = segment.partition(":")
        if sep:
            parsed[key.strip().lower()] = val.strip()
        else:
            notes.append(segment)
    if notes:
        parsed.setdefault("note", " | ".join(notes))
    return parsed
```

## References

- [SPDX 3.0 Specification](https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf)
- [SPDX 3.0 Model](https://spdx.org/rdf/3.0/spdx-model.ttl)
- [Core/Annotation class](https://spdx.github.io/spdx-spec/v3.0.1/model/Core/Classes/Annotation/)
- [PEP 621 - Project metadata](https://peps.python.org/pep-0621/)
- [Hatchling build backend](https://hatch.pypa.io/latest/config/build/)
- [Implementation plan: metadata provenance via SPDX 3 Core/Annotation](annotation-provenance.md)
