---
Created: 2026-10-21
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM from a Git URL

See also: [Command line](cli.md) for `loom project`, `loom model` and
`loom generate`,
[SBOM from a Git URL, behaviour and messages](git-urls-behaviour.md) for
what Pitloom does with a downloaded repository and every message it prints,
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
SBOM. The directory is removed afterwards (one that cannot be fully removed,
such as a file still held open on Windows, is one `WARNING:` ending
`[temp-dir-unwritable]`, not an error: the SBOM is already written), and a message that would name it says
`<checkout>` instead, so two runs print the same text. It needs the `git`
program (without it: `git is not installed or not on PATH; nothing fetched
[git-missing]`).

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
  an `INFO:` says so (`URL=<url>: the version names no branch, tag or commit;
  the default branch is read [query-no-effect]`).
- A **commit** must be given with its full 40 (or 64) hex digits; a server cannot
  be asked for an abbreviated id. A branch, tag or commit the repository does
  not have is an error naming it (`URL=<url>: no branch or tag <ref>; a commit
  needs its full 40 or 64 hex digits [git-ref-not-found]`, `git.ref-not-found`).
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
  cloned and fails (`git.clone-failed`,
  [`git-repository-unusable`](message-codes-git.md#git-repository-unusable)). Use the `github.com` `blob` or `raw`
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
  naming the right call (`pypi-url-unusable`). A link to a file on
  `files.pythonhosted.org` is a PyPI URL too: never cloned, and refused by
  `loom wheel` and `loom project` with the release page to give instead.
- A host is written in plain ASCII (an international name in its `xn--`
  form): a host with a non-ASCII character or a percent-encoding is refused
  before git runs
  ([`url-unsafe/host-spelling`](message-codes-network.md#url-unsafehost-spelling)),
  since git would resolve it to a host the URL's text does not spell; so is a
  host holding a character no host name holds (`=`, `!`, `;`, white space,
  a leading `-` or `.`), the shape of an option or of a setting smuggled into
  git's command line, and a name in brackets (`[v1.x]`), which would lose
  its brackets and name a DNS host. In brackets only an IPv6 address passes
  (`[::1]`, `[::ffff:1.2.3.4]`); one with a zone id (`[fe80::1%25eth0]`) is
  refused too.
- Refused with a message (see below): hosts that need a login, `ssh://`,
  `git://`, `file://` and scp-style `user@host:path` addresses.

## Verified platforms

Fetched with `loom` from a real server, on 2026-10-21 and 2026-10-23 (the live tests in
`tests/extract/remote/test_git_platforms_live.py` repeat these when run with
network access):

| Platform | Server | Forms fetched |
| :------- | :----- | :------------ |
| GitLab | `gitlab.com` | bare URL (redirected to `.git`), `/-/tree/` page |
| Forgejo | `codeberg.org` | bare URL, `/src/branch/` page, file page, `/src/tag/` page |
| Gerrit | `review.opendev.org` | bare URL |
| Gitiles | `pigweed.googlesource.com` | `/+/refs/heads/<branch>/<folder>` page |
| cgit | `git.kernel.org` | bare URL, `/tree/<folder>?h=<branch>` page |
| Azure DevOps | `dev.azure.com` | bare URL, `?path=<folder>&version=GB<branch>` page |
| Hugging Face Space | `huggingface.co/spaces/...` | bare URL, `/tree/<branch>` page |
| Gitea | `gitea.com` | `/src/branch/<branch>/<folder>` page |
| GitHub | `github.com` | bare URL, `/tree/` page |

Also fetched by hand on 2026-10-23, and not repeated by the live tests (they
keep one or two cases per platform, so an unrelated host's outage cannot block
a release):

- **Bitbucket Cloud** (`bitbucket.org`, 2026-10-23, `zzzeek/sqlalchemy`): the
  bare URL and `/src/<branch>/<folder>` are in the live tests; a file page,
  `/branch/<ref>` and `/commits/tag/<ref>` were fetched by hand. A repository that does not exist answers
  like one that needs a sign-in. Bitbucket serves a path below the repository
  as the default branch, so Pitloom reads these page forms itself (`/branch/x`,
  `/commits/<sha>`) rather than let a URL it did not recognise fetch the
  default branch without a word.
- **SourceHut** (`git.sr.ht`, 2026-10-23, `~sircmpwn/scm.sr.ht`): the bare URL is in
  the live tests; `/tree/<ref>/item/<folder>`, a file page and `/log/<ref>`
  were fetched by hand.
- **Azure DevOps** (2026-10-23, `mseng/PipelineTools`): the server answers
  `--filter=blob:limit` with HTTP 400. Pitloom asks again without the filter
  (an `INFO:` says so), also for a tag or commit page; a size cap, where one is
  set (see below), still bounds the transfer.
- **GNU Savannah**: the web pages (`/cgit/…`, `/gitweb/…`) redirect to hosts
  that answered 502 when tried; only the clone URL was fetched.
- **Gogs**: not tried live (the public demo, `try.gogs.io`, holds no
  repository with commits). Its page form, `…/src/<ref>/<folder>`, is the one
  Bitbucket uses and is parsed.
- **Self-hosted GitLab with a URL prefix**: `labs.etsi.org/rep` (ETSI),
  `code.europa.eu`, `gitlab.opencode.de`, `forge.apps.education.fr`,
  `framagit.org` and `gitlab.cern.ch` were fetched by hand like `gitlab.com`;
  so was `code.overheid.nl` (Forgejo). A Gitea under
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
  is `git.path-not-found` (`no file '<path>' in the repository at that
  branch [input-not-found]`); for `loom model`, any named file is. `loom
  project <url>` on a folder with models and no project says `ERROR: loom
  project: '<url>': no Python project (pyproject.toml, setup.cfg or
  setup.py); it holds files that may be AI models ...
  [project-not-found/model-files]`.
- **A name is read as the repository spells it, and stays inside the clone.**
  An encoded slash between plain names (`models%2Fm.keras`) is a path inside
  the folder (here `models/m.keras`). A URL segment that decodes (`%2F`) to a
  part `.` or `..`, an empty part, a backslash, a NUL or `.git` (any case,
  trailing dots or spaces, `git~1`, an NTFS stream such as `.git::$DATA`) is refused
  (`URL=<url>: a path part decodes to ., .., an empty part, a backslash, a NUL
  or .git; nothing fetched [git-url-invalid]`, `git.url-invalid`), and a name that does not match a file on disk letter for
  letter is "not found" on every operating system, also where the file system
  ignores case. `.gitmodules`, `.gitattributes`, `.gitignore`, `.github` and
  `foo.git` stay valid names. A link named in a
  `blob` URL is not followed and has its own line under
  [`input-not-found`](message-codes-targets.md#input-not-found). A named FIFO or other
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
  files are read in full. To read the others from a repository you trust, pass
  `--trust-model-files` (library `trust_model_files=True`, Action input
  `trust-model-files`): it lifts only this gate, and the repository's own
  `[tool.pitloom]` is still ignored. Cloning the repository (with Git LFS,
  when it stores the model there) and running `loom model <file>` or `loom
  project <dir>` on the copy reads them too, but also trusts the
  repository's configuration and build file list. The gate covers a
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
  [AI model formats](ai-model-formats-hugging-face.md#hugging-face-hub-models).

## What it does and does not do

Moved to [SBOM from a Git URL, behaviour and messages](git-urls-behaviour.md#what-it-does-and-does-not-do).

## Messages

Moved to [SBOM from a Git URL, behaviour and messages](git-urls-behaviour.md#messages).
