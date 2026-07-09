---
Created: 2026-07-08
Last-Modified: 2026-07-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom

[![PyPI - Version](https://img.shields.io/pypi/v/pitloom)](https://pypi.org/project/pitloom/)
![GitHub License](https://img.shields.io/github/license/bact/pitloom)
[![DOI](https://img.shields.io/badge/doi-10.5281%2Fzenodo.19246283-blue)](https://doi.org/10.5281/zenodo.19246283)

**Pitloom** automates the generation of SPDX 3-compliant SBOMs for AI models
and Python projects, documenting the composition and provenance of software
systems. It reads metadata directly from Python packages and AI models
(GGUF, ONNX, PyTorch, Safetensors) and offers native Hatchling integration
so SBOMs can be generated automatically as part of a build.

## Install

```bash
pip install pitloom
```

Install with AI model metadata extraction support:

```bash
pip install pitloom[ai]
```

## Use

### Command line

Create SBOM for the Python project in the current directory:

```shell
loom .
```

Create SBOM of a local AI model:

```shell
loom -m path/to/model.safetensors -o model.spdx3.json
loom -m path/to/model.gguf --pretty
```

Create SBOM of an AI model on Hugging Face Hub:

```shell
loom -m https://huggingface.co/mistralai/Mistral-7B-v0.1
loom -m Qwen/Qwen3-235B-A22B   # bare model ID also works
```

### GitHub Action

```yaml
- uses: bact/pitloom@v0.11.0
```

### Python build hook

Create SBOM during Hatchling build:

```toml
[build-system]
requires = ["hatchling>=1.28.0", "pitloom>=0.11.0"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.pitloom]
enabled = true
```

### Python API

```python
from pathlib import Path
from pitloom.assemble import generate_sbom

project_path = Path("/path/to/project")
generate_sbom(project_path)
```

### Python tracking decorator

```python
from pitloom import loom

@loom.run(output_file="fragments/train.json")
def train_model():
    loom.set_model("model-name")
    loom.add_dataset("dataset-name", dataset_type="text")
    # ... training logic ...
```

## Learn more

- [Creation metadata](creation-metadata.md) -- who/what/when/how every
  Pitloom-generated element records about its own creation.
- [Metadata provenance](metadata-provenance.md) -- how Pitloom tracks the
  source of each metadata field for auditability.
- [Resources](resources.md) -- SBOM, AIBOM, SPDX, and related standards
  reading list.

## Get started

See the [project README](https://github.com/bact/pitloom#readme) for
installation, quick start, and full usage instructions.
