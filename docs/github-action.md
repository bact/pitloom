---
Created: 2026-08-11
Last-Modified: 2026-08-11
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# GitHub Action

Use this when your project isn't Hatchling-based, or you just want CI to
produce an SBOM artifact with one `uses:` line -- for any Python build
backend, not just Hatchling.

The action creates a standalone SBOM file on the runner. It's useful for
compliance logs, CI/CD audits, and release assets.

> Running the GitHub Action alone does not embed the SBOM inside your
> distributed Python wheel -- use the [Hatchling build
> hook](hatchling-build-hook.md) for PEP 770 wheel embedding.

## Quick guide

```yaml
- uses: bact/pitloom@v0.13.4
```

## Installation

Nothing to install locally -- reference the action from a workflow step:

```yaml
jobs:
  sbom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: bact/pitloom@v0.13.4
```

Pin to a specific release tag (`@v0.13.4`) rather than a branch, the same
as any third-party action.

## Usage details

By default the action scans the checkout root as a Python project and
writes `sbom.spdx3.json`. Point it at an AI model instead of a project
directory with `model:`:

```yaml
- uses: bact/pitloom@v0.13.4
  with:
    model: path/to/model.safetensors
```

Pass extra raw CLI flags through with `args:` (shell-quoted, e.g. for
[creator/creation metadata](creation-metadata.md)):

```yaml
- uses: bact/pitloom@v0.13.4
  with:
    args: '--creator-name "CI Bot" --creator-type software-agent'
```

## Configuration

Inputs (all optional):

| Input | Default | Meaning |
| :--- | :--- | :--- |
| `project-path` | `.` | Directory to scan for a Python project. Ignored when `model` is set. |
| `model` | *(empty)* | Local model file path, or Hugging Face URL/model ID. Switches to model mode. |
| `output` | `sbom.spdx3.json` | SBOM output file path. |
| `extras` | *(empty)* | Comma-separated pip extras to install alongside Pitloom, e.g. `ai` (all AI model formats, including Hugging Face Hub support). |
| `pretty` | `false` | Pretty-print the SBOM output. |
| `enrich` | *(empty)* | `true`/`false` to force README/model-card enrichment on or off; empty defers to the project's `[tool.pitloom.enrich]` config (off by default). |
| `file-headers` | *(empty)* | `true`/`false` to force per-file SPDX header scanning on or off; empty defers to `[tool.pitloom.file-headers]` (on by default). |
| `content-type` | *(empty)* | `true`/`false` to force per-file content-type detection on or off; empty defers to `[tool.pitloom.file-headers] detect-content-type` (off by default). |
| `args` | *(empty)* | Extra raw flags passed through to the `loom` command. |
| `pitloom-version` | *(empty)* | Pitloom version/specifier to install, e.g. `0.13.4` or `>=0.13,<1.0`. Empty installs the latest release. |
| `python-version` | `3.x` | Python version passed to `actions/setup-python`. |
| `install` | `true` | Set `false` to skip installing Python/Pitloom and assume `loom` is already on `PATH`. |
| `upload-artifact` | `true` | Upload the generated SBOM via `actions/upload-artifact`. |
| `artifact-name` | `sbom` | Artifact name used when `upload-artifact` is `true`. |

Output:

| Output | Meaning |
| :--- | :--- |
| `sbom-path` | Path to the generated SBOM file. |

## Code example

```yaml
name: SBOM
on: [push]
jobs:
  sbom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: bact/pitloom@v0.13.4
        with:
          extras: ai
          pretty: "true"
          artifact-name: my-project-sbom
```

## See also

- [Command line](cli.md) -- the same generation options this action
  wraps, run directly.
- [Hatchling build hook](hatchling-build-hook.md) -- for embedding the
  SBOM into the wheel itself, not just a CI artifact.
