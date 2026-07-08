---
Created: 2026-07-05
Last-Modified: 2026-07-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom's `sbom` skill: copy-paste recipes

Companion to `../SKILL.md`. These recipes are meant to be run as-is or
adapted with minimal edits.

## Project SBOM, ephemeral run

```bash
uvx pitloom . -o sbom.spdx3.json --pretty
```

## Project SBOM, already-installed Pitloom

```bash
pip install pitloom
loom /path/to/project -o sbom.spdx3.json
```

## AI model SBOM, local file

```bash
uvx --from 'pitloom[aimodel]' pitloom -m model.safetensors -o model.spdx3.json
```

## AI model SBOM, Hugging Face Hub model

```bash
uvx --from 'pitloom[huggingface]' pitloom -m mistralai/Mistral-7B-v0.1 \
  -o mistral.spdx3.json --pretty
```

## Project SBOM, multiple creators

```bash
loom . --creator-name "Acme Corp" --creator-type organization \
       --creator-name "Alice" --creator-email alice@example.com \
       -o sbom.spdx3.json
```

## Verify the result

```bash
python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
assert "@graph" in d, "missing @graph"
print(len(d["@graph"]), "elements")
' sbom.spdx3.json

# Optional schema/SHACL validation:
pip install spdx3-validate
spdx3-validate --json sbom.spdx3.json
```

## See also

- `../SKILL.md` -- operating instructions for this skill.
- The sibling `enrich` skill -- for information an agent can infer that
  Pitloom's extraction cannot see.
