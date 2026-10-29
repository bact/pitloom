---
Created: 2026-09-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# The deterministic `loom enrich` pass: why the rules hold

See also: `../SKILL.md` (step 2, which holds the rules),
`dangling-references.md` and `model-stub-diagnosis.md` (a model the base holds
as a stub).

## What the pass writes

It parses only YAML frontmatter and writes a standalone fragment: fast, free,
safe. Each `datasets:` entry becomes a `dataset_DatasetPackage` with a
`trainedOn` relationship. A frontmatter `license` is only logged in the
fragment's enrichment `Annotation`, with no licence element: a base regenerated
with `--enrich` states it (or a step 6 fragment does). Read the fragment's
`@graph` to see what it filled.

Skip it when the base run used `--enrich` (same pass: merging both duplicates
each dataset and `trainedOn`), and when the target is not a local AI model file
(a plain Python project, a Hugging Face model, or a file that is not a model).

## Errors and a stub model

A model the base holds as a stub (`SKILL.md` step 3) because of a bound, a
missing library or a parse failure is no obstacle: `loom enrich` reads the model
too (native readers included, so a format a wheel scan's gate leaves unread is
read here) and the README or model card next to it. It writes the fragment and
exits 0 with the one `WARNING:` the scan gave (its `FILE=` is the path as given,
not the scan's project-relative one), and the model stays a stub. (A wheel's
gate, ceiling and budget do not apply to a local file.)

Only `ERROR: enrichment fragment generation failed: ... not an AI model ...`,
`header is not <fmt>` or `header is a Git LFS pointer, ...` means the file is
not a model: skip the step for it and relay Pitloom's own advice.

## Attaching

The fragment attaches only if the base has an `ai_AIPackage` for that model (the
model file is among the build's files); if not, say so instead of merging.

## `-o`: default name and location

Without `-o` the fragment is named `<model-file-name>.enrich.spdx3.json`
and written to the *current directory*, not the project directory, while
step 8 registers a project-relative path.

## `--project-dir`: why the base must be a project

A project-level and a single-model SBOM assign a model's `ai_AIPackage`
*different* ids, so without `--project-dir` the fragment misses the base.
`--project-dir` re-derives the base document's identity and registry from
the same `--config`, `--id-registry` and `--use-lockfile`/
`--no-use-lockfile` the base run used; omit them to auto-match the
project's own config. With `--project-dir`, `loom enrich` picks up the
project's own declared `id-registry` and never writes to it (see
`sbom-generate`'s "Pinning element ids"). A `loom model` base is never
merged into, and its ids are the model document's, not a project's, hence
no `--project-dir` for it.

## `--allow-build`: why the ids differ

`loom enrich` has no such flag and computes the base document's identity
from static file discovery, so the ids match only when the real build's
file list equals the static one.
