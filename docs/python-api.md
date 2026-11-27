---
Created: 2026-08-11
Last-Modified: 2026-11-27
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
  `enrich_model()` to read a local README/model-card's YAML frontmatter
  (licence, datasets) into a mergeable fragment: datasets and their
  `trainedOn` link, with the licence recorded in its enrichment annotation
  -- no code annotation needed, the Python equivalent of `loom enrich`.
- **[Tracking decorator](python-api-tracking.md)** -- annotate a training or
  evaluation script with `@loom.run(...)` to emit a small SPDX fragment
  describing what that run produced, to be merged into the SBOM later.

To embed an SBOM in a built wheel from code, see [Wheel SBOMs: From
Python](wheel-sbom.md#from-python).

See the [API reference](api.md) for exact call signatures, parameter
types, and defaults, generated from the docstrings.

See also: [Python API: remote targets](python-api-remote.md) (Git URL,
PyPI URL and Hugging Face targets) and [Python API: tracking
decorator](python-api-tracking.md) (`loom.run`).

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

A project in a Git repository, or a release on PyPI, is read through its URL
with `generate()` or a target-specific function (`generate_git_sbom()`,
`generate_pypi_sbom()`); a URL can name an AI model too. The options,
the errors and the safety rules are in [Python API: remote
targets](python-api-remote.md).

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

- `max_source_metadata_bytes=` (`generate()`, `generate_project_sbom()`,
  `generate_wheel_sbom()`, `generate_env_sbom()`, `generate_model_sbom()`):
  `--max-source-metadata-bytes`; see [Metadata
  provenance](metadata-provenance.md).
- `scan_model_usage=` (`generate()`, `generate_project_sbom()`,
  `generate_wheel_sbom()`; `ConfigOverrides.scan_model_usage` for
  `embed_wheel_sbom()`, with or without `project_dir=`): `--scan-model-usage`.
  Other targets warn that it has no effect.
- `trust_model_files=True` (`generate()`, `generate_wheel_sbom()`,
  `generate_git_sbom()`, `generate_git_project_sbom()`;
  `ConfigOverrides.trust_model_files` for `embed_wheel_sbom()` without
  `project_dir=`): `--trust-model-files`, for a wheel or Git repository you
  trust only. It has no config key, so a config cannot opt in. Never set it
  from a request a third party can make (a service that takes repository or
  wheel URLs): a hostile model file can crash or hang the process. Other
  targets warn that it has no effect.
- `max_model_extract_bytes=` (`generate()`, `generate_wheel_sbom()`;
  `ConfigOverrides.max_model_extract_bytes` for `embed_wheel_sbom()` without
  `project_dir=`): `--max-model-extract-bytes`, the per-model ceiling of a
  wheel's model scan; it wins over `pitloom_config=`'s
  `max-model-extract-bytes`. Other targets warn that it has no effect; on every
  target a value that is not an integer (`True` and `"5"` included) raises
  `TypeError` and an integer below 1 `ValueError`, both `option-invalid`.
- `max_download_bytes=` (`generate()`, `generate_wheel_sbom()`,
  `generate_project_sbom()`, `generate_pypi_sbom()`, `generate_git_sbom()`,
  `generate_git_project_sbom()`, `generate_model_sbom()`):
  `--max-download-bytes`, the cap on a file downloaded from a PyPI URL, on
  the disk a Git URL's checkout takes, and on each metadata file of a
  Hugging Face model (512 MiB by default); it wins over `pitloom_config=`'s
  `max-download-bytes`. Other targets warn that it has no effect; on every
  target a value that is not an integer (`True` and `"5"` included) raises
  `TypeError` and an integer below 1 `ValueError`, both `option-invalid`.
- `credentials=CredentialPolicy(...)` (every generator function,
  `loom.Run`; `ConfigOverrides.credentials` for `embed_wheel_sbom()`;
  `generate_merged_sbom()`, keyword only, which reads no config):
  `--accept-url-credential` (`accepted=`) and `--refuse-url-credentials`
  (`refuse=True`), added to the config's `accept-url-credentials` and
  `url-credentials` (`PitloomConfig(url_credentials="refuse")`; `refuse=True`
  turns refusal on, never off). By default (the `warn` mode) an SBOM with a URL
  field that holds a credential is written, and one `WARNING:` per value is
  logged, ending with `credentials=CredentialPolicy(refuse=True)`
  (`ConfigOverrides.credentials=CredentialPolicy(refuse=True)` from
  `embed_wheel_sbom()`). In the `refuse` mode it raises `ValueError`
  (`credentials-unsafe/refused`) and nothing is written; the `ERROR:` line of
  each value is logged and ends with the way to accept it
  (`credentials=CredentialPolicy(accepted=["<fingerprint>"])`, or
  `ConfigOverrides.credentials=...` from `embed_wheel_sbom()`);
  see [Credentials in URLs](url-credentials.md#by-surface). A `PitloomConfig`
  or `CredentialPolicy` whose fingerprint or mode is not one raises
  `ValueError` when it is built, not at its first use.
  `IdRegistry.register()` stores a key that holds one with a `WARNING:`, or
  raises for it when the registry was made with `refuse_credentials=True`.
  An `IdRegistry` passed as `id_registry=` takes the run's mode: one loaded
  in the default `warn` mode (an entry that holds a credential said with a
  `WARNING:` at load) and passed to a run that refuses is checked again and
  raises `ValueError` (`credentials-unsafe/registry`) for that entry; one
  made with `refuse_credentials=True` stays in the `refuse` mode in a `warn`
  run.
- `id_registry=`: `--id-registry`; see [Loom ID
  registry](id-registry.md#from-python).
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
`max_model_extract_bytes` in `pitloom_config=` is refused the same way
(`TypeError` or `ValueError`, `option-invalid`).

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
it, these functions fall back to `[[tool.pitloom.creator]]`,
`[[tool.pitloom.creation-tool]]` and `[tool.pitloom.creation]` from whichever
config applies to the target
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
identity. Raises `ValueError` (`option-invalid`) for a Hugging Face Hub
source -- Hugging Face model cards are already parsed natively when
generating the SBOM, so local enrichment doesn't apply there.

`generate_model_sbom()` and `generate()` also take a folder that holds exactly
one model file and no project. A folder with neither raises `ValueError`:
from `generate()` coded `project-or-model-not-found`, from `generate_model_sbom()` coded
`model-wrong-format` (not an AI model file of a supported format). `generate()` reads a file as a model by its header too (a
GGUF file named `x.dat`), not only by suffix. `generate_model_sbom(..., shown=)` names
the model file in messages as the caller knows it (a path in a repository)
when it has been copied elsewhere; the SBOM names it by its own file name.

A local model is read as a project scan reads it: one whose read fails
(truncated, over a bound, a missing extra) does not raise. `enrich_model()`
and `generate_model_sbom()` log the scan's one `WARNING:`, and the model is a
format-only entry. Both raise `ValueError` for a file that is not a model
(empty, an unknown format, a header that contradicts the suffix),
`FileNotFoundError` for an absent one and `OSError` for an unreadable one; see
[AI model scan limits](ai-model-scan-limits.md#which-scans-apply-which-limits).

The refusal of a file that is not a model carries the code
`model-wrong-format`, and of a file that opens like a Git LFS pointer
`lfs-pointer` or `lfs-pointer-malformed` (see [Message
codes](message-codes.md)): the `ValueError` carries the text `loom model`
prints and the attribute `pitloom_code` (`pitloom.messages.code_of(exc)`).
`read_ai_model()` in `pitloom.extract.ai_model.reader` raises the same errors.
A Hugging Face model read without `huggingface_hub` raises an `ImportError`
coded `library-missing`, naming the extra to install
(`library-unusable` when it is installed but fails to import).

## Tracking decorator

Moved to [Python API: tracking decorator](python-api-tracking.md):
`@loom.run(...)` and `loom.Run`, which record what a training or evaluation
run used and produced in a fragment merged into the SBOM later.

## See also

- [Command line](cli.md) -- the same generation targets, from a shell.
- [Python API: remote targets](python-api-remote.md) -- Git URL, PyPI URL
  and Hugging Face targets from code.
- [Python API: tracking decorator](python-api-tracking.md) -- `loom.run`
  fragments from a training or evaluation script.
- [Wheel SBOMs](wheel-sbom.md#from-python) -- embedding an SBOM in a wheel.
- [Loom ID registry](id-registry.md#from-python) and
  [`--allow-build`](allow-build.md#from-python) -- their library arguments.
- [Dependency sources and precedence](dependency-sources.md) -- how
  resolved lock files feed into Source SBOM dependencies.
- [Credentials in URLs](url-credentials.md) -- when an SBOM is warned of or
  refused, and `credentials=`.
- [Hatchling build hook](hatchling-build-hook.md) -- how registered
  fragments get merged automatically at build time.
- [Creation metadata](creation-metadata.md) and [Metadata
  provenance](metadata-provenance.md) -- the record every generated
  element carries.
- [AI model formats](ai-model-formats.md) -- every format
  `generate_model_sbom()` supports.
