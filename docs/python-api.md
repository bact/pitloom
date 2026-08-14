---
Created: 2026-08-11
Last-Modified: 2026-08-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Python API

Use this when you're calling Pitloom from Python code you control --
a build script, a notebook, or a training/evaluation pipeline that wants
to record its own provenance as it runs.

Two different needs, two different entry points:

- **[Generator functions](#generator-functions)** -- call `generate()` (or
  a target-specific function) to produce a full SBOM, the same output
  `loom project`/`loom model`/`loom env` produce on the [CLI](cli.md).
- **[Tracking decorator](#tracking-decorator)** -- annotate a training or
  evaluation script with `@loom.run(...)` to emit a small SPDX fragment
  describing what that run produced, to be merged into the SBOM later.

See the [API reference](api.md) for exact call signatures, parameter
types, and defaults, generated from the docstrings.

## Installation

```bash
pip install pitloom
```

Install with AI model metadata extraction support:

```bash
pip install "pitloom[ai]"
```

Install with extra content type detection:

```bash
pip install "pitloom[content-type]"
```

## Generator functions

### Quick guide

```python
from pathlib import Path
from pitloom.assemble import generate

generate(Path("/path/to/project"), output_path=Path("sbom.spdx3.json"))
```

`generate()` always returns the SBOM as a JSON string; pass `output_path`
to also write it to disk.

### Usage details

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
`generate_model_sbom()`, and `generate_env_sbom()` -- the same target
kinds the [CLI](cli.md)'s `loom wheel` / `loom model` / `loom env`
subcommands cover. See [AI model formats](ai-model-formats.md) for what
`generate_model_sbom()` accepts.

### Config

Pass `creation_metadata=CreationMetadata(...)` to name creators, tools, a
timestamp, or a comment on the record -- see [Creation
metadata](creation-metadata.md) for the full field reference. Without it,
these functions fall back to the same `pyproject.toml`
`[[tool.pitloom.creator]]` / `[tool.pitloom.provenance]` settings the CLI
reads.

## Tracking decorator

Annotate scripts or Jupyter notebooks to generate external SBOM fragments
that Pitloom merges during the build process, as a function decorator or
a context manager. Use `set_model` when generating a new model, and
`use_model` when consuming one for inference or evaluation.

### Quick guide

```python
from pitloom import loom


@loom.run(output_file="fragments/train.json")
def train_model():
    loom.set_model("model-name")
    loom.add_dataset("dataset-name", dataset_type="text")
    # ... training logic ...
```

### Usage details

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

- (A) and (C) set the relationship between the code and the model.
- (B) sets the relationship between the code and the dataset.

The run also records *which script produced what*: the calling script
becomes a `software_File` (with a SHA-256 hash) with `generates`
relationships to the model it trained and/or the output datasets it
wrote. Datasets that exist on disk get `verifiedUsing` SHA-256 hashes.
These `generates` edges are scoped `build` -- they describe a build-time
step, not something that runs in the shipped artifact. Contrast with the
`hasDataFile` relationship Pitloom emits when it detects a script *using*
a model file at runtime -- that one is scoped `runtime`.

`loom.run` can also be used as a context manager instead of a decorator,
which lets a single run cover more than one independent output batch
without their lineage bleeding into each other. Pass `input_datasets=` on
`add_output_dataset()` to name exactly which `add_input_dataset()` calls a
given output derives from:

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
batch -- it then derives from every input the run declared.

### Config

Register the fragment file(s) so a later `generate()`/`loom
project`/`loom generate` call merges them into the main SBOM:

```toml
[tool.pitloom.fragment]
files = ["fragments/train.json", "fragments/eval.json"]
```

`loom.run` accepts the same creator/tool/timestamp overrides as the CLI
and build hook, via `creation_metadata=CreationMetadata(...)`. With none
given, the fragment records the unattended-run default (Pitloom itself as
both creator and tool). See [Creation metadata](creation-metadata.md).

## See also

- [Command line](cli.md) -- the same generation targets, from a shell.
- [Hatchling build hook](hatchling-build-hook.md) -- how registered
  fragments get merged automatically at build time.
- [Creation metadata](creation-metadata.md) and [Metadata
  provenance](metadata-provenance.md) -- the record every generated
  element carries.
- [AI model formats](ai-model-formats.md) -- every format
  `generate_model_sbom()` supports.
