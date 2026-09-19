---
# Created: 2026-08-10
# Last-Modified: 2026-09-19
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
  "run spdx3-validate on this file". Also triggers, on the wheel-embedded
  SBOM specifically (see "Validate a wheel's embedded SBOM" below, which
  runs both `verify-wheel` and `validate-wheel`) -- "check validity of
  SBOM in wheel", "check the SBOM in this wheel", "validate the SBOM in
  this wheel", "validate wheel SBOM", "is the wheel's SBOM valid", "is the
  SBOM inside this wheel valid", "check if wheel SBOM is valid", "validate
  SBOM embedded in wheel". Also triggers, for presence/location only (see
  "Presence/location only" below, which runs `verify-wheel` alone and
  asks a follow-up before checking content) -- "is SBOM in correct
  location in the wheel", "is this wheel has an SBOM", "does this wheel
  have a SBOM", "check if the wheel has an SBOM", "where is the SBOM in
  this wheel". A quick
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
loom fragment validate <sbom-file>
```

Works on any SPDX 3 JSON document, Pitloom-generated or not -- despite
the `fragment` grouping (shared with `loom merge`), the underlying
`spdx3-validate` check has no dependency on Pitloom's own output.

Exit code `0` means valid; a non-zero exit code means at least one
schema or SHACL error, printed to stderr with every line `ERROR:`-tagged
(a SHACL violation's Severity/Source Shape/Focus Node breakdown spans
several `ERROR:` lines, not just one).

To validate several related documents (e.g. a base SBOM plus a fragment
that references it via `ExternalMap`) and additionally check the *merged*
graph, pass more than one path:

```bash
loom fragment validate base.spdx3.json fragment.spdx3.json
```

Add `--no-merge` to skip the merged-graph check and validate each
document only in isolation.

(The standalone `spdx3-validate --json <file>` CLI checks the same rules
and uses the same exit code convention, if `pitloom[validate]` isn't the
preferred install path in a given context -- but it writes its report to
*stdout*, not stderr, and doesn't `ERROR:`-tag lines the way `loom
fragment validate` does.)

## Validate a wheel's embedded SBOM

For "is this wheel's SBOM valid" rather than a standalone document, run
**both** checks -- they answer different questions and neither implies
the other:

```bash
loom verify-wheel dist/mypackage-1.0.0-py3-none-any.whl     # present, right place, name/version match
loom validate-wheel dist/mypackage-1.0.0-py3-none-any.whl   # schema/SHACL content check
```

`verify-wheel` (structural: is an SBOM present at the PEP 770 location,
does its extension match its format, does its declared name/version match
the wheel's own `.dist-info/METADATA`) and `validate-wheel` (content:
schema/SHACL conformance) are independent -- a wheel can pass one and fail
the other. A generic "is this wheel's SBOM valid/good" request runs both,
in that order (the cheap structural check first).

### Presence/location only -- ask before validating content

A narrower request -- "is SBOM in correct location in the wheel", "is
this wheel has an SBOM", "does this wheel have a SBOM", "check if the
wheel has an SBOM", "where is the SBOM in this wheel" -- asks only
whether an SBOM is present and correctly placed, not whether it's valid.
Answer that with `verify-wheel` alone; do not also run `validate-wheel`
unasked. **Presence in the right place says nothing about content** -- the
file at that path could be malformed JSON, or syntactically valid JSON
that isn't valid SPDX 3 -- so after reporting the `verify-wheel` result,
ask a follow-up: "Do you also want me to check whether the SBOM content
itself is valid (well-formed and SPDX 3 conformant)?" Only run
`validate-wheel` if they say yes.

**Non-interactive session (CI/batch, no human to answer):** don't block
waiting for a reply -- report the `verify-wheel` result, explicitly state
that content validity was not checked, and stop there. Don't silently run
`validate-wheel` on their behalf either -- expanding scope on an
unattended run is its own kind of unasked deviation.

See the `sbom-generate` skill's "Embed an SBOM into a wheel" section for
`embed-wheel --verify`/`--validate` (the combined flag form, run
immediately after an embed in the same command). `embed-wheel` also
accepts `--allow-build`; if the user asked for it, follow
`sbom-generate`'s "Choosing `--build-timeout`" section before running
the build.

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
