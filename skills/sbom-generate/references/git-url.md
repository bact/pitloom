---
Created: 2026-10-21
Last-Modified: 2026-11-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Generating an SBOM from a Git URL

See also: [examples.md](examples.md); the Pitloom site page "SBOM from a Git
URL" (<https://bact.github.io/pitloom/git-urls/>).

`loom project <url>` / `loom model <url>` / `loom generate <url> -o FILE`
fetch the repository (or the folder a pasted page URL names: GitLab `.../-/tree/main/svc`, GitHub
`.../tree/v1/src`, Codeberg/Gitea `.../src/branch/main/svc`, Bitbucket
`.../src/main/svc`, SourceHut `.../tree/main/item/svc`, Gitiles
`.../+/refs/heads/main/svc`, cgit `.../tree/svc?h=main`, Azure DevOps
`...?path=/svc&version=GBmain`) shallowly into a temporary directory and read
it as a project, or (see "A model file or folder" below) as an AI model. It
needs the `git` program. Recommend the repository's **clone URL** (the host's Clone button) unless the user wants one branch, tag
or folder: a clone URL names the default branch and is never misread, a page
URL is read by the host's conventions. Rules to state to the user:

- Only `http`/`https` URLs are fetched. `ssh://`, `git://`, `file://` and
  `git@host:path` get `WARNING: Git source: Cannot fetch <url>: only http and
  https URLs are fetched ...`, then `ERROR: SBOM generation failed: ...`
  (exit 1). A Hugging Face model address is a model, not a repository: use
  `loom model`; a Space or dataset (`huggingface.co/spaces/...`) is a
  repository.
- The repository is untrusted: its own `[tool.pitloom]` is ignored (an `INFO:`
  says so, `[config-unsafe]`; `--config FILE` applies) and its build backend never runs:
  `--allow-build` gets `WARNING: Build: <url>: --allow-build has no effect for
  a remote repository`.
- `--offline` is an error, not a fallback, for `loom project`, `loom model`
  and `loom generate` (`WARNING: Git source: Cannot fetch <url>: network
  access is forbidden.`, then the `ERROR:`).
- A page URL naming a file (`blob`, or `raw`: GitHub `.../raw/main/f`, GitLab
  `.../-/raw/main/f`, Codeberg/Gitea `.../raw/branch/main/f`, Bitbucket
  `.../raw/main/f`) reads the folder that holds it, unless the file is an AI
  model (below). A `raw.githubusercontent.com` URL, or the `/resolve/` link
  of a Hugging Face Space or dataset, is taken as a repository and its clone
  fails (`git.clone-failed`); a model's `/resolve/` link is read as the Hub
  model, its file part dropped. Use the repository's page URL (`github.com`
  `blob`/`raw` page) instead. A commit needs its full 40 (or 64) hex
  digits; a `#fragment` is ignored, and so is a query that names no ref
  (cgit's `?h=` and Azure's `?version=` are read).
- A monorepo with no Python project at the root fails with an error that names
  the projects below it (up to five): ask which one (non-interactively, report
  the list) and rerun with that folder's page URL.
- Read the `INFO:` lines: each redirect followed (`Git source: <url>
  redirected to <url>`), and the repository, branch and folder used.
- A `WARNING: ... Git LFS pointer, content not read ... [lfs-pointer]` is
  common here (most Hugging Face model repositories keep weights in LFS).
  Explain it from its section in `messages.md`; relay the message's advice.
  For a model file named by its own URL a pointer is an `ERROR:` (`... Git LFS
  pointer, content not fetched ...; clone with git lfs, then run on the
  file`): relay it; do not clone for the user.
- A relative `--id-registry` is relative to where `loom` runs, not to the
  checkout. The output file is named as for a local project
  (`<name>-<version>.spdx3.json`).

## A model file or folder (Pitloom 0.24.0 and later)

A URL naming an AI model file (any supported format), or a folder or the
repository holding one, gives a model SBOM; `loom generate <url>` chooses
and `loom model <url>` is model only. `loom project <url>` is project only:
a folder with models and no project fails with `git.no-project`
(`[project-not-found/model-files]`), naming `loom model <url>` and `loom
generate <url>`. Rules to state:

- A model file URL wins over a project in the same folder; a file URL whose
  name no model has (`pyproject.toml`, `README.md`) and that is no model, or
  is missing or a link, reads the folder (one `INFO:`; `loom model` refuses
  it). A file named as a model (`.gguf`, `.onnx`, `.bin`, ...) that is not
  one is refused (`[model-wrong-format]`), and one absent from the
  repository is `git.path-not-found` (`[input-not-found]`).
- A folder is read non-recursively (the repository URL reads the root files
  only): a model in a subfolder needs that folder's URL or the file's.
- One model per SBOM: several models in a folder give `INFO: FILE=<file>: one
  of several AI model files` per file, then `ERROR: ... several AI model files
  ...; name one file` (`[model-ambiguous]`). Ask which one and rerun with the
  file's URL (non-interactively, report the list). Neither a project nor a
  model: `ERROR: ... no Python project (pyproject.toml, setup.cfg or setup.py)
  and no AI model file of a supported format ...` (`[project-or-model-not-found]`).
- In a model SBOM, and in a project SBOM (`loom project`, or `loom generate`
  on a folder with a project config) for the model files in its build file
  list, fastText, GGUF, HDF5, ONNX and PyTorch `.pt`/`.pth` files are listed
  with name, format and hash only (one `INFO: AI models from a Git URL in
  these formats are listed without metadata ... [reader-unsafe/remote]` per
  SBOM): their readers (a C/C++ library, a pickle parser, GGUF's parsing
  loop) are not run on a download. Keras, Safetensors (its Rust library, on
  purpose), NumPy, CRFsuite and PT2 are read in full. Offer, never do
  unasked, cloning the repository (with Git LFS) and running
  `loom model <file>` on a file, or `loom project <dir>` on a project, the
  user trusts: a local directory is not gated.
- The output goes to `-o`, or for `loom model` to the current directory as
  `<file name>.spdx3.json`; never into the clone. No temporary path is in it.
- A Hugging Face model address is read through the Hub (card and
  configuration, no model file, no hash, no Keras fields): for those fields
  download the file and run `loom model <file>`.
