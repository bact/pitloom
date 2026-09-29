---
Created: 2026-09-29
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# The deterministic `loom enrich` pass: why the rules hold

See also: `../SKILL.md` (step 2, which holds the rules) and
`dangling-references.md`.

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
