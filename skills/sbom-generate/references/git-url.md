---
Created: 2026-10-21
Last-Modified: 2026-10-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Generating an SBOM from a Git URL

See also: [examples.md](examples.md); the Pitloom site page "SBOM from a Git
URL".

`loom project <url>` / `loom generate <url> -o FILE` fetch the repository (or the
folder a pasted page URL names: `.../-/tree/main/svc`, `.../tree/v1/src`,
`.../src/branch/main/svc`) shallowly into a temporary directory and read it as a
project. Rules to state to the user:

- Only `http`/`https` URLs are fetched; `ssh://`, `git@host:path` and `file://`
  are refused with a `WARNING:` and an `ERROR:`.
- The repository is untrusted: its own `[tool.pitloom]` is ignored (`--config FILE`
  applies) and **`--allow-build` has no effect** (its build backend is never run).
- `--offline` makes it an error, not a fallback.
- A monorepo with no Python project at the root fails with an error that names
  the projects below it: ask which one (or, non-interactively, report the list)
  and rerun with that folder's page URL.
- Read the `INFO:` lines: they name each redirect followed and the branch and
  folder used.
