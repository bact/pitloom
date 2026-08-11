---
Created: 2026-07-08
Last-Modified: 2026-08-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

<!-- markdownlint-disable-next-line MD041 -->
{% include nav.html %}

# Pitloom

[![PyPI - Version](https://img.shields.io/pypi/v/pitloom)](https://pypi.org/project/pitloom/)
![GitHub License](https://img.shields.io/github/license/bact/pitloom)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/14001/badge)](https://www.bestpractices.dev/projects/14001)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/bact/pitloom/badge)](https://scorecard.dev/viewer/?uri=github.com/bact/pitloom)
[![DOI](https://img.shields.io/badge/doi-10.5281%2Fzenodo.19246283-blue)](https://doi.org/10.5281/zenodo.19246283)

**Pitloom** automates the generation of SPDX 3-compliant SBOMs for AI models
and Python projects, documenting the composition and provenance of software
systems. It reads metadata directly from Python packages and AI models
(GGUF, ONNX, PyTorch, Safetensors) and offers native Hatchling integration
so SBOMs can be generated automatically as part of a build.

When used with Hatchling, it embeds the generated SBOM directly into
the Python distribution package (wheel) `.dist-info/sboms` --
follows [PEP 770].

[PEP 770]: https://peps.python.org/pep-0770/

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

Create a Source SBOM for the Python project in the current directory:

```shell
loom project .
```

Create an Analyzed SBOM of a local AI model:

```shell
loom model path/to/model.safetensors -o model.spdx3.json
loom model path/to/model.gguf --pretty
```

Create an Analyzed SBOM of an AI model on Hugging Face Hub:

```shell
loom model https://huggingface.co/mistralai/Mistral-7B-v0.1
loom model Qwen/Qwen3-235B-A22B   # bare model ID also works
```

Create a Deployed SBOM of the currently installed environment:

```shell
loom env -o env.spdx3.json
```

Or use the unified auto-detection entrypoint:

```shell
loom generate .
```

### GitHub Action

```yaml
- uses: bact/pitloom@v0.13.3
```

This creates a standalone SBOM file on the runner.
It can be used for compliance logs, CI/CD audits, and release assets.

> Note: Running the GitHub Action alone does not embed the SBOM
> inside your distributed Python wheel
> (use the Hatchling build hook for PEP 770 wheel embedding).

### Hatchling build hook

Create SBOM during Hatchling build:

```toml
[build-system]
requires = ["hatchling>=1.29.0", "pitloom>=0.13.3"]
build-backend = "hatchling.build"
```

This embeds an SBOM into the distributed Python wheel.

### Python API

```python
from pathlib import Path
from pitloom.assemble import generate

project_path = Path("/path/to/project")
generate(project_path)
```

### Python tracking decorator

```python
from pitloom import loom


@loom.run(output_file="fragments/train.json")
def train_model():
    loom.set_model("model-name")  # <-- (A)
    loom.add_dataset("dataset-name", dataset_type="text")  # <-- (B)
    # ... training logic ...


@loom.run(output_file="fragments/eval.json")
def evaluate_model():
    loom.use_model("model-name")  # <-- (C)
    loom.add_dataset("dataset-name", dataset_type="text")  # <-- (B)
    # ... evaluation logic ...
```

- (A) and (C) set relationship between the code and the model
- (B) sets relationship between the code and the dataset

### AI Skills and the Claude Code plugin

Pitloom ships three Anthropic Agent Skills (`sbom-generate`,
`sbom-enrich`, `sbom-validate`), also installable as a self-hosted
Claude Code plugin:

```text
/plugin marketplace add bact/pitloom
/plugin install pitloom@pitloom
```

Once installed, ask in plain language ("generate an SBOM for this
project") or invoke explicitly: `/pitloom:sbom-generate [target]`,
`/pitloom:sbom-enrich [sbom-file]`, `/pitloom:sbom-validate [sbom-file]`.
See [AI Skills and the Claude Code plugin](ai-skills-and-plugin.md) for
install options, usage for generation, enrichment, and validation, and
verification steps.

## Learn more

- [AI Skills and the Claude Code plugin](ai-skills-and-plugin.md) --
  installing and using Pitloom as an Agent Skill or a Claude Code plugin.
- [Creation metadata](creation-metadata.md) -- who/what/when/how every
  Pitloom-generated element records about its own creation.
- [Metadata provenance](metadata-provenance.md) -- how Pitloom tracks the
  source of each metadata field for auditability.
- [Resources](resources.md) -- SBOM, AIBOM, SPDX, and related standards
  reading list.

## Get started

See the [project README](https://github.com/bact/pitloom#readme) for
installation, quick start, and full usage instructions.

## Security

For supported versions and vulnerability reporting guidelines,
please read our [Security policy][security].

[security]: https://github.com/bact/pitloom/security/policy
