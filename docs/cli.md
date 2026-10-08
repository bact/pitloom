---
Created: 2026-08-11
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Command line

Use this when you want a one-off SBOM from a terminal, a Makefile target, or
any shell script. The console script is installed as `loom` and `pitloom`;
they run the same tool.

See also: [Wheel SBOMs and PEP 770 embedding](wheel-sbom.md),
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
```

> **Limitation:** the per-file inventory (file list and hashes) is
> backend-aware and accurate for Flit-core, PDM-backend, Poetry, Hatchling,
> setuptools and uv_build (uv_build needs [`--allow-build`](allow-build.md)).
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
  (`url=1`) is ignored with a `WARNING:`, and `setup.cfg`'s is used. A
  `setup.cfg` `file:` directive in `install_requires` is not read.
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
`README.md`/`MODEL_CARD.md`'s YAML frontmatter. Off by default: opt in with
`--enrich` on `loom model`/`project`/`generate`, or run it standalone to
produce a mergeable fragment:

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

### Pin ids across fragments

Independent runs give the same dataset or model different `spdxId`s. Pin ids
ahead of time, or reuse ids from an existing SBOM:

```bash
loom id generate data src --entity model -o loom-id-registry.json
loom id import existing-sbom.spdx3.json -o loom-id-registry.json
```

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
- `--pretty` -- indent the JSON (default: compact).
- `--offline` -- forbid network access (PyPI/Hugging Face lookups). Not on
  `enrich` either.
- `--use-lockfile` / `--no-use-lockfile` -- only on `project`/`generate` (the
  other targets never read a lock file) and `enrich` (for `--project-dir`
  document identity matching, see [Enrich an SBOM](#enrich-an-sbom)). On by
  default; see [Dependency sources and precedence](dependency-sources.md).
- `-v` / `--verbose` -- on `project`/`generate` with a project directory or
  sdist: log each effective option on stderr as `INFO: OPTION=<name>
  SOURCE=<source> VALUE=<value>` (an sdist's own `pyproject.toml` source is
  its member, e.g. `demo-1.0.0.tar.gz:pyproject.toml`). `wheel`/`env`/`model`/
  `enrich` log `PITLOOM_VERSION`, the target, `OUTPUT_PATH` (`-`: none) and
  `enrich`'s `PROJECT_DIR`. `generate` on any other target and `embed-wheel`
  warn that `-v` has no effect.
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
`--pretty`. A flag that does not apply prints one `WARNING: Options: <target>:
<flag> has no effect <reason>` and is dropped, never silently ignored:

| Target | Options that warn |
| --- | --- |
| project directory | `--trust-wheel-model` |
| sdist archive | `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--use-lockfile` |
| wheel | `--enrich`, `--extract-file-header`, `--content-type`, `--use-lockfile` |
| wheel --embed | `--pretty`, `--describe-relationship`, `--enrich`, `--extract-file-header`, `--content-type`, `--update-id-registry` |
| installed environment | `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--use-lockfile` |
| local model file | `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--content-type-method`, `--offline`, `--use-lockfile`, `--update-id-registry` |
| Hugging Face model | `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--content-type-method`, `--use-lockfile`, `--id-registry`, `--update-id-registry` |
| enrich --project-dir | `--describe-relationship`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--content-type-method`, `--max-source-metadata-bytes`, `--update-id-registry` |
| enrich without --project-dir | `--describe-relationship`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--content-type-method`, `--max-source-metadata-bytes`, `--use-lockfile`, `--update-id-registry` |
| embed-wheel --project-dir | `--pretty`, `--describe-relationship`, `--trust-wheel-model`, `--update-id-registry` |
| embed-wheel without --project-dir | `--pretty`, `--describe-relationship`, `--enrich`, `--extract-file-header`, `--content-type`, `--update-id-registry` |
| embed-wheel --sbom | `--pretty`, `--describe-relationship`, `--enrich`, `--extract-file-header`, `--content-type`, `--scan-model-usage`, `--trust-wheel-model`, `--content-type-method`, `--max-source-metadata-bytes`, `--offline`, `--id-registry`, `--update-id-registry`, `--creator-*`, `--config`, `--project-dir` |

Each `--flag` also covers its `--no-flag` form where one exists (e.g.
`--no-enrich`); the warning names both, e.g. `--enrich/--no-enrich`.

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
loom project . --creation-datetime "2026-01-15T10:00:00Z" --creation-comment "CI run #123"
```

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
