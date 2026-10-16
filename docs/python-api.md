---
Created: 2026-08-11
Last-Modified: 2026-10-16
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Python API

Use this when you're calling Pitloom from Python code you control --
a build script, a notebook, or a training/evaluation pipeline that wants
to record its own provenance as it runs.

Three entry points:

- **[Generator functions](#generator-functions)** -- call `generate()` (or
  a target-specific function) to produce a full SBOM, the same output
  `loom project`/`loom model`/`loom env` produce on the [CLI](cli.md).
- **[Standalone enrichment](#standalone-enrichment)** -- call
  `enrich_model()` to fill AI-model metadata gaps (licence, datasets) from
  a local README/model-card's YAML frontmatter, writing a mergeable
  fragment -- no code annotation needed, the Python equivalent of `loom
  enrich`.
- **[Tracking decorator](#tracking-decorator)** -- annotate a training or
  evaluation script with `@loom.run(...)` to emit a small SPDX fragment
  describing what that run produced, to be merged into the SBOM later.

To embed an SBOM in a built wheel from code, see [Wheel SBOMs: From
Python](wheel-sbom.md#from-python).

See the [API reference](api.md) for exact call signatures, parameter
types, and defaults, generated from the docstrings.

## Installation

```bash
pip install pitloom
pip install "pitloom[ai]"            # AI model metadata extraction
pip install "pitloom[content-type]"  # content type detection (magika)
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

When a supported lock file (`pylock.toml`, `uv.lock`, `poetry.lock`,
`pdm.lock`, `Pipfile.lock`, or pinned `requirements.txt`) is present
next to `pyproject.toml`, project generation automatically resolves and
includes its exact transitive dependencies -- see
[Dependency sources and precedence](dependency-sources.md). Pass
`use_lockfile=False` to `generate()`/`generate_project_sbom()` to opt out
(on by default; same as the CLI's `--no-use-lockfile`). Has no effect if
pre-resolved `project_metadata`/`pitloom_config` are BOTH also passed in
-- the cascade decision was already made when that metadata was
produced. Passing `project_metadata` without `pitloom_config` is not
supported: it is discarded and re-read from the target, with a
`WARNING:` explaining why. `pitloom_config` alone is supported -- see
below.

### Explicit config (`pitloom_config=`)

Every generator function (`generate()`, `generate_project_sbom()`,
`generate_wheel_sbom()`, `generate_model_sbom()`, `generate_env_sbom()`,
`enrich_model()`) and `embed_wheel_sbom()` take `pitloom_config=`, the library
equivalent of `--config FILE`: an already-built `PitloomConfig`. It
**replaces** the target's own `[tool.pitloom]` outright: a field left at its
default reverts to the default, not to what the target's config would set. On a
target with no `[tool.pitloom]` of its own (a wheel, an installed environment,
a model file, `enrich_model()` without `project_target=`) it is the *only*
config that call can get: nothing is read from the current directory. See
[Where settings come from](configuration.md#where-settings-come-from).

On `generate_project_sbom()`, `pitloom_config=` *with* `project_metadata=`
skips re-reading the project (the caller asserts the two are consistent);
`pitloom_config=` alone re-reads `project_target`'s metadata with the project's
own `[tool.pitloom]` replaced by the value given. The replaced config is not
parsed, so an invalid one in the project (or inside an sdist) does not fail the
call. An sdist's own config is read as its unpacked directory's is.

Other arguments that mirror a CLI flag or config key:

- `max_source_metadata_bytes=` (`generate()`, `generate_wheel_sbom()`,
  `generate_env_sbom()`, `generate_model_sbom()`): `--max-source-metadata-bytes`;
  see [Metadata provenance](metadata-provenance.md).
- `scan_model_usage=` (`generate()`, `generate_project_sbom()`,
  `generate_wheel_sbom()`; `ConfigOverrides.scan_model_usage` for
  `embed_wheel_sbom()`, with or without `project_dir=`): `--scan-model-usage`.
  Other targets warn that it has no effect.
- `trust_wheel_model=True` (`generate()`, `generate_wheel_sbom()`;
  `ConfigOverrides.trust_wheel_model` for `embed_wheel_sbom()` without
  `project_dir=`): `--trust-wheel-model`, for a wheel you trust only. It has no
  config key, so a config cannot opt in. Other targets warn that it has no
  effect.
- `id_registry=`: `--id-registry`; see [Loom ID registry](id-registry.md#from-python).
- `project_dir=` (`generate_wheel_sbom()`, `generate_project_sbom()` on an
  sdist, `generate()` on either): `--project-dir` of `wheel`/`project`, the
  project directory the archive was built from, so its files are keyed below
  that directory's path from the registry's root (see
  [Monorepo](id-registry-keys.md#monorepo)). A path that is not a directory
  raises `FileNotFoundError`; without a registry, or for any other target, it
  warns that it has no effect.
- `build_options=BuildOptions(...)`: `--allow-build` and its companions, with
  no config-file equivalent; see [`--allow-build`](allow-build.md#from-python).

What `scan_model_usage` records, and which wheel models are listed without
metadata and why: [Configuration](configuration.md) and [AI model scan
limits](ai-model-scan-limits.md#formats-gated-in-wheels). For a wheel, a bad
`max-model-extract-bytes` in `pitloom_config=` raises `ValueError`.

`pitloom.assemble` also exposes `generate_wheel_sbom()` (and
`generate_wheel_sbom_with_metadata()`, which returns `(json, metadata)`: the
SBOM and the `ProjectMetadata` read from the wheel),
`generate_model_sbom()`, and `generate_env_sbom()` -- the same target
kinds the [CLI](cli.md)'s `loom wheel` / `loom model` / `loom env`
subcommands cover. See [AI model formats](ai-model-formats.md) for what
`generate_model_sbom()` accepts. None of the three read a
`[tool.pitloom]` of their own -- not the current directory's, not one
beside the wheel/model file -- either may belong to an unrelated
project; `pitloom_config=` is the only config any of them can get (see
above).

### Config

Pass `creation_metadata=CreationMetadata(...)` to name creators, tools, a
timestamp, or a comment on the record -- see [Creation
metadata](creation-metadata.md) for the full field reference. Without
it, these functions fall back to `[[tool.pitloom.creator]]` /
`[tool.pitloom.provenance]` from whichever config applies to the target
-- the project's own `[tool.pitloom]` for `generate_project_sbom()` and
`embed_wheel_sbom(project_dir=...)`, or an explicit `pitloom_config=`
for every other target (see [Explicit config](#explicit-config-pitloom_config)
above) -- then the built-in default.

## Standalone enrichment

The Python equivalent of `loom enrich`: parses a local
`README.md`/`MODEL_CARD.md`'s YAML frontmatter only (no prose, no
reasoning) and writes a standalone fragment -- fast, free, and always
safe to run before anything else.

```python
from pathlib import Path
from pitloom.assemble import enrich_model

enrich_model(
    Path("path/to/model.safetensors"),
    output_path=Path("model.enrich.spdx3.json"),
)
```

Pass `project_target=` when merging into a project-level (not
single-model) base SBOM -- see the equivalent `--project-dir` note on the
[Command line](cli.md#enrich-an-sbom) page: `--project-dir`'s document
identity is derived from the resolved file list, so it changes whenever
that file list changes for the same project. The same applies to
`use_lockfile=`: it must match whatever produced the base SBOM's
identity, or the fragment references the wrong document -- omit it (the
default, `None`) to auto-match `project_target`'s own
`[tool.pitloom] use-lockfile` config; pass it explicitly only when the
base SBOM's generation used an explicit override that disagreed with
that config.
Pass `id_registry=` (a path, or an already-loaded `IdRegistry`) to reference
a pinned entity id (a relative path resolves against `project_target`
when it is a directory, else against the current directory) instead of
one freshly computed from the model's own
identity. Raises `ValueError` for a Hugging Face Hub source -- Hugging
Face model cards are already parsed natively when generating the SBOM,
so local enrichment doesn't apply there.

A local model is read as a project scan reads it: one whose read fails
(truncated, over a bound, a missing extra) does not raise. `enrich_model()`
and `generate_model_sbom()` log the scan's one `WARNING:`, and the model is a
format-only entry. Both raise `ValueError` for a file that is not a model
(empty, an unknown format, a header that contradicts the suffix),
`FileNotFoundError` for an absent one and `OSError` for an unreadable one; see [AI model scan
limits](ai-model-scan-limits.md#which-scans-apply-which-limits).

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

Pass `path=` (the model file, relative to the current directory at the call)
to `set_model()` or `use_model()` to give the model a SHA-256
(`verifiedUsing`). The file is hashed when the run ends without an
exception, so write it before the block exits. With a [Loom ID
registry](id-registry.md), the hash gates the lookup: a training and an
evaluation script declaring the same model name and file share one id, and a
retrained file gets a new one. The model is keyed by that file's path from the
registry's project root, the same key `loom model` and `id generate` use.
When a project build merges the run's fragment, the model file's `ai_AIPackage`
takes the name given to `set_model()`/`use_model()`, with one `INFO: Merge:
'name' on ...`; its id and registry key do not change. Runs naming one file two
ways keep the project's name, with a `WARNING:` (see
[SBOM fragments](fragments.md#merge-fragments)).
Without `path=` (one `WARNING:` when a registry is loaded), or when it is not
a file when the run ends (one `WARNING:`), the model is matched by name only
and gets no hash. The match hits an id held with no hash (a model with no
file) and never one recorded with a SHA-256, which no content vouches for: a
retrained model's id is not reused by a bare name. In the context-manager form,
`run.model` is `None` until the block exits.
A `path=` that cannot be read (a NUL in it included) gets the usual
unreadable-model `WARNING:`. Leaving a block, by an exception too, restores
the enclosing run, so a recursive `@loom.run` call is safe.

The run also records *which script produced what*: the calling script
becomes a `software_File` (with a SHA-256 hash) with `generates`
relationships to the model it trained and/or the output datasets it
wrote. A dataset that is a file gets a SHA-256 hash and a `software_File`
it `contains`; a directory gets a SHA-256 Merkle root over its files' paths
and content, its `comment` saying so, and no file elements. Below a dataset
directory, the [directories `id generate` skips](id-registry.md#directories-that-are-skipped)
and symbolic links to directories are left out of the root, as is the
declared registry file. A missing or remote dataset name gets no hash.
Hashing one dataset reads at most `max-dataset-hash-bytes` (4 GiB by
default); over it, the dataset gets no hash and one `WARNING:`.
A dataset is hashed when it is declared, an output dataset too: call
`add_output_dataset()` after the step has written the file, or it carries the
hash of the file it replaces. One name holding one content is one package per
run: declaring it again (as input and output, or twice) adds its roles to the
same package, with no collision warning.
These `generates` edges are scoped `build` -- they describe a build-time
step, not something that runs in the shipped artefact. Contrast with the
`hasDataFile` relationship Pitloom emits when it detects a script *using*
a model file at runtime -- that one is scoped `runtime`. Static detection of
such scripts needs `scan_model_usage` (off by default); a `loom.run` that
declares `use_model` emits it regardless.

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
`input_datasets=` matches the string an input was declared with, not its
resolved path: an input declared as `../data/t.txt` is not found by
`data/t.txt` (one `WARNING:`, that link skipped), even though a registry keys
both to one package.

### Config

Register the fragment file(s) so a later `generate()`/`loom
project`/`loom generate` call merges them into the main SBOM:

```toml
[tool.pitloom.fragment]
files = ["fragments/train.json", "fragments/eval.json"]
```

`loom.run`/`loom.Run` calls `configure_logging()` as it begins, so its
`WARNING:` and `INFO:` lines carry their tag as on the CLI. Each run resets
the `pitloom` logger's level (`INFO`, or `DEBUG` with `PITLOOM_DEBUG`) and
replaces its handlers with one stderr handler; propagation to the root
logger is left alone, so an application's own root handler also prints them.

`loom.run` accepts the same creator/tool/timestamp overrides as the CLI
and build hook, via `creation_metadata=CreationMetadata(...)`. With none
given, the fragment records the unattended-run default (Pitloom itself as
both creator and tool). See [Creation metadata](creation-metadata.md).

Pass `id_registry=` (a path, or an already-loaded `IdRegistry`) to
consult a Loom ID registry when minting ids for datasets, the model, and
the generating script -- see [Loom ID registry](id-registry.md). A dataset
package whose path exists below the registry's project root is looked up by
that path, as the same package from any directory or spelling
(`../data/t.txt` from a subdirectory is `data/t.txt`), and by its content
digest when the entry records one; a remote, missing or outside-the-root
dataset by its name. A file (a dataset's, or the script) is looked up by its
path from the registry's project root and its hash, so it keeps its id from
any directory (a path outside the root gets a new id and a `WARNING:`). A file
reached through a symlinked directory is keyed by the path as written, which
`id generate` does not index, so it finds no entry. See [keys and content
gates](id-registry-keys.md). The one entry loom
writes is a model declared with `path=` (hashed when the run ends) whose file
the registry does not know, saved after the fragment;
`update-id-registry = false` in `pitloom_config` stops it.
As on every other surface, `loom.run`/`loom.Run` uses a registry only when
one is declared (`id_registry=`, or `id-registry` in `pitloom_config=`
below): with none, no registry is used -- nothing is searched for or
auto-discovered. A declared registry that's missing, unreadable or invalid
(a format version 2 file included) raises `ValueError` when the `with
loom.run(...)` block (or the decorated call) begins, before any fragment
work happens.

`loom.run` reads no `[tool.pitloom]` of its own. Pass `pitloom_config=` (a
`PitloomConfig`, or the path of a TOML file holding `[tool.pitloom]`,
relative to the current directory) to set `id-registry`,
`update-id-registry` or `max-dataset-hash-bytes`; no other key has an
effect there.
`id_registry=` wins over the config's `id-registry`. A config file that is
missing, unreadable or invalid raises `ValueError` as the run begins.

The merge itself (`pitloom.assemble.merge_fragments`, run by
`generate()`/`generate_project_sbom()` whenever `[tool.pitloom.fragment]`
lists files) raises `pitloom.assemble.FragmentMergeError` if an element
of the merged graph references an id that resolves to nothing -- most
commonly a fragment recorded against a base SBOM whose ids have since
changed: regenerate the base SBOM and re-run the fragment-producing
script. `generate_merged_sbom(fragments_dir)` merges a directory of
fragments into one document, as `loom merge` does. See [SBOM
fragments](fragments.md) and [API reference](api.md#fragment-merging).

## See also

- [Command line](cli.md) -- the same generation targets, from a shell.
- [Wheel SBOMs](wheel-sbom.md#from-python) -- embedding an SBOM in a wheel.
- [Loom ID registry](id-registry.md#from-python) and [`--allow-build`](allow-build.md#from-python) -- their library arguments.
- [Dependency sources and precedence](dependency-sources.md) -- how
  resolved lock files feed into Source SBOM dependencies.
- [Hatchling build hook](hatchling-build-hook.md) -- how registered
  fragments get merged automatically at build time.
- [Creation metadata](creation-metadata.md) and [Metadata
  provenance](metadata-provenance.md) -- the record every generated
  element carries.
- [AI model formats](ai-model-formats.md) -- every format
  `generate_model_sbom()` supports.
