---
Created: 2026-07-05
Last-Modified: 2026-07-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Using Pitloom as a GitHub Action

Pitloom ships a composite GitHub Action (`action.yml` at the repository
root) that wraps the `loom` CLI. It works for any Python project -- any
build backend, not just Hatchling -- because it drives the CLI the same
way a developer would from a terminal.

See [adoption-surfaces.md](../design/adoption-surfaces.md) for how this
fits alongside Pitloom's other surfaces.

## Quick start

```yaml
name: SBOM

on: [push, pull_request]

jobs:
  sbom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: bact/pitloom@v0.11.0
        with:
          project-path: "."
          output: "sbom.spdx3.json"
```

This installs Pitloom, runs `loom . -o sbom.spdx3.json`, and uploads the
result as a workflow artefact named `sbom` (all defaults; see below to
change any of it).

## Inputs

| Input | Default | Purpose |
| :--- | :--- | :--- |
| `project-path` | `.` | Directory to scan. Ignored when `model` is set. |
| `model` | `""` | Local model file path or Hugging Face URL/ID -- runs model mode (`loom -m ...`) instead of project mode. |
| `output` | `sbom.spdx3.json` | SBOM output path. |
| `extras` | `""` | Comma-separated pip extras, e.g. `aimodel,huggingface`. |
| `pretty` | `false` | Pretty-print the SBOM JSON. |
| `args` | `""` | Extra raw flags passed through to `loom` (e.g. `-v --creator-name CI`). This is also how to record more than one creator or tool -- `--creator-name`/`--creation-tool` are repeatable CLI flags, and the Action has no dedicated multi-creator input; see the recipe below. |
| `pitloom-version` | `""` | Version/specifier to install; empty installs latest from PyPI. |
| `python-version` | `3.x` | Passed to `actions/setup-python`. |
| `install` | `true` | Set `false` to skip installing Python/Pitloom (assumes it is already on `PATH`). |
| `upload-artifact` | `true` | Upload the SBOM via `actions/upload-artifact`. |
| `artifact-name` | `sbom` | Artifact name when uploading. |

## Output

| Output | Description |
| :--- | :--- |
| `sbom-path` | Path to the generated SBOM file. |

## Recipe: AI model SBOM

```yaml
- uses: bact/pitloom@v0.11.0
  with:
    model: "models/my-model.safetensors"
    extras: "aimodel"
    output: "model.spdx3.json"
    pretty: "true"
```

## Recipe: multiple creators

`--creator-name` is repeatable -- each occurrence starts a new creator, and
`--creator-type`/`--creator-email` bind to the most recently named one.
Pass them through `args` (the Action itself has no dedicated multi-creator
input):

```yaml
- uses: bact/pitloom@v0.11.0
  with:
    project-path: "."
    output: "sbom.spdx3.json"
    args: >-
      --creator-name "Acme Corp" --creator-type organization
      --creator-name Alice
```

## Recipe: attach the SBOM to a GitHub Release

```yaml
name: Release SBOM

on:
  release:
    types: [published]

jobs:
  sbom:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v6
      - uses: bact/pitloom@v0.11.0
        id: pitloom
        with:
          project-path: "."
          output: "sbom.spdx3.json"
          pretty: "true"
      - name: Upload SBOM to the release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          gh release upload "${{ github.event.release.tag_name }}" \
            "${{ steps.pitloom.outputs.sbom-path }}"
```

## Recipe: matrix build across Python versions

```yaml
name: SBOM matrix

on: [push, pull_request]

jobs:
  sbom:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13", "3.14"]
    steps:
      - uses: actions/checkout@v6
      - uses: bact/pitloom@v0.11.0
        with:
          project-path: "."
          python-version: ${{ matrix.python-version }}
          artifact-name: "sbom-py${{ matrix.python-version }}"
```

## How Pitloom dogfoods this Action

`.github/workflows/action-selftest.yml` runs the Action against the
Pitloom repository itself (`uses: ./`, `install: false`, so it exercises
the checked-out code rather than a published release), then asserts that
the output file exists, parses as JSON-LD with an `@graph` array, and
contains both the `pitloom` package and a `pkg:pypi/pitloom@...` PURL.
Use the same assertions in your own CI if you want a smoke test beyond
"the step did not fail".

## Design notes

- The Action is **composite** (`runs.using: "composite"`), not a Docker
  action -- faster to start, no image to publish, and Marketplace-friendly.
  A Docker variant (for hermetic or self-hosted-runner use) is tracked in
  [roadmap.md](../design/roadmap.md) as future work.
- Every `run:` block uses `set -euo pipefail` and quotes all inputs, so a
  malformed or empty input fails the step rather than silently doing the
  wrong thing.
- Third-party actions are pinned by major version
  (`actions/checkout@v6`, `actions/setup-python@v6`,
  `actions/upload-artifact@v7`).
