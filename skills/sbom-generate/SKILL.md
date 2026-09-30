---
# Created: 2026-07-05
# Last-Modified: 2026-09-30
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

name: sbom-generate
description: >-
  Generate an SPDX 3 SBOM or AIBOM with Pitloom for a Python project, sdist,
  built wheel, installed environment, local AI model file (GGUF, ONNX,
  PyTorch/PT2, Safetensors, Keras, HDF5, NumPy, fastText) or Hugging Face
  model. Triggers: "generate/create/give me an SBOM/BOM", "gen SBOM of this
  model", "SBOM of this project", "SPDX 3 document", "software bill of
  materials", "dependency inventory", "AIBOM", "document this model's
  provenance". Also owns
  combined asks, generating first, then handing off to sbom-enrich:
  "generate SBOM and enrich it", "complete/full SBOM", "SBOM meeting CISA
  2026/NTIA/G7 minimum elements". Also PEP 770 wheel embedding ("embed the
  SBOM in this wheel", "embed SBOM to python wheel", "put the SBOM in
  dist/*.whl", "create PEP 770 SBOM", "embed-wheel") and
  --allow-build/--build-timeout ("generate with a real build", "the build is
  taking too long"). Checking an existing SBOM is sbom-validate; enriching
  one is sbom-enrich.
license: Apache-2.0
compatibility: >-
  Requires a shell, Python 3.10+ and pitloom >= 0.20.0 (pip, uvx or pipx).
  AI model targets need pitloom[ai] (or a format extra such as
  pitloom[gguf]); --allow-build needs pitloom[build]; --content-type needs
  pitloom[content-type]. Needs network access to install pitloom and for
  PyPI and Hugging Face lookups (not with --offline). Not usable where
  packages cannot be installed, e.g. Claude API code execution.
---

# Generate an SBOM with Pitloom

Pitloom is a command-line tool that generates SPDX 3 JSON SBOMs for
Python projects, sdist archives, wheels, AI/ML model files, and Python
environments. This skill drives Pitloom's existing CLI (`loom` / `pitloom`).

This skill is one of three (`sbom-generate`, `sbom-enrich`,
`sbom-validate`) meant to be installed together: it hands off to the other
two.

Triggers automatically on natural-language requests (see the trigger
phrasings above), or invoke it explicitly with `/sbom-generate [target]`
(`/pitloom:sbom-generate [target]` when installed via the Claude Code
plugin; the syntax depends on the client, e.g. `$sbom-generate` in Codex).
`target` is optional -- a project directory, an sdist/wheel path, a local
model file, or a Hugging Face model ID; omit it to default to the current
directory.

See `references/examples.md` for copy-paste recipes.

## Hard rules

- **`loom generate` needs `-o FILE`.** It dispatches across target types
  with no single natural default filename, so it exits 1 without one.
  `project`/`wheel`/`model`/`env` each have a default filename.
- **Never add `--allow-build`** (or `BuildOptions(allow=True)` via the
  library API) unless the user asked for it in this conversation. It runs
  the project's own PEP 517 build backend, i.e. third-party build-time
  code. Mention it as an option; don't decide to use it yourself.
- **Never create, edit or pass an ID registry the user did not name**
  (see "Pinning element ids").
- **Scan stderr after every `loom` call** (see "Check stderr").

## Requirements

- Python >= 3.10 and **pitloom >= 0.20.0** (earlier releases lack
  `--id-registry`, `loom id` and `--build-timeout`), the `loom`/`pitloom`
  entry point -- `pip install "pitloom>=0.20.0"`, or run ephemeral via
  `uvx`/`pipx`. Extras take the floor after the extra:
  `"pitloom[ai]>=0.20.0"`.
- AI model targets need the `ai` extra (`pitloom[ai]`) or a
  format-specific one (`pitloom[huggingface_hub]`, `pitloom[gguf]`,
  etc. -- see `pyproject.toml`'s `[project.optional-dependencies]`,
  <https://github.com/bact/pitloom/blob/main/pyproject.toml>).
- `--allow-build` needs the `build` extra (PyPA `build`);
  `--content-type` needs the `content-type` extra (`magika`).

## Run without installing anything persistent

Prefer an ephemeral run so the user's environment is not polluted.
Snippets are POSIX shell; on Windows use `python` or `py` for `python3`,
and PowerShell equivalents (PowerShell 5.1 has no `&&`: run the commands
one per line):

```bash
uvx --from "pitloom>=0.20.0" loom generate <target> -o sbom.spdx3.json
```

or

```bash
pipx run --spec "pitloom>=0.20.0" loom generate <target> -o sbom.spdx3.json
```

Fall back to a normal install only if neither `uv` nor `pipx` is available:

```bash
pip install "pitloom>=0.20.0"
loom generate <target> -o sbom.spdx3.json
```

`uvx --from` and `pipx run --spec` fetch the newest release matching the
spec, not the user's installed `loom`. Where the version matters (a
merge or re-run must reproduce a base SBOM's ids), pin the installed
one: `"pitloom==X.Y.Z"`, `X.Y.Z` being the number `loom --version` prints
(`Pitloom X.Y.Z`).

`loom` and `pitloom` are two names for the same console-script entry point.

## Smart Entrypoint: `loom generate`

Use `loom generate` for automatic target detection:

```bash
loom generate . -o sbom.spdx3.json                              # project directory -> Source SBOM
loom generate mypackage-1.0.0.tar.gz -o sbom.spdx3.json         # sdist archive     -> Source SBOM
loom generate dist/pkg-1.0-py3-none-any.whl -o sbom.spdx3.json  # wheel package     -> Analyzed SBOM
loom generate models/model.gguf -o sbom.spdx3.json              # local model file  -> AI Model SBOM
loom generate mistralai/Mistral-7B-v0.1 -o sbom.spdx3.json      # Hugging Face model ID -> AI Model SBOM
loom generate env -o sbom.spdx3.json                            # installed venv    -> Deployed SBOM
```

## Explicit Target Subcommands

For deterministic execution in CI/CD and sandboxed runners:

```bash
# 1. Project Directory or Sdist Archive (Source SBOM)
loom project . -o sbom.spdx3.json
loom project dist/mypackage-1.0.0.tar.gz

# 2. Built Wheel Package (Analyzed SBOM)
loom wheel dist/mypackage-1.0.0-py3-none-any.whl -o wheel.spdx3.json

# 3. AI Model Asset (AIBOM)
loom model models/model.safetensors
loom model mistralai/Mistral-7B-v0.1        # Hugging Face model ID

# 4. Deployed Environment (Installed venv)
loom env -o env.spdx3.json

# 5. Fragment Merging
loom merge .spdx3-fragments/ -o combined.spdx3.json
```

## Lock files

For a project directory, Pitloom reads a lock file (`pylock.toml`,
`uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile.lock` or a fully pinned
`requirements.txt`) for exact and transitive dependency versions. On by
default; `--no-use-lockfile` opts out. Formats, priority and effects:
`references/lockfile-discovery.md`.

## Pinning element ids (the Loom ID registry)

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
or invalid: one `ERROR:`, exit 1. Generating runs also add newly minted
ids to a declared registry; no run ever creates one.

What it pins (files, packages, AI models), which commands write to it and
how to stop that, how to create one with `loom id generate`/`loom id
import`, and what its log lines mean: `references/id-registry.md`. Read it
before creating a registry or reporting a registry line as a problem.

**Choose the registry before generating.** Skip this for a Hugging Face
model and for `embed-wheel --sbom` (`--id-registry` is ignored there,
with a `WARNING:`). Otherwise:

1. Always: if the applicable config declares a registry, it is used --
   tell the user which file, and that a `project`, `wheel`, `env` or
   `generate` run may add new ids to it (`references/id-registry.md`,
   "Harvest"); `model`, `enrich`, `embed-wheel` and the hook only read it.
2. None declared, and ids must stay stable across runs or a fragment
   will be merged after the source changes:
   - Interactive: ask "Pin ids with a Loom ID registry? If yes, which
     file -- an existing one, or create `loom-id-registry.json`?"
     Yes with a file: pass `--id-registry FILE` (create it first, per the
     reference, if new). No: generate without one.
   - Non-interactive: use none, create nothing, and report "No Loom ID
     registry used (none declared). To pin ids, run `loom id generate
     <PATH> -o loom-id-registry.json` in the project directory, then
     declare it as the INFO line says (project target) or pass
     `--id-registry loom-id-registry.json` on each run (other targets)."

## Embed an SBOM into a wheel (PEP 770)

For a request to *embed* an SBOM into a built wheel rather than write it
as a standalone file -- PEP 770's `.dist-info/sboms/` convention -- use
`embed-wheel` instead of `wheel`:

```bash
loom embed-wheel dist/mypackage-1.0.0-py3-none-any.whl        # standalone: no project scan
loom embed-wheel dist/*.whl --project-dir .   # multiple wheels, Build SBOM
```

`--project-dir` is required to have `embed-wheel` rescan the source
project (never inferred from the current directory) -- pass it whenever
the user has a project directory to scan; omit it only for a genuinely
standalone wheel. `embed-wheel` also accepts `--allow-build` (see
"Choosing `--build-timeout`").

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
match) and works on any wheel regardless of build backend, unlike the
Hatchling-specific build hook. Full flags, including `--output` (rejected
when more than one wheel matches) and `--sbom-basename`:
<https://bact.github.io/pitloom/cli/>.

To check the wheel's embedded SBOM right after this same embed, pass
`--verify`/`--validate` to `embed-wheel` itself -- both checks share the
one disk read this embed already did:

```bash
loom embed-wheel dist/*.whl --project-dir . --verify --validate
```

For checking an already-embedded wheel later, use the `sbom-validate`
skill ("Validate a wheel's embedded SBOM").

## Useful flags

- `-o FILE` / `--output FILE` -- explicit output path.
- `--config FILE` -- read `[tool.pitloom]` from *FILE* instead of the
  target's own `pyproject.toml`. The only way to give a `wheel`/`env`/
  `model` target, or `enrich`/`embed-wheel` without `--project-dir`, a
  `[tool.pitloom]` at all (they never read the current directory). On a
  project target it replaces the project's own config outright, not merges
  with it.
- `--pretty` -- indent the JSON for human reading (default: compact).
- `--offline` -- forbid network access (`project`, `wheel`, `env`,
  `embed-wheel`; `generate` follows its target). On a local model file it
  has no effect (a `WARNING:` if passed); on a Hugging Face model it is an
  error, as nothing can be fetched.
- `-v` / `--verbose` -- print effective options (with config-vs-default
  labels only for `project`, and `generate` on a project directory or
  sdist; elsewhere it prints nothing and logs a no-effect `WARNING:`).
- `--creator-name NAME`, `--creator-email EMAIL` -- name who created the SBOM.
- `--enrich` / `--no-enrich` -- Pitloom's own deterministic, local,
  frontmatter-only enrichment pass, in the same generate call. Add it only
  for a project directory or a local model file: on a wheel, env, sdist
  or Hugging Face target it has no effect and logs a `WARNING:`. See
  "Combine with enrichment or a named standard".
- `--extract-file-header` / `--no-extract-file-header` -- per-file SPDX
  header tag scanning (copyright, contributor, license, file type). On by
  default; cheap, no need to pass it explicitly.
- `--scan-model-usage` / `--no-scan-model-usage` -- record which Python
  files reference each discovered AI model file (`hasDataFile`), for a
  project directory (`project`, `generate <dir>`, `embed-wheel
  --project-dir`, and the Hatchling hook via the `scan-model-usage` config
  key) or a built wheel (`wheel`, `wheel --embed`, `embed-wheel` without
  `--project-dir`; models inside the wheel are found either way). Off by
  default and **opt-in only**: add it only when the request asks which code
  loads a model. Models are found either way; when the setting was
  never given, one `INFO:` line says how many were found and names this flag
  (once per run; silent after an explicit `--no-scan-model-usage` or
  `scan-model-usage = false`). sdist, env, model-file and Hugging Face
  targets, `enrich` and `embed-wheel --sbom` warn that it has no effect.
- `--content-type` / `--no-content-type` -- per-file content-type/MIME
  detection (`magika`, or a filename-extension guess). Off by default and
  **opt-in only**: add it only when the request implies wanting that data,
  since it costs ~5ms/file with `magika`. `--content-type-method
  {auto,magika,extension}` forces a detector (default `auto`).
- `--build-timeout DURATION` -- with `--allow-build` only; see "Choosing
  `--build-timeout`".
- `--id-registry FILE` -- declare the Loom ID registry for this run.
- `--update-id-registry`/`--no-update-id-registry` -- add newly minted
  ids to the declared registry (on by default; a `WARNING:` where it has
  no effect). Both registry flags: see "Pinning element ids".

## Combine with enrichment or a named standard

Some requests ask for generation plus more in one breath. The request's
own language signals the depth; plain "generate an SBOM" with none of it
just runs the base generate command.

| Request | Do |
| :--- | :--- |
| Light: "...and enrich it", "with enrichment" | `loom generate <target> --enrich -o sbom.spdx3.json`. Pitloom's own local pass (`enrich/readme.py`): no prose, no network, no separate skill. |
| Strong: "complete", "full SBOM", "as much detail/information as possible" | Generate with `--enrich` too, then invoke `sbom-enrich` on the result for the agentic pass: README/model-card *prose*, inferred license and dataset relationships. Costs more (agent reasoning, and outside sources such as PyPI/Hugging Face, each consent-gated by `sbom-enrich` step 5). Reasonable for an explicit "as much as possible", not for a bare "generate an SBOM". |
| Named standard: "meets NTIA requirements", "with CISA 2026 minimum elements", "AIBOM compliant with G7 SBOM for AI" | Generate with `--enrich` too, then invoke `sbom-enrich`'s "Complete a standard's minimum elements" section on the result. Don't stop at the base `loom generate` call. |

`--enrich` only applies to a project directory or local model file (see
"Useful flags"); for any other target, skip it and go straight to the
`sbom-enrich` hand-off. Registered fragments merge only into a
project-directory SBOM, so for a model file, Hugging Face, wheel, env or
sdist target the hand-off ends with an unmerged fragment (`sbom-enrich`,
"Where a fragment can be merged").

## Validate the result

Run the `sbom-validate` skill on the output: a schema/SHACL check catches
a missing required property or a wrong relationship type. The `@graph`
sanity check in `references/examples.md` is only a fallback for when
`pitloom[validate]` cannot be installed; it is not a substitute.

## Check stderr for INFO:/WARNING:/ERROR: lines

Pitloom logs to stderr with a grep-able `INFO:`/`WARNING:`/`ERROR:`
prefix -- exactly one of the three, always at the start of the line
(see AGENTS.md's "CLI output" section,
<https://github.com/bact/pitloom/blob/main/AGENTS.md#cli-output>).
`WARNING:` marks a recovered problem or a deviation (a config value
normalised, a requested detector not installed, an option with no effect
for this target); `INFO:` marks normal status, above all **generation
skipped or scoped down** (e.g. a Hatchling build hook run that produced no
SBOM because it is disabled). Neither always fails the command or reaches
the output JSON, so scan the captured stderr for all three prefixes after
every `loom` call and mention any hit to the user, even when the command
exited 0 and produced a file. A `WARNING: Options: ...` line about a flag
*you* added means it did not apply to that target: drop it next time.

Two families have their own reference: `WARNING: Build: ...`/`INFO:
Build: ...` lines from an `--allow-build` run (timeout, interrupt,
leftover processes; wording and what to tell the user:
`references/build-timeout.md`), and `INFO:`/`WARNING: ID registry: ...`
lines (which ones are expected: `references/id-registry.md`).

## Known limitations -- say so, don't paper over it

Pitloom's extraction is Python-packaging-native; outside it, coverage
drops. Tell the user plainly rather than hand back a JSON file that looks
complete but isn't. Per-case detail: `references/known-limitations.md`.

- **No Python packaging markers** (no `pyproject.toml`/`setup.cfg`/
  `setup.py`; only `package.json`, `Cargo.toml`, `go.mod`, etc.):
  `loom project`/`loom generate` refuse with an `ERROR:`. Don't work
  around it (no hand-authored fragment to fake coverage); say the
  ecosystem isn't supported yet.
- **Mixed-ecosystem repos** (`pyproject.toml` beside `package.json`/
  `Cargo.toml`/etc.): generation succeeds *silently* and inventories only
  the Python side. Say the SBOM covers the Python packaging surface, not
  the whole repo.
- **Non-PyPI dependencies** (`git+https://...`, local path, private index)
  get an entry whose supplier/license/hash stay `NOASSERTION`; name it
  when an entry looks sparse.
- **AI model formats** are broad, not universal (see the description). An
  unrecognised serialisation is not scanned: say so, don't skip silently.
- **Unsupported build backend:** check `[build-system] build-backend`
  *before* generating. Hatchling, setuptools, Poetry, PDM-backend and
  Flit-core get accurate file discovery; any other (`uv_build`,
  `maturin`, `scikit-build-core`, `meson-python`) falls back to a
  heuristic with a `WARNING:` that the file list can be incomplete or
  mis-pathed. Say so upfront. `--allow-build` closes the gap but is
  subject to the hard rule above.

### Choosing `--build-timeout`

Only after the user has already explicitly asked for `--allow-build` this
conversation -- never add `--allow-build` yourself just to use this flag.

`--build-timeout DURATION`: bare number = seconds, or `h`/`m`/`s` units
(`15m`, `1h30m`); default 20m, max 7 days; no effect without
`--allow-build`. **In an agent session, always pass an explicit value** --
Pitloom's default often outlives a harness's own call limit, and a
harness that `SIGKILL`s `loom` orphans the build process tree.

Full method (estimating build time from read-only signals, sizing
against harness limits, the interactive/non-interactive question flow,
and what to do on timeout) is in `references/build-timeout.md`; read it
before running `--allow-build`. The `sbom-enrich` and `sbom-validate`
skills point here for the same rule.

## See also

- `references/examples.md` -- copy-paste recipes for every target type.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/references/examples.md>
- `references/id-registry.md` -- what an ID registry pins, creating one,
  its log lines.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/references/id-registry.md>
- `references/lockfile-discovery.md` -- lock formats and their effect.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/references/lockfile-discovery.md>
- `references/known-limitations.md` -- what to tell the user when coverage
  is partial.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/references/known-limitations.md>
- `references/build-timeout.md` -- estimating/choosing a
  `--build-timeout` value.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/references/build-timeout.md>
- The sibling `sbom-enrich` skill -- the agentic enrichment pass and the
  NTIA/CISA/G7 "Complete a standard's minimum elements" section.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/SKILL.md>
- The sibling `sbom-validate` skill -- schema/SHACL conformance check for
  any SBOM this skill produces.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>
- `docs/resources.md` -- SPDX 3 spec, ontology, JSON-LD, and JSON Schema
  links (including the per-minor-version URL pattern) for the exact
  schema/spec a generated SBOM should conform to.
  <https://bact.github.io/pitloom/resources/>
