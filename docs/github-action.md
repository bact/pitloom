---
Created: 2026-08-11
Last-Modified: 2026-10-08
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
- uses: bact/pitloom@v0.20.1
```

Set up Python first: the action uses the Python on `PATH`. See
[Python selection](#python-selection).

Generate and embed PEP 770 SBOM into built wheels:

```yaml
- uses: bact/pitloom@v0.20.1
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
      - uses: bact/pitloom@v0.20.1
```

Pin a release tag (`@v0.20.1`) or a full commit SHA (`@<sha> # v0.20.1`),
not a branch. The pin also selects the Pitloom version: see
[What the pin covers](#what-the-pin-covers).

## What the pin covers

- **Pitloom version:** with `pitloom-version` empty, the action installs the
  version carried by the pinned ref (tag or SHA) from PyPI. `@v0.20.1` and that
  tag's commit SHA both give 0.20.1. It fails if the version is not on PyPI: an
  unreleased commit, a branch between a version bump and its release, or a tag
  pushed before the upload finishes.
- **`pitloom-version`** overrides it: a version (`0.20.1`) or a specifier
  (`>=0.20,<1.0`).
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
`[tool.pitloom] sbom-basename` overrides it, a trailing `.spdx3.json` dropped with a `WARNING:` -- the same default-naming
logic `loom project` uses directly). Point it at an AI model instead of a
project directory with `model:`:

```yaml
- uses: bact/pitloom@v0.20.1
  with:
    model: path/to/model.safetensors
```

A model whose read fails (truncated, over a bound, a missing extra) still
gives a format-only entry: the step succeeds and the action surfaces the
`WARNING:` as an annotation. A file that is not a model (a Git LFS pointer
included), or is absent or unreadable, fails the step.
See [AI model scan limits](ai-model-scan-limits.md#which-scans-apply-which-limits).

Set `embed-wheel: "dist/*.whl"` (see the quick guide) to embed the SBOM into
built wheels (PEP 770) for any build backend (`flit`, `setuptools`,
`poetry-core`, `maturin`, etc.).

Pass extra raw CLI flags through with `args:` (shell-quoted, e.g. for
[creator/creation metadata](creation-metadata.md)):

```yaml
- uses: bact/pitloom@v0.20.1
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

`-v` in `args` logs each effective option as an `INFO:` line, so each
becomes a `::notice::` annotation; GitHub caps how many a step shows.

## Loom ID registry in CI

Declare a registry with the `id-registry` input (or `[tool.pitloom] id-registry`);
the action then harvests newly minted ids back into it, in the runner's
checkout only. To commit it back without relaxing a publish job's permissions,
see [Loom ID registry: In CI](id-registry.md#in-ci).

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
| `scan-model-usage` | *(empty)* | `true`/`false` to force recording which Python files reference each AI model file (`hasDataFile`) on or off; empty defers to the `[tool.pitloom] scan-model-usage` in effect (off by default). |
| `content-type` | *(empty)* | `true`/`false` to force per-file content-type detection on or off; empty defers to `[tool.pitloom.content-type] enabled` (off by default). |
| `content-type-method` | *(empty)* | `auto`/`magika`/`extension` -- which detector resolves content-type values; empty defers to `[tool.pitloom.content-type] method` (`auto` by default). |
| `max-source-metadata-bytes` | *(empty)* | Cap the artifact-metadata preservation Annotation's serialised size to this many UTF-8 bytes, truncating the largest entries first when exceeded; empty defers to `[tool.pitloom.provenance] max-source-metadata-bytes` (unbounded by default); `0` or at least 8; anything else is an error. |
| `config` | *(empty)* | Path to a TOML file whose `[tool.pitloom]` table replaces the project's own (`loom --config`); a relative `id-registry` in it resolves against the file's directory. Empty uses the project's own; model mode reads no config otherwise. See [Where settings come from](configuration.md#where-settings-come-from). |
| `id-registry` | *(empty)* | Loom ID registry file path (`loom --id-registry`); relative to the runner's working directory. Empty defers to the `config` input file's `id-registry`, else the project's own `[tool.pitloom] id-registry`, else no registry is used -- nothing is auto-discovered. A declared file that's missing, unreadable or invalid fails the step. |
| `update-id-registry` | *(empty)* | `true`/`false` to force harvesting newly-minted ids back into a *declared* registry on or off; empty defers to `[tool.pitloom] update-id-registry` (on by default). No effect when no registry is declared, and never creates one. |
| `offline` | *(empty)* | `true`/`false` to force network access (PyPI/Hugging Face lookups) off or on; empty defers to `[tool.pitloom] offline` (off by default). |
| `use-lockfile` | *(empty)* | `true`/`false` to force the lock/pin file cascade off or on; empty defers to `[tool.pitloom] use-lockfile` (on by default). Only applies in project mode -- a no-op in model/embed-wheel mode, since neither reads a lock file. See [Dependency sources and precedence](dependency-sources.md). |
| `trust-wheel-model` | `false` | **SECURITY:** with `embed-wheel` **and `project-path: ""`**, `"true"` reads AI model files inside the wheel with every format reader, including the [formats gated in wheels](ai-model-scan-limits.md#formats-gated-in-wheels), whose readers can crash or hang on a hostile file; by default such a model is listed without metadata. Only for a wheel you trust: a hostile model file can crash or hang the step or exhaust memory. No `[tool.pitloom]` equivalent. With the default `project-path: .` the action passes `--project-dir`, the models are read from the project, not the wheel, and the input logs `::warning::trust-wheel-model has no effect with project-path set`; outside `embed-wheel` mode it logs `::warning::trust-wheel-model has no effect without embed-wheel (no wheel is read here)`. |
| `allow-signed-wheel` | `false` | **SECURITY:** with `embed-wheel`, `"true"` embeds into a wheel that carries a `RECORD` signature (`RECORD.jws`, `RECORD.p7s`), removing the signature (one `INFO:` per file); re-sign afterwards. By default such a wheel is refused and left untouched. Order the steps build, `embed-wheel`, sign/attest, upload: the embed invalidates signatures and hashes over the wheel file. See [Signed wheels](wheel-sbom.md#signed-wheels). No `[tool.pitloom]` equivalent. Outside `embed-wheel` mode it logs `::warning::allow-signed-wheel has no effect without embed-wheel (no wheel is rewritten here)`. |
| `allow-build` | `false` | **SECURITY:** `"true"` lets Pitloom invoke the scanned project's own PEP 517 build backend (subprocess; may install build-requires from the network) to discover a wheel's real file list. Executes third-party build-time code from the project being scanned -- only enable for a project whose build script you trust. No `[tool.pitloom]` equivalent; defaults to `"false"`, not empty, since there's no config layer to defer to. Applies in project/embed-wheel mode; explicitly set in model mode, it has no effect and logs `::warning::allow-build has no effect in model mode (no project-directory file discovery there)`. See [`--allow-build`](allow-build.md). |
| `no-build-isolation` | `false` | With `allow-build: "true"`, skip creating an isolated build environment and use the runner's already-installed build backend instead. No effect without `allow-build`; explicitly set in model mode, it also logs `::warning::no-build-isolation has no effect in model mode (no project-directory file discovery there)`. |
| `build-timeout` | *(empty)* | Seconds or `h`/`m`/`s` duration, e.g. `900` or `1h30m`, capping how long an `allow-build` build may run before Pitloom kills it and falls back to static discovery. Passed verbatim to `loom --build-timeout`, which validates it -- no shell-side parsing. Empty uses Pitloom's own default of 20 minutes. No effect without `allow-build`; explicitly set in model mode, it also logs `::warning::build-timeout has no effect in model mode (no project-directory file discovery there)`. See [`--build-timeout`](allow-build.md#timing-out-a-build). |
| `args` | *(empty)* | Extra raw flags passed through to the `loom` command, e.g. `--verify --validate` when `embed-wheel` is set. |
| `pitloom-version` | *(empty)* | Pitloom version or specifier, e.g. `0.20.1` or `>=0.20,<1.0`. Empty installs the version of the pinned ref; see [What the pin covers](#what-the-pin-covers). |
| `python-version` | *(empty)* | Passed to `actions/setup-python`. Empty uses the Python on `PATH`, falling back to `3.x` with a warning; see [Python selection](#python-selection). |
| `install` | `true` | Set `false` to skip installing Python/Pitloom and assume `loom` is already on `PATH`. |
| `upload-artifact` | `true` | Upload the generated SBOM via `actions/upload-artifact`. |
| `artifact-name` | `sbom` | Artifact name used when `upload-artifact` is `true`. |

Output:

| Output | Meaning |
| :--- | :--- |
| `sbom-path` | Path to the generated SBOM file (a path with a non-printable character arrives quoted and ASCII-escaped, as `loom` prints it). Empty when `embed-wheel` matches more than one wheel -- a standalone copy is ambiguous across wheels, so only the embedded copies are produced and `upload-artifact` is skipped for that run. |

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
        uses: bact/pitloom@v0.20.1
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
