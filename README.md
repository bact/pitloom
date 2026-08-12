# Pitloom - SBOM generator for AI models and Python projects

[![PyPI - Version](https://img.shields.io/pypi/v/pitloom)](https://pypi.org/project/pitloom/)
![GitHub License](https://img.shields.io/github/license/bact/pitloom)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/14001/badge)](https://www.bestpractices.dev/projects/14001)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/bact/pitloom/badge)](https://scorecard.dev/viewer/?uri=github.com/bact/pitloom)
[![DOI](https://img.shields.io/badge/doi-10.5281%2Fzenodo.19246283-blue)](https://doi.org/10.5281/zenodo.19246283)

*Automated transparency, woven from the ground up.*

**Pitloom** automates the generation of [SPDX 3]-compliant SBOMs for
AI models and Python projects. It reads metadata directly from Python
packages and AI models (GGUF, ONNX, PyTorch, Safetensors), producing
standardized SPDX 3 JSON artifacts -- as a CLI, a library, or a native
Hatchling build hook.

When used with Hatchling, Pitloom automatically embeds the generated
SBOM directly into the resulting Python distribution (wheel).
The file is placed in the `{name}-{version}.dist-info/sboms` directory,
ensuring compliance with the PyPA
[Package Installation Metadata][dist-info] specification ([PEP 770]).

[SPDX 3]: https://spdx.github.io/spdx-spec/
[dist-info]: https://packaging.python.org/en/latest/specifications/recording-installed-packages/#the-dist-info-directory
[PEP 770]: https://peps.python.org/pep-0770/

![The Pippin Pitloom](./docs/mascot.png)

## Contents

- [Quick start](#quick-start)
- [Usage](#usage)
- [Example](#example)
- [Detailed features](#detailed-features)
- [Metadata provenance](#metadata-provenance)
- [References](#references)
- [License](#license)
- [Name](#name)

## Quick start

```bash
pip install pitloom
loom project .     # SBOM for the Python project in the current dir
```

### Optional features

Install extras to enable more metadata extraction:

```bash
pip install "pitloom[ai]"              # Get metadata from AI model file and Hugging Face Hub
pip install "pitloom[content-type]"    # Get content type from Magika
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the dev install.

## Usage

| Surface | Reach for this when... |
| :--- | :--- |
| [Command line](#command-line) (`loom` / `pitloom`) | You want a one-off SBOM from a terminal, a Makefile target, or any shell script. |
| [Hatchling build hook](#hatchling-build-hook) | You build wheels with Hatchling and want an SBOM embedded automatically. |
| [Python API](#python-api) | You are calling Pitloom from Python code you control. |
| [Python tracking decorator](#python-tracking-decorator) | You are training/fine-tuning a model and want to capture provenance as you go, as an SPDX fragment. |
| [GitHub Action](#use-pitloom-as-a-github-action) | Your project isn't Hatchling-based, or you just want CI to produce an SBOM artifact with one `uses:` line. |
| [Agent Skill](#use-pitloom-as-an-ai-agent-skill) | You want an AI coding agent to generate (and optionally enrich) an SBOM on request. |
| [Claude Code plugin](#use-pitloom-as-a-claude-code-plugin) | You use Claude Code and want the Skills installable with one command. |

See [docs/agent-skills.md](docs/agent-skills.md) and
[docs/claude-code-plugin.md](docs/claude-code-plugin.md) for a dedicated
walkthrough of the Agent Skills and the Claude Code plugin.

### Command line

`loom -h` shows the full option list.

#### Generate an SBOM

Generate a **Source SBOM** for a Python project in the current directory:

```bash
loom project .
loom project /path/to/project -o sbom.spdx3.json
```

Generate an **Analyzed SBOM** from a pre-built wheel
(extracting bundled binaries as phantom dependencies):

```bash
loom wheel path/to/mypackage-1.0.0-py3-none-any.whl -o sbom.spdx3.json
```

Generate a **Deployed SBOM** reflecting the exact installed environment graph:

```bash
loom env -o env.spdx3.json
```

Generate an **Analyzed SBOM** for a single AI model file,
without a Python project directory
(output written to the current working directory).
Supported local formats: GGUF, ONNX, Safetensors, PyTorch (`.pt`/`.pth`),
Keras, HDF5, NumPy, fastText:

```bash
loom model path/to/model.safetensors -o model.spdx3.json
loom model path/to/model.gguf --pretty
```

Or pass a Hugging Face Hub URL or model ID directly -- no local file
required. Pitloom fetches metadata from the Hub (model card, `config.json`,
`tokenizer_config.json`, `generation_config.json`) and produces an enriched
`ai_AIPackage` SBOM. Requires `huggingface_hub`
(`pip install pitloom[huggingface_hub]`):

```bash
loom model https://huggingface.co/mistralai/Mistral-7B-v0.1
loom model Qwen/Qwen3-235B-A22B   # bare model ID also works
```

Or use the smart unified entrypoint:

```bash
loom generate .                           # project directory -> Source SBOM
loom generate path/to/model.safetensors   # AI model asset   -> Analyzed SBOM
loom generate env                         # installed venv    -> Deployed SBOM
```

#### Enrich an SBOM

Fill AI-model metadata gaps (license, datasets) from a local
`README.md`/`MODEL_CARD.md`'s YAML frontmatter -- off by default, opt in
with `--enrich` on `loom model`/`loom project`/`loom generate`, or run it
standalone to produce a mergeable fragment:

```bash
loom model path/to/model.safetensors --enrich -o model.spdx3.json

# Standalone: writes a fragment, doesn't generate a full SBOM
loom enrich path/to/model.safetensors -o model.enrich.spdx3.json
# When merging into a project-level (not single-model) base SBOM, add:
loom enrich path/to/model.safetensors --project-dir . -o model.enrich.spdx3.json
```

Register the fragment under `[tool.pitloom.fragments]` and re-run
`loom project`/`loom generate` to merge it in. See
[`sbom-enrichment.md`](working-docs/design/sbom-enrichment.md) for the
full surface list (Python API, Hatchling hook, GitHub Action, Skill).

### Hatchling build hook

Pitloom can embed an SBOM automatically into every wheel you build, at
`.dist-info/sboms/<name>-<version>.spdx3.json` by default (e.g.
`.dist-info/sboms/mypackage-1.0.0.spdx3.json`), per
[PEP 770](https://peps.python.org/pep-0770/) (wheels only).

Add `pitloom` as a build requirement (Hatchling **1.28.0+** required) and
register the hook:

```toml
[build-system]
requires = ["hatchling>=1.29.0", "pitloom>=0.13.4"]
build-backend = "hatchling.build"

[tool.hatch.build.hooks.pitloom]
enabled = true    # set to false to skip SBOM generation
```

That's all -- `hatch build`/`python -m build` now embeds the SBOM, always
as compact canonical JSON. Basename and fragments are configured under
`[tool.pitloom]`; creator/tool metadata uses the same
`[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]` /
`[tool.pitloom.creation]` tables the CLI reads (see
[Creation metadata](#creation-metadata) below):

```toml
[tool.pitloom]
sbom-basename = "custom-bom"       # -> "custom-bom.spdx3.json" (default: "<name>-<version>")

[tool.pitloom.fragments]
files = ["fragments/model.json"]   # merge externally tracked fragments
```

### Python API

The SBOM generator can be used programmatically
via the smart `generate()` entry point or target-specific functions:

```python
from pathlib import Path
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.assemble import generate, generate_project_sbom

# Smart auto-detection entrypoint
generate(
    target=Path("/path/to/project"),
    output_path=Path("sbom.spdx3.json"),
    creation_metadata=CreationMetadata(creators=[Creator(name="Your Name")]),
)

# Or target-specific generator
generate_project_sbom(
    project_target=Path("/path/to/project"),
    output_path=Path("sbom.spdx3.json"),
)
```

`pitloom.assemble` also exposes `generate_wheel_sbom()`,
`generate_model_sbom()`, and `generate_env_sbom()`.

### Python tracking decorator

Developers can annotate scripts or Jupyter notebooks to generate external
SBOM fragments that Pitloom will merge during the build process, as a
function decorator or a context manager. Use `set_model` when generating
a new model, and `use_model` when consuming one for inference or evaluation:

```python
from pitloom import loom


@loom.run(output_file="fragments/sentiment_model.json")
def train_model():
    loom.set_model("sentiment-clf")
    loom.add_dataset("imdb-reviews", dataset_type="text")
    # ... training logic ...


@loom.run(output_file="fragments/sentiment_eval.json")
def evaluate_model():
    loom.use_model("sentiment-clf")
    loom.add_dataset("imdb-test-set", dataset_type="text")
    # ... evaluation logic ...
```

See [Python tracking decorator advanced usage](#python-tracking-decorator-advanced-usage)
below for more details.

### Use Pitloom as a GitHub Action

Add SBOM generation to any repository's CI with a single step, for any
Python build backend, not just Hatchling:

```yaml
- uses: bact/pitloom@v0.13.4
```

See [working-docs/implementation/github-action.md](working-docs/implementation/github-action.md)
for inputs, outputs, and more recipes.

### Use Pitloom as an AI-agent skill

`skills/sbom-generate/`, `skills/sbom-enrich/`, and `skills/sbom-validate/`
are ready-to-install [Agent Skills](https://www.anthropic.com/) for
Claude Code and the Claude Agent SDK: `sbom-generate` generates an SBOM
on request; `sbom-enrich` augments an existing one with detail read from
a README or model card (or, interactively, asked directly of the SBOM
author), via Pitloom's fragment system; `sbom-validate` checks any
SPDX 3 document's schema/shape conformance.

```bash
mkdir -p ~/.claude/skills   # or .claude/skills for a project-scoped install
cp -r /path/to/pitloom/skills/sbom-generate \
      /path/to/pitloom/skills/sbom-enrich \
      /path/to/pitloom/skills/sbom-validate ~/.claude/skills/
```

Once installed, either ask in plain language ("generate an SBOM for this
project", "enrich this SBOM with the dataset it was trained on",
"validate this SBOM") or invoke a skill explicitly with
`/sbom-generate [target]` / `/sbom-enrich [sbom-file]` /
`/sbom-validate [sbom-file]`. Generate first, enrich and validate
second -- `sbom-enrich` needs a Pitloom-generated SBOM to already exist:

```text
/sbom-generate .                          # or /sbom-generate models/my-model.safetensors
/sbom-enrich sbom.spdx3.json
/sbom-validate sbom.spdx3.json
```

See [docs/agent-skills.md](docs/agent-skills.md) for a walkthrough of all
three skills, or
[working-docs/implementation/agent-skill.md](working-docs/implementation/agent-skill.md)
for full install instructions.

### Use Pitloom as a Claude Code plugin

The Skills above are also installable as a plugin, self-hosted from this
repository:

```text
/plugin marketplace add bact/pitloom
/plugin install pitloom@pitloom
```

Once installed, all three Skills are namespaced under the plugin:
`/pitloom:sbom-generate [target]`, `/pitloom:sbom-enrich [sbom-file]`,
and `/pitloom:sbom-validate [sbom-file]` (or just ask in plain
language -- natural-language triggering works the same as standalone
Skills). See
[docs/claude-code-plugin.md](docs/claude-code-plugin.md) or
[working-docs/implementation/claude-code-plugin.md](working-docs/implementation/claude-code-plugin.md)
for what the plugin bundles.

## Example

```bash
git clone https://github.com/bact/sentimentdemo.git
loom project sentimentdemo
```

The generated SBOM includes project metadata, dependencies with version
constraints, SPDX relationships, creator/creation info, and per-field
metadata provenance. See a more complete example in the
[examples/](./examples/) directory.

## Detailed features

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
loom project . --creator-name "Alice" --creator-email "alice@example.com"
loom project . --creator-name "Acme Corp" --creator-type organization
loom project . --creator-name "Acme Corp" --creator-type organization --creator-name Alice
loom project . --creation-datetime "2026-01-15T10:00:00Z" --creation-comment "CI run #123"
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

### Loom IDs across fragments (`pitloom ids`)

Fragments are written by independent runs, so the same dataset or model
would normally get a different `spdxId` in each -- leaving the merged SBOM
as disconnected islands. The Loom ID registry (`loom-ids.json`) fixes that:

```console
pitloom ids generate data src --entity model      # pin ids before running
pitloom ids import existing-sbom.spdx3.json       # or reuse ids from an SBOM
```

`pitloom.loom`, `loom model`, the build hook, and `generate()` all
auto-discover the registry (or take it from `[tool.pitloom.ids] file`),
so the same file/entity carries the same id everywhere. Regeneration is
stable: an unchanged file keeps its id; changed content gets a fresh one
(different bytes are different provenance).

At build time `merge_fragments` unifies fragment elements -- by shared
`spdxId`, by identical SHA-256 content, or (for the per-fragment "Pitloom"
`Agent`/`Tool` copies) by structural equality; **never by name alone**.
Fragment envelopes are dropped, duplicate relationships removed, the
document's `profileConformance` gains `ai`/`dataset` as appropriate, and a
second `software_Sbom` rooted at the merged `ai_AIPackage` is added, so the
wheel ships one connected AI-pipeline graph: the packaged training script
`generates` the model, which was `trainedOn` datasets that trace back
via `hasInput` to the raw data.

### Python tracking decorator advanced usage

`loom.run` accepts the same [creation metadata](#creation-metadata) as the
CLI and build hook, via `creation_metadata=CreationMetadata(...)`. With
none given, the fragment records the unattended-run default (Pitloom
itself as both creator and tool).

The run also records *which script produced what*: the calling script
becomes a `software_File` (with a SHA-256 hash) with `generates`
relationships to the model it trained and/or the output datasets it wrote.
Datasets that exist on disk get `verifiedUsing` SHA-256 hashes. These
`generates` edges are scoped `build` (`LifecycleScopedRelationship`) --
they describe a build-time step, not something that runs in the shipped
artifact. Contrast with the `hasDataFile` relationship Pitloom emits when it
detects a script *using* a model file at runtime (e.g. a `predict.py` that
loads it) -- that one is scoped `runtime`.

A single run can cover more than one independent preprocessing stage --
e.g. producing train/valid/test splits from separate raw sources in one
`loom.run` block -- without their `hasInput` lineage bleeding into each
other. Pass `input_datasets=` on `add_output_dataset()` to name exactly
which `add_input_dataset()` calls a given output derives from:

```python
with loom.run("fragments/preprocess.json") as run:
    for split in ("train", "valid", "test"):
        sources = [f"rawdata/{split}/{label}.txt" for label in labels]
        for source in sources:
            run.add_input_dataset(source, dataset_type="text")
        run.add_output_dataset(
            f"data/{split}.txt", dataset_type="text", input_datasets=sources
        )
```

Omit `input_datasets` (the default) when a run has exactly one output
batch -- it then derives from every input the run declared, as before.

## Metadata provenance

Pitloom tracks the source of each metadata field in the SBOM as SPDX 3
Core `Annotation` elements (plus a legacy `comment` form kept for
back-compat), so questions like "why does the SBOM say the concluded
license is MIT?" have a traceable answer. See
[Metadata provenance](docs/metadata-provenance.md) for the full explainer
and a worked example.

## References

- [SPDX 3.0 Specification](https://spdx.dev/wp-content/uploads/sites/31/2024/12/SPDX-3.0.1-1.pdf)
- [PEP 770 – SBOM metadata in Python packages](https://peps.python.org/pep-0770/)
- [Design document](working-docs/design/architecture-overview.md)
- Bennet et al., [“Implementing AI Bill of Materials with SPDX 3.0”](https://www.linuxfoundation.org/research/ai-bom),
  The Linux Foundation, 2024.

## License

- Source code: Apache License 2.0.
- Documentation: Creative Commons Attribution 4.0 International.
- Test fixture AI models: individually licensed (Apache-2.0, CC0-1.0, or
  MIT); see [tests/fixtures/README.md](tests/fixtures/README.md). Source
  repository only -- not included in distribution packages.

## Citation

If you use this software, please cite it as follows:

> Suriyawongkul, A. (2026). Pitloom - SBOM generator for AI models and Python projects (Version 0.13.4) [Computer software]. https://doi.org/10.5281/zenodo.19246283

BibTeX:

```bibtex
@software{Suriyawongkul_Pitloom_-_SBOM_2026,
    author = {Suriyawongkul, Arthit},
    doi = {10.5281/zenodo.19246283},
    month = aug,
    title = {{Pitloom - SBOM generator for AI models and Python projects}},
    url = {https://github.com/bact/pitloom},
    version = {0.13.4},
    year = {2026}
}
```

## Name

A [pit loom](https://en.wikipedia.org/wiki/Loom#Treadle_loom)
is a traditional handloom built into a ground-level pit
to house its internal mechanisms and the weaver's legs.
This "grounded" design provides stability and precision
during the weaving process.

We use the loom as a metaphor for the tool's function:
it weaves disparate threads of metadata into a cohesive SBOM,
creating a transparent, structured "fabric" for the software build.
