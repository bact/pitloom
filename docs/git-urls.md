---
Created: 2026-10-21
Last-Modified: 2026-11-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM from a Git URL

See also: [Command line](cli.md) for `loom project`, `loom model` and
`loom generate`,
[Python API: remote targets](python-api-remote.md) for `generate()`, `generate_git_sbom()` and
`generate_git_project_sbom()`,
[AI model formats](ai-model-formats.md) for what is read from each model file,
[Building a project (`--allow-build`)](allow-build.md) for why a downloaded
repository is never built.

Give `loom project`, `loom model` or `loom generate` the `http` or `https` URL
of a Git repository, or of one of its web pages, and Pitloom fetches the
repository shallowly into a temporary directory, reads the Python project in it
(or, for `loom model` and for `loom generate` on a folder with models and no
project, an AI model file; see [Model files](#model-files)) and writes the
SBOM. The directory is removed afterwards, and a message that would name
it says `<checkout>` instead, so two runs print the same text. It needs the
`git` program.

```bash
loom project https://gitlab.com/group/project                  # the default branch
loom project https://github.com/owner/repo/tree/v1.2/src       # a tag and a folder
loom project https://codeberg.org/owner/repo/src/branch/main/svc/api
loom generate https://labs.etsi.org/rep/ocf/capif/-/tree/staging/services/register -o sbom.json
loom model https://github.com/owner/repo/blob/main/models/m.keras   # one model file
```

## Which URLs

Prefer the repository's **clone URL** (the one the host's Clone button
shows): it names the default branch and is never misread. To read one branch,
tag, commit or folder, paste the address of that page instead; the `INFO:` lines
say what was read. The repository is the part of the path before the page marker, so a
URL prefix (`/rep` on ETSI's GitLab) and GitLab subgroups work. A branch name
may contain `/` (`feature/x`): the split between branch and folder is taken
from the server's own branches and tags, longest match first.

| Platform | Page URL read | Names |
| :------- | :------------ | :---- |
| GitLab | `…/-/tree/<ref>/<folder>`, `…/-/blob/<ref>/<file>`, `…/-/raw/<ref>/<file>` | branch, tag, commit; folder, file |
| GitHub | `…/tree/<ref>/<folder>`, `…/blob/<ref>/<file>`, `…/raw/<ref>/<file>` | branch, tag, commit; folder, file |
| Gitea, Forgejo, Codeberg | `…/src/branch/<ref>/…`, `…/src/tag/<ref>/…`, `…/src/commit/<sha>/…`, `…/raw/branch/<ref>/<file>`, `…/raw/tag/<ref>/<file>`, `…/raw/commit/<sha>/<file>` | branch, tag, commit; folder, file |
| Bitbucket Cloud | `…/src/<ref>/<folder>`, `…/raw/<ref>/<file>`, `…/branch/<ref>`, `…/commits/branch/<ref>`, `…/commits/tag/<ref>`, `…/commits/<sha>` | branch, tag, commit; folder, file |
| SourceHut | `…/tree/<ref>/item/<folder>`, `…/log/<ref>` | branch, tag; folder |
| Gitiles (Gerrit's code browser, `*.googlesource.com`) | `…/+/refs/heads/<ref>/<folder>`, `…/+/refs/tags/<ref>/<folder>`, `…/+/<ref>/<folder>` | branch, tag; folder |
| cgit (kernel.org, Launchpad) | `…/tree/<folder>?h=<ref>`, `…/log/?h=<ref>`, `…/commit/?id=<sha>` | branch, tag, commit; folder |
| Azure DevOps | `…/_git/<repo>?path=/<folder>&version=GB<branch>` (`GT` tag, `GC` commit) | branch, tag, commit; folder |
| Hugging Face Space or dataset | `huggingface.co/spaces/<org>/<name>`, `…/datasets/<org>/<name>`, with `…/tree/<ref>/<folder>` or `…/blob/<ref>/<file>` | branch, tag, commit; folder |

- A page URL naming a **file** (`blob` or `raw`) reads the folder that holds it,
  unless the file is an AI model: then it is the model that is read (see
  [Model files](#model-files)). A file page whose
  path is a folder reads that folder, and a folder page whose path is a file
  (Bitbucket, SourceHut, Forgejo and Gitiles write both alike) reads the folder
  holding the file.
- Where the ref is in the query (cgit, Azure DevOps) it is exact: it is not
  split from the folder, and a `?h=` or `?id=` after a cgit page name is the ref
  whatever the folder is called (`src`, `tree`), unless the path holds a GitLab
  (`-`) or Gitea (`src/commit|branch|tag`) marker, which makes the query stray.
  An Azure DevOps `version` that does
  not start with `GB`, `GT` or `GC` names no ref: the default branch is read and
  an `INFO:` says so.
- A **commit** must be given with its full 40 (or 64) hex digits; a server cannot
  be asked for an abbreviated id.
- A query or fragment (`?ref_type=heads`, `#readme`) is ignored.
- A tag and a branch with one name: a `src/tag` page takes the tag, any other
  page the branch.
- A URL ending in `.git` is always a repository. GitLab's `/-/` marker is
  read first, so a group called `src` or `tree` is no problem there; elsewhere,
  for a group or project called `src`, `tree` or `blob` after the second path
  segment, Pitloom tries the page reading first and then, when the server says
  the repository is not found, the whole URL as the repository.
- A Hugging Face **model** address (`huggingface.co/<org>/<name>`, also `hf.co`
  and `www.` forms) is not a Git repository for Pitloom: `loom model` reads it,
  and `loom project` refuses it with a message naming `loom model`. A **Space**
  or **dataset** (`huggingface.co/spaces/...`, `.../datasets/...`) is a Git
  repository and is fetched like any other (Git LFS files stay pointers; see
  below). A Space with no `pyproject.toml`, `setup.cfg` or `setup.py` has no
  Python project to read, and `loom project` says so (naming `loom model` when
  the folder holds files that may be models).
- Not read as a file: `raw.githubusercontent.com` is a file host, not a
  repository page, but its URL is taken as a repository: the whole URL is
  cloned and fails (`git.clone-failed`). Use the `github.com` `blob` or `raw`
  page of the file instead. A Hugging Face `/resolve/` file link of a model
  (`huggingface.co/<org>/<name>/resolve/main/<file>`) is read as the Hub
  model `<org>/<name>`: the file part is dropped and no model file is read.
  The `/resolve/` link of a Space or a dataset is taken as a repository and
  fails as `raw.githubusercontent.com` does: give the repository address.
- A **PyPI** address is not a Git URL: `pypi.org`, `www.pypi.org`, any other
  `*.pypi.org` host and `pypi.python.org` are never cloned. `loom wheel`,
  `loom project` and `loom generate` read a project or release page there
  (`https://pypi.org/project/<name>/`; see [SBOM from a PyPI URL](pypi-urls.md)),
  and `loom model` and the library's Git functions refuse one with a message
  naming the right call (`pypi-url-unusable`). A link to a file on `files.pythonhosted.org` is not
  recognised as a PyPI URL and is cloned as a repository, which fails.
- Refused with a message (see below): hosts that need a login, `ssh://`,
  `git://`, `file://` and scp-style `user@host:path` addresses.

## Verified platforms

Fetched with `loom` from a real server, on 2026-10-21 and 2026-10-23 (the live tests in
`tests/extract/remote/test_git_platforms_live.py` repeat these when run with
network access):

| Platform | Server | Forms fetched |
| :------- | :----- | :------------ |
| GitLab | `gitlab.com` | bare URL (redirected to `.git`), `/-/tree/` page |
| GitLab | `labs.etsi.org/rep` (ETSI) | bare URL, `/-/tree/<branch>/<folder>` page |
| GitLab | `code.europa.eu` (European Commission) | bare URL |
| GitLab | `gitlab.opencode.de` (German public sector) | `/-/tree/<branch>/<folder>` page |
| GitLab | `forge.apps.education.fr` (French education) | bare URL |
| GitLab | `framagit.org` | bare URL |
| GitLab | `gitlab.cern.ch` (CERN) | bare URL |
| Forgejo | `codeberg.org` | bare URL, `/src/branch/` page, file page, `/src/tag/` page |
| Forgejo | `code.overheid.nl` (Dutch government) | bare URL, `/src/branch/<branch>/<folder>` page, file page |
| Gerrit | `review.opendev.org` | bare URL |
| Gitea | `opendev.org` | `/src/branch/<branch>/<folder>` page |
| Gitiles | `gerrit.googlesource.com`, `pigweed.googlesource.com` | bare URL, `/+/refs/heads/<branch>/<folder>` page |
| cgit | `git.kernel.org` | bare URL, `/tree/<folder>?h=<branch>` and `?h=<tag>` pages |
| cgit | `git.launchpad.net` (Launchpad) | bare URL, `/tree/<folder>?h=<branch>` page |
| GNU Savannah | `git.savannah.gnu.org` | the `/git/<project>.git` clone URL |
| Azure DevOps | `dev.azure.com` | bare URL, `?path=<folder>&version=GB<branch>` page |
| Hugging Face Space | `huggingface.co/spaces/...` | bare URL, `/tree/<branch>` page |
| Gitea | `gitea.com` | `/src/branch/<branch>/<folder>`, `/src/tag/<tag>/<folder>` pages |
| GitHub | `github.com` | bare URL, `/tree/` page, `/blob/` page |

Also checked, with a narrower scope:

- **Bitbucket Cloud** (`bitbucket.org`, 2026-10-23, `zzzeek/sqlalchemy`): the
  bare URL, `/src/<branch>/<folder>`, a file page, `/branch/<ref>` and
  `/commits/tag/<ref>` are fetched. A repository that does not exist answers
  like one that needs a sign-in. Bitbucket serves a path below the repository
  as the default branch, so Pitloom reads these page forms itself (`/branch/x`,
  `/commits/<sha>`) rather than let a URL it did not recognise fetch the
  default branch without a word.
- **SourceHut** (`git.sr.ht`, 2026-10-23, `~sircmpwn/scm.sr.ht`): the bare URL,
  `/tree/<ref>/item/<folder>`, a file page and `/log/<ref>` are fetched.
- **Azure DevOps** (2026-10-23, `mseng/PipelineTools`): the server answers
  `--filter=blob:limit` with HTTP 400. Pitloom asks again without the filter
  (an `INFO:` says so), also for a tag or commit page; a size cap, where one is
  set (see below), still bounds the transfer.
- **GNU Savannah**: the web pages (`/cgit/…`, `/gitweb/…`) redirect to hosts
  that answered 502 when tried; only the clone URL was fetched.
- **Gogs**: not tried live (the public demo, `try.gogs.io`, holds no
  repository with commits). Its page form, `…/src/<ref>/<folder>`, is the one
  Bitbucket uses and is parsed.
- **Self-hosted GitLab with a URL prefix** is the ETSI row above. A Gitea under
  a prefix was not found to try; the repository is the path before the marker,
  so a prefix does not matter to the parser.

What a platform answers differs: every GitLab sends a redirect from
`group/project` to `group/project.git`, which Pitloom follows; Forgejo, Gitea,
GitHub and Bitbucket serve the bare URL as it is.

Beyond live servers, the whole path (redirect, branch, folder, tag, commit,
`.git`, refusals) runs in the test suite against a local Git server over smart
HTTP (`git http-backend`) that answers like GitLab does.

## Model files

A URL can name an AI model instead of a project: a `blob` or `raw` page of a
model file (also a `src/<ref>/<file>` page of Forgejo, Codeberg or Bitbucket,
and a SourceHut `blob` page), or a `tree` page (or the repository itself) of a
folder that holds one. The SBOM is then the model SBOM `loom model` writes for a local file,
whatever the format (CRFsuite, fastText, GGUF, HDF5, Keras, NumPy, ONNX,
PyTorch, PT2, Safetensors). Which command reads which URL:

| Command | A model file URL | A folder URL (or the repository) |
| :------ | :--------------- | :------------------------------- |
| `loom generate <url>` (and `generate()`) | the model | the project if the folder has one, else its one model file |
| `loom model <url>` | the model | its one model file, even beside a project |
| `loom project <url>` | the folder's project | the project; a folder with models and no project is refused (`git.no-project`), naming `loom model` and `loom generate` |

- **A model file URL wins** over a project in the same folder. A file URL whose
  name no model file has (`blob/.../pyproject.toml`, `README.md`) and that is
  not a model, or is missing or a link, reads the folder as before, with one
  `INFO:`; `loom model` refuses it. A file named as a model (`.gguf`, `.onnx`,
  `.bin`, ...) that is not one (empty, or of no supported format) is refused
  by both, as `loom model <file>` refuses it locally.
- **A folder is read non-recursively**: only the named folder, and for the
  repository itself only the files at its root. A model in a subfolder needs
  that folder's URL or the file's. A folder of more than 1000 files whose
  names could be models is not read (one `over-cap` `WARNING:`) and is
  refused (`more than 1000 files that could be AI models, none read`;
  `model-ambiguous/over-cap`).
- **One model per SBOM.** A folder with several model files is an error
  (`model-ambiguous`): one `INFO:` per file names them, sorted, and you give
  the URL of one file. A folder with neither project nor model is an error
  (`project-or-model-not-found`; the error code is `git.no-project` only when
  the repository has subprojects, which the message names; an empty or
  README-only repository gives `project-or-model-not-found` with no `git.*`
  code). `loom model <url>` on such a folder says `not an AI model file of a
  supported format` (`model-wrong-format`) instead, as for a local path that is
  not a model. A named file with
  a model suffix that is not in the repository, or is a link (not followed),
  is `git.path-not-found` (`No file '<path>' in the repository at that
  branch. [input-not-found]`); for `loom model`, any named file is. `loom
  project <url>` on a folder with models and no project says `ERROR: ... No
  pyproject.toml, setup.cfg, or setup.py found in <url>; it holds files that
  may be AI models ... [project-not-found/model-files]`.
- **A name is read as the repository spells it, and stays inside the clone.**
  An encoded slash between plain names (`models%2Fm.keras`) is a path inside
  the folder (here `models/m.keras`). A URL segment that decodes (`%2F`) to a
  part `.` or `..`, an empty part, a backslash, a NUL or `.git` (any case,
  trailing dots or spaces, `git~1`, an NTFS stream such as `.git::$DATA`) is refused (`Invalid path in URL`,
  `git.url-invalid`), and a name that does not match a file on disk letter for
  letter is "not found" on every operating system, also where the file system
  ignores case. `.gitmodules`, `.gitattributes`, `.gitignore`, `.github` and
  `foo.git` stay valid names. A link named in a
  `blob` URL is not followed and has its own line under
  [`input-not-found`](message-codes.md#input-not-found). A named FIFO or other
  special file is refused, never opened.
- A file is a model by its **content**, not its name: a GGUF file named `m.dat`
  is recognised as GGUF when its URL is given, and listed without metadata
  (the GGUF reader is not run on a download: next item). A folder's candidates are chosen by the
  suffixes the scan knows, then confirmed by their content.
- **Some readers are not run on a download.** The readers
  of fastText, HDF5 and ONNX files open the file with a C/C++ library, the
  PyTorch (`.pt`, `.pth`) reader parses a pickle, and the GGUF reader runs a
  parsing loop that a crafted file can make very slow or very large: a
  hostile file could crash, hang or exhaust them in memory. A model of one of
  these formats that a model SBOM from a Git URL describes, or that the build
  file list of a project from a Git URL holds, is listed with its name,
  format and hash only, and one `INFO:` per SBOM says so. Keras, Safetensors
  (with its Rust library, read in full on purpose), NumPy, CRFsuite and PT2
  files are read in full. To read the others, clone the repository (with Git
  LFS, when it stores the model there) and run `loom model <file>` on a file
  you trust, or `loom project <dir>` on a project you trust. The gate covers a
  folder read as a project too (`loom project`, or `loom generate` on a
  folder with `pyproject.toml`, `setup.cfg` or `setup.py`); a local project
  directory is not gated.
- **Git LFS pointers are refused.** A model file that is a pointer (LFS is off
  for the clone) is an error that gives the pointer's `oid` and size and says
  to clone with Git LFS and run on the file. In a folder, pointers beside
  a model are counted in one `WARNING:`; a folder of pointers only is refused
  as the first of them, with no warning.
- The SBOM names the file by its own name, and every message by its path in
  the repository: no temporary path is in the output, so two runs of one URL
  and commit give the same SBOM for a fixed creation time. `loom model <url>`
  writes `<file name>.spdx3.json` to `-o` or the current directory, never into
  the checkout.
- `--offline` is an error for `loom model <url>` too: nothing is fetched.
- Only a Git repository is read this way. A Hugging Face **model** (not
  Space or dataset) address is read through the Hub, which reads the model
  card and repository metadata and never opens a weights file: see
  [AI model formats](ai-model-formats.md#hugging-face-hub-models).

## What it does and does not do

- **A downloaded repository is untrusted.** Its own `[tool.pitloom]` settings are
  ignored (`INFO: Git source: the repository's own [tool.pitloom] settings are
  ignored (untrusted) ... [config-unsafe]`; `--config FILE` is yours and
  applies), and `--allow-build` is reported as having no effect. The URL's
  user information is not kept: the clone's `.git/config` is rewritten without
  it right after checkout. A discovery failure shows only the exception type
  ("text not shown for a downloaded repository"), and a line of the
  repository's requirements file is replaced by `<a line of the downloaded
  repository, not shown>`.
- **The repository's own build-time code is not run** while its files are
  listed. In a clone, these settings are ignored, with one `WARNING:` naming
  the file and the settings ([`config-unsafe/build-code`](message-codes.md#config-unsafebuild-code)):
  Hatchling metadata hooks (`pyproject.toml` and `hatch.toml`), setuptools
  `cmdclass` and an `attr:` version Pitloom cannot read statically, and PDM
  hooks (`pdm_build.py`, `custom-hook`, `run-setuptools`). The `[global]`
  section of `setup.cfg` is not applied either (`global` is named among the
  settings). Discovery does not import repository code through the working
  directory (`''`, relative and in-clone `sys.path` entries are removed while
  it runs). Hatchling build
  hooks, a `version` of `source = "code"` alone, PDM `source = "call"`, a Flit
  dynamic version, `setup.py` (read as a syntax tree), a Poetry build script
  and in-tree backends do not run the repository's code either. A local
  project is not changed: it still runs its own hooks, as a build would.
- The clone is shallow, asks the server to leave out blobs over 10 MiB that the
  checkout does not need (a server without partial clone sends them) and never
  follows a redirect on its own: Pitloom follows the Git server's redirect itself, one hop at a time
  (at most 5, 60 s for all probes), and a caller can check each hop first
  (`check_url=` in the Python API; Lumina uses it as its address guard).
- `git` has 10 minutes for all its calls together and 8 MiB of output (and of
  error text) per call. Ctrl-C stops `git` and what it started. `git` runs
  with only the http(s) transports, git-lfs off (a repository's LFS settings
  could name another host; LFS files are not downloaded) and without
  `GIT_DIR`-style variables of the calling environment.
- **Git LFS files are pointers.** LFS is off, so a file kept in LFS is a small
  pointer file in the checkout, and Pitloom never fetches its content. The SBOM
  lists it with the pointer's `oid` as its SHA-256 (no SHA-512; the hash
  comment says the content was not read, and the file's provenance is `Method:
  lfs_pointer`), so the hash is the same after `git lfs pull`. The stated size
  is only recorded in that comment. A pointer named like an AI model (`.onnx`,
  `.gguf`, ...) is listed as a file only, with no AI package; a pointer named
  by its own URL is an error (see [Model files](#model-files)). No content type,
  licence or copyright comes from the pointer text. One `WARNING:` per SBOM
  names the first pointer (and, for more than one, the count): `clone with git
  lfs, then run on the directory`. Run `loom project` on that directory for
  the content. Most model repositories on Hugging Face, and many on GitLab
  and Codeberg, keep their weights in LFS.
- **No size limit by default.** The command line sets none, so a very large
  repository is fetched in full: the 10 MiB filter leaves out only large blobs
  the checkout does not need, and a large file in the checked-out tree (a model
  of 12 MiB, say) is fetched. The library API can stop a fetch once the checkout
  takes more disk than a limit you give (`max_clone_bytes=`, error code
  `git.too-large`, message code [`over-cap`](message-codes.md#over-cap)):
  [Python API: remote targets](python-api-remote.md).
- A cloned project's build file list (Hatchling `force-include`, setuptools
  `package-dir`, `packages.find.where` or `package-data` with an absolute or
  `..` path, say) keeps only files inside the repository. Such an entry is
  dropped before the files are discovered, one `WARNING:` per entry as written
  ([`file-unreadable/outside-repository`](message-codes.md#file-unreadableoutside-repository)),
  and a file found outside after discovery is only counted, in one more line;
  so a host file is never listed, hashed or read. The same holds for a `file:`
  directive, `license-files`, `packages`/`py_modules` and Poetry
  `packages`/`include`/`exclude` naming a path outside the clone. Files under
  the clone's own `.git` are never read or listed. A local project is not changed.
- Not every build file list is checked before discovery: MANIFEST.in, PDM,
  Poetry and Flit entries are still walked, and a file outside the repository
  is dropped afterwards (and counted).
- A symbolic link in the checkout that leads out of it or into its `.git`, and
  every link to a folder, is removed before the project is read (an `INFO:`
  counts them), so a host file is never read or hashed. File discovery in a
  clone stops after 60 seconds (`over-cap` `WARNING:`, file list not read).
  Blocks of `fetch_git_project` that overlap each keep their own confinement.
- A relative `--id-registry` is relative to where you run `loom`, not to the
  checkout.
- `--offline` forbids the fetch: it is an error, not a fallback, for `loom
  project`, `loom model` and `loom generate` alike.
- An empty repository is an error that says so.
- The output file is named from the project (or the model file), as for a
  local one, and written to the current directory. `-o -` writes the SBOM to
  stdout.

## Messages

Every URL that is changed, refused or not followed is said, never silently:

| Level | Message | When |
| :---- | :------ | :--- |
| `INFO:` | `Git source: <url> redirected to <url>` | the server redirected: both URLs |
| `INFO:` | `Git source: <url> names repository <url>, branch <ref>, folder <path>` | the URL named more than a repository (or was cleaned) |
| `INFO:` | `Git source: <url> is not a repository; trying <url>` | a group called `src`/`tree`/`blob`: the whole URL is tried |
| `INFO:` | `Git source: <path> is a folder, not a file; reading it` | a file page whose path is a folder |
| `INFO:` | `Git source: <path> is a file, not a folder` | a folder page whose path is a file: the file is read as the one the URL named (a model file, or else its folder) |
| `INFO:` | `FILE=<file>: not an AI model file; reading its folder` | the file URL named a file whose name no model has, and that is not a model or is missing (`loom generate`) |
| `INFO:` | `FILE=<file>: no Python project; reading this AI model file` | `loom generate` on a folder with no project and one model |
| `INFO:` | `FILE=<file>: the one AI model file; reading it` | `loom model` on a folder with one model |
| `INFO:` | `FILE=<file>: one of several AI model files`, then `ERROR:` `<url>: several AI model files (N files); name one file` | a folder holds several models (one line per file; `model-ambiguous`) |
| `INFO:` | `AI models from a Git URL in these formats are listed without metadata, their reader not being run on a downloaded file: <formats>; clone the repository and run on the file you trust` | a model in a format whose reader is not run on a download |
| `ERROR:` | `<url>: no Python project (pyproject.toml, setup.cfg or setup.py) and no AI model file of a supported format; name a project folder or a model file` | neither a project nor a model (`project-or-model-not-found`) |
| `ERROR:` | `<file>: header is a Git LFS pointer, content not fetched (oid sha256:<oid>, size <size>); clone with git lfs, then run on the file` | the named model file is an LFS pointer |
| `INFO:` | `Git source: the server rejected the blob filter; fetching without it` | the server cannot leave out large blobs (Azure DevOps) |
| `INFO:` | `Git source: could not check <url> for a redirect (<reason>); asking git directly` | the redirect probe failed |
| `INFO:` | `Git source: $ git …` | each `git` call, credentials masked |
| `WARNING:` | `Git source: <url> redirected to <url>, which is not followed: <why>` | a redirect to another scheme, or to a page that is not a repository |
| `INFO:` | `Git source: <n> symbolic link(s) leading out of the repository, into its .git directory or to a folder were not followed` | such links were removed |
| `WARNING:` | `Git source: <reason>` | any refusal, as well as its `ERROR:`: an ssh, git, file or scp-style address, `--offline`, too many redirects, a redirect the caller's check refuses, an unknown ref or folder, a failed `git` call |
| `WARNING:` | `FILE=<file>: build-time code of the downloaded repository is not run; <settings> ignored [config-unsafe/build-code]` | a cloned project's build settings would run the repository's own code (once per SBOM) |
| `WARNING:` | `FILE=<entry>: outside the downloaded repository; not read [file-unreadable/outside-repository]` | a build file list entry, as written, names a path outside the repository (one line per entry) |
| `WARNING:` | `DIR=<dir>: larger than the 60-second file-discovery cap; file list not read [over-cap]` | file discovery in a clone ran over its time cap |
| `WARNING:` | `listed files outside the downloaded repository<count>; not read [file-unreadable/outside-repository]` | files found outside after discovery (counted, not named) |
| `ERROR:` | `Invalid path in URL: <url>` (`git.url-invalid`) | a branch or path part that decodes to `.`/`..`, an empty part, a backslash, a NUL or `.git` |
| `WARNING:` | `Build: <url>: --allow-build has no effect for a remote repository …` | a build flag |
| `ERROR:` | `SBOM generation failed: …` | the run could not finish |

A URL or ref in a message is shown without credentials (`https://***:***@host`,
and, in a URL, the value of a query or fragment parameter named `token`, `key`,
`secret`, `password`, `sig`, `signature` and the like, or ending in `_token`,
`_secret`, `_key` or `_password`: `?private_token=***`) and with control
characters escaped. A secret in a parameter with another name is not
recognised. What a server or `git` says is reduced to
one line (its `fatal:`, `error:` and `remote:` lines), so it cannot add a
tagged line of its own.

If the repository has no Python project at its root but has some in folders,
the error names them (up to five) and asks for the URL of one of them.
