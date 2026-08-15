---
Created: 2026-08-11
Last-Modified: 2026-08-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# GitHub Action

Use this when your project isn't Hatchling-based, or you just want CI to
produce an SBOM artifact or embed PEP 770 SBOMs into built wheels with
one `uses:` line -- for any Python build backend, not just Hatchling.

The action can create a standalone SBOM file on the runner, or embed the
generated SBOM directly into built `.whl` files via `embed-wheel: "dist/*.whl"`.

## Quick guide

Standalone SBOM artifact:

```yaml
- uses: bact/pitloom@v0.15.0
```

Generate and embed PEP 770 SBOM into built wheels:

```yaml
- uses: bact/pitloom@v0.15.0
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
      - uses: bact/pitloom@v0.15.0
```

Pin to a specific release tag (`@v0.15.0`) rather than a branch, the same
as any third-party action.

## Usage details

By default the action scans the checkout root as a Python project and
writes `sbom.spdx3.json`. Point it at an AI model instead of a project
directory with `model:`:

```yaml
- uses: bact/pitloom@v0.15.0
  with:
    model: path/to/model.safetensors
```

Embed the SBOM into built wheels (PEP 770) for any build backend
(`flit`, `setuptools`, `poetry-core`, `maturin`, etc.):

```yaml
- uses: bact/pitloom@v0.15.0
  with:
    embed-wheel: "dist/*.whl"
```

Pass extra raw CLI flags through with `args:` (shell-quoted, e.g. for
[creator/creation metadata](creation-metadata.md)):

```yaml
- uses: bact/pitloom@v0.15.0
  with:
    args: '--creator-name "CI Bot" --creator-type software-agent'
```

## Configuration

See [Configuration](configuration.md) for the full `[tool.pitloom]`
reference these inputs defer to.

Inputs (all optional):

| Input | Default | Meaning |
| :--- | :--- | :--- |
| `project-path` | `.` | Directory to scan for a Python project. Ignored when `model` is set. |
| `embed-wheel` | *(empty)* | Path or glob pattern of built wheel(s) to embed the SBOM into (PEP 770), e.g. `dist/*.whl`. |
| `model` | *(empty)* | Local model file path, or Hugging Face URL/model ID. Switches to model mode. |
| `output` | `sbom.spdx3.json` | SBOM output file path. |
| `extras` | *(empty)* | Comma-separated pip extras to install alongside Pitloom, e.g. `ai` (all AI model formats, including Hugging Face Hub support). |
| `pretty` | `false` | Pretty-print the SBOM output. |
| `enrich` | *(empty)* | `true`/`false` to force README/model-card enrichment on or off; empty defers to the project's `[tool.pitloom] enrich` config (off by default). |
| `extract-file-header` | *(empty)* | `true`/`false` to force per-file SPDX header scanning on or off; empty defers to `[tool.pitloom] extract-file-header` (on by default). |
| `content-type` | *(empty)* | `true`/`false` to force per-file content-type detection on or off; empty defers to `[tool.pitloom.content-type] enabled` (off by default). |
| `content-type-method` | *(empty)* | `auto`/`magika`/`extension` -- which detector resolves content-type values; empty defers to `[tool.pitloom.content-type] method` (`auto` by default). |
| `args` | *(empty)* | Extra raw flags passed through to the `loom` command. |
| `pitloom-version` | *(empty)* | Pitloom version/specifier to install, e.g. `0.15.0` or `>=0.13,<1.0`. Empty installs the latest release. |
| `python-version` | `3.x` | Python version passed to `actions/setup-python`. |
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

      # 1. Build wheel using ANY build backend (Flit, Setuptools, Maturin, etc.)
      - name: Build wheel
        run: python -m build --wheel

      # 2. Generate and embed PEP 770 SBOM into built wheels
      - name: Embed PEP 770 SBOM
        uses: bact/pitloom@v0.15.0
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
