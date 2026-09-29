---
Created: 2026-08-10
Last-Modified: 2026-09-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom's `sbom-validate` skill: copy-paste recipes

Companion to `../SKILL.md`. These recipes are meant to be run as-is or
adapted with minimal edits. Snippets are POSIX shell; on Windows use
PowerShell equivalents (PowerShell 5.1 has no `&&`: run the commands one
per line).

## Validate a single SBOM

```bash
pip install spdx3-validate  # if not already installed
spdx3-validate --json sbom.spdx3.json
```

## Validate quietly (no progress spinner, useful in CI logs)

```bash
spdx3-validate --json sbom.spdx3.json --quiet
```

## Validate a base SBOM plus a fragment that declares an ExternalMap

Checks each document individually, then the merged graph -- catches an
`ExternalMap`-referenced `spdxId` that the fragment expects but the base
document doesn't actually provide. Only for a fragment that declares an
`ExternalMap` for the base ids it uses:

```bash
spdx3-validate --json sbom.spdx3.json --json fragments/external.spdx3.json
```

A Pitloom enrichment fragment declares none, so this fails (exit 1) for
it, alone or with its base. Validate the merged SBOM instead:

```bash
loom project . -o sbom.spdx3.json   # fragment registered in [tool.pitloom.fragment]
spdx3-validate --json sbom.spdx3.json
```

## Validate several documents without the merged-graph check

```bash
spdx3-validate --json a.spdx3.json --json b.spdx3.json --no-merge
```

## Force a specific SPDX version

`spdx3-validate` auto-detects the SPDX version from each document's
`@context`; override it if a document's `@context` is ambiguous or
missing:

```bash
spdx3-validate --json sbom.spdx3.json --spdx-version 3.0.1
```

## Generate and validate in one go

```bash
loom project . -o sbom.spdx3.json && spdx3-validate --json sbom.spdx3.json
```

Write to a file: don't pipe `loom project . -o -` into the validator.
`loom` still prints a `PITLOOM_SBOM_OUTPUT_PATH=-` line after the JSON on
stdout, so `spdx3-validate` fails with `JSONDecodeError: Extra data`.

## Interpreting the result

- Exit code `0`: valid, no output beyond progress.
- Non-zero exit code: at least one error, printed per-document as
  `ERROR: JSON Schema validation failed for <file>:` or `ERROR: SHACL
  Validation failed for <file>:`, followed by the failing JSON path(s)
  and a description.

## See also

- `../SKILL.md` -- operating instructions for this skill.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-validate/SKILL.md>
- The sibling `sbom-generate` skill -- produces the SBOM this validates.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/SKILL.md>
- The sibling `sbom-enrich` skill -- its mandatory post-merge check uses
  this skill.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/SKILL.md>
- `docs/resources.md` -- SPDX 3 spec, ontology, and JSON Schema links,
  plus the `spdx3-validate` validator this skill wraps.
  <https://bact.github.io/pitloom/resources/>
