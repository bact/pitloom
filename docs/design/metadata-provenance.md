---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Metadata provenance and CreationInfo usage

This document describes how Loom implements metadata provenance tracking
and uses SPDX 3.0 CreationInfo for transparency and auditability.

## Overview

Metadata provenance tracking enables users to understand where each piece of
information in the SBOM comes from. This is essential for:

- **Transparency**: Clear understanding of data sources
- **Auditability**: Ability to verify and validate SBOM contents
- **Trust**: Building confidence in automated SBOM generation
- **Compliance**: Meeting requirements for supply chain security

## Provenance tracking implementation

### 1. Comment attribute in SPDX elements

SPDX 3.0 defines a `comment` attribute for all Element classes. Loom uses
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

Loom uses a consistent, machine-parsable format for provenance information:

**Format**: `Source: [location] | Field: [field_name]` or
           `Source: [location] | Method: [method_name]`

**Examples**:

- Static extraction: `Source: pyproject.toml | Field: project.name`
- Dynamic extraction: `Source: src/pkg/__about__.py | Method: dynamic_extraction`
- Inferred data: `Source: Loom generator | Method: inferred_from_authors`
- Tracking SDK: `Source: src/eval.py | Method: inspect_caller (tool: loom.bom, function: evaluate)`

### 3. Tracked metadata fields

Loom tracks provenance for the following metadata fields:

#### Package metadata

- **name**: Package name
  - Source: `pyproject.toml` → `project.name`
- **version**: Package version
  - Source: `pyproject.toml` → `project.version` (static)
  - Source: `__about__.py` or `__version__.py` (dynamic)
- **description**: Package description
  - Source: `pyproject.toml` → `project.description`
- **dependencies**: Package dependencies
  - Source: `pyproject.toml` → `project.dependencies`
- **urls**: Project URLs (homepage, source, etc.)
  - Source: `pyproject.toml` → `project.urls`
- **authors**: Package authors
  - Source: `pyproject.toml` → `project.authors`
- **license**: License information
  - Source: `pyproject.toml` → `project.license`
- **copyright_text**: Copyright information
  - Source: Loom generator (inferred from authors)

#### Relationship metadata

- **dependsOn relationships**: Package dependencies
  - Source: Same as dependencies field

## CreationInfo usage

### Current implementation

CreationInfo is used to record when the SBOM was created and who created it:

```python
creation_info = CreationInfo(
    created=datetime.now(timezone.utc),
    spec_version="3.0.1",
    created_by=[creator.spdx_id]
)
```

All SPDX elements share the same CreationInfo instance, which is referenced
by the blank node identifier `_:creationinfo`.

### CreationInfo attributes

According to SPDX 3.0, CreationInfo includes:

- **created**: Timestamp when the element was created
- **createdBy**: List of agents who created the element
- **specVersion**: SPDX specification version
- **comment**: Optional comment about creation (not currently used by Loom)

### Future enhancements for CreationInfo

1. **Tool information**: Record the Loom version used to generate the SBOM
2. **Build environment**: Track the build system and environment details
3. **Data enrichment**: Record when third-party tools enriched the data
4. **Validation**: Track validation steps and results

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
  "comment": "Metadata provenance: copyright_text: Source: Loom generator | Method: inferred_from_authors"
}
```

The copyright was inferred by Loom from the authors listed in `pyproject.toml`.

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
