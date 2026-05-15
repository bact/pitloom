# Pitloom

[![PyPI - Version](https://img.shields.io/pypi/v/pitloom)](https://pypi.org/project/pitloom/)
![GitHub License](https://img.shields.io/github/license/bact/pitloom)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19246283.svg)](https://doi.org/10.5281/zenodo.19246283)

![The Pippin Pitloom](./docs/mascot.png)

Automated transparency, woven from the ground up.

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
- **Multi-backend metadata extraction**:
  Reads project metadata from `pyproject.toml` (PEP 621 `[project]`),
  [Poetry](https://python-poetry.org/) (`[tool.poetry]`),
  and [setuptools](https://setuptools.pypa.io/) (`setup.cfg` / `setup.py`)
- **Dependency tracking**:
  Automatically includes project dependencies in the SBOM
- **AI/ML model metadata**:
  Extracts metadata from model files (GGUF, ONNX, PyTorch, Safetensors)
  for SPDX AI profile
- **License detection**:
  Detect [SPDX License ID](https://spdx.org/licenses/)
  from project metadata and license text,
  using [LicenseID](https://github.com/bact/licenseid/)
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
pip install -e ".[aimodel]"       # all supported local AI model formats
pip install -e ".[huggingface]"   # Hugging Face Hub model metadata
```

or choose individual local formats:

```bash
pip install -e ".[fasttext]"      # fastText models
pip install -e ".[gguf]"          # GGUF models
pip install -e ".[onnx]"          # ONNX models
pip install -e ".[safetensors]"   # Safetensors models
```

## Usage

### Command line

#### Project SBOM

Generate an SBOM for a Python project in the current directory:

```bash
loom .
```

Specify output file:

```bash
loom /path/to/project -o sbom.spdx3.json
```

#### AI model SBOM

Generate an SBOM for a single AI model file, without a Python
project directory. The model is treated as an `ai_AIPackage` root element.
The output file is written to the **current working directory**:

```bash
loom -m path/to/model.safetensors
loom -m path/to/model.onnx
loom -m path/to/model.gguf
```

Supported local formats: GGUF, ONNX, Safetensors, PyTorch (`.pt`/`.pth`),
Keras, HDF5, NumPy, fastText.

#### Hugging Face model SBOM

Pass a Hugging Face Hub URL or model ID directly - no local file required.
Pitloom fetches metadata from the Hub (model card, `config.json`,
`tokenizer_config.json`, and `generation_config.json`) and produces an
enriched `ai_AIPackage` SBOM with architecture, hyperparameters, license,
language, and linked training datasets.

```bash
# Full URL
loom -m https://huggingface.co/mistralai/Mistral-7B-v0.1

# URL with tree path (stripped automatically)
loom -m https://huggingface.co/mistralai/Mistral-7B-v0.1/tree/main

# Bare model ID
loom -m Qwen/Qwen3-235B-A22B
```

Requires `huggingface_hub`:

```bash
pip install pitloom[huggingface]
```

#### Common model SBOM options

Specify the output file explicitly:

```bash
loom -m model.safetensors -o my-model.spdx3.json
loom -m mistralai/Mistral-7B-v0.1 -o mistral.spdx3.json
```

Pretty-print the output:

```bash
loom -m model.gguf --pretty
loom -m Qwen/Qwen3-235B-A22B --pretty
```

Set creator metadata:

```bash
loom -m model.safetensors --creator-name "Alice" --creator-email "alice@example.com"
```

Show help:

```bash
loom -h
```

### Python API

The SBOM generator can be used programmatically:

```python
from pathlib import Path
from pitloom.core.creation import CreationMetadata
from pitloom.assemble import generate_sbom, generate_ai_model_sbom

# Generate SBOM for a Python project
generate_sbom(
    project_dir=Path("/path/to/project"),
    output_path=Path("sbom.spdx3.json"),
    creation_info=CreationMetadata(
        creator_name="Your Name",
        creator_email="your@example.com",
    ),
    pretty=False,
)

# Generate an SBOM for a standalone AI model file
generate_ai_model_sbom(
    model_path=Path("model.safetensors"),
    output_path=Path("model.spdx3.json"),
    creation_info=CreationMetadata(creator_name="Your Name"),
    pretty=True,
)

# Generate an SBOM from a Hugging Face model repository (no local file needed)
from pitloom.assemble import generate_huggingface_sbom

generate_huggingface_sbom(
    model_source="mistralai/Mistral-7B-v0.1",  # or full URL
    output_path=Path("mistral.spdx3.json"),
    creation_info=CreationMetadata(creator_name="Your Name"),
    pretty=True,
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
sbom-basename = "package-name"      # name part only (no extension); default "sbom"
creator-name = "SBOM Creator"       # defaults to "Pitloom"
creator-email = "mail@example.com"  # defaults to None
creation-datetime = "2026-04-01T00:00:00Z"  # Date and time in ISO 8601 UTC format
fragments = []  # extra SPDX fragment paths (relative to project root)
```

The full SBOM filename is `{sbom-basename}.spdx3.json` - e.g., the default
produces `sbom.spdx3.json`.  Setting `sbom-basename = "mypackage-1.0"` would
produce `mypackage-1.0.spdx3.json`.

That is all. Running `hatch build` or `python -m build` will now generate and
embed the SBOM automatically - no extra commands needed.

#### Merging AI/ML fragments

For AI-powered software, you can track model and dataset provenance during
training using `pitloom.loom`, then include those fragments in the wheel SBOM:

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
        └── sbom.spdx3.json   <- PEP 770
```

### Python tracking decorator

Developers can easily annotate scripts or Jupyter notebooks to generate
external SBOM fragments that Pitloom will merge during the build process:

```python
from pitloom import loom

# Use as a function decorator...
@loom.shoot(output_file="fragments/sentiment_model.json")
def train_model():
    loom.set_model("sentiment-clf")
    loom.add_dataset("imdb-reviews", dataset_type="text")
    # ... training logic ...

# ...or use as a context manager
with loom.shoot(output_file="fragments/sentiment_model.json"):
    loom.set_model("sentiment-clf")
    loom.add_dataset("imdb-reviews", dataset_type="text")
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

- **Package name**: Extracted from `pyproject.toml` -> `project.name`
- **Version**: Dynamically extracted from `src/mypackage/__about__.py`
- **Dependencies**: Listed in `pyproject.toml` -> `project.dependencies`

This transparency is crucial for:

- **Auditability**: Understanding where SBOM data comes from
- **Trust**: Verifying the accuracy of metadata
- **Machine consumption**: Automated tools can parse provenance
- **Human review**: Manual inspection of data sources

## Project structure

See [docs/implementation/summary.md](docs/implementation/summary.md) for the
canonical, up-to-date project tree.

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

See [docs/design/roadmap.md](docs/design/roadmap.md).

## References

- [SPDX 3.0 Specification](https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf)
- [PEP 770 – SBOM metadata in Python packages](https://peps.python.org/pep-0770/)
- [Design document](docs/design/architecture-overview.md)

For more information about implementing AI BOM using SPDX specification,
see *Karen Bennet, Gopi Krishnan Rajbahadur, Arthit Suriyawongkul,
and Kate Stewart,
[“Implementing AI Bill of Materials (AI BOM) with SPDX 3.0: A Comprehensive Guide to Creating AI and
Dataset Bill of Materials”](https://www.linuxfoundation.org/research/ai-bom),
The Linux Foundation, October 2024*.

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
