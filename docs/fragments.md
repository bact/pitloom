---
Created: 2026-10-04
Last-Modified: 2026-11-26
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
`[tool.pitloom.fragment]`: the same `spdxId` and type, the same SHA-256 and
type (files, packages, datasets), the same agent or tool, and the
same licence -- an expression or a text with the same canonical value, so
`mit` and `MIT` are one element, while an expression and a text stay two.
Elements are never unified by name alone. The earlier one is kept (the
project's own, then the earlier fragment, by file name for `loom merge`),
except that for equal SHA-256 the registry-pinned `spdxId` wins: the one whose
namespace the most inputs (the project and fragments) use, since a minted
id's namespace belongs to its one fragment. A tie keeps the earlier. An
`Annotation` records each unification. A kept licence keeps its own `name`
and `comment`. Fields merge into the kept element: lists as a union,
`ai_hyperparameter` and `ai_metric` entries by key (a missing value is
filled, a differing one is dropped with a
`WARNING: Merge: ELEMENT=<spdx-id>: <property> key <entry-key> differs; kept <kept>, dropped <dropped> [fragment-conflict]`),
a `comment` appended after `; `, or on a new line when either
side's adjoining line is a `Metadata provenance:` line, and any other field
keeps the kept element's value (an empty one takes the fragment's), with a
`WARNING: Merge: ELEMENT=<spdx-id>: <property> differs; kept <kept>, dropped <dropped> [fragment-conflict]`
naming the dropped one. A value is cut to its first 120 characters in the line.

A value Pitloom generated for the project's own AI model from its file's
format, not read from it, is the other exception: the `description` of a
CRFsuite model built from its labels, the `domain` of a fastText model, the
outputs a format fixes (their provenance says `Method: generated_from_labels`
or `derived_from_format`). A fragment's different value for that property
replaces it, with one `INFO: Merge: ELEMENT=<spdx-id>: <property> generated from the model file replaced by a fragment's; kept <kept>, dropped <dropped> [generated-value-conflict]`,
and the property's provenance is dropped. A property whose provenance says it
was not measured, and that a fragment now gives a value, drops that entry with
one `INFO: Merge: ELEMENT=<spdx-id>: <property> now holds a value; dropped its not_measured provenance of <provenance-field> [generated-value-conflict]`. The first fragment that gives one wins; a later fragment's value
conflicts with it as above. Either provenance form (`annotation`, `comment`,
`both`) says a value was generated. The value is replaced, not merged: a
generated `domain` is not unioned with the fragment's, and the text of the
input/output description is replaced whole, the model's inputs with its
outputs. An empty fragment value replaces nothing, and neither does the same
value in another spelling (a list in another order, JSON text with other
spacing), also when a later fragment says again what was replaced, whatever
the order of the fragments. Two values (fragment against fragment, or against
the base) that are the same JSON object or array in other spacing, key order
or escape spelling (`"\u0041"` and `"A"`) do not conflict, for a text property
such as the input/output description: the first one's spelling stays. Text
that is not an object or array is compared as text, a float as its text (`1E2`
and `1e2` differ), and an integer past Python's integer-conversion limit (4300
digits by default) is not folded. This applies to a text property merged field
by field, not to lists (items are compared as text), a comment (joined) or a
model's name (a fragment's name that differs replaces it). The input/output
text counts as generated when its `inputs` and `outputs` are; any other key in
it (an intended use) is replaced with it. Every AI model of the project SBOM
with generated provenance is covered: in `loom merge` there is no base
document, a model that `loom model` generated is an earlier fragment's, and
the earlier file's value wins as for any other field.

The `name` of the project's own AI model is the exception: fragments that
unify with it and agree on another name, as `loom.set_model(name,
path=...)` declares, rename it. One `INFO: Merge: ELEMENT=<spdx-id>: name replaced by the one the fragments agree on; kept <kept>, dropped <dropped> [generated-value-conflict]`
names both names, and the project's provenance record of the old name is
dropped; the `spdxId` and the registry key stay the model file's. Fragments
giving it two names keep the project's name, with a `fragment-conflict`
`WARNING:` (`name differs`, as above) per other name, whatever their order. `loom merge` has no project document, so there the
earlier fragment's name is kept.

A fragment element whose `spdxId` an element of another type
already holds is not unified with it: both are kept, and the fragment's
element gets a new id in the merged document's namespace, with
`WARNING: Merge: ELEMENT=<spdx-id>: id held by a '<holder-type>', also wanted by a '<type>'; both kept, the later is now <new-id> [fragment-id-conflict]`.
The same holds for the same `spdxId` and type with a different digest of the
same algorithm (disjoint digest sets: the content differs): the earlier
element keeps the id, the later gets a new one, and the line says
`id held by two '<type>' elements of different <algorithm> digests`. A digest
differing only in case, in another algorithm, or absent is not a conflict.
Two elements of one type that share a name but state different SHA-256 digests
both stay, with
`WARNING: Merge: ELEMENT=<spdx-id>: a '<type>' named <name> has SHA-256 <digest>, another of that name <other-digest>; both kept [fragment-hash-conflict]`.
All fragments are loaded before the first merge, so a load warning can precede
a merge warning.
To make independent runs agree on ids in the first place, see [Loom ID
registry](id-registry.md).

In a project build, fragment envelopes are dropped and duplicate relationships
removed. The document's `profileConformance` gains `ai`/`dataset` as
appropriate, and a second `software_Sbom` rooted at the merged `ai_AIPackage`
is added, so the wheel ships one connected AI-pipeline graph: the packaged
training script `generates` the model, which was `trainedOn` datasets that
trace back via `hasInput` to the raw data.

A fragment that cannot be merged is left out of the SBOM with one `WARNING:`
naming it as configured (for `loom merge`, the directory as typed joined with the
file name), and the rest are merged. When `required = true` the line ends
`; required, so the merge will fail` instead of `; not merged`, and the run then
ends with `ERROR: <number> required SBOM fragment(s) not merged: <files>; fix each as its WARNING says [fragment-missing]`
and no SBOM is written. The lines, by cause:

- `WARNING: FILE=<file>: SBOM fragment not found; not merged [input-not-found/fragment]`:
  a configured path that does not exist.
- `WARNING: FILE=<file>: SBOM fragment could not be read (<failure>); not merged [fragment-unreadable]`:
  the operating system refused it (permission, a directory in its place).
- `WARNING: FILE=<file>: SBOM fragment is not valid JSON (<failure>); not merged [fragment-invalid]`
  and `WARNING: FILE=<file>: SBOM fragment is not SPDX 3 JSON-LD Pitloom can merge (<failure>); not merged [fragment-invalid]`:
  a syntax error or an encoding other than UTF-8, UTF-16 or UTF-32, or JSON
  the SPDX 3.0.1 reader does not take (including a number the merged document
  could not be written with, such as an integer beyond +-(2**53 - 1)).
- `WARNING: FILE=<file>: SBOM fragment is the document being merged into (<spdx-id>); not merged [fragment-unusable]`:
  a configured fragment that is an earlier SBOM of the same project (the same
  `SpdxDocument` id).

`loom merge` of a directory in which no fragment could be merged writes nothing
and exits 1, with `ERROR: no SBOM fragment in '<path>' could be merged; fix each as its WARNING says [fragment-missing]`
after the `WARNING:` of each. Its `INFO: merge: merged <number> fragment(s)`
counts the fragments merged, not the files given; a file holding `[]` reads as
an empty fragment and counts. When no fragment states a creation time and
`SOURCE_DATE_EPOCH` is unset (every fragment empty), it says `WARNING: Merge: no fragment states a creation time; created set to <datetime> [datetime-missing]`
and the SBOM carries that placeholder date.

Exits non-zero (with an `ERROR:` line, after a `WARNING:` naming each
offending reference) if any element or root in the merged result
references an id absent from the merge and not imported by the merged
document (a fragment's own `import` is not carried over) -- most
commonly a fragment merged against a stale base SBOM (see the note in
[Enrich an SBOM](cli.md#enrich-an-sbom)):
`WARNING: Merge: ELEMENT=<spdx-id>: <property> names <reference>, which is not in the merged document; regenerate the base SBOM, then run the enrichment again [reference-not-found]`,
one per reference in sorted order, then
`ERROR: <number> reference(s) to elements not in the merged document; regenerate the base SBOM, then run the enrichment again [reference-not-found]`.
Regenerate the base SBOM and re-run the fragment-producing step before merging
again. Every line is in [Message codes: SBOM
fragments](message-codes-fragments.md).

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
finding to stderr, each line
`ERROR: loom fragment validate: spdx3-validate: <line>` -- a SHACL
violation's Severity/Source Shape/Focus Node breakdown spans several lines, not
just one, and a finding given twice is said once. Each document then gets one
coded `ERROR: FILE=<file>: not valid SPDX 3 (<number> finding(s) above)
[sbom-invalid]` line (`ERROR: the SBOMs together are not valid SPDX 3 (<number>
finding(s) above) [sbom-invalid]` for the merged graph), and no empty `ERROR:`
line. A document the validator could not load says why the same way, then ends
`could not be validated; spdx3-validate says why above`. See
[Message codes: Targets](message-codes-targets.md#sbom-invalid).

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
be read or the project's own metadata cannot be (one `WARNING:`).
A missing or broken fragment logs the same `WARNING:` as a real build
would, read by the same reader (a required fragment holding an integer
beyond +-(2**53 - 1) is rejected here too). Exits non-zero only when a
`required = true` fragment is missing, unreadable, fails to parse as valid
SPDX 3 JSON-LD, or is that same document -- the same conditions that would
also fail an actual build (see [Merge fragments](#merge-fragments) above); a
non-required missing fragment is informational only. A `SHA256` mismatch is
informational too, said once as
`WARNING: FILE=<file>: SHA-256 <sha256> does not match the configured <declared> [fragment-digest-invalid]`.
