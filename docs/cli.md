---
Created: 2026-08-11
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Command line

Use this when you want a one-off SBOM from a terminal, a Makefile target, or
any shell script. The console script is installed as `loom` and `pitloom`;
they run the same tool.

See also: [Command line flags](cli-flags.md) for the shared flags,
[SBOM from a Git URL](git-urls.md) for `loom project <url>` and
`loom model <url>`,
[SBOM from a PyPI URL](pypi-urls.md) for `loom wheel <url>`,
`loom project <url>` and `loom generate <url>` on a PyPI project page,
[Wheel SBOMs and PEP 770 embedding](wheel-sbom.md),
[SBOM fragments](fragments.md) and [Loom ID registry](id-registry.md), which
hold the `embed-wheel`, `verify-wheel`, `validate-wheel`, `merge`, `fragment`
and `id` subcommands.

## Quick guide

```bash
pip install pitloom
loom project .     # SBOM for the Python project in the current dir
```

`loom -h` shows the full option list.

## Installation

```bash
pip install pitloom
pip install "pitloom[ai]"            # AI model metadata extraction
pip install "pitloom[content-type]"  # content type detection (magika)
pip install "pitloom[validate]"      # SPDX 3 schema/SHACL validation (loom fragment validate, loom validate-wheel)
```

## Usage details

### Generate an SBOM

Generate a **Source SBOM** for a Python project (default: the current
directory):

```bash
loom project .
loom project /path/to/project -o sbom.spdx3.json
loom project https://gitlab.com/group/project   # a Git URL: see below
```

A target that is the `http` or `https` URL of a Git repository, or of one of its
web pages (a branch, tag or commit and a folder may be named), is fetched
shallowly into a temporary directory and read as a project; `loom generate` takes
the same URL. `loom project` reads only a project: a folder with AI model files
and no project is refused with a hint to use `loom model <url>` or `loom
generate <url>` ([below](#generate-an-sbom)). The repository is untrusted: its own `[tool.pitloom]` is ignored
(`--config FILE` applies) and its own build-time code is not run. `--offline` is an
error for it. Every redirect or change of the URL is an `INFO:` naming both URLs,
and a URL that is refused or not followed is a `WARNING:` or `ERROR:`. See
[SBOM from a Git URL](git-urls.md) for the URL forms, the platforms checked and
the messages.

> **Limitation:** the per-file inventory (file list and hashes) is
> backend-aware and accurate for Flit-core, PDM-backend, Poetry, Hatchling,
> setuptools and uv_build (uv_build needs [`--allow-build`](allow-build.md)).
> A `pyproject.toml` declaring no `build-backend` is read as setuptools, as
> PEP 517 build frontends build it.
> Other backends (maturin, scikit-build-core, meson-python, ...) fall back to
> a heuristic and log a `WARNING:`.

If a lock file (`pylock.toml`, `uv.lock`, `poetry.lock`, `pdm.lock`,
`Pipfile.lock`, or a fully pinned `requirements.txt`) sits next to
`pyproject.toml` (or `setup.py`, for `Pipfile.lock`/`requirements.txt`), its
resolved transitive dependencies join the dependency list. This is on by
default; `--no-use-lockfile` (or `[tool.pitloom] use-lockfile = false`) falls
back to direct dependencies and environment introspection. See [Dependency
sources and precedence](dependency-sources.md) for which lock file wins and
what counts as "resolved".

Generate an **Analyzed SBOM** from a built wheel (bundled binaries become
phantom dependencies):

```bash
loom wheel path/to/mypackage-1.0.0-py3-none-any.whl -o sbom.spdx3.json
```

Or give the URL of a **PyPI project or release page**: Pitloom downloads the
wheel that fits the running Python and platform, checks its SHA-256 against the
one PyPI declares, and reads it as a local wheel:

```bash
loom wheel https://pypi.org/project/demo/1.0/ -o sbom.spdx3.json    # that release's wheel
loom project https://pypi.org/project/demo/1.0/                     # that release's sdist
loom generate https://pypi.org/project/demo/ -o sbom.spdx3.json     # latest release, wheel
loom wheel https://pypi.org/project/huge/1.0/ --max-download-bytes 2147483648
```

`loom wheel` and `loom generate` read the wheel (an Analyzed SBOM, which
depends on where it is built); `loom project` reads the sdist (a Source SBOM).
No command falls back to the other kind. The file is untrusted: nothing in it
is run, its own `[tool.pitloom]` is ignored (`--config FILE` applies),
`--offline` is an error and `--embed` is refused. See [SBOM from a PyPI
URL](pypi-urls.md).

To embed SBOMs in wheels, check them, or recompute a package hash, see
[Wheel SBOMs and PEP 770 embedding](wheel-sbom.md).

Generate a **Deployed SBOM** of the installed environment graph:

```bash
loom env -o env.spdx3.json
```

Generate an **Analyzed SBOM** for a single AI model file (a Python project
is not needed, and one beside the file is not read; also a folder that holds
exactly one model file). Supported formats: GGUF, ONNX, Safetensors, PyTorch
(`.pt`/`.pth`, PT2 `.pt2`), Keras, HDF5, NumPy, fastText,
CRFsuite; see [AI model formats](ai-model-formats.md) for extensions and
install extras:

```bash
loom model path/to/model.safetensors -o model.spdx3.json
loom model path/to/model.gguf --pretty
loom model path/to/models/      # a folder with one model file
```

A file is read as a model by its content, not only its suffix (a GGUF file
named `x.dat` is GGUF, for `loom model` and `loom generate` alike); a folder
is read non-recursively, by suffix, and holds one model file: several are an
error (`several AI model files`; name one file) and none is a path that is
not a model. See [AI model formats](ai-model-formats.md#how-a-file-is-recognised).

A model file, or a folder holding one, in a **Git repository** is read the same
way from its web address (a `blob`, `raw` or `tree` page, or the repository):

```bash
loom model https://github.com/owner/repo/blob/main/models/m.keras
loom generate https://gitlab.com/group/project/-/tree/main/models -o model.spdx3.json
```

The repository is fetched shallowly into a temporary directory; the SBOM is
written to `-o` or the current directory, never into it. `--offline` is an
error. fastText, GGUF, HDF5, ONNX and PyTorch `.pt`/`.pth` files are listed
with name, format and hash only, with one `INFO:`: their readers open the
file with a C/C++ library (fastText, HDF5, ONNX), parse a pickle (PyTorch) or
run a parsing loop a crafted file can make very slow or very large (GGUF).
Keras, Safetensors (its Rust library, read in full on purpose), NumPy,
CRFsuite and PT2 files are read in full. Clone the repository and run `loom
model <file>` on a file you trust to read the others. The same formats are
gated in a project from a Git URL (`loom project <url>`, or `loom generate` on
a folder with a project): each model file in its build file list is listed by
the same rule, with one `INFO:` per SBOM; `loom project <dir>` on the clone
reads them in full. A Git LFS pointer is an error. See [SBOM from a Git URL](git-urls.md#model-files).

A model whose read fails (truncated, a bound exceeded, a missing extra) is
still written as a format-only entry, with one `WARNING:` and exit 0, as a
project scan lists it. A file that is not a model (empty, an unknown format, a
header contradicting the suffix, or a Git LFS pointer, whose `ERROR:` gives
the `oid`, the stated size and `git lfs pull`), absent or unreadable is an
`ERROR:` and exit 1. See
[AI model scan limits](ai-model-scan-limits.md#which-scans-apply-which-limits).

Or pass a Hugging Face Hub URL or model ID, with no local file (needs `pip
install pitloom[huggingface_hub]`). A huggingface.co or hf.co URL that names
no model (`https://huggingface.co/owner`) is
`URL=<url>: not a valid Hugging Face URL or model ID [hf-url-invalid]`, not a
missing model file, under `loom project` too; white space around a URL or
ID is ignored. `loom project` given a model says
`URL=<url>: a Hugging Face model, not a project; use 'loom model' [target-wrong-format]`:

```bash
loom model https://huggingface.co/mistralai/Mistral-7B-v0.1
loom model Qwen/Qwen3-235B-A22B   # bare model ID also works
```

A Hugging Face **Space** or **dataset** is a Git repository, not a model: give
its URL to `loom project` ([SBOM from a Git URL](git-urls.md)), or to `loom
model` to read a model file it holds.

Or let `generate` detect the target type:

```bash
loom generate . -o sbom.spdx3.json                           # project directory -> Source SBOM
loom generate path/to/model.safetensors -o model.spdx3.json  # AI model asset    -> Analyzed SBOM
loom generate path/to/models/ -o model.spdx3.json            # folder, no project, one model
loom generate env -o env.spdx3.json                          # installed venv    -> Deployed SBOM
```

`generate` requires `-o`/`--output`: it dispatches across several target
types with no single natural default filename, unlike `project`/`wheel`/
`model`/`env`. Pass `-o`, or use the target-specific command; without it,
`-o/--output is required: a detected target has no default file name; ... [option-missing]`.

#### setuptools projects (`setup.py` and `setup.cfg`)

When a directory has both, Pitloom follows setuptools' own precedence (see
[`setupcfg.py`](https://github.com/pypa/setuptools/blob/main/setuptools/config/setupcfg.py)):
a `setup()` keyword is used, and the same `setup.cfg` option only when the
keyword is empty (`""`, `[]`, `{}`, `None`, an `install_requires` of only
comments) or absent. It is decided per option (`author` and `author_email`
apart, `url` and `project_urls` apart), and a list replaces the other, never
joins it. The name is `setup.py`'s literal, else `setup.cfg`'s. Differences
from setuptools:

- `setup.py` is read, never run. A keyword that is not a literal
  (`name=NAME`), is blank (`"  "`) or holds a value Pitloom does not read
  (`url=1`) is ignored with a `WARNING:`, and `setup.cfg`'s is used.
- A `setup.cfg` `file:` directive, and `[tool.setuptools.dynamic]`
  `version = {file = ...}`, read a file only inside the project directory
  and up to 1 MiB; another file is skipped with a `WARNING:`. Requirements
  files follow [Dependency sources](dependency-sources.md#extras-and-the-optional-edge).
- A placeholder licence (`UNKNOWN`, `NOASSERTION`) in `setup()` gives way to
  the licence classifier kept, else to the `license` of `setup.cfg` it
  overrode; setuptools keeps the placeholder. `NONE` is a statement.
- When `setup.py` overrides a different real name, licence, version or
  `python_requires` of `setup.cfg`, Pitloom keeps `setup.py`'s, records the
  other as a conflict annotation and gives one `WARNING:` per field. For the
  licence, a real `license` field in either file beats a classifier, as in the
  built wheel.

Only a directory is read this way; an sdist or wheel carries the metadata
setuptools already merged. With `detail = "full"` provenance, an author or URL
entry built from both files names both, `setup.py` first:
`Source: setup.py, setup.cfg | Field: setup(author=...), metadata.author/author_email`.

### Enrich an SBOM

Fill AI-model metadata gaps (licence, datasets) from a local
`README.md`/`MODEL_CARD.md`'s YAML frontmatter (read up to 1 MiB: [Size and
count caps](ai-model-scan-limits-caps.md#size-and-count-caps)). Off by default: opt
in with `--enrich` on `loom model`/`project`/`generate`, which sets the model's
licence and datasets, or run it standalone to produce a mergeable fragment.
The fragment carries the datasets and their `trainedOn` link; the card's
licence appears only in its enrichment annotation:

```bash
loom model path/to/model.safetensors --enrich -o model.spdx3.json

# Standalone: writes a fragment, not a full SBOM
loom enrich path/to/model.safetensors -o model.enrich.spdx3.json
# When merging into a project-level (not single-model) base SBOM, add:
loom enrich path/to/model.safetensors --project-dir . -o model.enrich.spdx3.json
```

Register the fragment under `[tool.pitloom.fragment]` and re-run `loom
project`/`loom generate` to merge it in. For an AI agent that reads the README
prose, not just its frontmatter, use the `sbom-enrich` skill ([Agent
Skills](agent-skills.md)).

> **Note:** `--project-dir`'s document identity (and every spdxId in the
> resulting SBOM) derives from the resolved file list, so it changes whenever
> that list changes for the same project, e.g. after a Pitloom upgrade that
> changes file discovery for the project's build backend (see the Source SBOM
> limitation above). When merging into a base SBOM from an older Pitloom,
> regenerate the base first, or the fragment's element references will not
> match the base's ids and the merge fails outright.
>
> The same applies to `--use-lockfile`/`--no-use-lockfile`: the identity also
> depends on whether the lock-file cascade ran. `loom enrich --project-dir
> DIR` matches *DIR*'s own `[tool.pitloom] use-lockfile` when no flag is
> given, so pass one only if the base SBOM was generated with an explicit CLI
> override that disagreed with that config.

### Merge, validate and list fragments

`loom merge`, `loom fragment validate` and `loom fragment list`: see [SBOM
fragments](fragments.md).

### Flags of the other subcommands

Moved to [Command line flags](cli-flags.md#flags-of-the-other-subcommands).

### Pin ids across fragments

Independent runs give the same dataset or model different `spdxId`s. Pin ids
ahead of time, or reuse ids from an existing SBOM:

```bash
loom id generate data src --entity model -o loom-id-registry.json
loom id import existing-sbom.spdx3.json -o loom-id-registry.json
```

`id import` roots a new registry at `--project-dir` (default: the current
directory), the directory the SBOM's file names are relative to; run from above
the project without it, a later run of the project finds no file ids. `id
generate` also takes `--namespace IRI`, `-e NAME[:TYPE]` (a file, model
or dataset that exists below `--project-dir` is stored by its path with its
content hash, else by name; a package is `NAME@VERSION`, one release) and
`--max-dataset-hash-bytes BYTES` (the most
bytes read to hash one dataset; default: the project's own
`max-dataset-hash-bytes`, else 4 GiB), and both
commands write only a changed registry. The file is JSON (`version: 4`); a
version 3 or 2 file from an earlier release is an `ERROR:` (exit 1) on every
command, left as it is: delete it and re-run. Format, flags and log lines:
[Loom ID registry](id-registry.md); keys: [keys and content
gates](id-registry-keys.md).

Full reference, including the `--id-registry` precedence and automatic harvest
of new ids (`--update-id-registry`): [Loom ID registry](id-registry.md).

## Useful flags

The shared flags are listed in [Command line flags](cli-flags.md#useful-flags).

### Options with no effect

A subcommand's parent parser offers every shared flag to every target, but not
every target can act on every one: a wheel has no source files to scan a
header from, and a wheel-embedded SBOM is always canonical JSON regardless of
`--pretty`. A flag that does not apply prints one `WARNING:
Options: <target>: <flag> has no effect <reason>` and is dropped, never silently ignored:

| Target | Options that warn |
| --- | --- |
| project directory | `--trust-model-files`, `--max-model-extract-bytes`, `--max-download-bytes`, `--project-dir` |
| remote Git repository | `--max-model-extract-bytes`, `--project-dir` |
| sdist archive | `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-model-files`, `--max-model-extract-bytes`, `--max-download-bytes`, `--use-lockfile` |
| wheel | `--enrich`, `--extract-file-header`, `--content-type`, `--max-download-bytes`, `--use-lockfile` |
| wheel --embed | `--pretty`, `--describe-relationship`, `--enrich`, `--extract-file-header`, `--content-type`, `--max-download-bytes`, `--update-id-registry` |
| wheel at a PyPI URL | `--enrich`, `--extract-file-header`, `--content-type`, `--use-lockfile`, `--project-dir` |
| sdist at a PyPI URL | `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-model-files`, `--max-model-extract-bytes`, `--use-lockfile`, `--project-dir` |
| installed environment | `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-model-files`, `--max-model-extract-bytes`, `--max-download-bytes`, `--use-lockfile`, `--project-dir` |
| local model file | `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-model-files`, `--max-model-extract-bytes`, `--max-download-bytes`, `--content-type-method`, `--offline`, `--use-lockfile`, `--update-id-registry`, `--project-dir` |
| model file at a Git URL | `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--max-model-extract-bytes`, `--content-type-method`, `--use-lockfile`, `--update-id-registry`, `--project-dir` |
| Hugging Face model | `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-model-files`, `--max-model-extract-bytes`, `--content-type-method`, `--use-lockfile`, `--id-registry`, `--update-id-registry`, `--project-dir` |
| enrich --project-dir | `--describe-relationship`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-model-files`, `--max-model-extract-bytes`, `--max-download-bytes`, `--content-type-method`, `--max-source-metadata-bytes`, `--update-id-registry` |
| enrich without --project-dir | `--describe-relationship`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-model-files`, `--max-model-extract-bytes`, `--max-download-bytes`, `--content-type-method`, `--max-source-metadata-bytes`, `--use-lockfile`, `--update-id-registry` |
| embed-wheel --project-dir | `--pretty`, `--describe-relationship`, `--trust-model-files`, `--max-model-extract-bytes`, `--max-download-bytes`, `--update-id-registry` |
| embed-wheel without --project-dir | `--pretty`, `--describe-relationship`, `--enrich`, `--extract-file-header`, `--content-type`, `--max-download-bytes`, `--update-id-registry` |
| Hatchling build hook | `--describe-relationship`, `--update-id-registry` |
| embed-wheel --sbom | `--pretty`, `--describe-relationship`, `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-model-files`, `--max-model-extract-bytes`, `--max-download-bytes`, `--content-type-method`, `--max-source-metadata-bytes`, `--offline`, `--id-registry`, `--update-id-registry`, `--creator-*`, `--config`, `--project-dir` |

Each `--flag` also covers its `--no-flag` form where one exists (e.g.
`--no-enrich`); the warning names both, e.g. `--enrich/--no-enrich`.

The `Hatchling build hook` row is not a command: the hook reads
`[tool.pitloom]`, not flags, so a key set to `true` there is noted with one
`INFO:` (same wording, the flag's spelling) rather than a warning. `false`
agrees with what the hook does and is not noted. `embed-wheel --project-dir`
does the same for a key in the project's `[tool.pitloom]`, except one whose
flag was also given (that flag has its own warning).

The `--describe-relationship` warning on `embed-wheel`/`enrich` is a current
decision, not a permanent one. `--use-lockfile` is offered only by `project`,
`generate` and `enrich`; the rows list it for the targets those commands (or
the library's `use_lockfile=`) can reach without a lock-file cascade.
`--allow-build`/`--no-build-isolation`/`--build-timeout` have their own
no-effect warning: see [Building a project to discover its file
list](allow-build.md).

### Output

Stdout is data only (`--help`/`--version` aside), one `KEY=VALUE` record a
line; counts, hints and `-v` go to stderr as `INFO:`. A written SBOM prints
`PITLOOM_SBOM_OUTPUT_PATH=<path>`; embed prints `WHEEL=<w> SBOM=<arcname>`.
With `-o -` stdout is the SBOM alone (`loom project . -o - | jq .`): no path
line, and the embed record is an `INFO:` line. Others: `verify-wheel`
`WHEEL=<w> STATUS=ok|failed`; `validate-wheel` `WHEEL=<w>
STATUS=valid|skipped|failed`; `fragment validate` `FILE=<f> STATUS=valid`;
`fragment list` one `PATH=<p> ROLE=...` line per fragment ([SBOM
fragments](fragments.md#list-configured-fragments)); `id`
`PITLOOM_ID_REGISTRY_PATH=<path>`. A
value with a non-printable character (tab, NBSP, ZWJ) prints quoted,
ASCII-escaped. A catalogued stderr line ends in a stable `[code]`: see
[Messages and codes](messages.md).

### Default output file names

Without `-o`, an SBOM is written to the current directory:

| Command | File name |
| --- | --- |
| `project` (also a Git or PyPI URL) | `<name>-<version>.spdx3.json`; `<name>.spdx3.json` when the project has no version; `sbom.spdx3.json` when it has no name or the name is not a safe file name (`con`). A character no file name may hold (a path separator, `:`, a control character, whitespace) becomes `_`. `[tool.pitloom] sbom-basename` replaces the base name. |
| `wheel` (also a PyPI URL) | `<wheel file name>.spdx3.json`, e.g. `demo-1.0-py3-none-any.whl.spdx3.json`; with `--embed`, no file unless `-o` is given |
| `model` | `<model file name>.spdx3.json`; for a Hugging Face model, the last segment of its ID plus `.spdx3.json` |
| `enrich` | `<model file name>.enrich.spdx3.json` |
| `env` | `deployed-environment.spdx3.json` |
| `merge` | `merged.spdx3.json` |
| `generate` | none: `-o` is required |

## Debugging

`--debug` is global: unlike the [shared flags](cli-flags.md#useful-flags),
it works before *any* subcommand, including `merge`/`fragment`/`id`:

```bash
loom --debug project .
```

It surfaces `DEBUG:`-level diagnostics on stderr (e.g. why a metadata
extraction step was skipped). Setting the `PITLOOM_DEBUG` environment variable
(`1`/`true`/`yes`/`on`, case-insensitive) has the same effect and also covers
entry points that do not parse this flag: the Hatchling build hook and every
public library-API function (`generate_project_sbom()`, etc.).

`--no-debug` overrides an ambient `PITLOOM_DEBUG=1` back off for this
invocation, useful when it is set globally (a shell profile, CI). Omitting
both flags leaves `PITLOOM_DEBUG` as found. `--no-debug` sets
`PITLOOM_DEBUG=0` in the process environment for the rest of the run, which
looks scoped to one run only because the CLI process then exits. A script
calling the library API repeatedly in one long-lived process should not rely
on `--no-debug`/`apply_debug_override(False)` to reset between calls; see
`apply_debug_override()`'s docstring in `pitloom/logging_config.py`.

Ctrl-C ends any command with one `ERROR: loom <command>: interrupted` line and exit status
130. With `--debug` (or `PITLOOM_DEBUG`) the Python traceback follows, showing
where the command was interrupted: useful for a run that seems stuck.

## Configuration

See [Configuration](configuration.md) for every `[tool.pitloom]` setting;
the creator, creation and provenance flags are in [Command line
flags](cli-flags.md#configuration).

### Creator and creation metadata

Moved to [Command line flags](cli-flags.md#creator-and-creation-metadata).

### Metadata provenance

Moved to [Command line flags](cli-flags.md#metadata-provenance).

## See also

- [Command line flags](cli-flags.md) -- the shared flags, the flags of the
  other subcommands, and the creator and provenance flags.
- [Wheel SBOMs and PEP 770 embedding](wheel-sbom.md) -- `embed-wheel`,
  `verify-wheel`, `validate-wheel`, the package hash.
- [Building a project to discover its file list](allow-build.md) -- the
  `--allow-build`/`--no-build-isolation`/`--build-timeout` reference.
- [Dependency sources and precedence](dependency-sources.md) -- how lock
  files feed Source SBOM dependencies.
- [SBOM fragments](fragments.md) and [Loom ID registry](id-registry.md).
- [Python API](python-api.md) -- the same targets from Python code.
- [Hatchling build hook](hatchling-build-hook.md) and [GitHub
  Action](github-action.md) -- generate SBOMs at build time or in CI.
- [AI model formats](ai-model-formats.md) -- every format `loom model`
  supports, with install extras.
