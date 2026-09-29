---
Created: 2026-09-29
Last-Modified: 2026-09-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Automatic lock file discovery and resolved dependencies

Companion to `../SKILL.md`. When generating an SBOM for a project directory
(`loom project .` or `loom generate .`), Pitloom inspects the project root
for lock files to discover exact, pinned dependency versions and transitive
dependencies.

Supported lock formats, in priority order:

1. `pylock.toml` (PEP 751 standard lock file)
2. `uv.lock` (uv workspace/resolver)
3. `poetry.lock` (Poetry resolver)
4. `pdm.lock` (PDM resolver)
5. `Pipfile.lock` (Pipenv resolver)
6. `requirements.txt` (strictly fully-pinned requirement file)

When a lock file is present:

- Direct dependencies declared with version ranges (e.g. `requests>=2.0`)
  resolve to their exact locked version rather than falling back to host
  environment introspection.
- Transitive dependencies from the lock file are emitted as SPDX 3
  `software_Package` elements connected via `dependsOn` relationships.
- SHA-256 package hashes are extracted directly from supported lock files
  for `verifiedUsing` integrity validation, preserved in offline builds and
  prioritised over PyPI lookups.
- Relationship completeness is conservatively left unset (`None`) to
  avoid overstating completeness for partial closures (e.g. omitted
  VCS/path dependencies or marker-ambiguous variants).

To opt out and fall back to direct dependencies plus environment
introspection only, pass `--no-use-lockfile` (on `project`/`generate`, or on
`enrich` together with `--project-dir`; it has no effect on `enrich`
without `--project-dir`, since no project metadata is read in that case) or
set `[tool.pitloom] use-lockfile = false` in `pyproject.toml`. On by
default; an explicit CLI flag always wins over the config value.
