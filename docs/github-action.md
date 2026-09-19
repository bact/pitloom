---
Created: 2026-08-11
Last-Modified: 2026-09-19
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# GitHub Action

Use this when your project isn't Hatchling-based, or you just want CI to
produce an SBOM artifact or embed PEP 770 SBOMs into built wheels, for any
Python build backend.

The action can create a standalone SBOM file on the runner, or embed the
generated SBOM directly into built `.whl` files via `embed-wheel: "dist/*.whl"`.

## Quick guide

Standalone SBOM artifact:

```yaml
- uses: actions/setup-python@v7
  with:
    python-version: "3.x"
- uses: bact/pitloom@v0.19.0
```

Set up Python first: the action uses the Python on `PATH`. See
[Python selection](#python-selection).

Generate and embed PEP 770 SBOM into built wheels:

```yaml
- uses: bact/pitloom@v0.19.0
  with:
    embed-wheel: "dist/*.whl"
```

## Installation

Nothing to install locally -- reference the action from a workflow step:

```yaml
jobs:
  sbom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.x"
      - uses: bact/pitloom@v0.19.0
```

Pin a release tag (`@v0.19.0`) or a full commit SHA (`@<sha> # v0.19.0`),
not a branch. The pin also selects the Pitloom version: see
[What the pin covers](#what-the-pin-covers).

## What the pin covers

- **Pitloom version:** with `pitloom-version` empty, the action installs the
  version carried by the pinned ref (tag or SHA) from PyPI. `@v0.19.0` and that
  tag's commit SHA both give 0.19.0. It fails if the version is not on PyPI: an
  unreleased commit, a branch between a version bump and its release, or a tag
  pushed before the upload finishes.
- **`pitloom-version`** overrides it: a version (`0.19.0`) or a specifier
  (`>=0.19,<1.0`).
- Pitloom's own dependencies are resolved by pip at run time, not pinned.

## Python selection

With `python-version` empty, the action uses the `python` on `PATH` and
installs Pitloom into it. To keep Pitloom apart from your project's packages,
run the action in its own job.

If that Python is missing, older than 3.10, externally managed (PEP 668), or
otherwise cannot install packages, the action warns and installs Python 3.x
with `setup-python`, which changes `PATH` for later steps.

Set `python-version` to always run `setup-python` with that version.

## Usage details

By default the action scans the checkout root as a Python project and
writes `<name>-<version>.spdx3.json` (falling back to `<name>.spdx3.json`,
then `sbom.spdx3.json` as a last resort, unless the project's
`[tool.pitloom] sbom-basename` overrides it -- the same default-naming
logic `loom project` uses directly). Point it at an AI model instead of a
project directory with `model:`:

```yaml
- uses: bact/pitloom@v0.19.0
  with:
    model: path/to/model.safetensors
```

Embed the SBOM into built wheels (PEP 770) for any build backend
(`flit`, `setuptools`, `poetry-core`, `maturin`, etc.):

```yaml
- uses: bact/pitloom@v0.19.0
  with:
    embed-wheel: "dist/*.whl"
```

Pass extra raw CLI flags through with `args:` (shell-quoted, e.g. for
[creator/creation metadata](creation-metadata.md)):

```yaml
- uses: bact/pitloom@v0.19.0
  with:
    args: '--creator-name "CI Bot" --creator-type software-agent'
```

### Annotations

`loom`'s `INFO:`/`WARNING:`/`ERROR:` stderr lines (see
[Command line](cli.md)'s output convention) are re-emitted as native
GitHub Actions annotations -- `::notice::`/`::warning::`/`::error::` --
so they show up in the PR "Checks" tab and job summary, not just buried
in the raw log. A failing `loom` invocation still fails the step/job
(its `ERROR:` line is annotated first); this doesn't change the action's
exit behaviour.

## Persisting the Loom ID registry in CI

`loom project`/`wheel`/`env` (and this Action, which wraps them) harvest
newly-minted ids back into the resolved [Loom ID registry](https://github.com/bact/pitloom/blob/main/README.md#loom-ids-across-fragments-pitloom-ids)
(`loom-ids.json`) by default -- see `update-registry` in
[Configuration](configuration.md). That write only ever touches the
runner's local checkout; it never needs elevated permissions itself
(that's a `git push`, which Pitloom never does). But the write is
ephemeral unless a workflow step commits it back, so a release/publish
job that intentionally runs with `permissions: contents: read` (common
for trusted PyPI publishing -- see this repo's own
[`pypi-publish.yml`](https://github.com/bact/pitloom/blob/main/.github/workflows/pypi-publish.yml))
can update `loom-ids.json` locally but shouldn't have its permissions
relaxed just to push that one file.

Instead, run registry maintenance in a separate, appropriately-scoped
workflow -- the same shape this repo already uses to commit a generated
`CITATION.cff` back to the repo
([`codemeta2cff.yml`](https://github.com/bact/pitloom/blob/main/.github/workflows/codemeta2cff.yml)):

```yaml
name: Update Loom ID registry

on:
  push:
    branches: [main]
    paths:
      - "src/**"
      - "data/**"
      - "models/**"

permissions: read-all

concurrency:
  group: update-loom-ids-${{ github.ref }}
  cancel-in-progress: false

jobs:
  update-registry:
    runs-on: ubuntu-latest
    permissions:
      contents: write  # EndBug/add-and-commit needs write to push loom-ids.json
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.x"
      # Same release as the action below, which installs its own pinned version.
      - run: pip install pitloom==0.19.0

      # Extras-free, stem-keyed -- the only path that keeps ai_AIPackage
      # spdxIds stable regardless of whether "ai" extras are installed
      # (auto-harvest excludes AI packages -- see below). Omit this step
      # if the project has no AI model files.
      - name: Seed/refresh AI model registry entries
        run: loom ids generate

      - uses: bact/pitloom@v0.19.0
        with:
          project-path: .
          # Optional: richer ai_AIPackage metadata (architecture,
          # hyperparameters, etc.) -- NOT what keeps spdxIds stable, that's
          # the step above. Omit if there are no AI models, or if sparse
          # metadata is acceptable.
          extras: "ai"

      - name: Commit and push updated loom-ids.json
        uses: EndBug/add-and-commit@v11.0.0
        with:
          message: "Update loom-ids.json"
          add: "loom-ids.json"
```

Two things worth calling out about that snippet:

- **AI model id stability doesn't come from `extras: "ai"` or from
  auto-harvest at all.** `ai_AIPackage` elements are deliberately excluded
  from auto-harvest, because their correct registry key is the model
  file's stem -- which only ever comes from the extras-free
  `loom ids generate` step above. `extras: "ai"` only affects metadata
  richness (architecture, hyperparameters, etc.), not which spdxId a model
  gets.
- **Race conditions**: this workflow never competes with the publish
  workflow to push (the publish job doesn't commit, per the guidance
  above). It can race with *itself*, though -- two pushes to `main` close
  together could trigger two concurrent runs both trying to commit and
  push. The `concurrency:` group above queues same-branch runs instead of
  racing them. One sequencing caveat remains, shared by any
  generated-and-committed file (this repo's own `CITATION.cff` included):
  cutting a release at the exact moment a registry-update commit is in
  flight could still pick up a slightly-stale `loom-ids.json`.

## Configuration

See [Configuration](configuration.md) for the full `[tool.pitloom]`
reference these inputs defer to.

Inputs (all optional):

| Input | Default | Meaning |
| :--- | :--- | :--- |
| `project-path` | `.` | Directory to scan for a Python project. Ignored when `model` is set. |
| `embed-wheel` | *(empty)* | Path or glob pattern of built wheel(s) to embed the SBOM into (PEP 770), e.g. `dist/*.whl`. |
| `model` | *(empty)* | Local model file path, or Hugging Face URL/model ID. Switches to model mode. |
| `output` | *(empty)* | SBOM output file path. Empty lets `loom` apply its own default naming for the resolved mode: project mode uses `<name>-<version>.spdx3.json` (falling back to `<name>.spdx3.json`, then `sbom.spdx3.json`, unless `[tool.pitloom] sbom-basename` overrides it); model mode names the file after the model's own filename or Hugging Face repo ID; embed-wheel mode reuses the name it embeds into the wheel. |
| `extras` | *(empty)* | Comma-separated pip extras to install alongside Pitloom, e.g. `ai` (all AI model formats, including Hugging Face Hub support). |
| `pretty` | `false` | Pretty-print the SBOM output. |
| `enrich` | *(empty)* | `true`/`false` to force README/model-card enrichment on or off; empty defers to the project's `[tool.pitloom] enrich` config (off by default). |
| `extract-file-header` | *(empty)* | `true`/`false` to force per-file SPDX header scanning on or off; empty defers to `[tool.pitloom] extract-file-header` (on by default). |
| `content-type` | *(empty)* | `true`/`false` to force per-file content-type detection on or off; empty defers to `[tool.pitloom.content-type] enabled` (off by default). |
| `content-type-method` | *(empty)* | `auto`/`magika`/`extension` -- which detector resolves content-type values; empty defers to `[tool.pitloom.content-type] method` (`auto` by default). |
| `max-source-metadata-bytes` | *(empty)* | Cap the artifact-metadata preservation Annotation's serialised size to this many UTF-8 bytes, truncating the largest entries first when exceeded; empty defers to `[tool.pitloom.provenance] max-source-metadata-bytes` (unbounded by default). |
| `offline` | *(empty)* | `true`/`false` to force network access (PyPI/Hugging Face lookups) off or on; empty defers to `[tool.pitloom] offline` (off by default). |
| `use-lockfile` | *(empty)* | `true`/`false` to force the lock/pin file cascade off or on; empty defers to `[tool.pitloom] use-lockfile` (on by default). Only applies in project mode -- a no-op in model/embed-wheel mode, since neither reads a lock file. See [Dependency sources and precedence](dependency-sources.md). |
| `allow-build` | `false` | **SECURITY:** `"true"` lets Pitloom invoke the scanned project's own PEP 517 build backend (subprocess; may install build-requires from the network) to discover a wheel's real file list. Executes third-party build-time code from the project being scanned -- only enable for a project whose build script you trust. No `[tool.pitloom]` equivalent; defaults to `"false"`, not empty, since there's no config layer to defer to. Applies in project/embed-wheel mode; explicitly set in model mode, it has no effect and logs `::warning::allow-build has no effect in model mode (no project-directory file discovery there)`. See [`--allow-build`](allow-build.md). |
| `no-build-isolation` | `false` | With `allow-build: "true"`, skip creating an isolated build environment and use the runner's already-installed build backend instead. No effect without `allow-build`; explicitly set in model mode, it also logs `::warning::no-build-isolation has no effect in model mode (no project-directory file discovery there)`. |
| `build-timeout` | *(empty)* | Seconds or `h`/`m`/`s` duration, e.g. `900` or `1h30m`, capping how long an `allow-build` build may run before Pitloom kills it and falls back to static discovery. Passed verbatim to `loom --build-timeout`, which validates it -- no shell-side parsing. Empty uses Pitloom's own default of 20 minutes. No effect without `allow-build`; explicitly set in model mode, it also logs `::warning::build-timeout has no effect in model mode (no project-directory file discovery there)`. See [`--build-timeout`](allow-build.md#timing-out-a-build). |
| `args` | *(empty)* | Extra raw flags passed through to the `loom` command, e.g. `--verify --validate` when `embed-wheel` is set. |
| `pitloom-version` | *(empty)* | Pitloom version or specifier, e.g. `0.19.0` or `>=0.19,<1.0`. Empty installs the version of the pinned ref; see [What the pin covers](#what-the-pin-covers). |
| `python-version` | *(empty)* | Passed to `actions/setup-python`. Empty uses the Python on `PATH`, falling back to `3.x` with a warning; see [Python selection](#python-selection). |
| `install` | `true` | Set `false` to skip installing Python/Pitloom and assume `loom` is already on `PATH`. |
| `upload-artifact` | `true` | Upload the generated SBOM via `actions/upload-artifact`. |
| `artifact-name` | `sbom` | Artifact name used when `upload-artifact` is `true`. |

Output:

| Output | Meaning |
| :--- | :--- |
| `sbom-path` | Path to the generated SBOM file. Empty when `embed-wheel` matches more than one wheel -- a standalone copy is ambiguous across wheels, so only the embedded copies are produced and `upload-artifact` is skipped for that run. |

## Code example: Build and Publish PEP 770 Wheel

```yaml
name: Build and Publish
on: [push]
jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-python@v7
        with:
          python-version: "3.x"

      # 1. Build wheel using ANY build backend (Flit, Setuptools, Maturin, etc.)
      - name: Build wheel
        run: python -m build --wheel

      # 2. Generate and embed PEP 770 SBOM into built wheels
      - name: Embed PEP 770 SBOM
        uses: bact/pitloom@v0.19.0
        with:
          embed-wheel: "dist/*.whl"

      # 3. Publish PEP 770-compliant wheel to PyPI
      - name: Publish to PyPI
        uses: pypa/gh-action-pypa-publish@release/v1
```

## See also

- [Command line](cli.md) -- the same generation options this action
  wraps, run directly (`loom embed-wheel`).
- [Hatchling build hook](hatchling-build-hook.md) -- build-time SBOM
  embedding for Hatchling projects.
