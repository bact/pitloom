---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Loom

Creating SBOM during the build process. Now targeting Python Hatchling support.

## Overview

Loom is an automated Software Bill of Materials (SBOM) generator for Python
projects that use Hatchling as their build backend.
It generates SPDX 3.0 compliant SBOMs that document the composition,
provenance, and dependencies of software systems.

## Features

- **SPDX 3.0 support**:
  Generates SBOMs in SPDX 3.0 JSON-LD format
- **Hatchling integration**:
  Extracts metadata from Python projects using Hatchling
- **Dependency tracking**:
  Automatically includes project dependencies in the SBOM
- **AI/ML model metadata**:
  Extracts metadata from model files (ONNX, Safetensors, GGUF) for SPDX AI profile
- **Metadata provenance**:
  Tracks the source of each metadata field for transparency and auditability
- **Standards compliant**:
  Follows SPDX 3.0 specification and modern Python packaging standards

## Installation

Install Loom using pip:

```bash
pip install -e .
```

For development (lint + test), using pip >= 25:

```bash
pip install --group dev -e .
```

Or with uv:

```bash
uv sync --group dev
```

### Optional model format support

Install extras to enable metadata extraction from model files:

```bash
pip install -e ".[onnx]"          # ONNX models
pip install -e ".[safetensors]"   # Safetensors models
pip install -e ".[gguf]"          # GGUF models
pip install -e ".[model]"         # all of the above
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
loom /path/to/project --creator-name "Your Name" --creator-email "your@example.com"
```

### Python API

The SBOM generator can be used programmatically:

```python
from pathlib import Path
from loom.generator import generate_sbom_to_file

# Generate SBOM for a project
generate_sbom_to_file(
    project_dir=Path("/path/to/project"),
    output_path=Path("sbom.spdx3.json"),
    creator_name="Your Name",
    creator_email="your@example.com"
)
```

### Python tracking decorator

Developers can easily annotate scripts or Jupyter notebooks to generate
external SBOM fragments that Loom will merge during the build process:

```python
from loom import bom

# Use as a function decorator...
@bom.track(output_file="fragments/sentiment_model.json")
def train_model():
    bom.set_model("sentiment-clf")
    bom.add_dataset("imdb-reviews", dataset_type="text")
    # ... training logic ...

# ...or use as a context manager
with bom.track(output_file="fragments/sentiment_model.json"):
    bom.set_model("sentiment-clf")
    bom.add_dataset("imdb-reviews", dataset_type="text")
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
- **Metadata provenance** tracking for transparency

## Metadata provenance

Loom tracks the source of each metadata field in the SBOM using the SPDX 3.0
`comment` attribute. This enables answering questions like:

> "Why does the SBOM say the concluded license is MIT?"

> "Where did the version number come from?"

### Provenance examples

For a package with metadata extracted from various sources:

```json
{
  "type": "software_Package",
  "name": "mypackage",
  "software_packageVersion": "1.2.3",
  "comment": "Metadata provenance: name: Source: pyproject.toml | Field: project.name; version: Source: src/mypackage/__about__.py | Method: dynamic_extraction; dependencies: Source: pyproject.toml | Field: project.dependencies"
}
```

The provenance information shows:

- **Package name**: Extracted from `pyproject.toml` → `project.name`
- **Version**: Dynamically extracted from `src/mypackage/__about__.py`
- **Dependencies**: Listed in `pyproject.toml` → `project.dependencies`

This transparency is crucial for:

- **Auditability**: Understanding where SBOM data comes from
- **Trust**: Verifying the accuracy of metadata
- **Machine consumption**: Automated tools can parse provenance
- **Human review**: Manual inspection of data sources

## Project structure

```text
loom/
├── docs/
│   ├── design/
│   │   ├── architecture-overview.md
│   │   ├── format-neutral-representation.md
│   │   └── metadata-provenance.md
│   └── implementation/
│       ├── demo.md
│       ├── demo-provenance.md
│       └── summary.md
├── src/
│   └── loom/
│       ├── core/
│       │   └── models.py       # SPDX 3.0 data models
│       ├── extractors/
│       │   ├── metadata.py     # Metadata extractor for Hatchling
│       │   └── model.py        # AI model file extractor (ONNX, Safetensors, GGUF)
│       ├── exporters/
│       │   └── spdx3_json.py   # JSON-LD exporter
│       ├── __about__.py
│       ├── __init__.py
│       ├── __main__.py         # CLI entry point
│       ├── bom.py              # Metadata tracking SDK
│       └── generator.py        # Main SBOM generator
├── tests/
│   ├── test_bom.py
│   ├── test_generator.py
│   ├── test_metadata.py
│   ├── test_model_extractor.py
│   ├── test_models.py
│   ├── test_provenance.py
│   └── test_spdx3_compliance.py
├── LICENSE
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
- [ ] Format-Neutral Internal Rep (see [design doc](docs/design/format-neutral-representation.md))
- [ ] Build log extraction for compiled dependencies
- [x] AI/ML package profiles (AIPackage, DatasetPackage)
- [ ] PEP 770 support (.dist-info/sboms)
- [ ] PEP 740 attestation support
- [ ] Rust backend for performance optimization

## References

- [SPDX 3.0 Specification](https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf)
- [PEP 770 – SBOM metadata in Python packages](https://peps.python.org/pep-0770/)
- [Design document](docs/design/architecture-overview.md)

## License

- Source code licensed under the Apache License 2.0.
- Documentation licensed under Creative Commons Attribution 4.0 International.
