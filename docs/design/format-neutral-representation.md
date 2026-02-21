---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Format-Neutral SBOM Representation

## Overview

The current Loom implementation integrates deeply with `spdx-python-model` 
to produce SPDX 3.0 output. While this is highly effective for current 
needs, the future software supply chain landscape will likely require 
support for multiple SBOM specifications and formats 
(e.g., SPDX 2.3, SPDX 3.X, CycloneDX, SWID).

To ensure long-term maintainability and flexibility, Loom is planning to 
adopt a format-neutral internal representation. This approach will decouple 
metadata extraction from the final output serialization, enabling seamless 
generation of any requested SBOM format.

## Architectural Consideration

An ideal internal representation must be:

- **Format-neutral**: Not tied to a specific SBOM format structural quirk.
- **Lossless**: Preserves all information during format conversions.
- **Version-agnostic**: Can export to different versions of the same format
  (e.g., SPDX 3.0, 3.1, 3.2).

This architecture enables:

- Support for multiple SBOM formats simultaneously (SPDX, CycloneDX, SWID).
- Easy migration between standard versions without data loss.
- Flexible import/export pipelines.
- Format translation capabilities built natively into Loom.

## Protobom as the primary candidate

[Protobom](https://github.com/protobom/protobom) is an open-source library 
being developed specifically for format-neutral SBOM representation.

**Key Features:**

- Protocol Buffers-based universal SBOM representation.
- Designed to be format-agnostic from the ground up.
- Supports lossless conversion between different SBOM formats.
- Efficient binary serialization for extremely large dependency graphs.
- Strong typing and schema validation.

**Evaluation Needed:**

- Assess compatibility with Loom's metadata extraction pipelines.
- Evaluate performance characteristics vs direct `spdx-python-model`.
- Determine integration complexity for Python execution contexts.
- Verify support for SPDX 3.x specific features (like AI/ML profiles).
- Check community adoption and active maintenance status.

## Integration Approach

```text
Build Tools → Loom Extractors → Protobom (Internal) → Format Exporters
                                      ↓
                              SPDX 3.x / CycloneDX / etc.
```

## Action Items for Future Development

- [ ] Research and evaluate Protobom for format-neutral internal representation.
- [ ] Prototype Protobom integration to verify schema completeness.
- [ ] Design architecture for multi-format support (e.g. CycloneDX).
- [ ] Build a translation layer for unique SPDX 3.0 AI/ML profiles.

## References

- [Protobom GitHub Repository](https://github.com/protobom/protobom)
- [SPDX 3.0 Specification](https://spdx.dev/specifications/)
- [CycloneDX Specification](https://cyclonedx.org/specification/overview/)
