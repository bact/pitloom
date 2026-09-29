---
# Created: 2026-07-05
# Last-Modified: 2026-09-28
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

name: sbom-generate
description: >-
  Use this skill whenever the user asks to generate an SBOM, an SPDX
  document, a software bill of materials, a dependency inventory, or an AI
  model bill of materials (AIBOM) -- for a Python project, an sdist archive,
  a built wheel, a standalone AI/ML model file (GGUF, ONNX, PyTorch,
  PyTorch PT2/ExecuTorch, Safetensors, Keras, HDF5, NumPy, fastText, or a
  Hugging Face Hub model), or an
  installed environment. Trigger phrasings include "generate an SBOM", "give
  me an SBOM", "gen SBOM of this model", "can we have SBOM of this project",
  "create an SPDX 3 document", "create a BOM", "make a software bill of
  materials", "get an SBOM for <artifact>", "list this project's dependency
  inventory", "generate an AI model BOM / AIBOM", "document this model's
  provenance", and similar requests for a supply-chain transparency artefact.
  Also triggers, with enrichment layered on top (see "Combine with
  enrichment" below), on "generate SBOM and enrich it", "give me a complete
  SBOM", "create an SBOM and fill in information as much as possible", and
  "help me get a full SBOM". Also triggers, with a named standard's minimum
  elements layered on top (see "Combine with a named standard" below), on
  "give me SBOM with CISA 2026 minimum elements", "generate an SBOM that
  meets NTIA requirements", and "create an AIBOM compliant with G7 SBOM for
  AI". Also triggers on requests to embed an SBOM
  directly into a built wheel per PEP 770 -- "embed the SBOM in this
  wheel", "embed SBOM to the wheel", "embed SBOM to python wheel",
  "embed-wheel", "add the SBOM to dist/*.whl", "put the SBOM in the
  wheel", "create SBOM in the wheel", "create PEP 770 SBOM", "PEP 770
  wheel embedding", and similar phrasings naming an SBOM together with a
  wheel/PEP 770 -- see "Embed an SBOM into a wheel (PEP 770)" below.
  Also triggers on choosing or discussing how long an `--allow-build`
  build may run -- "generate the SBOM with a real build", "use
  --allow-build", "limit the build to 30 minutes", "how long should the
  build timeout be", "the build is taking too long" -- see "Choosing
  `--build-timeout`" below.
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

See `references/examples.md` for copy-paste recipes (URL in "See also"
below, for a copy without the `references/` folder).

## Requirements

- Python >= 3.10, the `loom`/`pitloom` entry point -- `pip install
  pitloom`, or run ephemeral via `uvx`/`pipx` (see below).
- AI model targets need the `ai` extra (`pitloom[ai]`) or a
  format-specific one (`pitloom[huggingface_hub]`, `pitloom[gguf]`,
  etc. -- see `pyproject.toml`'s `[project.optional-dependencies]`,
  <https://github.com/bact/pitloom/blob/main/pyproject.toml>).
- `--allow-build` needs the `build` extra (PyPA `build`);
  `--content-type` needs the `content-type` extra (`magika`).

## Run without installing anything persistent

Prefer an ephemeral run so the user's environment is not polluted:

```bash
uvx pitloom generate <target> -o sbom.spdx3.json       # Smart auto-detection entrypoint
```

or

```bash
pipx run pitloom generate <target> -o sbom.spdx3.json  # pipx's ephemeral runner
```

Fall back to a normal install only if neither `uv` nor `pipx` is available:

```bash
pip install pitloom
loom generate <target> -o sbom.spdx3.json
```

`-o`/`--output` is required for `generate` -- unlike `project`/`wheel`/
`model`/`env` below, which each know their target type and so have an
obvious default filename, `generate` dispatches across several target
types with no single natural default.

`loom` and `pitloom` are two names for the same console-script entry point.

## Smart Entrypoint: `loom generate`

Use `loom generate` for automatic target detection:

```bash
loom generate . -o sbom.spdx3.json                              # project directory -> Source SBOM
loom generate mypackage-1.0.0.tar.gz -o sbom.spdx3.json         # sdist archive     -> Source SBOM
loom generate dist/pkg-1.0-py3-none-any.whl -o sbom.spdx3.json  # wheel package     -> Analyzed SBOM
loom generate models/model.gguf -o sbom.spdx3.json              # local model file  -> AI Model SBOM
loom generate mistralai/Mistral-7B-v0.1 -o sbom.spdx3.json      # Hugging Face URL  -> AI Model SBOM
loom generate env -o sbom.spdx3.json                            # installed venv    -> Deployed SBOM
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

### Automatic lock file discovery & resolved dependencies

When generating an SBOM for a project directory (`loom project .` or
`loom generate .`), Pitloom automatically inspects the project root for lock
files to discover exact, pinned dependency versions and transitive
dependencies.

Supported lock formats in priority order:

1. `pylock.toml` (PEP 751 standard lock file)
2. `uv.lock` (uv workspace/resolver)
3. `poetry.lock` (Poetry resolver)
4. `pdm.lock` (PDM resolver)
5. `Pipfile.lock` (Pipenv resolver)
6. `requirements.txt` (Strictly fully-pinned requirement file)

When a lock file is present:

- Direct dependencies declared with version ranges (e.g. `requests>=2.0`)
  automatically resolve to their exact locked version rather than falling
  back to host environment introspection.
- Transitive dependencies from the lock file are emitted as SPDX 3
  `software_Package` elements connected via `dependsOn` relationships.
- SHA-256 package hashes are extracted directly from supported lock files
  for `verifiedUsing` integrity validation, preserved in offline builds and
  prioritised over PyPI lookups.
- Relationship completeness is conservatively left unset (`None`) to
  avoid overstating completeness for partial closures (e.g. omitted
  VCS/path dependencies or marker-ambiguous variants).

To opt out and fall back to direct dependencies + environment introspection
only, pass `--no-use-lockfile` (on `project`/`generate`, or on `enrich`
together with `--project-dir` -- it has no effect on `enrich` without
`--project-dir`, since no project metadata is read at all in that case) or
set `[tool.pitloom] use-lockfile = false` in `pyproject.toml`. On by
default; an explicit CLI flag always wins over the config value.

### Why element ids stay stable across reruns (the Loom ID registry)

Element ids are content-addressed: rerunning on unchanged source
reproduces them with no registry. A Loom ID registry pins ids across
runs whose inputs differ -- e.g. a fragment written today, merged into
next week's regeneration after the source changed (see `sbom-enrich`).

A registry is used **only when declared**, never searched for:
`--id-registry FILE` (relative to the current directory), else
`id-registry` in the applicable config -- a `--config FILE` (relative
to that file's directory; replaces the project config), or the
project's own `[tool.pitloom]`/`[tool:pitloom]` (relative to the
project). Wheel, env and model-file targets, and `enrich`/`embed-wheel`
without `--project-dir`, read no project config; an sdist's own key is
ignored. Nothing declared: no registry, silently. Declared but missing
or invalid: one `ERROR:`, exit 1. A declared registry is also updated:
`project`/`wheel`/`env`/`generate` runs add newly-minted ids to it
(stop with `--no-update-id-registry` or `update-id-registry = false`);
no run ever creates one.

Only `loom id generate`/`loom id import` create or index a registry --
never hand-edit one:

- **Create**: run from the project directory (`PATH` and `-o` resolve
  against the current directory; a `PATH` outside the project is an
  `ERROR:`): `loom id generate <PATH...> -o loom-id-registry.json`.
  `-o`/`--id-registry` is required unless the project config already
  declares `id-registry`; without either, one `ERROR:`, exit 1.
  `PATH` = `src` (src layout) or the package directory (flat layout);
  with no `PATH`, whichever of `src`/`data`/`models` exist are used
  (`ERROR:` if none). Or reuse an SBOM's ids: `loom id import <sbom>
  -o loom-id-registry.json`. A newly created, undeclared registry
  prints one of these lines -- relay it verbatim (the second when the
  project already declares a different `id-registry`: change that key,
  never add a second one):

  ```text
  INFO: ID registry: to use this registry, add to [tool.pitloom] in pyproject.toml: id-registry = "<path>"
  INFO: ID registry: to use this registry, change id-registry in [tool.pitloom] in pyproject.toml to: id-registry = "<path>"
  ```

  (`[tool:pitloom] in setup.cfg` for a setup.cfg project -- there the
  path is unquoted, `id-registry = <path>` with no quotes, since
  `setup.cfg` values are read as plain INI strings; relay that line
  verbatim too, quotes and all, exactly as each variant prints it).
  Until that key is added or changed, pass `--id-registry <file>` on
  each run.
- **Models**: `loom id generate` registers every AI model file under
  `PATH` by file stem; add `--entity <stem>` for one outside `PATH`.
  Runs never add model ids -- only `loom id generate` does.
- **Datasets**: pinned only by the Python SDK
  (`pitloom.loom.Run(..., id_registry=...)`, which ignores
  `[tool.pitloom]`), by path and content hash; index them with
  `loom id generate <dataset-dir> -o <registry>`.

**Choose the registry before generating.** Skip this for a Hugging Face
model and for `embed-wheel --sbom` (`--id-registry` is ignored there,
with a `WARNING:`). Otherwise:

1. Always: if the applicable config declares a registry, it is used --
   tell the user which file, and (for `project`/`wheel`/`env`/`generate`
   unless `update-id-registry` is off) that the run adds new ids to it.
2. None declared, and ids must stay stable across runs or a fragment
   will be merged after the source changes:
   - Interactive: ask "Pin ids with a Loom ID registry? If yes, which
     file -- an existing one, or create `loom-id-registry.json`?"
     Yes with a file: pass `--id-registry FILE` (create it first, as
     above, if new). No: generate without one. Never create or pass a
     registry the user did not name.
   - Non-interactive: use none, create nothing, and report "No Loom ID
     registry used (none declared). To pin ids, run `loom id generate
     <PATH> -o loom-id-registry.json` in the project directory, then
     declare it as the INFO line says (project target) or pass
     `--id-registry loom-id-registry.json` on each run (other targets)."

Full command reference: [docs/cli.md's "Pin ids across fragments"
section](https://github.com/bact/pitloom/blob/main/docs/cli.md#pin-ids-across-fragments).

## Embed an SBOM into a wheel (PEP 770)

For a request to *embed* an SBOM into a built wheel rather than write it
as a standalone file -- PEP 770's `.dist-info/sboms/` convention -- use
`embed-wheel` instead of `wheel`:

```bash
loom embed-wheel dist/mypackage-1.0.0-py3-none-any.whl        # standalone: no project scan
loom embed-wheel dist/*.whl --project-dir .   # multiple wheels, Build SBOM
```

`--project-dir` is required to have `embed-wheel` rescan the source
project (it is never inferred from the current directory, even when the
shell is already there) -- pass it whenever the user has a project
directory to scan; omit it only for a genuinely standalone wheel with no
project of its own.

Or embed an already-generated SBOM file directly -- its declared subject
name/version is cross-checked against the wheel's own METADATA first; a
mismatch aborts the embed (`--allow-mismatch` downgrades to a warning):

```bash
loom embed-wheel dist/*.whl --sbom sbom.spdx3.json
```

Or embed directly on `loom wheel` for a single wheel's own Analyzed SBOM
(no project-directory scanning):

```bash
loom wheel dist/mypackage-1.0.0-py3-none-any.whl --embed
```

`embed-wheel` mutates the `.whl` archive in place (RECORD is updated to
match); it works on any wheel regardless of build backend, since a wheel
is just a ZIP archive -- unlike the Hatchling-specific build hook. See
[`docs/cli.md`](https://github.com/bact/pitloom/blob/main/docs/cli.md)
for the full flag reference, including `--output` (rejected when more
than one wheel matches) and `--sbom-basename`.

To check the wheel's embedded SBOM right after this same embed, pass
`--verify`/`--validate` to `embed-wheel` itself -- both checks share the
one disk read this embed already did:

```bash
loom embed-wheel dist/*.whl --project-dir . --verify --validate
```

For checking an already-embedded wheel later (not right after an embed
in this same command), see the `sbom-validate` skill's "Validate a
wheel's embedded SBOM" section -- it runs `verify-wheel`/`validate-wheel`
together (or `verify-wheel` alone with a follow-up question, for a
presence-only ask).

## Useful flags

- `-o FILE` / `--output FILE` -- explicit output path.
- `--config FILE` -- read `[tool.pitloom]` from *FILE* instead of the
  target's own `pyproject.toml`. Needed whenever the user wants
  non-default settings applied to a `wheel`/`env`/`model`/`enrich`
  target, or an `embed-wheel` without `--project-dir` -- those never
  read the current directory or the target's own location, so `--config`
  is the only way to give them a `[tool.pitloom]` at all. On a project
  target it replaces the project's own config outright, not merges with
  it.
- `--pretty` -- indent the JSON for human reading (default: compact).
- `--offline` -- enforce offline execution across `project`, `wheel`,
  `model`, `env`, `embed-wheel`, and `generate`.
- `-v` / `--verbose` -- print effective options and where each came
  from; source labelling (config file vs. default) only for `project`/
  `generate` on a project directory or sdist.
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
- `--build-timeout DURATION` -- with `--allow-build`, cap how long the
  build may run (default 20m, max 7 days; no effect without
  `--allow-build`). See "Choosing `--build-timeout`" below.
- `--id-registry FILE` -- declare the Loom ID registry for this run;
  see "Why element ids stay stable across reruns" above.
- `--update-id-registry`/`--no-update-id-registry` -- add newly-minted
  ids to the declared registry (on by default; no effect on `model`, a
  Hugging Face model, `enrich`, `embed-wheel`, `wheel --embed`); see
  the same section.

## Combine with enrichment

Some requests ask for generation *and* enrichment in one breath -- "generate
SBOM and enrich it", "give me a complete SBOM", "create an SBOM and fill in
information as much as possible", "help me get a full SBOM". The request's
own language signals which of two depths to answer with:

- **Light ask** ("...and enrich it", "with enrichment") -- add `--enrich`:

  ```bash
  loom generate <target> --enrich -o sbom.spdx3.json
  ```

  Runs Pitloom's own deterministic, local, frontmatter-only pass
  (`enrich/readme.py`) in the same command -- no prose, no network, no
  separate skill invocation.

- **Strong ask** ("complete", "as much detail/information as possible",
  "full SBOM") -- generate with `--enrich` too (it's free), then invoke
  the `sbom-enrich` skill on the result for the agentic pass: reading
  README/model-card *prose* and inferring license/dataset relationships
  neither frontmatter nor static extraction can see. Costs more (agent
  reasoning, possibly Hugging Face/PyPI network lookups) -- reasonable
  for an explicit "as much as possible", not a bare "generate an SBOM".

Plain "generate an SBOM" with no enrichment language skips both -- just
run the base generate command.

## Combine with a named standard (NTIA/CISA/G7)

The same one-breath pattern, naming a standard instead of asking for
enrichment in general -- "give me SBOM with CISA 2026 minimum elements",
"generate an SBOM that meets NTIA requirements", "create an AIBOM
compliant with G7 SBOM for AI": generate the base SBOM first (with
`--enrich` too, since it's free and the gap analysis benefits from it),
then invoke `sbom-enrich`'s "Complete a standard's minimum elements"
section on the result -- don't stop at the base `loom generate` call.

```bash
loom generate <target> --enrich -o sbom.spdx3.json
```

## Verify the result

A quick `@graph`-presence sanity check is enough for most runs (see
`references/examples.md`), but for a schema/shape-level conformance
check, use the `sbom-validate` skill (see "See also" below for its URL)
on the output.

## Check stderr for INFO:/WARNING:/ERROR: lines

Pitloom logs to stderr with a grep-able `INFO:`/`WARNING:`/`ERROR:`
prefix -- exactly one of the three, always at the start of the line
(see AGENTS.md's "CLI output" section,
<https://github.com/bact/pitloom/blob/main/AGENTS.md#cli-output>, for the
full convention). `WARNING:` examples: "a config value was too small to
be useful and got normalised instead", "a requested detector isn't
installed". `INFO:` covers normal status worth a human seeing, most
importantly **generation being skipped or scoped down** (e.g. a
Hatchling build hook run that produced no SBOM because it's disabled or
the target isn't `wheel`). Neither always fails the command or shows up
in the output JSON, so after running `loom`, scan the captured stderr
for all three prefixes and mention any hit to the user -- don't let a
real warning or a skipped-generation `INFO:` pass by unmentioned just
because the command exited 0 and (maybe) produced a file.

A `--allow-build` run adds three more prefixes -- exact wording and what
to tell the user for each is in `references/build-timeout.md` (URL in
"See also" below):

- `WARNING: Build: ... timed out after <N>s (--build-timeout) -- ...`
  -- hit the timeout; SBOM still written, from the static fallback.
- `WARNING: Build: received <SIGNAL> during/after the build -- ...` --
  build interrupted (SIGTERM/SIGHUP); Ctrl-C shows a traceback instead.
- `INFO: Build: killed processes ...` / `WARNING: Build: could not
  confirm the processes ... terminated` -- leftover-process cleanup.

## Known limitations -- say so, don't paper over it

Pitloom's dependency/supplier/license extraction is Python-packaging-native:
it reads `pyproject.toml`/`setup.cfg`/`setup.py`, installed
`importlib.metadata`, and the PyPI JSON API. Outside that world, coverage
drops, and the honest move is to tell the user plainly rather than hand
back a JSON file that looks complete but isn't:

- **No Python packaging markers at all** (only `package.json`,
  `Cargo.toml`, `go.mod`, `pom.xml`/`build.gradle`, `Gemfile`,
  `composer.json`, or a `.csproj`/`.sln` -- no
  `pyproject.toml`/`setup.cfg`/`setup.py` anywhere) -- `loom project`/
  `loom generate` already refuses outright ("No project configuration
  found ... Expected pyproject.toml, setup.cfg, or setup.py"). Don't
  work around this (e.g. hand-authoring a fragment to fake coverage) --
  tell the user this ecosystem isn't supported yet.
- **Mixed-ecosystem repos** (`pyproject.toml` alongside
  `package.json`/`Cargo.toml`/etc.) -- generation *succeeds* here,
  silently: the SBOM only inventories the Python side
  (`[project.dependencies]` and what's importable); every non-Python
  dependency is invisible, no error, no NOASSERTION placeholder. If you
  see non-Python ecosystem files, say explicitly that the SBOM covers
  only the Python packaging surface, not the whole repo.
- **Non-PyPI dependencies** (`git+https://...`, a local path
  requirement, or a private-index-only package) get a package entry,
  but supplier/license/hash enrichment has nothing to look up, so those
  fields land on `NOASSERTION` -- correct and honest for "genuinely
  unknown", worth naming when a dependency's entry looks sparse.
- **AI model formats**: broad but not universal (GGUF, ONNX, PyTorch,
  PyTorch PT2/ExecuTorch, Safetensors, Keras, HDF5, NumPy, fastText,
  plus Hugging Face Hub). Any other serialisation isn't recognised at
  all -- same "say so" rule, don't silently skip it.
- **Unsupported build backend** for `loom project`/`loom generate` --
  check `pyproject.toml`'s `[build-system] build-backend` *before*
  generating, not after. Hatchling, setuptools, Poetry, PDM-backend, and
  Flit-core get accurate file-level discovery (files, hashes, Merkle
  root) by default; any other backend (`uv_build`, or one still without
  its own toolchain, e.g. `maturin`/`scikit-build-core`/`meson-python`)
  falls back to a Hatchling-based heuristic and logs a `WARNING:` that
  the file list can be silently incomplete or mis-pathed. Project-level
  metadata (name, version, dependencies, license, authors) is read
  independently and unaffected either way. Say this upfront, don't wait
  for the user to ask why the SBOM looks off -- full detail in
  [docs/cli.md's Generate an SBOM
  section](https://bact.github.io/pitloom/cli/#generate-an-sbom).
  `--allow-build` (`loom project`/`loom generate`/`loom embed-wheel`
  only) closes this gap by invoking the project's own PEP 517 build
  backend for the real file list -- but it executes third-party
  build-time code, so **never pass `--allow-build` (or
  `BuildOptions(allow=True)` via the library API) on the user's behalf
  unless they have explicitly asked for it in this conversation.**
  Mention it as an available option; don't decide to use it yourself.

### Choosing `--build-timeout`

Only after the user has already explicitly asked for `--allow-build`
this conversation -- the hard rule above still stands: never add
`--allow-build` yourself just to be able to use this flag.

`--build-timeout DURATION`: bare number = seconds, or `h`/`m`/`s` units
(`15m`, `1h30m`); default 20m, max 7 days. **In an agent session, always
pass an explicit value** -- Pitloom's default often outlives a harness's
own call limit, and a harness that `SIGKILL`s `loom` orphans the build
process tree.

Full method (estimating build time from read-only signals, sizing
against harness limits, the interactive/non-interactive question flow,
and what to do on timeout) is in `references/build-timeout.md` (URL in
"See also" below); read it before running `--allow-build`.

## See also

- `references/examples.md` -- copy-paste recipes for every target type.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/references/examples.md>
- `references/build-timeout.md` -- estimating/choosing a
  `--build-timeout` value; see "Choosing `--build-timeout`" above.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/references/build-timeout.md>
- The sibling `sbom-enrich` skill -- see "Combine with enrichment" above
  for its agentic enrichment pass, "Combine with a named standard" above
  for its NTIA/CISA/G7 "Complete a standard's minimum elements" section.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/SKILL.md>
- The sibling `sbom-validate` skill -- schema/shape-level conformance
  check for any SBOM this skill produces.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>
- `docs/resources.md` -- SPDX 3 spec, ontology, JSON-LD, and JSON Schema
  links (including the per-minor-version URL pattern) for the exact
  schema/spec a generated SBOM should conform to.
  <https://bact.github.io/pitloom/resources/>
