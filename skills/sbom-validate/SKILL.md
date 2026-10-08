---
# Created: 2026-08-10
# Last-Modified: 2026-10-04
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

name: sbom-validate
description: >-
  Check any SPDX 3 JSON document (an SBOM/AIBOM, Pitloom-generated or not)
  for schema and SHACL conformance with `loom fragment validate` or
  spdx3-validate, and check a wheel's PEP 770 embedded SBOM. `verify-wheel`
  is structural (present, right place, name/version match); `validate-wheel`
  checks content (schema/SHACL). Triggers: "validate/check/verify this
  SBOM/BOM", "is this SBOM valid", "is it a valid SBOM", "is this SBOM in
  good shape", "validate the merged output", "run spdx3-validate". Wheel
  content, runs both: "is the wheel's SBOM valid", "check validity of SBOM in
  wheel", "check the SBOM in this wheel", "validate wheel SBOM", "validate
  SBOM embedded in wheel". Presence only, runs verify-wheel alone and offers
  a content check: "does this wheel have an SBOM", "check if the wheel has an
  SBOM", "is SBOM in correct location in the wheel", "where is the SBOM in
  this wheel". A quick @graph check is not a substitute. Not for
  NTIA/CISA/G7 completeness (sbom-enrich).
license: Apache-2.0
compatibility: >-
  Requires a shell, Python 3.10+ and pitloom >= 0.20.2 with the validate
  extra (pitloom[validate], which brings spdx3-validate) via pip, uvx or
  pipx, or spdx3-validate alone. Needs network access to install them. Not
  usable where packages cannot be installed, e.g. Claude API code execution.
---

# Validate an SPDX 3 document

A syntactically valid JSON file (or a file that merely contains a
`@graph` array) can still fail the SPDX 3 spec: a missing required
property, a relationship pointing at the wrong type, an `spdxId` that
doesn't match its own `ExternalMap` entry. This skill runs
[`spdx3-validate`](https://github.com/JPEWdev/spdx3-validate) -- schema
(JSON Schema) plus shape (SHACL) validation, with SPDX-3-aware handling of
`ExternalMap`-declared IDs that plain `pyshacl`/`check-jsonschema` gets
wrong. It works on any SPDX 3 JSON document, not just Pitloom's own
output: a hand-authored fragment, a merged SBOM, a third-party file.

This skill is one of three (`sbom-generate`, `sbom-enrich`,
`sbom-validate`) meant to be installed together: it refers to sections of
`sbom-generate`.

Pitloom's CLI splits two checks, and users treat the words as synonyms:

| Check | Command | Answers |
| :--- | :--- | :--- |
| Verify (structural) | `loom verify-wheel` | Is an SBOM present at the PEP 770 location, with the right extension and a name/version matching the wheel's METADATA? |
| Validate (content) | `loom fragment validate`, `loom validate-wheel` | Does the SBOM conform to the SPDX 3 schema and SHACL shapes? |

Neither implies the other; a generic "is it valid" runs the content check
(for a wheel, both, verify first).

**"Valid" is not "complete."** This skill only checks that what's present
conforms to the spec's shape -- it says nothing about whether the SBOM
covers everything it should. A Pitloom-generated SBOM for a mixed-ecosystem
project (Python plus a JS/Rust/Go/etc. component) will validate cleanly
even though the non-Python dependencies are simply missing, not
flagged -- see `sbom-generate`'s "Known limitations" section.
When a user asks "is this SBOM valid?" meaning "is this SBOM complete?",
answer both questions, not just the one this skill actually checks.

Triggers automatically on natural-language requests (see the trigger
phrasings above), or invoke it explicitly with `/sbom-validate
[sbom-file]` (`/pitloom:sbom-validate [sbom-file]` when installed via the
Claude Code plugin; the syntax depends on the client, e.g.
`$sbom-validate` in Codex). `sbom-file` is optional -- point it at a
specific file when a project has more than one SBOM; omit it to let the
agent find the one to validate.

See `references/examples.md` for copy-paste recipes.

## Requirements

Python >= 3.10 and **pitloom >= 0.20.2** (earlier releases lack
`--id-registry`, `loom id` and `--build-timeout`, which the sibling skills
use), the `loom`/`pitloom` entry point or standalone `spdx3-validate` CLI;
`loom fragment validate` needs the `validate` extra (`pip install
"pitloom[validate]>=0.20.2"`).

## Run the validator

Snippets are POSIX shell. On Windows use `python` or `py` for `python3`,
and PowerShell equivalents (PowerShell 5.1 has no `&&`: run the commands
one per line).

```bash
pip install "pitloom[validate]>=0.20.2"  # if not already installed
loom fragment validate <sbom-file>
```

Without a persistent install: `uvx --from "pitloom[validate]>=0.20.2"
loom fragment validate <sbom-file>`.

Despite the `fragment` grouping (shared with `loom merge`), the
underlying `spdx3-validate` check has no dependency on Pitloom's own
output.

Exit code `0` means valid; a non-zero exit code means at least one
schema or SHACL error, printed to stderr with every line `ERROR:`-tagged
(a SHACL violation's Severity/Source Shape/Focus Node breakdown spans
several `ERROR:` lines, not just one).

To validate several related documents (e.g. a base SBOM plus a fragment
that declares an `ExternalMap` for the base ids it uses) and additionally
check the *merged* graph, pass more than one path:

```bash
loom fragment validate base.spdx3.json fragment.spdx3.json
```

Add `--no-merge` to skip the merged-graph check and validate each
document only in isolation.

**A Pitloom enrichment fragment is not such a fragment.** It names the
base SBOM's ids directly, with no `ExternalMap`, so it fails SHACL alone
and paired with its base (exit 1) even when correct. To check one,
validate the **merged** SBOM: regenerate the project with the fragment
registered (`sbom-enrich`, steps 8-10) and run `loom fragment validate
<merged-sbom-file>`.

(The standalone `spdx3-validate --json <file>` CLI checks the same rules
and uses the same exit code convention, if `pitloom[validate]` isn't the
preferred install path in a given context -- but it writes its report to
*stdout*, not stderr, and only each document's header line is
`ERROR:`-tagged; the continuation lines are not.)

## Validate a wheel's embedded SBOM

For "is this wheel's SBOM valid" rather than a standalone document, run
**both** checks, the cheap structural one first -- a wheel can pass one
and fail the other:

```bash
loom verify-wheel dist/mypackage-1.0.0-py3-none-any.whl     # present, right place, name/version match
loom validate-wheel dist/mypackage-1.0.0-py3-none-any.whl   # schema/SHACL content check
```

Each command prints one stdout line per wheel, `WHEEL=<name>
STATUS=<status>`: `ok`/`failed` for `verify-wheel`, `valid`/`skipped`/
`failed` for `validate-wheel` (a failure's reason is the `ERROR:` on
stderr). **Exit 0 is not always a clean pass.** A name/version mismatch in
`verify-wheel` is only a `WARNING:` (exit 0, still `STATUS=ok`) unless
`--fail-on-mismatch` is given: report any `WARNING:`, and add
`--fail-on-mismatch` in CI. `validate-wheel` on an SBOM in a format it has
no validator for prints `STATUS=skipped` and exits 0: report it as "not
validated".

A wheel Pitloom refuses gets one `ERROR: ARCHIVE=... -- wheel refused` and
exit 1; the other wheels are still checked (an unexpected `validate-wheel`
error, `ERROR: wheel SBOM validation failed: ...`, stops the batch instead).
`verify-wheel` reads only the member names, the own `.dist-info`'s
`METADATA` and the embedded SBOM, and `validate-wheel` only the names and
the embedded SBOM, so they refuse a file
that is not a ZIP, and a wheel with one of those unreadable, two members
with one name, a NUL in a name or no single own `.dist-info` (where a
`WARNING: ... -- identity unknown` line comes before the `ERROR:`): a damaged
other member does not fail them. `WARNING: ... the file name names no
top-level .dist-info; using ...` means the file name and the wheel's
`.dist-info` disagree: report it.

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

A wheel that was embedded with `--allow-signed-wheel` has no `RECORD`
signature any more: if `verify-wheel`/`validate-wheel` passes but the user
expected the wheel to be signed, say so and remind them to re-sign (see
`sbom-generate`'s "Signed wheels"); never re-embed with the flag yourself.
Pitloom wheel SBOMs list the payload only (nothing under the wheel's own
`.dist-info`), so a missing `RECORD` file element is expected, not a defect.

Right after an embed, `loom embed-wheel dist/*.whl --project-dir .
--verify --validate` runs both checks in the same command
(`sbom-generate`'s "Embed an SBOM into a wheel" section). If the user
asked for `embed-wheel --allow-build`, always pass an explicit
`--build-timeout` (see `sbom-generate`'s "Choosing `--build-timeout`").

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
  <https://github.com/bact/pitloom/blob/main/skills/sbom-validate/references/examples.md>
- The sibling `sbom-generate` skill -- produces the SBOM this validates.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-generate/SKILL.md>
- The sibling `sbom-enrich` skill -- this skill is its mandatory
  post-merge conformance check.
  <https://github.com/bact/pitloom/blob/main/skills/sbom-enrich/SKILL.md>
- `docs/resources.md` -- SPDX 3 spec, ontology, JSON-LD, and JSON Schema
  links (including the per-minor-version URL pattern), plus the
  `spdx3-validate` validator this skill wraps.
  <https://bact.github.io/pitloom/resources/>
