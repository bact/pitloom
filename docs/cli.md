---
Created: 2026-08-11
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Command line

Use this when you want a one-off SBOM from a terminal, a Makefile target, or
any shell script. The console script is installed as `loom` and `pitloom`;
they run the same tool.

See also: [SBOM from a Git URL](git-urls.md) for `loom project <url>`,
[Wheel SBOMs and PEP 770 embedding](wheel-sbom.md),
[SBOM fragments](fragments.md) and [Loom ID registry](id-registry.md), which hold the
`embed-wheel`, `verify-wheel`, `validate-wheel`, `merge`, `fragment` and `id`
subcommands.

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
the same URL. The repository is untrusted: its own `[tool.pitloom]` is ignored
(`--config FILE` applies) and its build backend is never run. `--offline` is an
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

To embed SBOMs in wheels, check them, or recompute a package hash, see
[Wheel SBOMs and PEP 770 embedding](wheel-sbom.md).

Generate a **Deployed SBOM** of the installed environment graph:

```bash
loom env -o env.spdx3.json
```

Generate an **Analyzed SBOM** for a single AI model file, with no Python
project directory. Supported formats: GGUF, ONNX, Safetensors, PyTorch
(`.pt`/`.pth`, PT2/ExecuTorch `.pt2`), Keras, HDF5, NumPy, fastText,
CRFsuite; see [AI model formats](ai-model-formats.md) for extensions and
install extras:

```bash
loom model path/to/model.safetensors -o model.spdx3.json
loom model path/to/model.gguf --pretty
```

A model whose read fails (truncated, a bound exceeded, a missing extra) is
still written as a format-only entry, with one `WARNING:` and exit 0, as a
project scan lists it. A file that is not a model (empty, an unknown format, a
header contradicting the suffix such as a Git LFS pointer), absent or
unreadable is an `ERROR:` and exit 1. See [AI model scan
limits](ai-model-scan-limits.md#which-scans-apply-which-limits).

Or pass a Hugging Face Hub URL or model ID, with no local file (needs `pip
install pitloom[huggingface_hub]`):

```bash
loom model https://huggingface.co/mistralai/Mistral-7B-v0.1
loom model Qwen/Qwen3-235B-A22B   # bare model ID also works
```

A Hugging Face **Space** or **dataset** is a Git repository, not a model: give
its URL to `loom project` ([SBOM from a Git URL](git-urls.md)); `loom model`
refuses it and names `loom project`.

Or let `generate` detect the target type:

```bash
loom generate . -o sbom.spdx3.json                           # project directory -> Source SBOM
loom generate path/to/model.safetensors -o model.spdx3.json  # AI model asset    -> Analyzed SBOM
loom generate env -o env.spdx3.json                          # installed venv    -> Deployed SBOM
```

`generate` requires `-o`/`--output`: it dispatches across several target
types with no single natural default filename, unlike `project`/`wheel`/
`model`/`env`. Pass `-o`, or use the target-specific command.

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
count caps](ai-model-scan-limits.md#size-and-count-caps)). Off by default: opt
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

These take their own flags, besides the shared ones of [Useful
flags](#useful-flags) where noted (`embed-wheel` takes both):

| Command | Flag | Meaning |
| --- | --- | --- |
| `embed-wheel` | `--sbom FILE` | Embed a pre-generated SBOM instead of generating one |
| `embed-wheel` | `--sbom-basename NAME` | Name of the embedded file under `.dist-info/sboms/`, without extension |
| `embed-wheel` | `--allow-mismatch` | With `--sbom`: embed with a `WARNING:` when its name/version differs from the wheel's |
| `embed-wheel` | `--verify` / `--validate` | Run `verify-wheel` / `validate-wheel` on the result; with `--sbom`, `--validate` checks the file first |
| `verify-wheel` | `--sbom-filename NAME` | The exact file expected under `.dist-info/sboms/` |
| `verify-wheel` | `--fail-on-mismatch` | Exit non-zero (not only `WARNING:`) when the SBOM's name/version differs from the wheel's |
| `validate-wheel` | `--sbom-filename NAME` | The exact file expected under `.dist-info/sboms/` |
| `merge` | `-o FILE`, `--pretty` / `--no-pretty` | Output path and indentation |
| `fragment validate` | `--no-merge` | Validate each document alone, skipping the merged-graph check |
| `fragment list` | `--project-dir DIR` | The project whose configured fragments are listed |
| `id generate`, `id import` | see below | [Pin ids across fragments](#pin-ids-across-fragments) |

Details: [Wheel SBOMs and PEP 770 embedding](wheel-sbom.md) and [SBOM
fragments](fragments.md).

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
generate` also takes `--namespace IRI` and `-e NAME[:TYPE]` (a file, model
or dataset that exists below `--project-dir` is stored by its path with its
content hash, else by name), and both
commands write only a changed registry. The file is JSON (`version: 3`); a
version 2 file from an earlier release is an `ERROR:` (exit 1) on every
command: delete it and re-run. Format, flags and log lines:
[Loom ID registry](id-registry.md); keys: [keys and content
gates](id-registry-keys.md).

Full reference, including the `--id-registry` precedence and automatic harvest
of new ids (`--update-id-registry`): [Loom ID registry](id-registry.md).

## Useful flags

Available on `project`/`generate`/`model`/`wheel`/`embed-wheel`/`env` (not
`merge`/`fragment`/`id`, which take only their own flags), unless noted:

- `-o FILE` / `--output FILE` -- explicit output path.
- `--config FILE` -- read `[tool.pitloom]` from *FILE* instead of the
  target's own `pyproject.toml`. On a project target (`project`, `generate` on
  a project directory or sdist, `embed-wheel --project-dir`) it replaces the
  project's own config outright, not merges with it. On every other target
  (`wheel`, `env`, `model`, `enrich`, `embed-wheel` without `--project-dir`)
  it is the *only* config that target can get: none of them read the current
  directory or the target's own location. A relative path inside *FILE*
  (`id-registry`, a fragment's `path`) resolves against *FILE*'s directory. A
  missing or invalid *FILE* is an `ERROR:`, except under `embed-wheel --sbom`,
  where it is not read and only warns. The replaced project config is not
  parsed, so `--config` also rescues a project or sdist whose own
  `[tool.pitloom]` is invalid. See [Where settings come
  from](configuration.md#where-settings-come-from) for the precedence table.
- `--pretty` -- indent the JSON (default: compact). Only whitespace between
  tokens is added; key order and values are the compact (RFC 8785) text's.
- `--offline` / `--no-offline` -- forbid network access (PyPI/Hugging Face
  lookups), or, with `--no-offline`, allow it over a config `offline = true`.
  Not on `enrich` either.
- `--use-lockfile` / `--no-use-lockfile` -- only on `project`/`generate` (the
  other targets never read a lock file) and `enrich` (for `--project-dir`
  document identity matching, see [Enrich an SBOM](#enrich-an-sbom)). On by
  default; see [Dependency sources and precedence](dependency-sources.md).
- `-v` / `--verbose` -- on `project`/`generate` with a project directory or
  sdist: log each effective option on stderr as `INFO: OPTION=<name>
  SOURCE=<source> VALUE=<value>` (an sdist's own `pyproject.toml` source is
  its member, e.g. `demo-1.0.0.tar.gz:pyproject.toml`). `wheel`/`env`/`model`/
  `enrich` log `PITLOOM_VERSION`, the target, `OUTPUT_PATH` (`-`: none) and
  the `PROJECT_DIR` of `enrich` and `wheel`. `generate` on any other target and `embed-wheel`
  warn that `-v` has no effect.
- `--project-dir DIR` -- on `wheel`, and `project`/`generate` with an sdist or
  wheel target: the project directory the archive was built from. With a Loom
  ID registry rooted above the project (a monorepo), the archive's files are
  keyed below DIR's path from the registry's root, as `embed-wheel
  --project-dir` keys them, so they reuse the ids `id generate` or `project`
  recorded. Nothing else is read from DIR. A DIR that is not a directory is an
  `ERROR:`; without a registry, or for a project directory target, it warns
  that it has no effect. See [Monorepo](id-registry-keys.md#monorepo).
- `--id-registry FILE` -- declare a Loom ID registry, taking precedence over the
  target's own `id-registry` key. Nothing is searched for; a declared file
  that is missing, unreadable or invalid is an `ERROR:` and exit 1. See [Loom ID
  registry](id-registry.md).
- `--describe-relationship` / `--no-describe-relationship` -- include (or
  suppress) human-readable text on SPDX relationships.
- `--content-type` / `--no-content-type` -- detect each file's real content
  type via magika/mimetypes (off by default: real per-file cost).
  `--content-type-method {auto,magika,extension}` picks the detector: `auto`
  tries magika, then an extension guess; `magika` errors at once if magika is
  not installed; `extension` skips magika (stdlib-only).
- `--scan-model-usage` / `--no-scan-model-usage` -- on a project directory
  (`project`, `generate <dir>`, `embed-wheel --project-dir`, and the Hatchling
  hook via the `scan-model-usage` key) or a built wheel (`wheel`, `wheel
  --embed`, `embed-wheel` without `--project-dir`), also record which Python
  files reference each discovered AI model file (`hasDataFile`). Off by
  default: it reads every Python file. AI models are found either way. When
  the setting was never given (no flag, no config key), one `INFO:` line says
  how many were found and names the flag (on a wheel also a `--config` file or
  `pitloom_config=`, as no config is read implicitly there), once per
  `embed-wheel` run. Caps and what it misses: [AI model scan
  limits](ai-model-scan-limits.md).
- `--allow-signed-wheel` -- `embed-wheel` and `wheel --embed`: embed into a
  wheel with a `RECORD` signature by removing the signature. See [Signed
  wheels](wheel-sbom.md#signed-wheels). No `[tool.pitloom]` equivalent.
- `--trust-wheel-model` -- on a built wheel (`wheel`, `wheel --embed`,
  `embed-wheel` without `--project-dir`), also read the AI model formats that
  are otherwise listed without metadata in a wheel, because a hostile file can
  crash, hang or exhaust memory in their readers. Use it only for a wheel you
  trust. With `embed-wheel --project-dir` the models are read from the
  project, not the wheel. No config key, so no config file can opt in. Which
  formats, and why: [Formats gated in
  wheels](ai-model-scan-limits.md#formats-gated-in-wheels); see also [Settings
  that change the SBOM](ai-model-scan-limits.md#settings-that-change-the-sbom).

`--enrich`/`--no-enrich`: see [Enrich an SBOM](#enrich-an-sbom).
`--allow-build`/`--no-build-isolation`/`--build-timeout` (only on `project`/
`generate`/`embed-wheel`): see [Building a project to discover its file
list](allow-build.md), an off-by-default, security-relevant opt-in with no
`[tool.pitloom]` equivalent.

### Options with no effect

A subcommand's parent parser offers every shared flag to every target, but not
every target can act on every one: a wheel has no source files to scan a
header from, and a wheel-embedded SBOM is always canonical JSON regardless of
`--pretty`. A flag that does not apply prints one `WARNING:
Options: <target>: <flag> has no effect <reason>` and is dropped, never silently ignored:

| Target | Options that warn |
| --- | --- |
| project directory | `--trust-wheel-model`, `--project-dir` |
| remote Git repository | `--trust-wheel-model`, `--project-dir` |
| sdist archive | `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--use-lockfile` |
| wheel | `--enrich`, `--extract-file-header`, `--content-type`, `--use-lockfile` |
| wheel --embed | `--pretty`, `--describe-relationship`, `--enrich`, `--extract-file-header`, `--content-type`, `--update-id-registry` |
| installed environment | `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--use-lockfile`, `--project-dir` |
| local model file | `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--content-type-method`, `--offline`, `--use-lockfile`, `--update-id-registry`, `--project-dir` |
| Hugging Face model | `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--content-type-method`, `--use-lockfile`, `--id-registry`, `--update-id-registry`, `--project-dir` |
| enrich --project-dir | `--describe-relationship`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--content-type-method`, `--max-source-metadata-bytes`, `--update-id-registry` |
| enrich without --project-dir | `--describe-relationship`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--content-type-method`, `--max-source-metadata-bytes`, `--use-lockfile`, `--update-id-registry` |
| embed-wheel --project-dir | `--pretty`, `--describe-relationship`, `--trust-wheel-model`, `--update-id-registry` |
| embed-wheel without --project-dir | `--pretty`, `--describe-relationship`, `--enrich`, `--extract-file-header`, `--content-type`, `--update-id-registry` |
| Hatchling build hook | `--describe-relationship`, `--update-id-registry` |
| embed-wheel --sbom | `--pretty`, `--describe-relationship`, `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--content-type-method`, `--max-source-metadata-bytes`, `--offline`, `--id-registry`, `--update-id-registry`, `--creator-*`, `--config`, `--project-dir` |

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
line, and the embed record is an `INFO:` line. Others: `verify-`/
`validate-wheel` `WHEEL=<w> STATUS=ok|valid|skipped|failed`; `fragment
validate` `FILE=<f> STATUS=valid`; `id` `PITLOOM_ID_REGISTRY_PATH=<path>`. A
value with a non-printable character (tab, NBSP, ZWJ) prints quoted,
ASCII-escaped.

### Default output file names

Without `-o`, an SBOM is written to the current directory:

| Command | File name |
| --- | --- |
| `project` (also a Git URL) | `<name>-<version>.spdx3.json`; `<name>.spdx3.json` when the project has no version; `sbom.spdx3.json` when it has no name or the name is not a safe file name (`con`). A character no file name may hold (a path separator, `:`, a control character, whitespace) becomes `_`. `[tool.pitloom] sbom-basename` replaces the base name. |
| `wheel` | `<wheel file name>.spdx3.json`, e.g. `demo-1.0-py3-none-any.whl.spdx3.json`; with `--embed`, no file unless `-o` is given |
| `model` | `<model file name>.spdx3.json`; for a Hugging Face model, the last segment of its ID plus `.spdx3.json` |
| `enrich` | `<model file name>.enrich.spdx3.json` |
| `env` | `deployed-environment.spdx3.json` |
| `merge` | `merged.spdx3.json` |
| `generate` | none: `-o` is required |

## Debugging

`--debug` is global: unlike the flags above, it works before *any* subcommand,
including `merge`/`fragment`/`id`:

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

Ctrl-C ends any command with one `ERROR: interrupted` line and exit status
130. With `--debug` (or `PITLOOM_DEBUG`) the Python traceback follows, showing
where the command was interrupted: useful for a run that seems stuck.

## Configuration

See [Configuration](configuration.md) for every `[tool.pitloom]` setting, its
default and its CLI/Action/API mapping. Two settings need more explanation.

### Creator and creation metadata

These flags apply to project, AI model and Hugging Face SBOM generation alike.
`--creator-name` is repeatable: each occurrence starts a new creator, in
order. `--creator-type` (`person` default, `organization`, `software-agent`,
`agent`) and `--creator-email` set the type/email of the *most recently named*
creator. `--creation-tool` records *what* produced the SBOM (default
`"Pitloom"`, repeatable; `--no-creation-tool` omits it).
`--creation-comment`/`--creation-datetime` set free-text provenance and an ISO
8601 timestamp:

```bash
loom project . --creator-name "Alice" --creator-email "alice@example.com"
loom project . --creator-name "Acme Corp" --creator-type organization
loom project . --creator-name "Acme Corp" --creator-type organization --creator-name Alice
loom project . --creator-name "My CI service" --creator-type software-agent
loom project . --creation-datetime "2026-01-15T10:00:00Z" --creation-comment "CI run #123"
```

A `software-agent` creator (a service that runs Pitloom) is the SBOM's author;
it is never the main package's supplier, which stays the first person,
organisation or generic-agent creator, or none.

The same fields can be set in `pyproject.toml`. CLI flags take precedence,
replacing the whole list rather than merging:

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

See [Creation metadata](creation-metadata.md) for what these fields record and
why.

### Metadata provenance

Set by `[tool.pitloom.provenance]` (keys and defaults:
[Configuration](configuration.md#toolpitloomprovenance); what each does:
[Metadata provenance](metadata-provenance.md)). Of its keys, only
`max-source-metadata-bytes` has a flag, `--max-source-metadata-bytes BYTES`,
to change the byte cap for one run.

## See also

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
