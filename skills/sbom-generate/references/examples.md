---
Created: 2026-07-05
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom's `sbom-generate` skill: copy-paste recipes

Companion to `../SKILL.md`. These recipes are meant to be run as-is or
adapted with minimal edits. Snippets are POSIX shell; on Windows use
`python` or `py` for `python3`, save a multi-line `python -c '...'` to a
`.py` file, and use PowerShell equivalents.

## Where the output goes

Without `-o`, `project` writes `<name>-<version>.spdx3.json` (`sbom.spdx3.json`
for a project with no name), `wheel` and `model` write `<file name>.spdx3.json`
(e.g. `model.onnx.spdx3.json`) and `env` writes `deployed-environment.spdx3.json`,
all in the current directory; `generate` exits 1 without `-o`. Stdout is one line, `PITLOOM_SBOM_OUTPUT_PATH=<path>`;
`-o -` writes the SBOM there instead. `embed-wheel` prints one
`WHEEL=<name> SBOM=<path inside the wheel>` line per wheel (default `<name>-<version>.spdx3.json` under `.dist-info/sboms/`;
`--sbom-basename` or the config key `sbom-basename` changes it).

## Project SBOM (directory or sdist), ephemeral run

```bash
uvx --from "pitloom>=0.21.0" loom project . -o sbom.spdx3.json --pretty
# or sdist archive
uvx --from "pitloom>=0.21.0" loom project dist/mypackage-1.0.0.tar.gz -o sbom.spdx3.json
```

## Project SBOM from a Git URL

```bash
# A repository (a GitLab URL without .git works: Pitloom follows the redirect)
loom project https://gitlab.com/group/project -o sbom.spdx3.json
# A folder of a monorepo, from the page you were looking at
loom project https://github.com/owner/repo/tree/main/services/api -o api.spdx3.json
loom project https://codeberg.org/owner/repo/src/branch/main/svc -o svc.spdx3.json
# Read stderr: every redirect and every branch/folder used is an INFO: line
```

## Project SBOM with lock file (resolved transitive dependencies)

```bash
# Automatically discovers pylock.toml, uv.lock, poetry.lock, pdm.lock,
# Pipfile.lock, or pinned requirements.txt in the project directory:
loom project . -o sbom.spdx3.json --pretty
```

## Project SBOM, already-installed Pitloom

```bash
pip install "pitloom>=0.21.0"
loom project /path/to/project -o sbom.spdx3.json
```

## Licence database (once per user)

Without it, licences stay as written and one `WARNING: licenseid database
cannot be used: ...` line says so (`known-limitations.md`):

```bash
licenseid update                     # from an install of pitloom
uvx --from "licenseid>=0.6.0" licenseid update --source packaged  # no install; the list licenseid ships
```

## Built Wheel SBOM

```bash
loom wheel dist/mypackage-1.0.0-py3-none-any.whl -o wheel.spdx3.json
```

## Pin ids with a Loom ID registry (only when the user asks)

```bash
loom id generate src data -o loom-id-registry.json   # files, AI models
loom id generate src -e my-pkg:software_Package -o loom-id-registry.json
loom id import sbom.spdx3.json -o loom-id-registry.json   # reuse an SBOM's ids
loom project . --id-registry loom-id-registry.json -o sbom.spdx3.json
```

stdout is `PITLOOM_ID_REGISTRY_PATH=<path>`; relay the `INFO:`/`WARNING:`
lines (see `id-registry.md`).

## Embed an SBOM into a built wheel (PEP 770)

```bash
loom embed-wheel dist/mypackage-1.0.0-py3-none-any.whl --project-dir .
# or, for a single wheel's own Analyzed SBOM, no project dir:
loom wheel dist/mypackage-1.0.0-py3-none-any.whl --embed
```

Confirm the embed:

```bash
python3 -c '
import zipfile, sys
with zipfile.ZipFile(sys.argv[1]) as zf:
    sboms = [n for n in zf.namelist() if "/sboms/" in n]
    assert sboms, "no SBOM embedded"
    print(f"Embedded: {sboms}")
' dist/mypackage-1.0.0-py3-none-any.whl
```

## AI model SBOM, local file

```bash
uvx --from 'pitloom[ai]>=0.21.0' loom model model.safetensors -o model.spdx3.json
```

## AI model SBOM, Hugging Face Hub model

```bash
uvx --from 'pitloom[huggingface_hub]>=0.21.0' loom model mistralai/Mistral-7B-v0.1 \
  -o mistral.spdx3.json --pretty
```

## Deployed SBOM, currently installed environment

```bash
loom env -o env.spdx3.json
```

## Explicit target subcommands (CI/CD, sandboxed runners)

For deterministic execution, name the target kind instead of `loom generate`:

```bash
loom project . -o sbom.spdx3.json
loom project dist/mypackage-1.0.0.tar.gz
loom wheel dist/mypackage-1.0.0-py3-none-any.whl -o wheel.spdx3.json
loom model models/model.safetensors
loom model mistralai/Mistral-7B-v0.1        # Hugging Face model ID
loom env -o env.spdx3.json
loom merge .spdx3-fragments/ -o combined.spdx3.json
```

## Project SBOM with a real build, capped build time

Only after the user has explicitly asked for `--allow-build` -- see
`../SKILL.md`'s "Hard rules" and "Choosing `--build-timeout`":

```bash
loom project . --allow-build --build-timeout 8m -o sbom.spdx3.json
```

## Project SBOM, multiple creators

```bash
loom project . --creator-name "Acme Corp" --creator-type organization \
       --creator-name "Alice" --creator-email alice@example.com \
       -o sbom.spdx3.json
```

## Fallback check when `pitloom[validate]` cannot be installed

A `@graph`-presence sanity check only. It cannot catch a missing required
property or a wrong relationship type: use the `sbom-validate` skill on
`sbom.spdx3.json` whenever it can be installed.

```bash
python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
assert "@graph" in d, "missing @graph"
print("@graph present:", len(d["@graph"]), "nodes (not validated)")
' sbom.spdx3.json
```

## See also

- `../SKILL.md` -- operating instructions for this skill.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/SKILL.md>
- The sibling `sbom-validate` skill -- schema/SHACL conformance check
  (minimal: `pip install "pitloom[validate]>=0.21.0"` then
  `loom fragment validate sbom.spdx3.json`).
  <https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>
- `docs/resources.md` -- SPDX 3 spec, ontology, and JSON Schema links.
  <https://bact.github.io/pitloom/resources/>
