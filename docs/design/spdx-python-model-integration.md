---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Future Integration with spdx-python-model

## Overview

The current implementation uses custom SPDX 3.0 models defined in
`src/loom/core/models.py`.

For future development, we may consider integrating with the official
[spdx-python-model](https://github.com/spdx/spdx-python-model) library.

## Tutorial Reference

A comprehensive tutorial on using spdx-python-model is available at:
<https://gist.github.com/bact/7227ad858500c2097a25344a4af015d6>

## Key Features of spdx-python-model

1. **Official SPDX Python Bindings**:
    Generated directly from the SPDX 3.0 specification
2. **Version-specific Imports**:
    Support for different SPDX versions (e.g., v3_0_1)
3. **JSON-LD Deserialization**:
    Built-in support for reading SPDX 3 JSON files
4. **SHACLObjectSet**:
    Efficient object storage and querying with type-based indexing
5. **Property Access**:
    Direct Python attribute access to SPDX properties

## Example Usage

```python
from spdx_python_model import v3_0_1 as spdx3

# Read SPDX document
object_set = spdx3.SHACLObjectSet.from_json_ld_file("sbom.spdx3.json")

# Query by type
for doc in object_set.foreach_type("SpdxDocument"):
    print(doc.spdxId)
    print(doc.rootElement)

# Query by ID
obj = object_set.find_by_id("https://spdx.org/spdxdocs/Package/...")
```

## Current Implementation vs. spdx-python-model

### Current Implementation (Custom Models)

**Advantages:**

- Lightweight - no external dependencies
- Simple and easy to understand
- Full control over serialization format
- Fast prototyping and iteration
- No version compatibility issues

**Disadvantages:**

- Manual maintenance required for spec updates
- May not cover all SPDX 3.0 features
- No built-in validation against SPDX schema
- No deserialization support

### Using spdx-python-model

**Advantages:**

- Official SPDX bindings - stays up-to-date with spec
- Built-in JSON-LD serialization/deserialization
- Type-safe with proper Python bindings
- Rich querying capabilities (SHACLObjectSet)
- Validation support
- Better interoperability with other SPDX tools

**Disadvantages:**

- Additional dependency to manage
- Learning curve for the API
- Potential overhead for simple use cases
- May require adaptation of current code structure

## Migration Path

If we decide to migrate to spdx-python-model,
the recommended approach would be:

1. **Phase 1: Add spdx-python-model as optional dependency**

   - Keep current implementation as default
   - Add alternative exporter using spdx-python-model
   - Allow users to choose between implementations

2. **Phase 2: Gradual Migration**

   - Migrate exporters to use spdx-python-model serialization
   - Keep custom models for internal data representation
   - Use spdx-python-model for validation

3. **Phase 3: Full Adoption (if beneficial)**

   - Replace custom models with spdx-python-model bindings
   - Leverage SHACLObjectSet for complex querying
   - Utilize built-in validation and serialization

## Recommendation for Current Prototype

For the **current prototype**, we should **keep the custom models** because:

1. **Simplicity**:
    The prototype is focused on demonstrating basic SBOM generation
2. **No External Dependencies**:
    Easier to install and test
3. **Educational Value**:
    Custom models help understand SPDX 3.0 structure
4. **Sufficient for Requirements**:
    Current implementation meets all prototype goals

For **production use** or when adding advanced features (AI/Dataset profiles,
complex relationships, validation), we should consider adopting
spdx-python-model.

## Format-Neutral Internal Representation

### Future Architectural Consideration

For long-term maintainability and flexibility,
we may need an internal representation that is:

- **Format-neutral**: Not tied to a specific SBOM format
- **Lossless**: Preserves all information during format conversions
- **Version-agnostic**: Can export to different versions of the same format
  (e.g., SPDX 3.0, 3.1, 3.2)

This would enable:

- Support for multiple SBOM formats (SPDX, CycloneDX, SWID, etc.)
- Easy migration between SPDX versions without data loss
- Flexible import/export pipelines
- Format translation capabilities

### Protobom as a Potential Option

[Protobom](https://github.com/protobom/protobom) is a promising candidate for
format-neutral SBOM representation:

**Key Features:**

- Protocol Buffers-based universal SBOM representation
- Designed to be format-agnostic
- Supports conversion between different SBOM formats
- Efficient binary serialization
- Strong typing and schema validation

**Evaluation Needed:**

- Assess compatibility with our use cases
- Evaluate performance characteristics
- Determine integration complexity
- Verify support for SPDX 3.x features
- Test with AI/ML SBOM profiles
- Check community adoption and maintenance status

**Integration Approach:**

```text
Build Tools → Loom Extractors → Protobom (Internal) → Format Exporters
                                      ↓
                              SPDX 3.x / CycloneDX / etc.
```

## Action Items for Future Development

- [ ] Add spdx-python-model as optional dependency
- [ ] Create alternative exporter using spdx-python-model
- [ ] Add validation tests comparing custom models with spdx-python-model
- [ ] Benchmark performance differences
- [ ] Evaluate for setuptools integration roadmap
- [ ] Consider for AI/ML SBOM features (AIPackage, DatasetPackage)
- [ ] Research and evaluate Protobom for format-neutral internal representation
- [ ] Prototype Protobom integration if it meets requirements
- [ ] Design architecture for multi-format support

## References

- [spdx-python-model GitHub](https://github.com/spdx/spdx-python-model)
- [Tutorial by @bact](https://gist.github.com/bact/7227ad858500c2097a25344a4af015d6)
- [SPDX 3.0 Specification](https://spdx.dev/specifications/)
- [SPDX Examples Repository](https://github.com/spdx/spdx-examples)
- [Protobom GitHub](https://github.com/protobom/protobom)
