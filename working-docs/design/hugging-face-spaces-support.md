---
Created: 2026-10-23
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Hugging Face Spaces: what Pitloom does and what it could do

See also: [remote-source-ingestion.md](remote-source-ingestion.md) (remote
targets), [target-resolution-and-purl.md](target-resolution-and-purl.md) (a
`pkg:huggingface` PURL), [roadmap.md](roadmap.md),
[remote-git-ingestion.md](../implementation/remote-git-ingestion.md).

> **Status (2026-10-23):** a limitation is recorded and a direction sketched.
> Nothing here is built or decided.

## What works today

A Space (`huggingface.co/spaces/<org>/<name>`) and a dataset
(`huggingface.co/datasets/...`) are Git repositories. Since PR #347 Pitloom
fetches them like any Git URL (`loom project <url>`, `loom generate <url>`, the
library); before, `spaces/<org>` was read as a model id. A model address
(`huggingface.co/<org>/<name>`) is still read by `loom model`.

## The limitation

`loom project` reads a Python **project**: it needs `pyproject.toml`,
`setup.cfg` or `setup.py`. A Space is an **application**, and almost none has
one. Fetching works, and then:

```text
ERROR: SBOM generation failed: No pyproject.toml, setup.cfg, or setup.py found in '/tmp/pitloom-git-...'
```

Measured on 2026-10-23: of about 390 Spaces that a Hub search returned for
`onnx`, `tflite`, `fasttext`, `language identification`, `vad` and `sentiment`,
about 35 held an ONNX, TFLite or fastText model file, and one of those had a
`pyproject.toml` (`ccds/vits_onnx`; its SBOM builds but lists no files and no
AI model, because the model is under a hidden folder, `app/.model/`). Two
Spaces named in an earlier example list do not exist. So a Space cannot be an
example for Lumina, and a user who pastes one gets an error.

Other limits of a Git fetch of a Space or of any repository:

- **Git LFS.** Model files are usually LFS objects; Pitloom switches LFS off,
  so the working tree holds pointer files (`version https://git-lfs...`, about
  130 bytes), and no AI model is read. The same holds for any GitLab or Codeberg
  repository that stores a model through LFS (a GitLab repository searched the
  same day had three `.onnx` files, all pointers). This is a known limitation of 0.21.0, planned for 0.22.0: see the item "Git
  LFS pointers" in [roadmap.md](roadmap.md).
- **Where the model lives.** The file list of a project comes from its build
  backend; a model at the repository root or in a hidden folder is not in it.

## How a Space is built

A Space is a Git repository with a `README.md` whose YAML front matter is the
Space's configuration, plus the code:

| Piece | What it says |
| :---- | :----------- |
| `README.md` front matter | `sdk` (`gradio`, `streamlit`, `docker`, `static`), `sdk_version`, `app_file`, `python_version`, `license`, `models`, `datasets`, `title` |
| `app.py` (or `app_file`) | the application; loads models by Hub id |
| `requirements.txt` | Python dependencies, often unpinned |
| `packages.txt` | apt packages |
| `Dockerfile` | for `sdk: docker` |
| LFS files | model weights, data |

The Space's API record (`https://huggingface.co/api/spaces/<org>/<name>`) adds
`sdk`, `sha` (the commit), `runtime`, `tags`, `siblings` (the file list) and
**`models`**: the Hub ids of the models the Space uses, which the Hub derives
itself. Checked on `Chuanming/facebook-fasttext-language-identification`:
`models` is `['facebook/fasttext-language-identification']`, and its whole
`app.py` is `gr.Interface.load("models/facebook/fasttext-language-identification").launch()`.
No Python is packaged and the only model is named by a string.

## Direction (for discussion, in order of cost)

1. **Read the Space's own metadata, not a Python project.** The `README.md`
   front matter and the API record give the name, licence, SDK, the commit
   (`sha`) and the used models and datasets, with no code reading. A Space would
   be a `software_Package` (primary purpose `application`) whose `dependsOn` or
   `uses` link goes to the model packages by Hub id (`pkg:huggingface/...`), the
   way a model card's datasets are linked today.
2. **`requirements.txt` as the dependency list**, through the requirements
   reader that already exists (it reads continuation lines and extras).
   `packages.txt` and a `Dockerfile` are separate sources with their own
   semantics, to measure first.
3. **Model references in code.** `app.py` loads models through
   `from_pretrained("org/model")`, `pipeline(model="...")`, `hf_hub_download`,
   `gr.Interface.load("models/...")`, `fasttext.load_model(path)`. A static
   scan (`ast`) can find a string-literal id; a path built at run time cannot be
   found. The Hub's own `models` list is the cheaper and more complete source
   when the network is allowed. A reference found in code is a claim with
   provenance (`Method: ast_literal`); one that cannot be resolved stays absent
   (CLAUDE.md: absent data is not an error).
4. **The LFS pointer as a hash.** An LFS pointer holds `oid sha256:<hex>` and
   `size`: the SHA-256 and the length of the real file, by the LFS design. Pitloom
   could record that digest as the model file's hash (`Method: lfs_pointer`)
   without downloading it, and say that the file itself was not read. This also
   helps every Git source with LFS, not only Spaces; it needs the 0.22.0 LFS item above
   (one shared pointer detector). The file's format and metadata stay unread, so
   an AI package built from a pointer is only a hash and a name: say so.
5. **Fetching an LFS file** (one that is small, under the clone cap) is a policy
   question: it contacts a second server (the LFS endpoint), which the Git URL
   guard does not cover (CLAUDE.md: a check on the URL does not cover every
   client a fetch starts).

## Questions

- Is a Space a `loom project` target with its own reader (Spaces are Python), or
  a separate kind (`hf-space`) in the target table of
  [target-resolution-and-purl.md](target-resolution-and-purl.md)? A
  `pkg:huggingface/` PURL with a type for spaces does not exist in the PURL
  type definition read on 2026-10-23 (it names models only).
- Whether the Hub API may be used by default (network, rate limits, a token for
  a private Space) or only the Git content, with the API as a fallback.
- What an SBOM of an application says about the models it loads at run time and
  does not ship: a `dependsOn` to a model that is not in the repository, by id
  and revision.
- How the G7 and CISA elements read such an SBOM (a Space has no producer or
  version of its own besides the commit); see the checker's rules before choosing
  the relationship types.
- The format-gaps ledger: a relationship "this application loads that model at
  run time" has no precise SPDX 3.0.1 term (`dependsOn` with a scope is the
  nearest); add an entry when built ([sbom-format-gaps.md](sbom-format-gaps.md)).

## Out of scope here

`loom project` for a non-Python Space (`sdk: docker` with a Node app, `static`):
the same metadata reading applies, the dependency reader does not.
