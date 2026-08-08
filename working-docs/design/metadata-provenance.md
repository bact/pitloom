---
Created: 2026-02-07
Last-Modified: 2026-08-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Metadata provenance and CreationInfo usage

This document describes how Pitloom implements metadata provenance tracking
and uses SPDX 3 CreationInfo for transparency and auditability.

## Overview

Metadata provenance tracking enables users to understand where each piece of
information in the SBOM comes from. This is essential for:

- **Transparency**: Clear understanding of data sources
- **Auditability**: Ability to verify and validate SBOM contents
- **Trust**: Building confidence in automated SBOM generation
- **Compliance**: Meeting requirements for supply chain security

> **Status (2026-08):** Provenance is now recorded as SPDX 3 Core
> `Annotation` elements -- systematic and machine-readable -- with the
> original `comment`-based format kept for back-compat. The native-first
> backfill (Phase 2) has also landed for five of six items -- declared vs.
> concluded license, external identifiers (DOI/arXiv/URL), base-model
> lineage, dataset creator, and fragment-origin `imports` are now emitted
> as native SPDX constructs with no provenance residual for the value
> itself; only enrichment `CreationInfo` (N3) remains, blocked on the
> unbuilt `enrich/` subpackage. See
> [`working-docs/implementation/annotation-provenance.md`](../implementation/annotation-provenance.md)
> §10 for the full design and the Phase 2 checklist, and
> [`working-docs/implementation/phase2-native-backfill-handover.md`](../implementation/phase2-native-backfill-handover.md)
> for current status.

## Provenance tracking implementation

### 1. Core/Annotation elements (primary mechanism)

Each element with tracked provenance gets one `Annotation` (per
[`pitloom.assemble.spdx3.provenance`](../../src/pitloom/assemble/spdx3/provenance.py)):
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
  "statement": "{\"schema\":\"https://pitloom.dev/provenance/1\",\"fields\":{\"version\":{\"source\":\"src/mypackage/__about__.py\",\"method\":\"dynamic_extraction\"}}}"
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

## CreationInfo usage

### Current implementation

`CreationInfo` records who created a set of elements, what tool produced
them, when, and (optionally) how. Construction is centralised in
`pitloom.assemble.spdx3.creation_info.build_creation_info()`, shared by the
CLI, the Hatchling build hook, and `pitloom.loom` fragments, so all three
paths model creation identically:

```python
spdx_ci, agents, tools = build_creation_info(
    creation_metadata,  # a CreationMetadata
    doc_name,
    doc_uuid,
    default_comment="Generated via Pitloom CLI",
)
```

`agents` (`createdBy`) contains a `Person` or `Organization` per entry in
`CreationMetadata.creators` (`Creator.type` selects which, plus
`software-agent` and the generic `agent` for naming an automated creator
that isn't Pitloom itself); with no creators given, it is a single
`SoftwareAgent` "Pitloom" -- Pitloom acting unattended, not a fabricated
human. `tools` (`createdUsing`) defaults to a single `Tool` "Pitloom"
(carrying a `summary` with Pitloom's version), unless suppressed via
`tools=[]` (`--no-creation-tool` on the CLI).

Elements created together in one generation event -- one CLI run, one
Hatchling build, one `loom.run` -- share a single `CreationInfo` instance,
referenced by a blank node identifier such as `_:CreationInfo0`. A composite
SBOM assembled from merged fragments (`[tool.pitloom.fragments]`) is *not*
limited to one: each fragment keeps the `CreationInfo` from whichever run
actually produced it, so the final graph can contain several, one per
generation event that contributed to it. Don't assume a single-`CreationInfo`
graph when consuming SBOMs Pitloom produces.

### CreationInfo attributes

Per SPDX 3:

- **created**: Timestamp when the elements were created (`--creation-datetime`,
  else the current UTC time)
- **createdBy**: One or more Agents who created the elements -- see above
- **createdUsing**: Zero or more Tools used -- Pitloom itself, unless suppressed
- **specVersion**: SPDX specification version (`"3.0.1"`)
- **comment**: A short, static, per-channel note (e.g. `"Generated via
  Pitloom CLI"`), or the caller's own `--creation-comment` /
  `creation_comment`

### Future enhancements for CreationInfo

1. **Data enrichment**: Record when third-party tools (e.g. the `enrich`
   skill) augmented the data
2. **Validation**: Track validation steps and results

## Use cases

The examples below show the legacy `comment` form, since it reads well
inline; with the default `format = "both"`, the same information is *also*
present as an Annotation (§1 above) alongside every `comment` shown here.

### Example 1: Understanding version extraction

**Question**: "Why does the SBOM say version 1.2.3?"

**Answer**: Check the package's `comment` attribute:

```json
{
  "type": "software_Package",
  "name": "mypackage",
  "software_packageVersion": "1.2.3",
  "comment": "Metadata provenance: version: Source: src/mypackage/__about__.py | Method: dynamic_extraction"
}
```

The version was dynamically extracted from `src/mypackage/__about__.py`.

### Example 2: License determination

**Question**: "How was the license determined?"

**Answer**: Look at the license field provenance:

```json
{
  "comment": "Metadata provenance: license: Source: pyproject.toml | Field: project.license"
}
```

The license was read from the `project.license` field in `pyproject.toml`.

### Example 3: Copyright attribution

**Question**: "Where does the copyright text come from?"

**Answer**: Check the copyright_text provenance:

```json
{
  "software_copyrightText": "Copyright (c) 2026 Jane Doe",
  "comment": "Metadata provenance: copyright_text: Source: Pitloom generator | Method: inferred_from_authors"
}
```

The copyright was inferred by Pitloom from the authors listed in `pyproject.toml`.

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

## Best practices

### For SBOM generators

1. **Always track provenance**: Record source for every metadata field
2. **Use consistent format**: Follow the established pattern
3. **Be specific**: Include exact file paths and field names
4. **Handle uncertainty**: Clearly mark inferred or generated data

### For SBOM consumers

1. **Check provenance**: Review the comment field for data sources
2. **Validate critical fields**: Verify important metadata against sources
3. **Trust indicators**: Consider provenance when assessing SBOM quality
4. **Automated processing**: Parse provenance for tool integration

## References

- [SPDX 3.0 Specification](https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf)
- [SPDX 3.0 Model](https://spdx.org/rdf/3.0/spdx-model.ttl)
- [Core/Annotation class](https://spdx.github.io/spdx-spec/v3.0.1/model/Core/Classes/Annotation/)
- [PEP 621 - Project metadata](https://peps.python.org/pep-0621/)
- [Hatchling build backend](https://hatch.pypa.io/latest/config/build/)
- [Implementation plan: metadata provenance via SPDX 3 Core/Annotation](../implementation/annotation-provenance.md)
