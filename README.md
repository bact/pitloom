---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC-BY-4.0
---

# Loom

Creating SBOM during the build process. Now targeting Python Hatchling support.

## Overview

Loom is an automated Software Bill of Materials (SBOM) generator for Python
projects that use Hatchling as their build backend.
It generates SPDX 3.0 compliant SBOMs that document the composition,
provenance, and dependencies of software systems.

## Features

- **SPDX 3.0 Support**:
  Generates SBOMs in SPDX 3.0 JSON-LD format
- **Hatchling Integration**:
  Extracts metadata from Python projects using Hatchling
- **Dependency Tracking**:
  Automatically includes project dependencies in the SBOM
- **Standards Compliant**:
  Follows SPDX 3.0 specification and modern Python packaging standards

## Installation

Install Loom using pip:

```bash
pip install -e .
```

Or with development dependencies:

```bash
pip install -e ".[dev]"
```

## Usage

### Command line

Generate an SBOM for a Python project:

```bash
loom /path/to/project
```

Specify output file:

```bash
loom /path/to/project -o sbom.spdx3.json
```

Specify creator information:

```bash
loom /path/to/project --creator-name "Your Name" --creator-email "your@email.com"
```

### Python API

```python
from pathlib import Path
from loom.generator import generate_sbom_to_file

# Generate SBOM for a project
generate_sbom_to_file(
    project_dir=Path("/path/to/project"),
    output_path=Path("sbom.spdx3.json"),
    creator_name="Your Name",
    creator_email="your@email.com"
)
```

## Example

Generate an SBOM for the sentimentdemo project:

```bash
# Clone the sentimentdemo repository
git clone https://github.com/bact/sentimentdemo.git

# Generate SBOM
loom sentimentdemo -o sentimentdemo-sbom.spdx3.json
```

The generated SBOM will include:

- Project metadata (name, version, description)
- Project dependencies with version constraints
- SPDX relationships between components
- Creator and creation timestamp information

## Project structure

```text
loom/
├── src/
│   └── loom/
│       ├── __init__.py
│       ├── __about__.py
│       ├── __main__.py          # CLI entry point
│       ├── generator.py          # Main SBOM generator
│       ├── core/
│       │   └── models.py         # SPDX 3.0 data models
│       ├── extractors/
│       │   └── metadata.py       # Metadata extractor for Hatchling
│       └── exporters/
│           └── spdx3_json.py     # JSON-LD exporter
├── tests/
│   ├── test_models.py
│   ├── test_metadata.py
│   └── test_generator.py
├── design-docs/
│   └── architecture-overview.md
├── pyproject.toml
└── README.md
```

## Development

### Running tests

```bash
pytest
```

### Running linter

```bash
ruff check src/ tests/
```

### Building the package

```bash
pip install build
python -m build
```

## Roadmap

- [x] Basic SPDX 3.0 SBOM generation
- [x] Hatchling metadata extraction
- [x] Dependency tracking
- [ ] Support for setuptools
- [ ] Integration with spdx-python-model (see [design doc](design-docs/spdx-python-model-integration.md))
- [ ] Build log extraction for compiled dependencies
- [ ] AI/ML package profiles (AIPackage, DatasetPackage)
- [ ] PEP 770 support (.dist-info/sboms)
- [ ] PEP 740 attestation support
- [ ] Rust backend for performance optimization

## References

- [SPDX 3.0 Specification](https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf)
- [PEP 770 – SBOM metadata in Python packages](https://peps.python.org/pep-0770/)
- [Design Document](design-docs/architecture-overview.md)

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
