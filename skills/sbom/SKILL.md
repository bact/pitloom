---
name: sbom
description: >-
  Use this skill whenever the user asks to generate an SBOM, an SPDX
  document, a software bill of materials, a dependency inventory, or an AI
  model bill of materials (AIBOM) -- for a Python project or a standalone
  AI/ML model file (GGUF, ONNX, PyTorch, Safetensors, Keras, HDF5, NumPy,
  fastText, or a Hugging Face Hub model). Trigger phrasings include
  "generate an SBOM", "create an SPDX 3 document", "make a software bill of
  materials", "list this project's dependency inventory", "generate an AI
  model BOM / AIBOM", "document this model's provenance", and similar
  requests for a supply-chain transparency artefact.
license: Apache-2.0
---

<!-- Created: 2026-07-05 -->
<!-- Last-Modified: 2026-07-08 -->
<!-- SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul -->
<!-- SPDX-FileType: SOURCE -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Generate an SBOM with Pitloom

Pitloom is a command-line tool that generates SPDX 3 JSON SBOMs for
Python projects and AI/ML model files. This skill drives Pitloom's existing
CLI (`loom` / `pitloom`) -- it does not modify or reimplement Pitloom.

See `references/examples.md` for copy-paste recipes.

## Run without installing anything persistent

Prefer an ephemeral run so the user's environment is not polluted:

```bash
uvx pitloom <project-or-model-path>       # uv's ephemeral runner
# or
pipx run pitloom <project-or-model-path>  # pipx's ephemeral runner
```

Fall back to a normal install only if neither `uv` nor `pipx` is available:

```bash
pip install pitloom
loom <project-or-model-path>
```

`loom` and `pitloom` are two names for the same console-script entry point;
`uvx`/`pipx run` resolve `pitloom <args>` to that entry point automatically.

## Project SBOMs (Python packages)

```bash
loom .                              # scan the current directory
loom /path/to/project -o sbom.spdx3.json
```

Requires a `pyproject.toml` (PEP 621 `[project]` or Poetry
`[tool.poetry]`), or `setup.cfg` / `setup.py`, in the target directory.

## AI model SBOMs (AIBOMs)

Pass `-m` with a local model file or a Hugging Face URL/model ID -- no
project directory required:

```bash
loom -m model.safetensors
loom -m model.onnx
loom -m model.gguf
loom -m mistralai/Mistral-7B-v0.1                # bare Hugging Face model ID
loom -m https://huggingface.co/Qwen/Qwen3-235B-A22B
```

Supported local formats: GGUF, ONNX, Safetensors, PyTorch (`.pt`/`.pth`),
Keras, HDF5, NumPy, fastText. Hugging Face Hub models need
`pip install pitloom[huggingface]` (or `uvx --from 'pitloom[huggingface]'
pitloom`).

## Useful flags (both modes)

- `-o FILE` / `--output FILE` -- explicit output path.
- `--pretty` -- indent the JSON for human reading (default: compact).
- `-v` / `--verbose` -- print effective options and where each came from.
- `--creator-name NAME`, `--creator-email EMAIL` -- name who created the
  SBOM (person by default); `--creator-type` selects `person`,
  `organization`, `software-agent`, or `agent`. Without a named creator,
  Pitloom records itself as an unattended `software-agent` creator.
  Pitloom is always recorded as the generating tool regardless.

## What Pitloom produces

- An **SPDX 3 JSON** (JSON-LD) document (`@context` + `@graph`), by default
  named `<name>-<version>.spdx3.json` (project mode) or
  `<stem>.spdx3.json` (model mode).
- Project mode includes: the main package, its dependencies, per-file
  SHA-256 hashes (Merkle root over the wheel's file set), and a
  `pkg:pypi/<name>@<version>` PURL for the main package.
- Model mode includes: an `ai_AIPackage` element with whatever metadata the
  model format embeds (architecture, hyperparameters, framework, etc.).
- If the target project registers Pitloom's Hatchling build hook
  (`[tool.hatch.build.hooks.pitloom]`), building a wheel
  (`python -m build` / `hatch build`) also embeds an SBOM at
  `.dist-info/sboms/sbom.spdx3.json`, per
  [PEP 770](https://peps.python.org/pep-0770/). Mention this if relevant,
  but do not assume it -- it only applies to projects that opt in.

## How to verify the output

- Confirm the file exists and parses as JSON with an `@graph` array.
- If `spdx3-validate` is installed (`pip install spdx3-validate`), run
  `spdx3-validate --json <sbom-file>` for schema/SHACL validation.
- Sanity-check that the main project or model name appears among the
  `software_Package` / `ai_AIPackage` elements in `@graph`.

## When NOT to use this skill

- Pitloom **generates** SBOMs; it does not scan for known vulnerabilities
  or license-compliance violations. For vulnerability scanning, point the
  user at a scanner (e.g. Grype, Trivy) that *consumes* the SBOM Pitloom
  produces.
- Pitloom does not sign or attest SBOMs (no PEP 740 support yet).
- If the target has neither a Python project descriptor nor a supported
  model file, Pitloom has nothing to scan -- say so rather than guessing.

## Enriching the result

Static extraction cannot read prose. For information an agent can infer
that Pitloom's extraction cannot see -- an unstated license, a
dependency's purpose, a `trainedOn`/`testedOn` dataset relationship --
use the sibling `enrich` skill (`pitloom:enrich` when installed as a
plugin) after generating the base SBOM here.
