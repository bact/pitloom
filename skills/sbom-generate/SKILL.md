---
# Created: 2026-07-05
# Last-Modified: 2026-08-11
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

name: sbom-generate
description: >-
  Use this skill whenever the user asks to generate an SBOM, an SPDX
  document, a software bill of materials, a dependency inventory, or an AI
  model bill of materials (AIBOM) -- for a Python project, an sdist archive,
  a built wheel, a standalone AI/ML model file (GGUF, ONNX, PyTorch,
  Safetensors, Keras, HDF5, NumPy, fastText, or a Hugging Face Hub model), or an
  installed environment. Trigger phrasings include "generate an SBOM", "give
  me an SBOM", "gen SBOM of this model", "can we have SBOM of this project",
  "create an SPDX 3 document", "create a BOM", "make a software bill of
  materials", "get an SBOM for <artifact>", "list this project's dependency
  inventory", "generate an AI model BOM / AIBOM", "document this model's
  provenance", and similar requests for a supply-chain transparency artefact.
  Also triggers, with enrichment layered on top (see "Combine with
  enrichment" below), on "generate SBOM and enrich it", "give me a complete
  SBOM", "create an SBOM and fill in information as much as possible", and
  "help me get a full SBOM".
license: Apache-2.0
argument-hint: "[target]"
---

# Generate an SBOM with Pitloom

Pitloom is a command-line tool that generates SPDX 3 JSON SBOMs for
Python projects, sdist archives, wheels, AI/ML model files, and Python
environments. This skill drives Pitloom's existing CLI (`loom` / `pitloom`).

Triggers automatically on natural-language requests (see the trigger
phrasings above), or invoke it explicitly with `/sbom-generate [target]`
(`/pitloom:sbom-generate [target]` when installed via the Claude Code
plugin). `target` is optional -- a project directory, an sdist/wheel path,
a local model file, or a Hugging Face model ID; omit it to default to the
current directory.

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
- `--enrich` / `--no-enrich` -- opt in to (or force off) Pitloom's own
  deterministic, local, frontmatter-only enrichment pass as part of the
  same generate call. See "Combine with enrichment" below for when to use
  this versus the fuller `sbom-enrich` skill.
- `--extract-file-header` / `--no-extract-file-header` -- per-file SPDX
  header tag scanning (copyright, contributor, license, file type). On by
  default; cheap, no need to pass it explicitly.
- `--content-type` / `--no-content-type` -- per-file content-type
  detection via `magika`/a filename-extension guess. Off by default and
  **opt-in only** -- only add this flag when the user's request
  specifically implies wanting per-file content-type/MIME data, not
  reflexively on every SBOM request, since it costs real time per file
  (~5ms/file with `magika`) across potentially thousands of files.
- `--content-type-method {auto,magika,extension}` -- which detector
  `--content-type` uses; defaults to `auto` (try `magika`, fall back to
  the extension guess). Only needed to force a specific detector.

## Combine with enrichment

Some requests ask for generation *and* enrichment in one breath -- "generate
SBOM and enrich it", "give me a complete SBOM", "create an SBOM and fill in
information as much as possible", "help me get a full SBOM". Two different
depths answer these, and the request's own language is the signal for
which one:

- **Light ask** ("...and enrich it", "with enrichment") -- add `--enrich`
  to the generate command:

  ```bash
  loom generate <target> --enrich
  ```

  This runs Pitloom's own deterministic, local, frontmatter-only pass
  (`enrich/readme.py`) as part of the same command -- no prose reading, no
  network, no separate skill invocation.

- **Strong ask** ("complete", "as much detail/information as possible",
  "full SBOM") -- generate with `--enrich` too (it's free), then invoke
  the `sbom-enrich` skill on the result for the agentic pass: reading
  README/model-card *prose* and inferring license/dataset relationships
  that neither frontmatter nor static extraction can see. This costs more
  (agent reasoning, and possibly network for Hugging Face/PyPI lookups
  some of `sbom-enrich`'s steps make) -- reasonable for an explicit "as
  much as possible", not for a bare "generate an SBOM".

Plain "generate an SBOM" with no enrichment language in the request skips
both -- just run the base generate command.

## Verify the result

A quick `@graph`-presence sanity check is enough for most runs (see
`references/examples.md`), but for a schema/shape-level conformance
check, use the `sbom-validate` skill on the output.

## Known limitations -- say so, don't paper over it

Pitloom's dependency/supplier/license extraction is Python-packaging-native:
it reads `pyproject.toml`/`setup.cfg`/`setup.py`, installed
`importlib.metadata`, and the PyPI JSON API. Outside that world, coverage
drops, and the honest move is to tell the user plainly rather than hand
back a JSON file that looks complete but isn't:

- **No Python packaging markers at all** (a directory with only
  `package.json`, `Cargo.toml`, `go.mod`, `pom.xml`/`build.gradle`,
  `Gemfile`, `composer.json`, or a `.csproj`/`.sln` -- no
  `pyproject.toml`/`setup.cfg`/`setup.py` anywhere) -- `loom project`/
  `loom generate` already refuses outright ("No project configuration
  found ... Expected pyproject.toml, setup.cfg, or setup.py"). Don't try
  to work around this (e.g. by hand-authoring a fragment to fake
  coverage) -- tell the user this ecosystem isn't supported yet.
- **Mixed-ecosystem repos** (a `pyproject.toml` sitting alongside
  `package.json`/`Cargo.toml`/etc., e.g. a Python backend with a JS
  frontend in the same repo) -- generation *succeeds* here, silently. The
  resulting SBOM only inventories the Python side (`[project.dependencies]`
  and what's importable); every non-Python dependency is invisible to
  Pitloom and simply won't appear -- no error, no NOASSERTION placeholder,
  nothing marking the gap. If you see non-Python ecosystem files during
  generation, say explicitly that the SBOM covers only the Python
  packaging surface, not the whole repo.
- **Non-PyPI dependencies** (a `git+https://...` URL, a local path
  requirement, or a private-index-only package) -- these get a package
  entry, but supplier/license/hash enrichment (both the deterministic
  local pass and the PyPI JSON API fallback) has nothing to look up, so
  those fields land on `NOASSERTION`. That's the correct, honest output
  for "genuinely unknown" -- not a bug -- but worth naming when a user
  asks why a dependency's entry looks sparse.
- **AI model formats**: broad but not universal coverage (GGUF, ONNX,
  PyTorch, Safetensors, Keras, HDF5, NumPy, fastText, plus Hugging Face
  Hub models). A model in some other serialization format isn't
  recognized at all -- same "say so" rule applies rather than silently
  skipping it.

## See also

- `references/examples.md` -- copy-paste recipes for every target type.
- The sibling `sbom-enrich` skill -- the agentic, prose-reading enrichment
  pass; see "Combine with enrichment" above for when a request calls for it.
- The sibling `sbom-validate` skill -- schema/shape-level conformance
  check for any SBOM this skill produces.
- `docs/resources.md` in the Pitloom repository -- SPDX 3 spec, ontology,
  JSON-LD, and JSON Schema links (including the per-minor-version URL
  pattern) for looking up the exact schema/spec a generated SBOM should
  conform to.
