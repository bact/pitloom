---
name: sbom
description: >-
  Use this skill whenever the user asks to generate an SBOM, an SPDX
  document, a software bill of materials, a dependency inventory, or an AI
  model bill of materials (AIBOM) -- for a Python project, an sdist archive,
  a built wheel, a standalone AI/ML model file (GGUF, ONNX, PyTorch,
  Safetensors, Keras, HDF5, NumPy, fastText, or a Hugging Face Hub model), or an
  installed environment. Trigger phrasings include "generate an SBOM", "create
  an SPDX 3 document", "make a software bill of materials", "list this
  project's dependency inventory", "generate an AI model BOM / AIBOM",
  "document this model's provenance", and similar requests for a supply-chain
  transparency artefact.
license: Apache-2.0
argument-hint: "[target]"
---

<!-- Created: 2026-07-05 -->
<!-- Last-Modified: 2026-08-09 -->
<!-- SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul -->
<!-- SPDX-FileType: SOURCE -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Generate an SBOM with Pitloom

Pitloom is a command-line tool that generates SPDX 3 JSON SBOMs for
Python projects, sdist archives, wheels, AI/ML model files, and Python
environments. This skill drives Pitloom's existing CLI (`loom` / `pitloom`).

Triggers automatically on natural-language requests (see the trigger
phrasings above), or invoke it explicitly with `/sbom [target]`
(`/pitloom:sbom [target]` when installed via the Claude Code plugin).
`target` is optional -- a project directory, an sdist/wheel path, a local
model file, or a Hugging Face model ID; omit it to default to the current
directory.

See `references/examples.md` for copy-paste recipes.

## Run without installing anything persistent

Prefer an ephemeral run so the user's environment is not polluted:

```bash
uvx pitloom generate <target>       # Smart auto-detection entrypoint
```

or

```bash
pipx run pitloom generate <target>  # pipx's ephemeral runner
```

Fall back to a normal install only if neither `uv` nor `pipx` is available:

```bash
pip install pitloom
loom generate <target>
```

`loom` and `pitloom` are two names for the same console-script entry point.

## Smart Entrypoint: `loom generate`

Use `loom generate` for automatic target detection:

```bash
loom generate .                              # project directory -> Source SBOM
loom generate mypackage-1.0.0.tar.gz         # sdist archive     -> Source SBOM
loom generate dist/pkg-1.0-py3-none-any.whl  # wheel package     -> Analyzed SBOM
loom generate models/model.gguf              # local model file  -> AI Model SBOM
loom generate mistralai/Mistral-7B-v0.1      # Hugging Face URL  -> AI Model SBOM
loom generate env                            # installed venv    -> Deployed SBOM
```

## Explicit Target Subcommands

For deterministic execution in CI/CD and sandboxed runners:

```bash
# 1. Project Directory or Sdist Archive (Source SBOM)
loom project .
loom project /path/to/project -o sbom.spdx3.json
loom project dist/mypackage-1.0.0.tar.gz

# 2. Built Wheel Package (Analyzed SBOM)
loom wheel dist/mypackage-1.0.0-py3-none-any.whl -o wheel.spdx3.json

# 3. AI Model Asset (AIBOM)
loom model models/model.safetensors
loom model models/model.gguf --offline      # --offline forbids network calls
loom model mistralai/Mistral-7B-v0.1        # Hugging Face model ID

# 4. Deployed Environment (Installed venv)
loom env -o env.spdx3.json

# 5. Fragment Merging
loom merge .spdx3-fragments/ -o combined.spdx3.json
```

## Useful flags

- `-o FILE` / `--output FILE` -- explicit output path.
- `--pretty` -- indent the JSON for human reading (default: compact).
- `--offline` -- enforce offline execution for `loom model` / `loom generate`.
- `-v` / `--verbose` -- print effective options and where each came from.
- `--creator-name NAME`, `--creator-email EMAIL` -- name who created the SBOM.
