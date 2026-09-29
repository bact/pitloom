---
Created: 2026-08-11
Last-Modified: 2026-09-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Command line

Use this when you want a one-off SBOM from a terminal, a Makefile target,
or any shell script. The console script is installed under two names,
`loom` and `pitloom` -- pick whichever reads better; they run the same
tool.

## Quick guide

```bash
pip install pitloom
loom project .     # SBOM for the Python project in the current dir
```

`loom -h` shows the full option list.

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

Install with SPDX 3 schema/SHACL validation support (`loom fragment
validate`, `loom validate-wheel`):

```bash
pip install "pitloom[validate]"
```

## Usage details

### Generate an SBOM

Generate a **Source SBOM** for a Python project in the current directory:

```bash
loom project .
loom project /path/to/project -o sbom.spdx3.json
```

> **Limitation:** the per-file inventory (file list and hashes)
> is backend-aware and accurate for Flit-core, PDM-backend, Poetry,
> Hatchling, setuptools, and uv_build
> (uv_build needs the [`--allow-build` flag](allow-build.md)).
> Other backends (e.g. maturin, scikit-build-core, meson-python)
> fall back to a heuristic and log a `WARNING:`.

If a lock file (`pylock.toml`, `uv.lock`, `poetry.lock`, `pdm.lock`,
`Pipfile.lock`, or a fully pinned `requirements.txt`) is present next
to `pyproject.toml` (or `setup.py`, for `Pipfile.lock`/`requirements.txt`),
its resolved transitive dependencies are added to the Source SBOM's
dependency list too -- see
[Dependency sources and precedence](dependency-sources.md) for which
one wins when more than one is present, and what counts as "resolved"
for each. On by default; pass `--no-use-lockfile` (or set
`[tool.pitloom] use-lockfile = false`) to fall back to direct dependencies
and environment introspection only.

Generate an **Analyzed SBOM** from a pre-built wheel (extracting bundled
binaries as phantom dependencies):

```bash
loom wheel path/to/mypackage-1.0.0-py3-none-any.whl -o sbom.spdx3.json
```

### Embed an SBOM into a wheel (PEP 770)

Generate and embed an SPDX 3 SBOM directly into one or more built `.whl`
files (writing to `.dist-info/sboms/` and updating `.dist-info/RECORD`):

```bash
loom embed-wheel dist/*.whl --project-dir .
```

`--project-dir` rescans the source project so the SBOM can carry project
metadata (dependencies, license, AI models). It is never inferred from
the current directory -- pass it explicitly, even when the shell is
already sitting in the project root, since the current directory may not
be the wheel's own project.

Without `--project-dir` (and without `--sbom`, below), `embed-wheel`
still embeds a standalone-wheel SBOM built from the wheel's own contents
alone -- no project directory scan, so no AI-model enrichment and no
`[tool.pitloom]` beyond an explicit `--config`:

```bash
loom embed-wheel dist/mypackage-1.0.0-py3-none-any.whl
```

With `--project-dir`, the file list and hashes always come from the
wheel itself, so they're accurate regardless of build backend. What can
still be affected by the Source SBOM limitation above is `--content-type`
and `--extract-file-header`, for any backend still on the Hatchling-based
fallback (see above): that per-file enrichment can silently fail to
attach to any file (falls back to no content-type/header data for it,
not a wrong one).

Or inject an existing pre-generated SBOM into built wheels:

```bash
loom embed-wheel dist/*.whl --sbom sbom.spdx3.json
```

`sbom.spdx3.json`'s declared subject name/version (PEP 503/440-normalised)
is cross-checked against the target wheel's own `.dist-info/METADATA`
*before* anything is written: a mismatch is an `ERROR:` that aborts the
embed (exit 1, nothing written); pass `--allow-mismatch` to downgrade it
to a `WARNING:` and embed anyway (useful for CI/automation that wants
best-effort embedding). A Pitloom-generated SBOM (no `--sbom`) is never
checked -- it's built from the same wheel metadata, so it can't diverge.

`--sbom-basename NAME` overrides the embedded file's basename (default:
derived from the wheel's own name/version, `<name>-<version>.spdx3.json`).
`-o`/`--output` names the modified wheel's own output path and is
rejected with an `ERROR:` when more than one wheel is passed -- ambiguous
without a per-wheel naming scheme; omit it to modify each wheel in place.

Check a wheel's embedded SBOM is at the correct PEP 770 location
(`.dist-info/sboms/`), uses its format's recommended extension, and its
declared subject name/version (PEP 503/440-normalised) match the wheel's
own `.dist-info/METADATA`:

```bash
loom verify-wheel dist/*.whl
loom verify-wheel dist/mypackage-1.0.0-py3-none-any.whl --sbom-filename mypackage-1.0.0.spdx3.json
loom verify-wheel dist/*.whl --fail-on-mismatch
```

A missing SBOM is an `ERROR:` (exit 1); a present-but-non-conventional
extension is a `WARNING:` only -- not fatal, still exit 0. Multiple
`sboms/` entries need `--sbom-filename` to pick one, else it's an
`ERROR:`. A name/version mismatch is a `WARNING:` by default (exit 0);
pass `--fail-on-mismatch` to make it an `ERROR:` (exit 1) instead. When
the SBOM's subject name/version can't be extracted at all (unsupported
format, or SPDX3 with an unexpected graph shape), the cross-check is
skipped with a `WARNING:` naming why, regardless of `--fail-on-mismatch`.

Validate a wheel's embedded SBOM content against its format's schema and
SHACL rules (currently SPDX3 JSON-LD only, via the same `spdx3-validate`
library used by [`loom fragment validate`](#validate-fragments) --
needs `pip install "pitloom[validate]"`):

```bash
loom validate-wheel dist/*.whl
```

An embedded file in an unrecognised format prints a `WARNING:` and skips
validation (exit 0) rather than failing -- unsupported isn't the same as
invalid. `embed-wheel` itself takes `--verify`/`--validate` as convenience
flags that run these same checks against the wheel just embedded:

```bash
loom embed-wheel dist/*.whl --project-dir . --verify --validate
```

Embedding and the post-embed check are independent steps -- a `--verify`/
`--validate` failure is reported and affects the exit code, but the
embed itself isn't rolled back.

Or use `--embed` directly on `loom wheel`:

```bash
loom wheel dist/mypackage-1.0.0-py3-none-any.whl --embed
```

It embeds the same kind of SBOM `embed-wheel` does: RFC 8785 canonical
JSON, no relationship descriptions, no registry update -- so `--pretty`,
`--describe-relationship` and `--update-id-registry` warn and have no
effect, and `-o FILE` writes a copy of exactly what was embedded.

Generate a **Deployed SBOM** reflecting the exact installed environment
graph:

```bash
loom env -o env.spdx3.json
```

Generate an **Analyzed SBOM** for a single AI model file, without a Python
project directory. Supported local formats: GGUF, ONNX, Safetensors,
PyTorch (`.pt`/`.pth`), Keras, HDF5, NumPy, fastText -- see [AI model
formats](ai-model-formats.md) for the full extension/install-extra table:

```bash
loom model path/to/model.safetensors -o model.spdx3.json
loom model path/to/model.gguf --pretty
```

Or pass a Hugging Face Hub URL or model ID directly -- no local file
required (needs `pip install pitloom[huggingface_hub]`):

```bash
loom model https://huggingface.co/mistralai/Mistral-7B-v0.1
loom model Qwen/Qwen3-235B-A22B   # bare model ID also works
```

Or use the smart unified entrypoint, which auto-detects the target type:

```bash
loom generate . -o sbom.spdx3.json                           # project directory -> Source SBOM
loom generate path/to/model.safetensors -o model.spdx3.json  # AI model asset    -> Analyzed SBOM
loom generate env -o env.spdx3.json                          # installed venv    -> Deployed SBOM
```

`-o`/`--output` is required for `generate`: unlike `project`/`wheel`/
`model`/`env`, which each know their target type and so have an obvious
default filename, `generate` dispatches across several target types with
no single natural default -- pass `-o` explicitly, or use the
target-specific command for its own default.

### Enrich an SBOM

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

Register the fragment under `[tool.pitloom.fragment]` and re-run
`loom project`/`loom generate` to merge it in.

> **Note:** `--project-dir`'s document identity (and every spdxId in the
> resulting SBOM) is derived from the resolved file list, so it changes
> whenever that file list changes for the same project -- e.g. after a
> Pitloom upgrade that changes file discovery for the project's build
> backend (see the Source SBOM limitation above). If merging into a
> base SBOM generated by an older Pitloom version, regenerate that base
> SBOM first -- otherwise the fragment's element references won't match
> the base document's ids, and the merge fails outright (see below).
>
> The same applies to `--use-lockfile`/`--no-use-lockfile` (see
> [Generate an SBOM](#generate-an-sbom) above): the document identity
> also depends on whether the lock-file cascade ran. `loom enrich
> --project-dir DIR` auto-matches *DIR*'s own `[tool.pitloom] use-lockfile`
> config when no explicit flag is given, so only pass one here if the
> base SBOM's own generation used an explicit CLI-flag override that
> disagreed with that config.

For prose-reading enrichment (an AI agent reading the actual README text,
not just its frontmatter), see the [Agent Skills](agent-skills.md) page
instead -- the `sbom-enrich` skill.

### Merge fragments

```bash
loom merge .spdx3-fragments/ -o combined.spdx3.json
```

Exits non-zero (with an `ERROR:` line, after a `WARNING:` naming each
offending reference) if any element in the merged result references an
id absent from the merge -- most commonly a fragment merged against a
stale base SBOM (see the note above). Regenerate the base SBOM and
re-run the fragment-producing step before merging again.

`merge`, `fragment`, and `id` each take only their own small flag set,
not the common options below -- e.g. `--offline`/`-v`/`--config`/
`--enrich` don't apply to any of them (`id generate`/`id import` do take
`-o`/`--id-registry`, as an alias for their own target-file flag -- not
in the common-options sense described below). `merge`'s own `--pretty`
also defaults to `True` (pretty-printed), the opposite of every other
subcommand's compact default.

### Validate fragments

```bash
loom fragment validate combined.spdx3.json
loom fragment validate base.spdx3.json fragment.spdx3.json  # + merged-graph check
```

Checks JSON Schema and SHACL conformance via
[`spdx3-validate`](https://pypi.org/project/spdx3-validate/)'s library
API (requires the `validate` extra above). Works on any SPDX 3 JSON
document, not just Pitloom's own output. Passing more than one path also
validates the graph formed by merging them, which catches type errors
across `ExternalMap` references -- pass `--no-merge` to skip that and
check each document only in isolation. Non-zero exit reports every
finding to stderr with every line `ERROR:`-tagged -- a SHACL violation's
Severity/Source Shape/Focus Node breakdown spans several `ERROR:` lines,
not just one.

### List configured fragments

```bash
loom fragment list
loom fragment list --project-dir path/to/project
```

Reads `[tool.pitloom.fragment]` from that directory's `pyproject.toml`
(default: cwd) and prints one line per configured fragment:

```text
PATH=fragments/model.spdx3.json ROLE=ai_model REQUIRED=false EXISTS=true ELEMENTS=42 SHA256=match MODIFIED=2026-09-10T12:00:00+00:00
```

`ELEMENTS` is the fragment's `@graph` entry count -- `0` for valid JSON
with no `@graph` key (a real, valid empty fragment), `-` if the file is
missing, unreadable, or not valid JSON at all; `SHA256` is
`-`/`unknown`/`match`/`mismatch` depending on whether a `sha256` is
configured and, if so, whether the file could be checked -- display
only, not yet enforced before merge.
A missing or broken fragment logs the same `WARNING:` wording a real
build would log for it. Exits non-zero only when a `required = true`
fragment is missing, unreadable, or fails to parse as valid SPDX3
JSON-LD -- the same conditions that would also fail an actual build
(see [Merge fragments](#merge-fragments) above); a non-required missing
fragment or a `SHA256` mismatch is informational only.

### Pin ids across fragments

Fragments are written by independent runs, so the same dataset or model
would normally get a different `spdxId` in each run. Pin ids ahead of
time, or reuse ids already present in an SBOM:

```bash
loom id generate data src --entity model -o loom-id-registry.json
loom id import existing-sbom.spdx3.json -o loom-id-registry.json
```

(`-o`/`--id-registry` is required unless the project's own
`pyproject.toml`/`setup.cfg` already declares `id-registry` -- see
below.)

`id generate [PATH...]` flags: `-o`/`--id-registry FILE` (registry file to
create or update), `--project-dir DIR`, `-e`/`--entity NAME[:TYPE]`
(repeatable -- register an explicit entity id ahead of a run; `TYPE`
defaults to `ai_AIPackage`). `id import SBOM_FILE` takes only
`-o`/`--id-registry FILE`.

Target file: `-o`/`--id-registry` if given -- a relative value resolves
against the current directory, like every other command; a relative
`PATH` argument to `generate` does too -- else the project's own
configured `id-registry` key, read the same way every other Pitloom
surface selects `pyproject.toml`'s `[tool.pitloom]` vs. `setup.cfg`'s
`[tool:pitloom]` (`generate`: from `--project-dir`; `import`: from the
current directory). The registry location is required, never assumed:
with neither `-o`/`--id-registry` nor a declared `id-registry` key,
`id generate`/`id import` print one line --
`ERROR: no ID registry declared: pass --id-registry FILE or set
id-registry in [tool.pitloom]` (`[tool:pitloom]` for a
setup.cfg-configured project) -- exit 1, and write nothing. There is no
implicit default registry file; `loom-id-registry.json` is only the
suggested name to declare. Registry keys (and the implicit default
`PATH`s -- `src`/`data`/`models`) stay relative to `--project-dir`
regardless of where `-o`/`PATH` resolve from. A missing target is
created. A target that exists but can't be loaded (not valid JSON,
wrong version, etc.) is one `ERROR:` line and exit 1 -- it is never
silently replaced, and a broken/invalid `pyproject.toml`/`setup.cfg` is
the same one `ERROR:` line, never a traceback (and takes precedence
over the "no registry declared" error above).

Each `generate` `PATH` must resolve inside `--project-dir`; a `PATH`
outside it -- directly, or reached only through a symlink -- is
`ERROR: PATH <p> is outside --project-dir <dir>` and exit 1. `..` is
collapsed lexically before any symlink is followed. A symlink
that itself lives *inside* the project is fine either way, even when it
points somewhere outside (e.g. `data/models -> ../bigdisk/models`):
`generate` indexes it under its in-project location, the same as the
implicit default `PATH`s do.

After a successful write that *created* a new registry file -- never on
a write to one that already existed -- and unless the target is the
project's own declared `id-registry` (whether it came from the config's
own key, or from `-o`/`--id-registry` naming that same file), `id
generate`/`id import` log `INFO: ID registry: to use this registry, add
to [tool.pitloom] in pyproject.toml: id-registry = "<path>"` for a
pyproject.toml-configured project (a `json.dumps`-quoted TOML string). For
a setup.cfg-configured project the line names `[tool:pitloom] in
setup.cfg` instead, and the path is unquoted (`id-registry = <path>`,
no quotes) -- `setup.cfg`'s `[tool:pitloom]` values are read as plain INI
strings, with no quote-stripping, so a quoted value would become part of
the value itself. Either way the line can be pasted verbatim so the next
run can declare it.

`project`/`wheel`/`env` also harvest newly-minted ids back into a
*declared* registry after each run (`--update-id-registry` on by
default, or `--no-update-id-registry`) -- it never creates one. See
[Loom IDs across fragments](https://github.com/bact/pitloom/blob/main/README.md#loom-ids-across-fragments-loom-id)
for what's excluded (`ai_AIPackage`, `dataset_DatasetPackage`) and why.

## Useful flags

Available on `project`/`generate`/`model`/`wheel`/`embed-wheel`/`env`
(not `merge`/`fragment`/`id`, see above), unless noted otherwise:

- `-o FILE` / `--output FILE` -- explicit output path.
- `--config FILE` -- read `[tool.pitloom]` from *FILE* instead of the
  target's own `pyproject.toml`. On a project target (`project`,
  `generate` on a project directory or sdist, `embed-wheel
  --project-dir`), it replaces the project's own config outright, not
  merges with it. On every other target (`wheel`, `env`, `model`,
  `enrich`, `embed-wheel` without `--project-dir`), it is the *only*
  config that target can ever get -- none of these read the current
  directory or the target's own location. A relative path inside *FILE*
  (`id-registry`, a fragment's `path`) resolves against *FILE*'s own
  directory. A missing or invalid *FILE* is an `ERROR:`, except under
  `embed-wheel --sbom`, where it is not read at all and only warns. The
  replaced project config is not parsed, so `--config` also rescues a
  project or sdist whose own `[tool.pitloom]` is invalid. See
  [Where settings come from](configuration.md#where-settings-come-from)
  for the full precedence table.
- `--pretty` -- indent the JSON for human reading (default: compact).
- `--offline` -- forbid network access (PyPI/Hugging Face lookups).
  Not on `enrich` either.
- `--use-lockfile` / `--no-use-lockfile` -- only on `project`/`generate` (not
  `model`/`wheel`/`embed-wheel`/`env`, which never read a lock file) and
  `enrich` (for `--project-dir` document identity matching, see
  [Enrich an SBOM](#enrich-an-sbom)). On by default; see
  [Dependency sources and precedence](dependency-sources.md).
- `-v` / `--verbose` -- on `project`/`generate` with a project directory
  or sdist: print the effective options and where each came from (a
  value from an sdist's own `pyproject.toml` is labelled with the archive
  member, e.g. `demo-1.0.0.tar.gz:pyproject.toml`).
  `wheel`/`env`/`model`/`enrich` print only the version, target and
  output path. `generate` on any other target and `embed-wheel` print
  nothing more and warn that `-v` has no effect.
- `--id-registry FILE` -- declare a Loom ID registry file, taking
  precedence over the target's own `id-registry` config key -- see [Pin
  ids across fragments](#pin-ids-across-fragments). A relative path
  resolves against the current directory on every command. Nothing is
  ever searched for; without this flag or a config key, no registry is
  used. A declared file that's missing, unreadable or invalid is an
  `ERROR:` and exit 1.
- `--describe-relationship` / `--no-describe-relationship` -- include (or
  suppress) human-readable text on SPDX relationships.
- `--content-type` / `--no-content-type` -- detect each file's real
  content type via magika/mimetypes (off by default: real per-file
  cost). `--content-type-method {auto,magika,extension}` picks the
  detector: `auto` tries magika and falls back to an extension guess,
  `magika` errors immediately if the `magika` package isn't installed,
  `extension` skips magika entirely (stdlib-only).

See [Enrich an SBOM](#enrich-an-sbom) above for `--enrich`/`--no-enrich`,
and [Building a project to discover its file list](allow-build.md) for
`--allow-build`/`--no-build-isolation`/`--build-timeout` (only on
`project`/`generate`/`embed-wheel`).

### Options with no effect

A subcommand's parent parser offers every shared flag above to every
target, but not every target can act on every one -- e.g. a wheel has no
source files to scan a header from, and a wheel-embedded SBOM is always
canonical JSON regardless of `--pretty`. Passing one that doesn't apply
prints one `WARNING: Options: <target>: <flag> has no effect <reason>`
and drops it, rather than silently ignoring it:

| Target | Options that warn |
| --- | --- |
| project directory | — |
| sdist archive | `--enrich`, `--extract-file-header`, `--content-type`, `--use-lockfile` |
| wheel | `--enrich`, `--extract-file-header`, `--content-type`, `--use-lockfile` |
| wheel --embed | `--pretty`, `--describe-relationship`, `--enrich`, `--extract-file-header`, `--content-type`, `--update-id-registry` |
| installed environment | `--enrich`, `--extract-file-header`, `--content-type`, `--use-lockfile` |
| local model file | `--extract-file-header`, `--content-type`, `--content-type-method`, `--offline`, `--use-lockfile`, `--update-id-registry` |
| Hugging Face model | `--enrich`, `--extract-file-header`, `--content-type`, `--content-type-method`, `--use-lockfile`, `--id-registry`, `--update-id-registry` |
| enrich --project-dir | `--describe-relationship`, `--extract-file-header`, `--content-type`, `--content-type-method`, `--max-source-metadata-bytes`, `--update-id-registry` |
| enrich without --project-dir | `--describe-relationship`, `--extract-file-header`, `--content-type`, `--content-type-method`, `--max-source-metadata-bytes`, `--use-lockfile`, `--update-id-registry` |
| embed-wheel --project-dir | `--pretty`, `--describe-relationship`, `--update-id-registry` |
| embed-wheel without --project-dir | `--pretty`, `--describe-relationship`, `--enrich`, `--extract-file-header`, `--content-type`, `--update-id-registry` |
| embed-wheel --sbom | `--pretty`, `--describe-relationship`, `--enrich`, `--extract-file-header`, `--content-type`, `--content-type-method`, `--max-source-metadata-bytes`, `--offline`, `--id-registry`, `--update-id-registry`, `--creator-*`, `--config`, `--project-dir` |

Each `--flag` above also covers its `--no-flag` boolean-negation form
where one exists (e.g. `--no-enrich`, `--no-pretty`); the warning names
both spellings, e.g. `--enrich/--no-enrich`.

`--describe-relationship` warning on `embed-wheel`/`enrich` is a current
decision, not a permanent one -- it may change in a future release.
`--use-lockfile` is offered only by `project`, `generate` and `enrich`;
the rows list it for the targets those commands (or the library's
`use_lockfile=`) can reach without a lock-file cascade.
`--allow-build`/`--no-build-isolation`/`--build-timeout` have their own,
separate no-effect warning -- see [Building a project to discover its
file list](allow-build.md).

Every subcommand that writes an SBOM (`project`, `model`, `env`, `wheel`,
`embed-wheel`) prints `PITLOOM_SBOM_OUTPUT_PATH=<path>` to stdout after
writing it -- the resolved path, including when a command's own
default-naming logic picked it rather than an explicit `-o`. Scripts and
CI can parse this line instead of re-deriving the default-naming logic
themselves.

## Building a project to discover its file list (`--allow-build`)

`--allow-build` (with `--no-build-isolation` and `--build-timeout`) opts
`project`/`generate`/`embed-wheel` into invoking the target project's own
PEP 517 build backend to discover its real file list, instead of
Pitloom's default static read -- a security-relevant, off-by-default
decision with no `[tool.pitloom]` config-file equivalent. See [Building a
project to discover its file list](allow-build.md) for the full
security rationale, the flags, `--build-timeout`'s duration grammar, and
signal-handling behaviour (Ctrl-C/SIGTERM/SIGHUP/SIGKILL) during a build.

## Debugging

`--debug` is global -- unlike the flags above, it works before *any*
subcommand, including `merge`/`fragment`/`id`:

```bash
loom --debug project .
```

Surfaces `DEBUG:`-level diagnostics on stderr (e.g. why a metadata
extraction step was skipped) that are otherwise suppressed. Setting the
`PITLOOM_DEBUG` environment variable (`1`/`true`/`yes`/`on`,
case-insensitive) has the same effect and also covers entry points that
don't parse this flag themselves: the Hatchling build hook and every
public library-API function (`generate_project_sbom()`, etc.).

`--no-debug` overrides an ambient `PITLOOM_DEBUG=1` back off for this
invocation -- useful when it's set globally (a shell profile, CI) and a
specific invocation should stay quiet. Omitting `--debug` entirely
(neither flag given) leaves `PITLOOM_DEBUG` as found, ambient or not.
Under the hood, `--no-debug` sets `PITLOOM_DEBUG=0` in the process
environment for the rest of the run; this only looks scoped to "one
run" because the CLI process exits afterward. A script embedding
Pitloom's library API and calling it more than once in one long-lived
process should not rely on `--no-debug`/`apply_debug_override(False)`
to reset itself between calls -- see `apply_debug_override()`'s
docstring in `pitloom/logging_config.py`.

## Configuration

See [Configuration](configuration.md) for the full reference -- every
`[tool.pitloom]` setting, its default, and its CLI/Action/API mapping.
The sections below walk through the two settings with the most nuance.

### Creator and creation metadata

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

[[tool.pitloom.creation-tool]]
name = "MyCompany SBOM Wrapper"

[tool.pitloom.creation]
creation-datetime = "2026-01-15T10:00:00Z"
creation-comment = "Generated in CI pipeline #123"
```

See [Creation metadata](creation-metadata.md) for what these fields record
and why.

### Metadata provenance

Controlled by `[tool.pitloom.provenance]` in `pyproject.toml`:

```toml
[tool.pitloom.provenance]
format = "both"                    # "annotation" | "comment" | "both" (default)
detail = "minimal"                 # "minimal" (default) | "full"
preserve-source-metadata = "auto"  # "auto" (default) | "always" | "never"
max-source-metadata-bytes = 0      # 0 (default, unlimited) | a byte budget
```

`max-source-metadata-bytes` also has a `--max-source-metadata-bytes BYTES`
CLI flag -- an operational override for the byte cap without editing
`pyproject.toml`, unlike every other key above.

See [Metadata provenance](metadata-provenance.md) for what each setting
does and worked examples.

## See also

- [Building a project to discover its file list](allow-build.md) -- the
  full `--allow-build`/`--no-build-isolation`/`--build-timeout` reference.
- [Dependency sources and precedence](dependency-sources.md) -- how
  resolved lock files feed into Source SBOM dependencies.
- [Python API](python-api.md) -- calling Pitloom from Python code instead
  of the shell.
- [Hatchling build hook](hatchling-build-hook.md) -- generate the SBOM
  automatically at build time instead of a manual CLI call.
- [GitHub Action](github-action.md) -- run the CLI as a CI step.
- [AI model formats](ai-model-formats.md) -- every format `loom model`
  supports, with install extras.
