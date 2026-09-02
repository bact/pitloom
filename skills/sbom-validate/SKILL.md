---
# Created: 2026-08-10
# Last-Modified: 2026-09-02
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

name: sbom-validate
description: >-
  Use this skill whenever an SPDX 3 JSON document (an SBOM/AIBOM, whether
  Pitloom-generated or not) needs a schema/shape-level conformance check --
  after generating or enriching a Pitloom SBOM, after hand-editing or
  merging SPDX 3 JSON, or whenever asked to validate, check, or verify an
  SPDX 3 document against the spec. Trigger phrasings include "validate
  this SBOM", "validate this BOM", "is this SBOM valid", "is it a valid
  SBOM", "check this SBOM", "check this SBOM's SPDX conformance", "verify
  this SBOM", "is this SBOM in good shape", "validate the merged output",
  "run spdx3-validate on this file". A quick
  `@graph`-presence sanity check (see the sibling `sbom-generate`/
  `sbom-enrich` skills) is not a substitute for this: it cannot catch a
  missing required property or a wrong relationship type, which only
  schema/SHACL validation catches.
license: Apache-2.0
argument-hint: "[sbom-file]"
---

# Validate an SPDX 3 document

A syntactically valid JSON file (or a file that merely contains a
`@graph` array) can still fail the SPDX 3 spec: a missing required
property, a relationship pointing at the wrong type, an `spdxId` that
doesn't match its own `ExternalMap` entry. This skill runs
[`spdx3-validate`](https://github.com/JPEWdev/spdx3-validate) -- schema
(JSON Schema) plus shape (SHACL) validation, with SPDX-3-aware handling of
`ExternalMap`-declared IDs that plain `pyshacl`/`check-jsonschema` gets
wrong.

Works on any SPDX 3 JSON document, not just Pitloom's own output --
useful for a hand-authored fragment, a merged SBOM, or a third-party SPDX
3 file.

**"Valid" is not "complete."** This skill only checks that what's present
conforms to the spec's shape -- it says nothing about whether the SBOM
covers everything it should. A Pitloom-generated SBOM for a mixed-ecosystem
project (Python plus a JS/Rust/Go/etc. component) will validate cleanly
even though the non-Python dependencies are simply missing, not
NOASSERTION-flagged -- see `sbom-generate`'s "Known limitations" section.
When a user asks "is this SBOM valid?" meaning "is this SBOM complete?",
answer both questions, not just the one this skill actually checks.

Triggers automatically on natural-language requests (see the trigger
phrasings above), or invoke it explicitly with `/sbom-validate
[sbom-file]` (`/pitloom:sbom-validate [sbom-file]` when installed via the
Claude Code plugin). `sbom-file` is optional -- point it at a specific
file when a project has more than one SBOM; omit it to let the agent find
the one to validate.

See `references/examples.md` for copy-paste recipes.

## Run the validator

```bash
pip install "pitloom[validate]"  # if not already installed
pitloom fragment validate <sbom-file>
```

Works on any SPDX 3 JSON document, Pitloom-generated or not -- despite
the `fragment` grouping (shared with `pitloom merge`), the underlying
`spdx3-validate` check has no dependency on Pitloom's own output.

Exit code `0` means valid; a non-zero exit code means at least one
schema or SHACL error, printed to stderr with every line `ERROR:`-tagged
(a SHACL violation's Severity/Source Shape/Focus Node breakdown spans
several `ERROR:` lines, not just one).

To validate several related documents (e.g. a base SBOM plus a fragment
that references it via `ExternalMap`) and additionally check the *merged*
graph, pass more than one path:

```bash
pitloom fragment validate base.spdx3.json fragment.spdx3.json
```

Add `--no-merge` to skip the merged-graph check and validate each
document only in isolation.

(The standalone `spdx3-validate --json <file>` CLI checks the same rules
and uses the same exit code convention, if `pitloom[validate]` isn't the
preferred install path in a given context -- but it writes its report to
*stdout*, not stderr, and doesn't `ERROR:`-tag lines the way `pitloom
fragment validate` does.)

## Validate a wheel's embedded SBOM

For "is this wheel's SBOM valid" rather than a standalone document, use
`validate-wheel` instead -- it locates the embedded SBOM under
`.dist-info/sboms/` (PEP 770) and runs the same schema/SHACL check:

```bash
pitloom validate-wheel dist/mypackage-1.0.0-py3-none-any.whl
```

See the `sbom-generate` skill's "Embed an SBOM into a wheel" section for
`verify-wheel` (PEP 770 location/extension only, no content check) and
`embed-wheel --verify`/`--validate`.

## Report the result

- **Valid:** say so plainly; no need to reproduce validator output for a
  clean pass.
- **Invalid:** show the validator's error output (it already includes the
  failing JSON path and a description) and explain in plain language what
  it means, rather than just pasting the raw error. Do not attempt to
  auto-fix a hand-authored fragment's SPDX-shape errors without asking --
  the fix usually requires understanding intent (which relationship type
  was meant, which element a dangling reference should point to).

## See also

- `references/examples.md` -- copy-paste recipes, including multi-file
  and merged-graph validation.
- The sibling `sbom-generate` and `sbom-enrich` skills -- this skill is
  their recommended post-generation/post-merge conformance check.
- `docs/resources.md` in the Pitloom repository -- SPDX 3 spec, ontology,
  JSON-LD, and JSON Schema links (including the per-minor-version URL
  pattern), plus the `spdx3-validate` validator this skill wraps.
