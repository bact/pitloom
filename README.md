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
It generates SPDX 3 compliant SBOMs that document the composition,
provenance, and dependencies of software systems.

## Features

- **SPDX 3 support**:
  Generates SBOMs in SPDX 3 JSON-LD format
- **Hatchling integration**:
  Extracts metadata from Python projects using Hatchling
- **Dependency tracking**:
  Automatically includes project dependencies in the SBOM
- **AI/ML model metadata**:
  Extracts metadata from model files (ONNX, Safetensors, GGUF)
  for SPDX AI profile
- **Metadata provenance**:
  Tracks the source of each metadata field for transparency and auditability
- **Standards compliant**:
  Follows SPDX 3 specification and modern Python packaging standards

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
from loom.core.creation import CreationMetadata
from loom.assemble import generate_sbom

# Generate SBOM for a project
generate_sbom(
    project_dir=Path("/path/to/project"),
    output_path=Path("sbom.spdx3.json"),
    creation_info=CreationMetadata(
        creator_name="Your Name",
        creator_email="your@example.com",
    ),
    pretty=False,
)
```

### Hatchling build hook

Loom can embed an SBOM automatically into every wheel you build by acting as
a Hatchling build hook. The SBOM is placed at
`.dist-info/sboms/sbom.spdx3.json` inside the wheel, following
[PEP 770](https://peps.python.org/pep-0770/).

#### Adding Loom to your build requirements

Add `loom` to your project's build requirements:

```toml
[build-system]
requires = ["hatchling", "loom"]
build-backend = "hatchling.build"
```

#### Registering the hook

Enable the hook by adding a section to your `pyproject.toml`:

```toml
[tool.hatch.build.hooks.loom]
# All fields are optional. Defaults are shown.
enabled = true
sbom-basename = ""      # name part only (no extension); default "sbom"
creator-name = ""       # defaults to "Loom"
creator-email = ""
fragments = []          # extra SPDX fragment paths (relative to project root)
```

The full SBOM filename is `{sbom-basename}.spdx3.json` — e.g., the default
produces `sbom.spdx3.json`.  Setting `sbom-basename = "mypackage-1.0"` would
produce `mypackage-1.0.spdx3.json`.

That is all. Running `hatch build` or `python -m build` will now generate and
embed the SBOM automatically — no extra commands needed.

#### Merging AI/ML fragments

For AI-powered software, you can track model and dataset provenance during
training using `loom.bom`, then include those fragments in the wheel SBOM:

```toml
[tool.hatch.build.hooks.loom]
fragments = [
    "fragments/train_run.spdx3.json",
    "fragments/eval_run.spdx3.json",
]
```

Fragments listed under `[tool.hatch.build.hooks.loom]` are merged together
with any fragments already listed under `[tool.loom]`.

#### Resulting wheel structure

```text
mypackage-1.0-py3-none-any.whl
└── mypackage-1.0.dist-info/
    └── sboms/
        └── sbom.spdx3.json   ← PEP 770
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

Loom tracks the source of each metadata field in the SBOM using the SPDX 3
`comment` attribute. This enables answering questions like:

> "Why does the SBOM say the concluded license is MIT?"
>
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
│       ├── assemble/            # Layers 2+3 — build DocumentModel + map to spec
│       │   ├── spdx3/           # SPDX 3 specific (future: spdx23, cyclonedx)
│       │   │   ├── assembler.py # SPDX 3 assembler — build(DocumentModel)
│       │   │   ├── deps.py      # Dependency element assembly
│       │   │   └── fragments.py # Fragment merging
│       │   └── __init__.py      # generate_sbom() orchestrator
│       ├── core/
│       │   ├── ai_metadata.py   # Format-neutral AI model metadata
│       │   ├── config.py        # [tool.loom] settings (LoomConfig)
│       │   ├── creation.py      # SBOM creation metadata (CreationMetadata)
│       │   ├── document.py      # Format-neutral document model (DocumentModel)
│       │   ├── models.py        # SPDX ID generation utilities
│       │   └── project.py       # Python project metadata (ProjectMetadata)
│       ├── export/              # Layer 4 — serialise to physical format
│       │   └── spdx3_json.py    # SPDX 3 JSON-LD serialiser
│       ├── extract/             # Layer 1 — read from sources
│       │   ├── ai_model.py      # AI model file extractor (GGUF, ONNX, Safetensors)
│       │   └── pyproject.py     # pyproject.toml extractor
│       ├── plugins/
│       │   ├── __init__.py
│       │   └── hatch.py         # Hatchling build hook (PEP 770)
│       ├── __about__.py
│       ├── __init__.py
│       ├── __main__.py          # CLI entry point
│       └── bom.py               # ML tracking SDK
├── tests/
│   ├── fixtures/
│   │   └── sampleproject/       # minimal wheel-build fixture
│   ├── test_ai_model_extractor.py
│   ├── test_bom.py
│   ├── test_generator.py
│   ├── test_hatch_hook.py
│   ├── test_metadata.py
│   ├── test_models.py
│   ├── test_provenance.py
│   └── test_spdx3_compliance.py
├── LICENSE
├── README.md
└── pyproject.toml
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
- [x] Format-neutral internal representation (`DocumentModel`
  — see [design doc](docs/design/format-neutral-representation.md))
- [ ] Build log extraction for compiled dependencies
- [x] AI/ML package profiles (AIPackage, DatasetPackage)
- [x] PEP 770 support (.dist-info/sboms via `build_data["sbom_files"]`)
- [ ] PEP 740 attestation support
- [ ] Rust backend for performance optimization

## References

- [SPDX 3.0 Specification](https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf)
- [PEP 770 – SBOM metadata in Python packages](https://peps.python.org/pep-0770/)
- [Design document](docs/design/architecture-overview.md)

## License

- Source code: Apache License 2.0.
- Documentation: Creative Commons Attribution 4.0 International.
- Test fixture AI models:
  individual files carry Apache-2.0 or MIT licenses — see
  [tests/fixtures/README.md](tests/fixtures/README.md) for details.
