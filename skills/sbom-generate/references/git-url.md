---
Created: 2026-10-21
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Generating an SBOM from a Git URL

See also: [examples.md](examples.md); the Pitloom site page "SBOM from a Git
URL" (<https://bact.github.io/pitloom/git-urls/>).

`loom project <url>` / `loom generate <url> -o FILE` fetch the repository (or the
folder a pasted page URL names: GitLab `.../-/tree/main/svc`, GitHub
`.../tree/v1/src`, Codeberg/Gitea `.../src/branch/main/svc`, Bitbucket
`.../src/main/svc`, SourceHut `.../tree/main/item/svc`, Gitiles `.../+/refs/heads/main/svc`,
cgit `.../tree/svc?h=main`, Azure DevOps `...?path=/svc&version=GBmain`) shallowly
into a temporary directory and read it as a project. It needs the `git` program.
Recommend the repository's **clone URL** (the host's Clone button) unless the user
wants one branch, tag or folder: a clone URL names the default branch and is never
misread, a page URL is read by the host's conventions. Rules to state to the user:

- Only `http`/`https` URLs are fetched. `ssh://`, `git://`, `file://` and
  `git@host:path` get `WARNING: Git source: Cannot fetch <url>: only http and
  https URLs are fetched ...`, then `ERROR: SBOM generation failed: ...`
  (exit 1). A Hugging Face model address is a model, not a repository: use
  `loom model`; a Space or dataset (`huggingface.co/spaces/...`) is a repository.
- The repository is untrusted: its own `[tool.pitloom]` is ignored (an `INFO:`
  says so; `--config FILE` applies) and its build backend never runs:
  `--allow-build` gets `WARNING: Build: <url>: --allow-build has no effect for
  a remote repository`.
- `--offline` is an error, not a fallback (`WARNING: Git source: Cannot
  fetch <url>: network access is forbidden.`, then the `ERROR:`).
- A page URL naming a file reads the folder that holds it; a commit needs its
  full 40 (or 64) hex digits; a `#fragment` is ignored, and so is a query that
  names no ref (cgit's `?h=` and Azure's `?version=` are read).
- A monorepo with no Python project at the root fails with an error that names
  the projects below it (up to five): ask which one (non-interactively, report
  the list) and rerun with that folder's page URL.
- Read the `INFO:` lines: each redirect followed (`Git source: <url>
  redirected to <url>`), and the repository, branch and folder used.
- **Git LFS is a limitation of this release.** LFS is switched off, so a file
  kept in LFS is a pointer in the checkout: a pointer named like a model
  (`.onnx`, `.gguf`, ...) is not read as a model (no `ai_AIPackage` for it), and
  any other LFS file (a dataset, an image) is hashed as its pointer text, with no
  warning. Most Hugging Face model repositories keep weights in LFS. Tell the user;
  `git lfs pull` does not help here (there is no local checkout): for the real
  files, clone with `git lfs` installed and run `loom project` on the directory.
- A relative `--id-registry` is relative to where `loom` runs, not to the
  checkout. The output file is named as for a local project
  (`<name>-<version>.spdx3.json`).
