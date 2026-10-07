---
Created: 2026-07-05
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom's `sbom-generate` skill: copy-paste recipes

Companion to `../SKILL.md`. These recipes are meant to be run as-is or
adapted with minimal edits. Snippets are POSIX shell; on Windows use
`python` or `py` for `python3`, save a multi-line `python -c '...'` to a
`.py` file, and use PowerShell equivalents.

## Project SBOM (directory or sdist), ephemeral run

```bash
uvx --from "pitloom>=0.20.1" loom project . -o sbom.spdx3.json --pretty
# or sdist archive
uvx --from "pitloom>=0.20.1" loom project dist/mypackage-1.0.0.tar.gz -o sbom.spdx3.json
```

## Project SBOM with lock file (resolved transitive dependencies)

```bash
# Automatically discovers pylock.toml, uv.lock, poetry.lock, pdm.lock,
# Pipfile.lock, or pinned requirements.txt in the project directory:
loom project . -o sbom.spdx3.json --pretty
```

## Project SBOM, already-installed Pitloom

```bash
pip install "pitloom>=0.20.1"
loom project /path/to/project -o sbom.spdx3.json
```

## Built Wheel SBOM

```bash
loom wheel dist/mypackage-1.0.0-py3-none-any.whl -o wheel.spdx3.json
```

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
uvx --from 'pitloom[ai]>=0.20.1' loom model model.safetensors -o model.spdx3.json
```

## AI model SBOM, Hugging Face Hub model

```bash
uvx --from 'pitloom[huggingface_hub]>=0.20.1' loom model mistralai/Mistral-7B-v0.1 \
  -o mistral.spdx3.json --pretty
```

## Deployed SBOM, currently installed environment

```bash
loom env -o env.spdx3.json
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
  (minimal: `pip install "pitloom[validate]>=0.20.1"` then
  `loom fragment validate sbom.spdx3.json`).
  <https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>
- `docs/resources.md` -- SPDX 3 spec, ontology, and JSON Schema links.
  <https://bact.github.io/pitloom/resources/>
