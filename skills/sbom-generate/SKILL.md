---
# Created: 2026-07-05
# Last-Modified: 2026-10-29
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

name: sbom-generate
description: >-
  Generate an SPDX 3 SBOM or AIBOM with Pitloom for a Python project, sdist,
  wheel, installed environment, local AI model file (GGUF, ONNX,
  PyTorch/PT2, Safetensors, Keras, HDF5, NumPy, fastText, CRFsuite), Hugging
  Face model or Git URL (repo or branch/folder page). Triggers:
  "generate/create/give me an SBOM/BOM", "SPDX 3 document", "software bill of
  materials", "dependency inventory", "AIBOM", "document this model's
  provenance". Also combined asks (then hand off to
  sbom-enrich): "generate SBOM and enrich it", "complete/full SBOM", "SBOM
  meeting NTIA/FSCT/CISA 2026/G7/BSI minimum elements". PEP 770 wheel
  embedding ("embed the SBOM in this wheel", "put the SBOM in dist/*.whl",
  "embed-wheel", "signed wheel / RECORD.jws", "--allow-signed-wheel"),
  --allow-build/--build-timeout ("generate with a real build", "the build is
  taking too long") and stable ids ("pin ids", "keep ids stable", "create or
  update an ID registry", "loom id generate/import"). Checking an SBOM is
  sbom-validate; enriching one is sbom-enrich.
license: Apache-2.0
compatibility: >-
  Requires a shell, Python 3.10+ and pitloom >= 0.21.0 (pip, uvx or pipx).
  AI model targets need pitloom[ai] (or a format extra such as
  pitloom[gguf]); --allow-build needs pitloom[build]; --content-type needs
  pitloom[content-type]. Needs network access to install pitloom and for
  PyPI and Hugging Face lookups (not with --offline). Not usable where
  packages cannot be installed, e.g. Claude API code execution.
---

# Generate an SBOM with Pitloom

Pitloom generates SPDX 3 JSON SBOMs for Python projects, sdists, wheels,
AI/ML model files and Python environments. This skill drives its CLI
(`loom` / `pitloom`) and hands off to its siblings `sbom-enrich` and
`sbom-validate` (install all three).

Triggers on natural-language requests (see the description), or explicitly
with `/sbom-generate [target]` (`/pitloom:sbom-generate` via the Claude Code
plugin; `$sbom-generate` in Codex). `target` is optional: a project
directory, sdist/wheel path, local model file, Hugging Face model ID or
`http(s)` Git URL (default: the current directory). For more recipes
(multiple creators, a capped real build), read `references/examples.md`.

## Hard rules

- **`loom generate` needs `-o FILE`** (exit 1 without one). The other
  commands write a default-named file in the current directory (when you need
  the names, read `references/examples.md`, "Where the output goes"). `-o -`
  writes the SBOM to stdout; stdout otherwise holds only
  `PITLOOM_SBOM_OUTPUT_PATH=<path>`.
- **Never add `--allow-build`** (or `BuildOptions(allow=True)` via the
  library API) unless the user asked for it in this conversation. It runs
  the project's own PEP 517 build backend, i.e. third-party build-time
  code. Mention it as an option; don't decide to use it yourself.
- **Never create, edit or pass an ID registry the user did not name** in an
  unasked run. Asked to pin ids, create or update one: "Pinning element ids".
  `sbom-enrich` never does this: it hands the request to this skill.
- **Scan stderr after every `loom` call** (see "Check stderr").

## Requirements

- Python >= 3.10 and **pitloom >= 0.21.0** (earlier releases lack ID
  registry format 3 and Git URL targets): `pip install "pitloom>=0.21.0"`, or
  run ephemeral via `uvx`/`pipx`. Extras take the floor after the extra:
  `"pitloom[ai]>=0.21.0"`.
- AI model targets, and any project or wheel that ships model files, need
  the `ai` extra (`pitloom[ai]`) or a format-specific one
  (`pitloom[gguf]`, `pitloom[huggingface_hub]`, ...; see
  `pyproject.toml` extras:
  <https://github.com/bact/pitloom/blob/main/pyproject.toml>).
  `--allow-build` needs `build`; `--content-type` needs `content-type`.
- **Prepare the licence database before the first `loom` run** of a session
  that reads licences (project, wheel, sdist, model, Git URL): run
  `licenseid update --source packaged` (ephemeral: `uvx --from
  "licenseid>=0.6.0" licenseid update --source packaged`; one command per line
  in PowerShell). No network, skips when current, safe to repeat. Do not
  generate first and fix after: without the database licences stay as written.
  If it fails, say so once, generate anyway and report the resulting
  `WARNING:`/`INFO:` line; never run a network `licenseid update` or
  regenerate unasked (ask; non-interactive: report only). If the preflight
  fails or that line appears, read "Licence detection unavailable" in
  `references/known-limitations.md`.

## Run without installing anything persistent

Prefer an ephemeral run so the user's environment is not polluted. Snippets
are POSIX shell; on Windows use `python` or `py` for `python3` and PowerShell
equivalents (PowerShell 5.1 has no `&&`: one command per line):

```bash
uvx --from "pitloom>=0.21.0" loom generate <target> -o sbom.spdx3.json
pipx run --spec "pitloom>=0.21.0" loom generate <target> -o sbom.spdx3.json
```

Install normally only if neither `uv` nor `pipx` is available:

```bash
pip install "pitloom>=0.21.0"
loom generate <target> -o sbom.spdx3.json
```

These fetch the newest release matching the spec, not the user's installed
`loom`. Where the version matters (a merge or re-run must reproduce a base
SBOM's ids), pin the installed one: `"pitloom==X.Y.Z"`, the number `loom
--version` prints (`Pitloom X.Y.Z`).

## Smart Entrypoint: `loom generate`

Use `loom generate` for automatic target detection:

```bash
loom generate . -o sbom.spdx3.json                  # project directory
loom generate mypackage-1.0.0.tar.gz -o sbom.spdx3.json         # sdist
loom generate dist/pkg-1.0-py3-none-any.whl -o sbom.spdx3.json  # wheel
loom generate models/model.gguf -o sbom.spdx3.json              # model file
loom generate mistralai/Mistral-7B-v0.1 -o sbom.spdx3.json      # HF model ID
loom generate env -o sbom.spdx3.json                # installed venv
loom generate https://gitlab.com/group/project -o sbom.spdx3.json  # Git URL
```

For CI/CD and sandboxed runners, use the explicit subcommands `loom
project|wheel|model|env|merge`; when you need the exact commands, read
`references/examples.md`.

### A Git URL

`loom project <url>` / `loom generate <url> -o FILE` take an `http(s)` Git
URL: the repository's clone URL (recommend this one), or a page naming a
branch/tag/commit and a folder when only that is wanted. The repository is
untrusted (its `[tool.pitloom]` is ignored, **`--allow-build` has no
effect**), `ssh://`/`git@host:path`/`file://` are refused; read the `INFO:`
lines for each redirect and the branch and folder used. A monorepo with no
project at the root fails naming the projects below it: ask which one
(non-interactively, report the list). To explain a refusal or redirect, read
`references/git-url.md`.

## Lock files

For a project directory, Pitloom reads a lock file (`pylock.toml`,
`uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile.lock` or a fully pinned
`requirements.txt`) for exact and transitive versions; `--no-use-lockfile`
opts out. For which file wins or why a version differs, read
`references/lockfile-discovery.md`.

## Pinning element ids (the Loom ID registry)

Element ids are content-addressed, so unchanged source reproduces them with
no registry. A Loom ID registry (a JSON file) pins ids across runs whose
inputs differ. It is used **only when declared**, never searched for:
`--id-registry FILE`, else the `id-registry` config key. Nothing declared: no
registry, silently. Declared but missing, invalid or an old version 2 file:
one `ERROR:`, exit 1. No run ever creates one.

**When the user asks to pin ids** ("pin the ids", "keep ids stable", "create
or update an ID registry"), run `loom id generate PATH... -o FILE` or `loom
id import SBOM -o FILE --project-dir PROJECT` yourself, without asking
again, and report the exact command and every `INFO:`/`WARNING:`/`ERROR:` it
printed. FILE is the one the user names,
else the config's, else `loom-id-registry.json` in the project root. A
rejected version 2 file: ask before deleting it (its pins are lost;
non-interactive: stop and report the `ERROR:`).

**Before generating:** a declared registry is used: tell the user which file,
and that a `project`/`wheel`/`env`/`generate` run may add new ids to it
(`--no-update-id-registry` stops that). None declared and ids must stay
stable: ask, or, non-interactively, use none and report how to pin. Read
`references/id-registry.md` before creating a registry, using the `loom.run`
SDK, or reporting a registry line as a problem.

## Embed an SBOM into a wheel (PEP 770)

To *embed* an SBOM into a built wheel (`.dist-info/sboms/`) rather than write
a standalone file, use `embed-wheel`, not `wheel`:

```bash
loom embed-wheel dist/mypackage-1.0.0-py3-none-any.whl
loom embed-wheel dist/*.whl --project-dir .
```

`--project-dir` makes `embed-wheel` rescan the source project (never inferred
from the current directory): pass it whenever the user has a project
directory; omit it only for a standalone wheel. The `.whl` is changed in
place. For `--sbom FILE`, `wheel --embed`, `--output`, `--sbom-basename`,
`--allow-build` or `--verify --validate` (a pass adds no line; a failure
prints `ERROR:` and exits 1 after the rewrite), read
`references/embed-wheel.md`. Checking an embedded wheel later: `sbom-validate`.

**Signed wheels.** A `RECORD.jws`/`RECORD.p7s` signature would stop verifying
once `RECORD` is rewritten, so Pitloom refuses the wheel (`ERROR:`, exit 1,
untouched). Check first: `unzip -l <wheel> | grep 'RECORD\.'` (no output and
exit 1 means no signature). If found, **before** embedding read
`references/known-limitations.md` ("Signed wheels: what to tell the user"),
explain it in terms of their wheel, and ask before adding
`--allow-signed-wheel` (never unasked; non-interactive: don't add it, report
the refusal and the command to re-run). No signature file: embed without
asking.

A non-ZIP or unreadable wheel is refused with one `ERROR:` (exit 1, nothing
written); a missing `METADATA` only warns (`identity unknown`). If either
line appears, report it and read `references/known-limitations.md` ("Refused
wheels and unknown identity").

## Flags: what to add, what to leave out

Never add these unless the request or the user calls for it:

- `--allow-build` (hard rule above) and `--allow-signed-wheel` ("Signed
  wheels"): only with the user's agreement.
- `--trust-wheel-model`: only when the user states the wheel is trusted (its
  readers can crash, hang or exhaust memory on a hostile model file).
- `--scan-model-usage`: only when asked which code loads a model.
- `--content-type`: only when the request implies wanting MIME data.
- `--enrich`: only for a project directory or local model file (see below).

Everything else is on request (`--config FILE`, `--pretty`, `--offline`,
`-v`, `--creator-*`, `--creation-*`, `--id-registry`, ...). If the user asks
for one, or a `WARNING: Options:` line names one, read
`references/cli-flags.md`.

## Combine with enrichment or a named standard

A request may ask for generation plus more; plain "generate an SBOM" just
runs the base command.

- **Light** ("...and enrich it", "with enrichment"): `loom generate <target>
  --enrich -o sbom.spdx3.json` (Pitloom's own local pass: no prose, no
  network).
- **Strong** ("complete", "full SBOM", "as much detail as possible"):
  generate with `--enrich`, then invoke `sbom-enrich` on the result for the
  agentic pass (README/model-card prose, inferred licences and datasets;
  costs more, outside sources consent-gated). Not for a bare "generate an
  SBOM".
- **Named standard** (NTIA 2021, FSCT 2024, CISA 2026, G7 SBOM for AI 2026,
  BSI TR-03183-2; "meets NTIA requirements", "with CISA 2026 minimum
  elements"): generate with `--enrich`, then run `sbom-enrich`'s "Complete a
  standard's minimum elements" on the result.

`--enrich` applies only to a project directory or local model file; for any
other target skip it and go straight to the `sbom-enrich` hand-off.
Registered fragments merge only into a project-directory SBOM, so for any
other target the hand-off ends with an unmerged fragment (`sbom-enrich`,
"Where a fragment can be merged").

## Validate the result

Run the `sbom-validate` skill on the output: a schema/SHACL check catches a
missing required property or a wrong relationship type. The `@graph` check in
`references/examples.md` is only a fallback when `pitloom[validate]` cannot be
installed; it is not a substitute.

## Check stderr for INFO:/WARNING:/ERROR: lines

Pitloom logs to stderr with a grep-able `INFO:`/`WARNING:`/`ERROR:`
prefix -- exactly one of the three, always at the start of the line.
`WARNING:` marks a recovered problem or a deviation (a config value
normalised, a detector not installed, an option with no effect for this
target); `INFO:` marks normal status, above all **generation skipped or
scoped down**. Neither always fails the command or reaches the output JSON,
so scan the captured stderr for all three prefixes after every `loom` call
and mention any hit to the user, even when the command exited 0 and produced
a file. A `WARNING: Options: ...` line about a flag *you* added
means it did not apply to that target: drop it next time.

For `Build: ...` lines from an `--allow-build` run, read
`references/build-timeout.md`; for `ID registry: ...` lines (which are
expected), `references/id-registry.md`.

## Known limitations -- say so, don't paper over it

Pitloom's extraction is Python-packaging-native; outside it, coverage drops.
Tell the user plainly rather than hand back a JSON file that looks complete
but isn't. For the wording and bounds of any case, read
`references/known-limitations.md`.

- **No Python packaging markers** (no `pyproject.toml`/`setup.cfg`/
  `setup.py`; only `package.json`, `Cargo.toml`, `go.mod`, etc.):
  `loom project`/`loom generate` refuse with an `ERROR:`. Don't work
  around it (no hand-authored fragment to fake coverage); say the
  ecosystem isn't supported yet.
- **Mixed-ecosystem repos** (`pyproject.toml` beside `package.json`/
  `Cargo.toml`/etc.): generation succeeds *silently*, Python side only. Say so.
- **Non-PyPI dependencies** (`git+https://...`, local path, private index)
  get `NOASSERTION` copyright, no supplier/hash/licence unless installed;
  name them.
- **AI model formats** are broad, not universal: say so when one is not
  scanned.
- **AI model stubs:** an `ai_AIPackage` with no `ai_*` property and no
  `Source: <model file> | Field: ...` comment was not read. Name the cause
  from stderr (wheel gate `INFO:`, missing library: install `pitloom[ai]`,
  corrupt file, size cap or budget, Git LFS pointer: relay Pitloom's advice,
  never run the fix yourself) and tell the user. Never raise a ceiling or add
  `--trust-wheel-model` on your own. A failed read leaves a stub with a
  `WARNING:` (exit 0); a file whose header contradicts its suffix is no model
  (`WARNING:`, no `ai_AIPackage`), and `loom model FILE`/`loom enrich` refuse
  it (`ERROR:`, exit 1).
- **Model producer, parameter count** exist for some formats only (absence is
  no failure); **a name ending `...~<hex>`, missing labels or `\u202e` in
  text** are Pitloom's caps and escapes (one `WARNING: FORMAT=<fmt>
  FILE=<path>:` each; the original is in the model file).
- **Unsupported build backend:** check `[build-system] build-backend`
  *before* generating. Hatchling, setuptools, Poetry, PDM-backend and
  Flit-core get accurate file discovery; any other (`uv_build`, `maturin`,
  `scikit-build-core`, `meson-python`) falls back to a heuristic with a
  `WARNING:` that the file list can be incomplete. Say so upfront.
  `--allow-build` closes the gap but is subject to the hard rule.

### Choosing `--build-timeout`

Only after the user has already explicitly asked for `--allow-build` this
conversation -- never add `--allow-build` yourself just to use this flag.

`--build-timeout DURATION`: bare number = seconds, or `h`/`m`/`s` units
(`15m`, `1h30m`); default 20m, max 7 days; no effect without `--allow-build`.
**In an agent session, always pass an explicit value**: Pitloom's default
often outlives a harness's own call limit, and a harness that `SIGKILL`s
`loom` orphans the build process tree.

Before running `--allow-build`, read `references/build-timeout.md`
(estimating the build time, sizing against harness limits, the interactive
and non-interactive question flow, what to do on timeout). The `sbom-enrich`
and `sbom-validate` skills point here for the same rule.

## See also

- `sbom-enrich`: the agentic enrichment pass and minimum-elements checks.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/SKILL.md>
- `sbom-validate`: schema/SHACL check of any SBOM this skill produces.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>
- `docs/resources.md`: SPDX 3 spec, ontology and JSON Schema links.
  <https://bact.github.io/pitloom/resources/>
