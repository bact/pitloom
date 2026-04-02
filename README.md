# Pitloom

[![PyPI - Version](https://img.shields.io/pypi/v/pitloom)](https://pypi.org/project/pitloom/)
https://doi.org/10.5281/zenodo.19376560
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19376560.svg)](https://doi.org/10.5281/zenodo.19376560)

![The Pippin Pitloom](./docs/mascot.png)

Automated transparency, woven from the ground up.

**Under development** --
**NOT FOR PRODUCTION**

## Overview

**Pitloom** automates the generation of SPDX 3-compliant SBOMs for Python projects,
documenting the composition and provenance of software systems.
By reading metadata directly from Python packages and AI models (GGUF, ONNX,
PyTorch, Safetensors), it creates standardized SPDX 3 JSON artifacts.
It also offers native Hatchling integration, allowing users to hook into
the build process to generate SBOMs automatically.

## Features

- **SPDX 3 support**:
  Generates SBOMs in SPDX 3 JSON-LD format
- **Hatchling integration**:
  Extracts metadata from Python projects using Hatchling
- **Dependency tracking**:
  Automatically includes project dependencies in the SBOM
- **AI/ML model metadata**:
  Extracts metadata from model files (GGUF, ONNX, PyTorch, Safetensors)
  for SPDX AI profile
- **Metadata provenance**:
  Tracks the source of each metadata field for transparency and auditability
- **Standards compliant**:
  Follows SPDX 3 specification and modern Python packaging standards

## Installation

Install Pitloom using pip:

```bash
pip install pitloom
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
pip install -e ".[gguf]"          # GGUF models
pip install -e ".[onnx]"          # ONNX models
pip install -e ".[safetensors]"   # Safetensors models
pip install -e ".[aimodel]"       # all of the above
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
from pitloom.core.creation import CreationMetadata
from pitloom.assemble import generate_sbom

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

Pitloom can embed an SBOM automatically into every wheel you build
by acting as a Hatchling build hook. The SBOM is placed at
`.dist-info/sboms/sbom.spdx3.json` inside the wheel, following
[PEP 770](https://peps.python.org/pep-0770/).

#### Adding Pitloom to your build requirements

Add `loom` to your project's build requirements:

```toml
[build-system]
requires = ["hatchling", "pitloom"]
build-backend = "hatchling.build"
```

#### Registering the hook

Enable the hook by adding a section to your `pyproject.toml`:

```toml
[tool.hatch.build.hooks.pitloom]
# All fields are optional. Defaults are shown.
enabled = true
sbom-basename = ""      # name part only (no extension); default "sbom"
creator-name = ""       # defaults to "Pitloom"
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
training using `pitloom.bom`, then include those fragments in the wheel SBOM:

```toml
[tool.hatch.build.hooks.pitloom]
fragments = [
    "fragments/train_run.spdx3.json",
    "fragments/eval_run.spdx3.json",
]
```

Fragments listed under `[tool.hatch.build.hooks.pitloom]` are merged together
with any fragments already listed under `[tool.pitloom]`.

#### Resulting wheel structure

```text
mypackage-1.0-py3-none-any.whl
└── mypackage-1.0.dist-info/
    └── sboms/
        └── sbom.spdx3.json   ← PEP 770
```

### Python tracking decorator

Developers can easily annotate scripts or Jupyter notebooks to generate
external SBOM fragments that Pitloom will merge during the build process:

```python
from pitloom import bom

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
loom sentimentdemo
```

The generated SBOM will include:

- Project metadata (name, version, description)
- Project dependencies with version constraints
- SPDX relationships between components
- Creator and creation timestamp information
- **Metadata provenance** tracking for transparency

## Metadata provenance

Pitloom tracks the source of each metadata field in the SBOM using the SPDX 3
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
pitloom/
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
│   └── pitloom/
│       ├── assemble/
│       │   ├── spdx3/           # SPDX 3 specific (future: spdx23, cyclonedx)
│       │   │   ├── document.py  # SPDX 3 document assembly — build(DocumentModel)
│       │   │   ├── deps.py      # Dependency element assembly
│       │   │   ├── ai.py        # AI model element assembly
│       │   │   └── fragments.py # Fragment merging
│       │   └── __init__.py      # generate_sbom() orchestrator
│       ├── core/
│       │   ├── ai_metadata.py   # Format-neutral AI model metadata
│       │   ├── config.py        # [tool.pitloom] settings (PitloomConfig)
│       │   ├── creation.py      # SBOM creation metadata (CreationMetadata)
│       │   ├── document.py      # Format-neutral document model (DocumentModel)
│       │   ├── models.py        # SPDX ID generation utilities
│       │   └── project.py       # Python project metadata (ProjectMetadata)
│       ├── export/
│       │   └── spdx3_json.py    # SPDX 3 JSON-LD serialiser
│       ├── extract/
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
  Individual files are licensed under Apache-2.0, CC0-1.0, or MIT.
  See [tests/fixtures/README.md](tests/fixtures/README.md) for details.
  Note that these are available in the source repository only and
  are not included in the distribution packages.

## Name

A [pit loom](https://en.wikipedia.org/wiki/Loom#Treadle_loom)
is a traditional handloom built into a ground-level pit
to house its internal mechanisms and the weaver's legs.
This "grounded" design provides stability and precision
during the weaving process.

We use the loom as a metaphor for the tool's function:
it weaves disparate threads of metadata into a cohesive SBOM,
creating a transparent, structured "fabric" for the software build.
