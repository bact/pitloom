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
<!-- Last-Modified: 2026-08-08 -->
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
uvx pitloom source <project-path>       # uv's ephemeral runner
# or
pipx run pitloom source <project-path>  # pipx's ephemeral runner
```

Fall back to a normal install only if neither `uv` nor `pipx` is available:

```bash
pip install pitloom
loom source <project-path>
```

`loom` and `pitloom` are two names for the same console-script entry point;
`uvx`/`pipx run` resolve `pitloom <args>` to that entry point automatically.
Every invocation needs a subcommand -- `source` (a Python project) or
`analyze` (a built wheel, an AI model file, or a Hugging Face repo); see
below.

## Project SBOMs (Python packages)

```bash
loom source .                              # scan the current directory
loom source /path/to/project -o sbom.spdx3.json
```

Requires a `pyproject.toml` (PEP 621 `[project]` or Poetry
`[tool.poetry]`), or `setup.cfg` / `setup.py`, in the target directory.

## AI model SBOMs (AIBOMs)

Use `loom analyze` with a local model file or a Hugging Face URL/model ID --
no project directory required:

```bash
loom analyze model.safetensors
loom analyze model.onnx
loom analyze model.gguf
loom analyze mistralai/Mistral-7B-v0.1                # bare Hugging Face model ID
loom analyze https://huggingface.co/Qwen/Qwen3-235B-A22B
```

Supported local formats: GGUF, ONNX, Safetensors, PyTorch (`.pt`/`.pth`),
Keras, HDF5, NumPy, fastText. Hugging Face Hub models need
`pip install pitloom[huggingface]` (or `uvx --from 'pitloom[huggingface]'
pitloom`). `analyze` also accepts a built `.whl` file (an Analyzed SBOM
from the wheel's own metadata and file list).

## Deployed SBOMs (installed environment)

```bash
loom deployed -o env.spdx3.json
```

No positional argument -- it always inspects the *current* Python
environment (via `pipdeptree`) rather than a project directory or file.
Use this when the request is about "what's installed" / "what's in this
venv", not about a specific project's source or a specific model file.

## Useful flags (both modes)

- `-o FILE` / `--output FILE` -- explicit output path.
- `--pretty` -- indent the JSON for human reading (default: compact).
- `-v` / `--verbose` -- print effective options and where each came from.
- `--creator-name NAME`, `--creator-email EMAIL` -- name who created the
  SBOM (person by default); `--creator-type` selects `person`,
  `organization`, `software-agent`, or `agent`. `--creator-name` is
  repeatable -- each occurrence starts a new creator, in order;
  `--creator-type`/`--creator-email` bind to the most recently named one
  (e.g. `--creator-name "Acme Corp" --creator-type organization
  --creator-name Alice`). Without a named creator, Pitloom records itself
  as an unattended `software-agent` creator. Pitloom is recorded as the
  generating tool by default too (suppress with `--no-creation-tool`).

## Metadata provenance

Pitloom records where each metadata field came from as SPDX 3 Core
`Annotation` elements (plus a legacy `comment` form), controlled by
`[tool.pitloom.provenance]` in `pyproject.toml` -- `format` (`annotation`
/ `comment` / `both`, default `both`), `detail` (`minimal` default /
`full`), and `preserve-source-metadata` for embedding an AI model's
verbatim original metadata when it isn't shipped with the distribution.
No CLI flags for this -- it's `pyproject.toml`-only. Mention it if the
user asks how to audit or configure provenance; don't assume they need
it otherwise.

## What Pitloom produces

- An **SPDX 3 JSON** (JSON-LD) document (`@context` + `@graph`), by default
  named `<name>-<version>.spdx3.json` (`source`) or `<stem>.spdx3.json`
  (`analyze`, model target).
- `source` includes: the main package, its dependencies, per-file
  SHA-256 hashes (Merkle root over the wheel's file set), and a
  `pkg:pypi/<name>@<version>` PURL for the main package.
- `analyze` (model target) includes: an `ai_AIPackage` element with
  whatever metadata the model format embeds (architecture,
  hyperparameters, framework, etc.).
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
