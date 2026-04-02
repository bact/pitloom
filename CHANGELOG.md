---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

<!-- markdownlint-disable MD024 -->

# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

- Full release notes: <https://github.com/bact/pitloom/releases>
- Commit history: <https://github.com/bact/pitloom/compare/v0.3.0...v0.4.0>

## [0.4.0] 2026-04-02

### Added

- File and directory information in SBOM, with "contains" relationship
  ([#42][])
- Human-readable description to Relationship ([#44][])
- Creation information config to pyproject.toml and command line ([#47][])

[#42]: https://github.com/bact/pitloom/pull/42
[#44]: https://github.com/bact/pitloom/pull/44
[#47]: https://github.com/bact/pitloom/pull/47

## [0.3.0] - 2026-04-01

### Added

- AI model metadata extraction from fastText, HDF5, Keras, NumPy,
  PyTorch, PyTorch PT2 ([#33][], [#36][])
- Dogfooding: Pitloom Hatchling plugin in Pitloom's pyproject.toml ([#39][])
- Dataset metadata model and extraction (experiment) ([#40][])

### Changed

- JSON output is now sorted ([#29][]), implements:
  - [RFC 8785 JSON Canonicalization Scheme (JCS)][jcs]
  - [SPDX 3 canonical serialization][spdx3-canon]
  - Ordering as proposed in [spdx/spdx-spec issue #1339][spdx-spec-1339]:
    - 1: CreationInfo
    - 2: SpdxDocument
    - 3: Bom
    - 4: software_Sbom
    - 5: the rest of the SBOM

[spdx3-canon]: https://spdx.github.io/spdx-spec/v3.0.1/serializations/#canonical-serialization
[jcs]: https://www.rfc-editor.org/rfc/rfc8785
[spdx-spec-1339]: https://github.com/spdx/spdx-spec/issues/1339
[#29]: https://github.com/bact/pitloom/pull/29
[#33]: https://github.com/bact/pitloom/pull/33
[#36]: https://github.com/bact/pitloom/pull/36
[#39]: https://github.com/bact/pitloom/pull/39
[#40]: https://github.com/bact/pitloom/pull/40

## [0.2.0] - 2026-03-27

### Changed

- spdxId is now using deterministic UUID ([#27][])
  - A UUIDv5 generated using seeds from the project name, project version,
    dependency list, and the Merkle root of all files included in the wheel.

[#27]: https://github.com/bact/pitloom/pull/27

## [0.1.0] - 2026-03-27

First public pre-release.

Originally titled "Loom," the project was renamed Pitloom before
release because "Loom" and "Pyloom" were unavailable on PyPI.

### Added

- Minimum SBOM generation ([#9][])
- SBOM fragments integration ([#10][])
- AI model metadata extraction from GGUF, ONNX, and Safetensors ([#11][])
- Add Hatch plugin (hatchling.plugin.hookimpl) ([#17][])

[#9]: https://github.com/bact/pitloom/pull/9
[#10]: https://github.com/bact/pitloom/pull/10
[#11]: https://github.com/bact/pitloom/pull/11
[#17]: https://github.com/bact/pitloom/pull/17

---

[0.4.0]: https://github.com/bact/pitloom/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/bact/pitloom/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/bact/pitloom/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/bact/pitloom/releases/tag/v0.1.0
