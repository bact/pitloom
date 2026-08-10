---
Created: 2026-08-10
Last-Modified: 2026-08-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pitloom's `sbom-validate` skill: copy-paste recipes

Companion to `../SKILL.md`. These recipes are meant to be run as-is or
adapted with minimal edits.

## Validate a single SBOM

```bash
pip install spdx3-validate  # if not already installed
spdx3-validate --json sbom.spdx3.json
```

## Validate quietly (no progress spinner, useful in CI logs)

```bash
spdx3-validate --json sbom.spdx3.json --quiet
```

## Validate a base SBOM plus a fragment together

Checks each document individually, then the merged graph -- catches an
`ExternalMap`-referenced `spdxId` that the fragment expects but the base
document doesn't actually provide:

```bash
spdx3-validate --json sbom.spdx3.json --json fragments/agent-enrichment.spdx3.json
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

## Validate from stdin

```bash
loom project . | spdx3-validate --json -
```

## Interpreting the result

- Exit code `0`: valid, no output beyond progress.
- Non-zero exit code: at least one error, printed per-document as
  `ERROR: JSON Schema validation failed for <file>:` or `ERROR: SHACL
  Validation failed for <file>:`, followed by the failing JSON path(s)
  and a description.

## See also

- `../SKILL.md` -- operating instructions for this skill.
- The sibling `sbom-generate` skill -- produces the SBOM this validates.
- The sibling `sbom-enrich` skill -- its mandatory post-merge check uses
  this skill.
- `docs/resources.md` in the Pitloom repository -- SPDX 3 spec, ontology,
  and JSON Schema links, plus the `spdx3-validate` validator this skill
  wraps.
