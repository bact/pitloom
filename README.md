# Pitloom - An SBOM generator for AI models and Python projects

[![PyPI - Version](https://img.shields.io/pypi/v/pitloom)](https://pypi.org/project/pitloom/)
![GitHub License](https://img.shields.io/github/license/bact/pitloom)
[![DOI](https://img.shields.io/badge/doi-10.5281%2Fzenodo.19246283-blue)](https://doi.org/10.5281/zenodo.19246283)

*Automated transparency, woven from the ground up.*

**Pitloom** automates the generation of SPDX 3-compliant SBOMs for AI models
and Python projects, documenting the composition and provenance of software
systems.
By reading metadata directly from Python packages and AI models (GGUF, ONNX,
PyTorch, Safetensors), it creates standardized SPDX 3 JSON artifacts.
It also offers native Hatchling integration, allowing users to hook into
the build process to generate SBOMs automatically.

![The Pippin Pitloom](./docs/mascot.png)

## Features

- **SPDX 3 support**:
  Generates SBOMs in SPDX 3 JSON (JSON-LD) format
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
```

Show help:

```bash
loom -h
```

#### Creation metadata options

These apply to project, AI model, and Hugging Face SBOM generation alike.
`--creator-name` names *who* initiated the generation and `--creator-type`
(`person` (default), `organization`, `software-agent`, or `agent`) selects
how they are modelled; `--creator-email` attaches an e-mail. `--creation-tool`
records *what* produced it (defaults to `"Pitloom"`); `--creation-comment`
and `--creation-datetime` set free-text provenance and an ISO 8601
timestamp. See [Creation metadata](#creation-metadata) below for how
these fields are recorded.

```bash
loom . --creator-name "Alice" --creator-email "alice@example.com"
loom . --creator-name "Acme Corp" --creator-type organization
loom . --creator-name "release-bot" --creator-type software-agent
loom . --creation-datetime "2026-01-15T10:00:00Z"
loom . --creation-comment "Generated in CI pipeline #123"
loom . --creation-tool "MyCompany SBOM Wrapper"
loom . --no-creation-tool        # omit the Tool element entirely
```

The same fields can be set in `pyproject.toml` under `[tool.pitloom.creation]`
(CLI flags take precedence):

```toml
[tool.pitloom.creation]
creator-name = "Alice"
creator-email = "alice@example.com"
creator-type = "person"          # or "organization", "software-agent", "agent"
creation-datetime = "2026-01-15T10:00:00Z"
creation-comment = "Generated in CI pipeline #123"
creation-tool = "MyCompany SBOM Wrapper"
```

#### Creation metadata

Every element Pitloom emits carries a record of *who* created it, *what*
tool produced it, *when*, and (optionally) *how* it was invoked -- Pitloom's
own creation-metadata model (`CreationMetadata`, see
[`pitloom.core.creation`](src/pitloom/core/creation.py)). Don't assume a
whole SBOM has exactly one such record: elements created together in the
same generation event share one, but a graph is free to contain several,
each covering whichever elements actually came from that event -- see
below.

SPDX 3 is Pitloom's only output format today, and it happens to define
almost exactly this shape as `CreationInfo`, so that's what this metadata
becomes in practice: `createdBy` (who), `createdUsing` (what tool),
`created` (when), `comment` (how). Should Pitloom add other output formats
later, the same who/what/when/how model would map onto whatever equivalent
concept that format defines -- this isn't an SPDX-specific design, just its
current, and so far only, expression. The [SPDX 3
spec](https://spdx.github.io/spdx-spec/v3.1-dev/model/Core/Classes/CreationInfo/)
is the authoritative reference for the field-level detail below.

A single Pitloom run -- one CLI invocation, one Hatchling build, one
`pitloom.loom.run` -- produces one such record, shared by every element
that run generated. When a composite SBOM merges pre-generated fragments
(see [Hatchling build hook](#hatchling-build-hook) and [Python tracking
decorator](#python-tracking-decorator) below) via `[tool.pitloom.fragments]`,
each fragment keeps the record from whichever run actually produced it. The
result contains as many of these records as generation events contributed
to it -- correct provenance to keep, since each part genuinely was created
separately, at a different time, possibly by a different creator.

| Field (SPDX 3 name) | Meaning | What Pitloom puts there |
| :--- | :--- | :--- |
| `createdBy` (**≥1**) | *Who* created it | The **creator**: a person, organization, software agent, or generic agent when you name one (`--creator-type`); otherwise Pitloom itself, acting unattended (see below). |
| `createdUsing` (0+) | *What* tool produced it | **Pitloom**, with a version summary. Suppress with `--no-creation-tool`. |
| `created` (1) | *When* | `--creation-datetime` if set, else the current UTC time. |
| `comment` (0-1) | *How* it was invoked | A short static note per channel (`Generated via Pitloom CLI`, `... Hatchling build hook`, `... loom SDK`), or your `--creation-comment`. |

Pitloom's design distinguishes *who acted* from *what tool was used* --
naming a creator never means naming Pitloom, and Pitloom itself is always
recorded as the tool, never as the creator. In SPDX 3 terms this is the
`Agent`/`Tool` split: an `Agent` (`Person` / `Organization` / `SoftwareAgent`
/ the generic `Agent`) is who acts; a `Tool` is the instrument used. Pitloom
is the instrument, so it belongs in `createdUsing` as a `Tool` -- **not** in
`createdBy`.

- **You name a creator** (`--creator-name`, or `[tool.pitloom.creation]`):
  it becomes a person (default), organization, software agent, or generic
  agent as the creator (via `--creator-type`), and the main package's
  supplier. The software-agent/agent types are for naming an automated
  creator that isn't Pitloom itself -- e.g. a CI bot that invoked Pitloom on
  someone's behalf.
- **You name no creator** (zero-config): rather than invent a fake person,
  Pitloom records itself as the creator too, but as a software agent, not a
  person or organization -- honestly "an unattended Pitloom run made this" --
  and omits a supplier for the main package. Pitloom is still recorded as
  the tool regardless, so the same Pitloom shows up twice in this case: once
  as the (software agent) creator, once as the tool.

This applies uniformly to the CLI, the Hatchling build hook, and
`pitloom.loom` fragments -- all three accept the same creator/tool/timestamp
overrides and fall back to the same `SoftwareAgent` default.

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
    creation_metadata=CreationMetadata(
        creator_name="Your Name",
        creator_email="your@example.com",
    ),
    pretty=False,
)

# Generate an SBOM for a standalone AI model file
generate_ai_model_sbom(
    model_path=Path("model.safetensors"),
    output_path=Path("model.spdx3.json"),
    creation_metadata=CreationMetadata(creator_name="Your Name"),
    pretty=True,
)

# Generate an SBOM from a Hugging Face model repository (no local file needed)
from pitloom.assemble import generate_huggingface_sbom

generate_huggingface_sbom(
    model_source="mistralai/Mistral-7B-v0.1",  # or full URL
    output_path=Path("mistral.spdx3.json"),
    creation_metadata=CreationMetadata(creator_name="Your Name"),
    pretty=True,
)
```

### Hatchling build hook

Pitloom can embed an SBOM automatically into every wheel you build,
acting as a native Hatchling build hook.
The SBOM is placed at `.dist-info/sboms/sbom.spdx3.json` inside the wheel,
per [PEP 770](https://peps.python.org/pep-0770/) --
the hook only runs for wheels (sdists have no such convention).

Add `pitloom` as a build requirement (Hatchling **1.28.0+** is required for
native PEP 770 support) and register the hook:

```toml
[build-system]
requires = ["hatchling>=1.28.0", "pitloom>=0.9.0"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.pitloom]
enabled = true    # set to false to skip SBOM generation; this is the only
                  # setting that lives here
```

That's all -- running `hatch build` or `python -m build` now embeds the SBOM
in every wheel, no extra commands needed.

Basename, fragments, and creator/tool metadata are configured once, under
`[tool.pitloom]` / `[tool.pitloom.creation]` -- the same settings the CLI
uses (see [Creation metadata options](#creation-metadata-options) above):

```toml
[tool.pitloom]
sbom-basename = "sbom"   # -> "sbom.spdx3.json"; e.g. "mypkg-1.0" -> "mypkg-1.0.spdx3.json"
```

The hook always emits compact, canonical JSON regardless of `[tool.pitloom]`'s
`pretty` setting.

For AI-powered software, track model/dataset provenance during training with
`pitloom.loom` (below), then list the resulting fragment file paths under
`[tool.pitloom.fragments]` to merge them into the wheel's SBOM:

```toml
[tool.pitloom.fragments]
files = ["fragments/model.json"]
```

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
@loom.run(output_file="fragments/sentiment_model.json")
def train_model():
    loom.set_model("sentiment-clf")
    loom.add_dataset("imdb-reviews", dataset_type="text")
    # ... training logic ...

# ...or use as a context manager
with loom.run(output_file="fragments/sentiment_model.json"):
    loom.set_model("sentiment-clf")
    loom.add_dataset("imdb-reviews", dataset_type="text")
```

`loom.run` accepts the same [creation metadata](#creation-metadata)
as the CLI and build hook -- via a `creation_metadata=` `CreationMetadata`:
name a creator, override the tool, timestamp, or comment. With none given,
the fragment records the unattended-run default (Pitloom itself as creator
and as tool):

```python
from pitloom.core.creation import CreationMetadata

with loom.run(
    "fragments/train.spdx3.json",
    creation_metadata=CreationMetadata(
        creator_name="Acme Corp",
        creator_type="organization",  # or "person" (default), "software-agent", "agent"
        creator_email="ml@acme.example",
        creation_datetime="2026-01-15T10:00:00Z",  # default: now
        # creation_tool=None,          # omit the Tool element entirely
    ),
):
    loom.set_model("sentiment-clf")
```

### Use Pitloom as a GitHub Action

Add SBOM generation to any repository's CI with a single step -- works for
any Python build backend, not just Hatchling:

```yaml
- uses: bact/pitloom@v0.9.0
```

See [docs/implementation/github-action.md](docs/implementation/github-action.md)
for inputs, outputs, and more recipes (release-asset upload, matrix
builds, AI model SBOMs).

### Use Pitloom as an AI-agent skill

`skills/sbom/` and `skills/enrich/` are ready-to-install
[Agent Skills](https://www.anthropic.com/) for Claude Code and the Claude
Agent SDK: `sbom` lets an agent generate an SBOM on request; `enrich`
optionally augments an existing one (reading a README or model card to
infer detail Pitloom's static extraction cannot see) via Pitloom's
fragment system. Both work independently, by natural language or by
explicit invocation.

Copy either (or both) into a skills directory Claude Code reads from:

```bash
mkdir -p ~/.claude/skills   # or .claude/skills for a project-scoped install
cp -r /path/to/pitloom/skills/sbom ~/.claude/skills/
cp -r /path/to/pitloom/skills/enrich ~/.claude/skills/
```

A skill's invocable name is its directory name. If you already have an
unrelated skill called `sbom` or `enrich`, copy to a different destination
name instead of overwriting it -- e.g. `~/.claude/skills/pitloom-sbom` -- a
plain rename that only changes the explicit-invocation name (`SKILL.md`
needs no edits).

See [docs/implementation/agent-skill.md](docs/implementation/agent-skill.md)
for full install instructions and
[docs/design/adoption-surfaces.md](docs/design/adoption-surfaces.md) for
how this fits alongside Pitloom's other surfaces.

### Use Pitloom as a Claude Code plugin

The Skills above are also installable as a plugin, self-hosted from this
repository, with namespaced explicit invocation:

```text
/plugin marketplace add bact/pitloom
/plugin install pitloom@pitloom
```

Once installed: `/pitloom:sbom`, `/pitloom:enrich` (or just ask in plain
language -- both remain auto-triggerable). See
[docs/implementation/claude-code-plugin.md](docs/implementation/claude-code-plugin.md)
for what the plugin bundles.

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

See a more complete example in the [examples/](./examples/) directory.

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
