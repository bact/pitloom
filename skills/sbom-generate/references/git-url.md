---
Created: 2026-10-21
Last-Modified: 2026-10-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Generating an SBOM from a Git URL

See also: [examples.md](examples.md); the Pitloom site page "SBOM from a Git
URL" (<https://bact.github.io/pitloom/git-urls/>).

`loom project <url>` / `loom generate <url> -o FILE` fetch the repository (or the
folder a pasted page URL names: GitLab `.../-/tree/main/svc`, GitHub
`.../tree/v1/src`, Codeberg/Gitea `.../src/branch/main/svc`) shallowly into a
temporary directory and read it as a project. It needs the `git` program. Rules
to state to the user:

- Only `http`/`https` URLs are fetched. `ssh://`, `git://`, `file://` and
  `git@host:path` get `WARNING: Git source: Cannot fetch <url>: only http and
  https URLs are fetched ...`, then `ERROR: SBOM generation failed: ...`
  (exit 1). A Hugging Face address is a model, not a repository: use `loom model`.
- The repository is untrusted: its own `[tool.pitloom]` is ignored (an `INFO:`
  says so; `--config FILE` applies) and its build backend never runs:
  `--allow-build` gets `WARNING: Build: <url>: --allow-build has no effect for
  a remote repository`.
- `--offline` is an error, not a fallback (`WARNING: Git source: Cannot fetch
  <url>: network access is forbidden.`, then the `ERROR:`).
- A page URL naming a file reads the folder that holds it; a commit needs its
  full 40 (or 64) hex digits; a query or `#fragment` is ignored.
- A monorepo with no Python project at the root fails with an error that names
  the projects below it (up to five): ask which one (non-interactively, report
  the list) and rerun with that folder's page URL.
- Read the `INFO:` lines: each redirect followed (`Git source: <url>
  redirected to <url>`), and the repository, branch and folder used.
- A relative `--id-registry` is relative to where `loom` runs, not to the
  checkout. The output file is named as for a local project (`sbom.spdx3.json`).
