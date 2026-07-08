# Pitloom - An SBOM generator for AI models and Python projects

[![PyPI - Version](https://img.shields.io/pypi/v/pitloom)](https://pypi.org/project/pitloom/)
![GitHub License](https://img.shields.io/github/license/bact/pitloom)
[![DOI](https://img.shields.io/badge/doi-10.5281%2Fzenodo.19246283-blue)](https://doi.org/10.5281/zenodo.19246283)

*Automated transparency, woven from the ground up.*

**Pitloom** automates the generation of SPDX 3-compliant SBOMs for AI
models and Python projects. It reads metadata directly from Python
packages and AI models (GGUF, ONNX, PyTorch, Safetensors), producing
standardized SPDX 3 JSON artifacts -- as a CLI, a library, or a native
Hatchling build hook.

![The Pippin Pitloom](./docs/mascot.png)

## Contents

- [Quick start](#quick-start)
- [Ways to use Pitloom](#ways-to-use-pitloom)
- [Usage](#usage)
- [Example](#example)
- [Metadata provenance](#metadata-provenance)
- [References](#references)
- [License](#license)
- [Name](#name)

## Quick start

```bash
pip install pitloom
loom .            # SBOM for the Python project in the current dir
```

### Optional model format support

Install extras to enable metadata extraction from model files, either all
at once or one format at a time:

```bash
pip install -e ".[aimodel]"       # all supported local AI model formats
pip install -e ".[huggingface]"   # Hugging Face Hub model metadata
pip install -e ".[gguf]"          # or a single format: fasttext/gguf/onnx/safetensors
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the dev install.

## Ways to use Pitloom

| Surface | Reach for this when... |
| :--- | :--- |
| [Command line](#command-line) (`loom` / `pitloom`) | You want a one-off SBOM from a terminal, a Makefile target, or any shell script. |
| [Python API](#python-api) | You are calling Pitloom from Python code you control. |
| [Hatchling build hook](#hatchling-build-hook) | You build wheels with Hatchling and want an SBOM embedded automatically. |
| [Python tracking decorator](#python-tracking-decorator) | You are training/fine-tuning a model and want to capture provenance as you go, as an SPDX fragment. |
| [GitHub Action](#use-pitloom-as-a-github-action) | Your project isn't Hatchling-based, or you just want CI to produce an SBOM artifact with one `uses:` line. |
| [Agent Skill](#use-pitloom-as-an-ai-agent-skill) | You want an AI coding agent to generate (and optionally enrich) an SBOM on request. |
| [Claude Code plugin](#use-pitloom-as-a-claude-code-plugin) | You use Claude Code and want the Skills installable with one command. |

## Usage

### Command line

Generate an SBOM for a Python project in the current directory:

```bash
loom .
loom /path/to/project -o sbom.spdx3.json
```

Generate an SBOM for a single AI model file, without a Python project
directory (output written to the current working directory). Supported
local formats: GGUF, ONNX, Safetensors, PyTorch (`.pt`/`.pth`), Keras,
HDF5, NumPy, fastText:

```bash
loom -m path/to/model.safetensors -o my-model.spdx3.json
loom -m path/to/model.gguf --pretty
```

Or pass a Hugging Face Hub URL or model ID directly -- no local file
required. Pitloom fetches metadata from the Hub (model card, `config.json`,
`tokenizer_config.json`, `generation_config.json`) and produces an enriched
`ai_AIPackage` SBOM. Requires `huggingface_hub`
(`pip install pitloom[huggingface]`):

```bash
loom -m https://huggingface.co/mistralai/Mistral-7B-v0.1
loom -m Qwen/Qwen3-235B-A22B   # bare model ID also works
```

`loom -h` shows the full option list.

### Creation metadata

These flags apply to project, AI model, and Hugging Face SBOM generation
alike. `--creator-name` is repeatable -- each occurrence starts a new
creator, in order; `--creator-type` (`person` default, `organization`,
`software-agent`, `agent`) and `--creator-email` set the type/email of the
*most recently named* creator. `--creation-tool` records *what* produced
it (default `"Pitloom"`, also repeatable; `--no-creation-tool` to omit);
`--creation-comment`/`--creation-datetime` set free-text provenance and an
ISO 8601 timestamp:

```bash
loom . --creator-name "Alice" --creator-email "alice@example.com"
loom . --creator-name "Acme Corp" --creator-type organization
loom . --creator-name "Acme Corp" --creator-type organization --creator-name Alice
loom . --creation-datetime "2026-01-15T10:00:00Z" --creation-comment "CI run #123"
```

The same fields can be set in `pyproject.toml` under
`[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]` (CLI flags
take precedence, replacing the whole list rather than merging):

```toml
[[tool.pitloom.creator]]
name = "Alice"
email = "alice@example.com"
type = "person"       # or "organization", "software-agent", "agent"

[[tool.pitloom.creator]]
name = "Acme Corp"
type = "organization"

[[tool.pitloom.creation-tool]]
name = "MyCompany SBOM Wrapper"

[tool.pitloom.creation]
creation-datetime = "2026-01-15T10:00:00Z"
creation-comment = "Generated in CI pipeline #123"
```

See [Creation metadata](docs/creation-metadata.md) for what these fields
record and why -- the who/what/when/how model behind every element Pitloom
emits.

### Python API

The SBOM generator can be used programmatically:

```python
from pathlib import Path
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.assemble import generate_sbom

generate_sbom(
    project_dir=Path("/path/to/project"),
    output_path=Path("sbom.spdx3.json"),
    creation_metadata=CreationMetadata(creators=[Creator(name="Your Name")]),
)
```

`pitloom.assemble` also exposes `generate_ai_model_sbom()` (a local model
file) and `generate_huggingface_sbom()` (a Hub model ID or URL), with the
same `output_path`/`creation_metadata`/`pretty` keywords.

### Hatchling build hook

Pitloom can embed an SBOM automatically into every wheel you build, at
`.dist-info/sboms/sbom.spdx3.json`, per
[PEP 770](https://peps.python.org/pep-0770/) (wheels only). Add `pitloom`
as a build requirement (Hatchling **1.28.0+** required) and register the
hook:

```toml
[build-system]
requires = ["hatchling>=1.28.0", "pitloom>=0.10.0"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.pitloom]
enabled = true    # set to false to skip SBOM generation
```

That's all -- `hatch build`/`python -m build` now embeds the SBOM, always
as compact canonical JSON. Basename and fragments are configured under
`[tool.pitloom]`; creator/tool metadata uses the same
`[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]` /
`[tool.pitloom.creation]` tables the CLI reads (see
[Creation metadata](#creation-metadata) above):

```toml
[tool.pitloom]
sbom-basename = "sbom"   # -> "sbom.spdx3.json"

[tool.pitloom.fragments]
files = ["fragments/model.json"]   # merge externally tracked fragments
```

### Python tracking decorator

Developers can annotate scripts or Jupyter notebooks to generate external
SBOM fragments that Pitloom will merge during the build process, as a
function decorator or a context manager:

```python
from pitloom import loom

@loom.run(output_file="fragments/sentiment_model.json")
def train_model():
    loom.set_model("sentiment-clf")
    loom.add_dataset("imdb-reviews", dataset_type="text")
    # ... training logic ...
```

`loom.run` accepts the same [creation metadata](#creation-metadata) as the
CLI and build hook, via `creation_metadata=CreationMetadata(...)`. With
none given, the fragment records the unattended-run default (Pitloom
itself as both creator and tool).

### Use Pitloom as a GitHub Action

Add SBOM generation to any repository's CI with a single step, for any
Python build backend, not just Hatchling:

```yaml
- uses: bact/pitloom@v0.10.0
```

See [working-docs/implementation/github-action.md](working-docs/implementation/github-action.md)
for inputs, outputs, and more recipes.

### Use Pitloom as an AI-agent skill

`skills/sbom/` and `skills/enrich/` are ready-to-install
[Agent Skills](https://www.anthropic.com/) for Claude Code and the Claude
Agent SDK: `sbom` generates an SBOM on request; `enrich` augments an
existing one with detail read from a README or model card, via Pitloom's
fragment system.

```bash
mkdir -p ~/.claude/skills   # or .claude/skills for a project-scoped install
cp -r /path/to/pitloom/skills/sbom /path/to/pitloom/skills/enrich ~/.claude/skills/
```

See [working-docs/implementation/agent-skill.md](working-docs/implementation/agent-skill.md)
for full install instructions.

### Use Pitloom as a Claude Code plugin

The Skills above are also installable as a plugin, self-hosted from this
repository:

```text
/plugin marketplace add bact/pitloom
/plugin install pitloom@pitloom
```

Once installed: `/pitloom:sbom`, `/pitloom:enrich` (or just ask in plain
language). See
[working-docs/implementation/claude-code-plugin.md](working-docs/implementation/claude-code-plugin.md)
for what the plugin bundles.

## Example

```bash
git clone https://github.com/bact/sentimentdemo.git
loom sentimentdemo
```

The generated SBOM includes project metadata, dependencies with version
constraints, SPDX relationships, creator/creation info, and per-field
metadata provenance. See a more complete example in the
[examples/](./examples/) directory.

## Metadata provenance

Pitloom tracks the source of each metadata field in the SBOM using the
SPDX 3 `comment` attribute, so questions like "why does the SBOM say the
concluded license is MIT?" have a traceable answer. See
[Metadata provenance](docs/metadata-provenance.md) for the full explainer
and a worked example.

## References

- [SPDX 3.0 Specification](https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf)
- [PEP 770 – SBOM metadata in Python packages](https://peps.python.org/pep-0770/)
- [Design document](working-docs/design/architecture-overview.md)
- Bennet et al., [“Implementing AI Bill of Materials with SPDX 3.0”](https://www.linuxfoundation.org/research/ai-bom), The Linux Foundation, 2024.

## License

- Source code: Apache License 2.0.
- Documentation: Creative Commons Attribution 4.0 International.
- Test fixture AI models: individually licensed (Apache-2.0, CC0-1.0, or
  MIT); see [tests/fixtures/README.md](tests/fixtures/README.md). Source
  repository only -- not included in distribution packages.

## Name

A [pit loom](https://en.wikipedia.org/wiki/Loom#Treadle_loom)
is a traditional handloom built into a ground-level pit
to house its internal mechanisms and the weaver's legs.
This "grounded" design provides stability and precision
during the weaving process.

We use the loom as a metaphor for the tool's function:
it weaves disparate threads of metadata into a cohesive SBOM,
creating a transparent, structured "fabric" for the software build.
