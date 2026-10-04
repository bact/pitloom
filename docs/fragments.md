---
Created: 2026-10-04
Last-Modified: 2026-10-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM fragments

See also: [Command line](cli.md) for every other subcommand, and
[Configuration](configuration.md) for `[tool.pitloom.fragment]`.

A fragment is an SPDX 3 JSON-LD document that adds to an SBOM: an
enrichment (`loom enrich`), a training run (`pitloom.loom`), or one you
write. A project merges the fragments its `[tool.pitloom.fragment]` lists;
`loom merge` merges a directory of them into a document of their own.

## Merge fragments

```bash
loom merge .spdx3-fragments/ -o combined.spdx3.json
```

Merges every `*.json` file directly in the directory, in file-name order,
into one SPDX 3 document: one `SpdxDocument` with `profileConformance`
(the profiles its elements use, plus those each fragment's document
declared), an `import` entry per fragment document, rooted at what each
fragment's own `SpdxDocument`/`Sbom` rooted. Its id derives from the
fragments' names and content, not the directory, and `created` is
`SOURCE_DATE_EPOCH`, else the latest `created` of the fragments, never
the current time: the same fragments give the same bytes. The Python API is
`pitloom.assemble.generate_merged_sbom()`.

Equal elements unify, here and in a project build with
`[tool.pitloom.fragment]`: the same `spdxId`, the same SHA-256 (files and
packages), the same agent or tool, and the same licence -- an expression
or a text with the same canonical value, so `mit` and `MIT` are one
element, while an expression and a text stay two. The earlier one is kept
(the project's own, then the earlier fragment, by file name for `loom
merge`), and an `Annotation` records each unification. A kept licence
keeps its own `name` and `comment`.

A configured fragment that is the document being merged into (an earlier
SBOM of the same project, with the same `SpdxDocument` id) is skipped
with a `WARNING:`, and fails the build when `required = true`.

Exits non-zero (with an `ERROR:` line, after a `WARNING:` naming each
offending reference) if any element or root in the merged result
references an id absent from the merge and not imported by the merged
document (a fragment's own `import` is not carried over) -- most
commonly a fragment merged against a stale base SBOM (see the note in
[Enrich an SBOM](cli.md#enrich-an-sbom)). Regenerate the base SBOM and
re-run the fragment-producing step before merging again.

`merge`, `fragment`, and `id` each take only their own small flag set,
not the [common options](cli.md#useful-flags) -- e.g.
`--offline`/`-v`/`--config`/`--enrich` don't apply to any of them (`id
generate`/`id import` do take `-o`/`--id-registry`, as an alias for their
own target-file flag -- not in the common-options sense). `merge`'s own
`--pretty` also defaults to `True` (pretty-printed), the opposite of every
other subcommand's compact default.

## Validate fragments

```bash
loom fragment validate combined.spdx3.json
loom fragment validate base.spdx3.json fragment.spdx3.json  # + merged-graph check
```

Checks JSON Schema and SHACL conformance via
[`spdx3-validate`](https://pypi.org/project/spdx3-validate/)'s library
API (requires the `validate` extra, see [Installation](cli.md#installation)).
Works on any SPDX 3 JSON document, not just Pitloom's own output. Passing
more than one path also validates the graph formed by merging them, which
catches type errors across `ExternalMap` references -- pass `--no-merge`
to skip that and check each document only in isolation. Non-zero exit reports every
finding to stderr with every line `ERROR:`-tagged -- a SHACL violation's
Severity/Source Shape/Focus Node breakdown spans several `ERROR:` lines,
not just one.

## List configured fragments

```bash
loom fragment list
loom fragment list --project-dir path/to/project
```

Reads `[tool.pitloom.fragment]` from that directory's `pyproject.toml`
(default: cwd) and prints one line per configured fragment:

```text
PATH=fragments/model.spdx3.json ROLE=ai_model REQUIRED=false EXISTS=true ELEMENTS=42 SHA256=match MODIFIED=2026-09-10T12:00:00+00:00 SAME_DOCUMENT=false
```

`ELEMENTS` is the fragment's `@graph` entry count -- `0` for valid JSON
with no `@graph` key (a real, valid empty fragment), `-` if the file is
missing, unreadable, or not valid JSON at all; `SHA256` is
`-`/`unknown`/`match`/`mismatch` depending on whether a `sha256` is
configured and, if so, whether the file could be checked -- display
only, not yet enforced before merge; `SAME_DOCUMENT` is `true` when the
fragment is the document a `loom project` build of the directory would
merge it into (an earlier SBOM of the project), `-` if the file could not
be read.
A missing or broken fragment logs the same `WARNING:` wording a real
build would log for it. Exits non-zero only when a `required = true`
fragment is missing, unreadable, fails to parse as valid SPDX3 JSON-LD,
or is that same document -- the same conditions that would also fail
an actual build (see [Merge fragments](#merge-fragments) above); a
non-required missing fragment or a `SHA256` mismatch is informational
only.
