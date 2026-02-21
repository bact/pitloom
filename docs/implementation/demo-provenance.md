---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Metadata provenance demonstration

This document demonstrates the metadata provenance tracking feature in Loom.

## What is metadata provenance?

Metadata provenance tracking records where each piece of information in the SBOM
comes from. This enables transparency and auditability, allowing both humans and
machines to verify the source of SBOM data.

## Example: Generate SBOM with provenance

### 1. Create a sample project

```bash
mkdir /tmp/demo-project
cd /tmp/demo-project

# Create project structure
mkdir -p src/demopackage

# Create version file
cat > src/demopackage/__about__.py << 'EOF'
__version__ = "1.2.3"
EOF

# Create pyproject.toml
cat > pyproject.toml << 'EOF'
[project]
name = "demopackage"
dynamic = ["version"]
description = "A demo package for testing provenance"
dependencies = ["requests>=2.28.0", "numpy==1.24.0"]
authors = [
    {name = "Jane Doe", email = "jane@example.com"}
]

[project.urls]
Homepage = "https://example.com"
Source = "https://github.com/example/demopackage"

[tool.hatch.version]
path = "src/demopackage/__about__.py"
EOF
```

### 2. Generate SBOM

```bash
loom /tmp/demo-project -o demo-sbom.spdx3.json \
  --creator-name "John Smith" \
  --creator-email "john@example.com"
```

### 3. Examine provenance in the SBOM

Open `demo-sbom.spdx3.json` and look for the main package:

```json
{
  "spdxId": "https://spdx.org/spdxdocs/Package/P-...",
  "type": "software_Package",
  "name": "demopackage",
  "software_packageVersion": "1.2.3",
  "description": "A demo package for testing provenance",
  "comment": "Metadata provenance: name: Source: pyproject.toml | Field: project.name; version: Source: src/demopackage/__about__.py | Method: dynamic_extraction; description: Source: pyproject.toml | Field: project.description; urls: Source: pyproject.toml | Field: project.urls; dependencies: Source: pyproject.toml | Field: project.dependencies; authors: Source: pyproject.toml | Field: project.authors; copyright_text: Source: Loom generator | Method: inferred_from_authors"
}
```

### 4. Parse provenance programmatically

```python
import json

with open('demo-sbom.spdx3.json', 'r') as f:
    sbom = json.load(f)

# Find main package
for elem in sbom['@graph']:
    if elem['type'] == 'software_Package' and elem['name'] == 'demopackage':
        if 'comment' in elem:
            print("Provenance information:")
            comment = elem['comment'].replace('Metadata provenance: ', '')
            for item in comment.split('; '):
                print(f"  • {item}")
```

Output:

```text
Provenance information:
  • name: Source: pyproject.toml | Field: project.name
  • version: Source: src/demopackage/__about__.py | Method: dynamic_extraction
  • description: Source: pyproject.toml | Field: project.description
  • urls: Source: pyproject.toml | Field: project.urls
  • dependencies: Source: pyproject.toml | Field: project.dependencies
  • authors: Source: pyproject.toml | Field: project.authors
  • copyright_text: Source: Loom generator | Method: inferred_from_authors
```

## Use cases

### Use case 1: Version verification

**Question**: "Why does the SBOM say version 1.2.3?"

**Answer**: Check the provenance comment for the version field:

```text
version: Source: src/demopackage/__about__.py | Method: dynamic_extraction
```

The version was dynamically extracted from `src/demopackage/__about__.py` file.

### Use case 2: License determination

**Question**: "How was the license determined?"

**Answer**: Look at the license field provenance:

```text
license: Source: pyproject.toml | Field: project.license
```

The license was read from the `project.license` field in `pyproject.toml`.

### Use case 3: Copyright attribution

**Question**: "Where does the copyright text come from?"

**Answer**: Check the copyright_text provenance:

```text
copyright_text: Source: Loom generator | Method: inferred_from_authors
```

The copyright was inferred by Loom from the authors listed in `pyproject.toml`.

### Use case 4: Dependency source

**Question**: "How do we know these are the correct dependencies?"

**Answer**: Check the dependencies provenance:

```text
dependencies: Source: pyproject.toml | Field: project.dependencies
```

Dependencies were extracted from the `project.dependencies` field in `pyproject.toml`.

### Use case 5: ML Traceability with `loom.bom`

**Question**: "Where did this specific AI Model or Dataset originate?"

**Answer**: Check the provenance embedded dynamically by the `loom.bom` 
tracking SDK when generating fragments:

```text
comment: Metadata provenance: package: Source: src/eval.py | Method: inspect_caller (tool: loom.bom, function: evaluate)
```

Loom inherently uses Python's `inspect` module at runtime to identify 
exactly which file and function produced the metric.

## Benefits

1. **Transparency**: Clear understanding of where data comes from
2. **Auditability**: Ability to verify and validate SBOM contents
3. **Trust**: Building confidence in automated SBOM generation
4. **Debugging**: Easy to identify issues with metadata extraction
5. **Machine-readable**: Tools can parse and process provenance
6. **Compliance**: Meets requirements for supply chain security

## Provenance format specification

### Pattern

```text
Source: [location] | Field: [field_name]
Source: [location] | Method: [method_name]
```

### Examples

- **Static extraction**: `Source: pyproject.toml | Field: project.name`
- **Dynamic extraction**: `Source: src/pkg/__about__.py | Method:...`
- **Inferred data**: `Source: Loom generator | Method: inferred_from_authors`
- **Tracking SDK**: `Source: src/eval.py | Method: inspect_caller (tool: loom.bom, function: eval)`
- **External tool**: `Source: licensee tool | Method: license_detection`

## Advanced: Custom provenance parser

Here's a Python function to parse provenance comments:

```python
def parse_provenance(comment: str) -> dict[str, dict[str, str]]:
    """Parse provenance comment into structured data.
    
    Args:
        comment: The comment string from SPDX element
        
    Returns:
        dict: Structured provenance data
        
    Example:
        >>> comment = "Metadata provenance: name: Source: pyproject.toml | Field: project.name"
        >>> parse_provenance(comment)
        {'name': {'source': 'pyproject.toml', 'detail': 'Field: project.name'}}
    """
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

# Usage example
import json

with open('demo-sbom.spdx3.json', 'r') as f:
    sbom = json.load(f)

for elem in sbom['@graph']:
    if elem['type'] == 'software_Package' and 'comment' in elem:
        provenance = parse_provenance(elem['comment'])
        print(f"Package: {elem['name']}")
        for field, info in provenance.items():
            print(f"  {field}: {info['source']}")
            if info['detail']:
                print(f"    ({info['detail']})")
```

## Future enhancements

Potential future enhancements to provenance tracking:

1. **Timestamp tracking**: Record when each field was extracted
2. **Tool versions**: Track which version of Loom extracted the data
3. **Confidence scores**: Add confidence levels for inferred data
4. **Multiple sources**: Support data from multiple sources
5. **Structured format**: Use dedicated SPDX annotations instead of comments
6. **Hash verification**: Include checksums for file-based sources

## Conclusion

Metadata provenance tracking in Loom provides transparency and auditability
for SBOM generation. It enables both humans and machines to understand and
verify where SBOM data comes from, building trust in the automated generation
process.

For more information, see:

- [metadata-provenance.md](../design/metadata-provenance.md)
- [README.md](../../README.md)
