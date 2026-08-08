---
Created: 2026-07-05
Last-Modified: 2026-08-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom's `sbom` skill: copy-paste recipes

Companion to `../SKILL.md`. These recipes are meant to be run as-is or
adapted with minimal edits.

## Project SBOM (directory or sdist), ephemeral run

```bash
uvx pitloom project . -o sbom.spdx3.json --pretty
# or sdist archive
uvx pitloom project dist/mypackage-1.0.0.tar.gz -o sbom.spdx3.json
```

## Project SBOM, already-installed Pitloom

```bash
pip install pitloom
loom project /path/to/project -o sbom.spdx3.json
```

## Built Wheel SBOM

```bash
loom wheel dist/mypackage-1.0.0-py3-none-any.whl -o wheel.spdx3.json
```

## AI model SBOM, local file

```bash
uvx --from 'pitloom[aimodel]' pitloom model model.safetensors -o model.spdx3.json --offline
```

## AI model SBOM, Hugging Face Hub model

```bash
uvx --from 'pitloom[huggingface]' pitloom model mistralai/Mistral-7B-v0.1 \
  -o mistral.spdx3.json --pretty
```

## Deployed SBOM, currently installed environment

```bash
loom env -o env.spdx3.json
```

## Project SBOM, multiple creators

```bash
loom project . --creator-name "Acme Corp" --creator-type organization \
       --creator-name "Alice" --creator-email alice@example.com \
       -o sbom.spdx3.json
```

## Verify the result

```bash
python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
assert "@graph" in d, "missing @graph"
print(f"Valid SPDX 3 graph with {len(d[\"@graph\"])} nodes")
' sbom.spdx3.json
```
