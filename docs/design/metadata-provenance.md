---
Created: 2026-02-07
Last-Modified: 2026-07-08
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

## Provenance tracking implementation

### 1. Comment attribute in SPDX elements

SPDX 3 defines a `comment` attribute for all Element classes. Pitloom uses
this attribute to record metadata provenance information.

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

### 2. Provenance format pattern

Pitloom uses a consistent, machine-parsable format for provenance information:

**Format**: `Source: [location] | Field: [field_name]` or
           `Source: [location] | Method: [method_name]`

**Examples**:

- Static extraction: `Source: pyproject.toml | Field: project.name`
- Dynamic extraction: `Source: src/pkg/__about__.py | Method: dynamic_extraction`
- Inferred data: `Source: Pitloom generator | Method: inferred_from_authors`
- Tracking SDK:
  `Source: src/eval.py | Method: inspect_caller (tool: pitloom.loom, function: evaluate)`

### 3. Tracked metadata fields

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
spdx_ci, creator, tool = build_creation_info(
    creation_metadata,  # a CreationMetadata
    doc_name,
    doc_uuid,
    default_comment="Generated via Pitloom CLI",
)
```

`creator` (`createdBy`) is a `Person` or `Organization` when
`CreationMetadata.creator_name` is set (`creator_type` selects which, plus
`software-agent` and the generic `agent` for naming an automated creator
that isn't Pitloom itself); with no name given, it is the `SoftwareAgent`
"Pitloom" -- Pitloom acting unattended, not a fabricated human. `tool`
(`createdUsing`) is the `Tool` "Pitloom" (carrying a `summary` with
Pitloom's version), unless suppressed via `creation_tool=None`
(`--no-creation-tool` on the CLI).

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

The provenance format is designed to be both human-readable and machine-parsable.

**Parsing example**:

```python
def parse_provenance(comment: str) -> dict[str, dict[str, str]]:
    """Parse provenance comment into structured data."""
    if not comment.startswith("Metadata provenance:"):
        return {}
    
    provenance = {}
    content = comment.replace("Metadata provenance: ", "")
    
    for item in content.split("; "):
        if ": " in item:
            field, source_info = item.split(": ", 1)
            parts = source_info.split(" | ")
            provenance[field] = {
                "source": parts[0].replace("Source: ", ""),
                "detail": parts[1] if len(parts) > 1 else ""
            }
    
    return provenance
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
- [PEP 621 - Project metadata](https://peps.python.org/pep-0621/)
- [Hatchling build backend](https://hatch.pypa.io/latest/config/build/)
