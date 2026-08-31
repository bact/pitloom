---
Created: 2026-08-11
Last-Modified: 2026-08-31
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

## Usage details

### Generate an SBOM

Generate a **Source SBOM** for a Python project in the current directory:

```bash
loom project .
loom project /path/to/project -o sbom.spdx3.json
```

> **Limitation:** the per-file inventory (which files are listed, their
> hashes, and the package's Merkle-root integrity hash) is discovered
> using each build backend's own file-inclusion rules where supported.
> Hatchling, setuptools (including `[tool.setuptools.packages.find]
> where=`, `package_data`, and `include_package_data`/`MANIFEST.in`), and
> Poetry (including `[tool.poetry.packages]`'s `include`/`from`, and
> `[tool.poetry]`'s own `include`/`exclude`) are all accurate. For a PDM
> or Flit project, or any other backend using its own inclusion rules
> Pitloom doesn't yet understand, the discovery falls back to a
> Hatchling-based heuristic and logs a warning -- the file list can be
> silently incomplete or mis-pathed for those. Project-level metadata
> (name, version, dependencies, license, authors) is unaffected -- it's
> read independently and isn't subject to this limitation. Backend-aware
> support for the remaining backends is tracked as a near-term roadmap
> priority.
>
> For a Poetry project with a `poetry.lock` next to `pyproject.toml`,
> the Source SBOM's dependency list also includes the lock's resolved
> `main`-group transitive dependencies, in addition to the direct
> `[tool.poetry.dependencies]` constraints.

Generate an **Analyzed SBOM** from a pre-built wheel (extracting bundled
binaries as phantom dependencies):

```bash
loom wheel path/to/mypackage-1.0.0-py3-none-any.whl -o sbom.spdx3.json
```

### Embed an SBOM into a wheel (PEP 770)

Generate and embed an SPDX 3 SBOM directly into one or more built `.whl`
files (writing to `.dist-info/sboms/` and updating `.dist-info/RECORD`):

```bash
loom embed-wheel dist/mypackage-1.0.0-py3-none-any.whl
loom embed-wheel dist/*.whl --project-dir .
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

`--sbom-basename NAME` overrides the embedded file's basename (default:
derived from the wheel's own name/version, `<name>-<version>.spdx3.json`).
`-o`/`--output` names the modified wheel's own output path and is
rejected with an `ERROR:` when more than one wheel is passed -- ambiguous
without a per-wheel naming scheme; omit it to modify each wheel in place.

Or use `--embed` directly on `loom wheel`:

```bash
loom wheel dist/mypackage-1.0.0-py3-none-any.whl --embed
```

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

`merge` and `ids` each take only their own small flag set, not the
common options below -- e.g. `--offline`/`-v`/`--registry`/`--enrich`
don't apply to either. `merge`'s own `--pretty` also defaults to `True`
(pretty-printed), the opposite of every other subcommand's compact
default.

### Pin ids across fragments

Fragments are written by independent runs, so the same dataset or model
would normally get a different `spdxId` in each run. Pin ids ahead of
time, or reuse ids already present in an SBOM:

```bash
pitloom ids generate data src --entity model      # pin ids before running
pitloom ids import existing-sbom.spdx3.json       # or reuse ids from an SBOM
```

`ids generate [PATH...]` flags: `-o`/`--registry FILE` (registry file to
update, default `.pitloom-ids.json` under `--project-dir`), `--project-dir
DIR`, `-e`/`--entity NAME[:TYPE]` (repeatable -- register an explicit
entity id ahead of a run; `TYPE` defaults to `ai_AIPackage`). `ids import
SBOM_FILE` takes only `-o`/`--registry FILE`.

`project`/`wheel`/`env` also auto-harvest newly-minted ids back into the
resolved registry after each run (`--update-registry`/`--no-update-registry`,
on by default) -- see
[Loom IDs across fragments](https://github.com/bact/pitloom/blob/main/README.md#loom-ids-across-fragments-pitloom-ids)
for what's excluded (`ai_AIPackage`, `dataset_DatasetPackage`) and why.

## Useful flags

Available on `project`/`generate`/`model`/`wheel`/`embed-wheel`/`env`
(not `merge`/`ids`, see above), unless noted otherwise:

- `-o FILE` / `--output FILE` -- explicit output path.
- `--pretty` -- indent the JSON for human reading (default: compact).
- `--offline` -- forbid network access (PyPI/Hugging Face lookups).
  Not on `enrich` either.
- `-v` / `--verbose` -- print effective options and where each came from.
- `--registry FILE` -- Loom ID registry file path, overriding the
  auto-resolved default -- see [Pin ids across
  fragments](#pin-ids-across-fragments).
- `--describe-relationship` / `--no-describe-relationship` -- include (or
  suppress) human-readable text on SPDX relationships.
- `--content-type` / `--no-content-type` -- detect each file's real
  content type via magika/mimetypes (off by default: real per-file
  cost). `--content-type-method {auto,magika,extension}` picks the
  detector: `auto` tries magika and falls back to an extension guess,
  `magika` errors immediately if the `magika` package isn't installed,
  `extension` skips magika entirely (stdlib-only).

See [Enrich an SBOM](#enrich-an-sbom) above for `--enrich`/`--no-enrich`.

Every subcommand that writes an SBOM (`project`, `model`, `env`, `wheel`,
`embed-wheel`) prints `PITLOOM_SBOM_OUTPUT_PATH=<path>` to stdout after
writing it -- the resolved path, including when a command's own
default-naming logic picked it rather than an explicit `-o`. Scripts and
CI can parse this line instead of re-deriving the default-naming logic
themselves.

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

- [Python API](python-api.md) -- calling Pitloom from Python code instead
  of the shell.
- [Hatchling build hook](hatchling-build-hook.md) -- generate the SBOM
  automatically at build time instead of a manual CLI call.
- [GitHub Action](github-action.md) -- run the CLI as a CI step.
- [AI model formats](ai-model-formats.md) -- every format `loom model`
  supports, with install extras.
