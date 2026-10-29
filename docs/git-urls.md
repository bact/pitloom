---
Created: 2026-10-21
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM from a Git URL

See also: [Command line](cli.md) for `loom project` and `loom generate`,
[Python API](python-api.md) for `generate()` and `generate_git_project_sbom()`,
[Building a project (`--allow-build`)](allow-build.md) for why a downloaded
repository is never built.

Give `loom project` or `loom generate` the `http` or `https` URL of a Git
repository, or of one of its web pages, and Pitloom fetches the repository
shallowly into a temporary directory, reads the Python project in it and writes
the SBOM. The directory is removed afterwards, and a message that would name
it says `<checkout>` instead, so two runs print the same text. It needs the
`git` program.

```bash
loom project https://gitlab.com/group/project                  # the default branch
loom project https://github.com/owner/repo/tree/v1.2/src       # a tag and a folder
loom project https://codeberg.org/owner/repo/src/branch/main/svc/api
loom generate https://labs.etsi.org/rep/ocf/capif/-/tree/staging/services/register -o sbom.json
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
| GitLab | `…/-/tree/<ref>/<folder>`, `…/-/blob/<ref>/<file>` | branch, tag, commit; folder |
| GitHub | `…/tree/<ref>/<folder>`, `…/blob/<ref>/<file>` | branch, tag, commit; folder |
| Gitea, Forgejo, Codeberg | `…/src/branch/<ref>/…`, `…/src/tag/<ref>/…`, `…/src/commit/<sha>/…` | branch, tag, commit; folder |
| Bitbucket Cloud | `…/src/<ref>/<folder>`, `…/branch/<ref>`, `…/commits/branch/<ref>`, `…/commits/tag/<ref>`, `…/commits/<sha>` | branch, tag, commit; folder |
| SourceHut | `…/tree/<ref>/item/<folder>`, `…/log/<ref>` | branch, tag; folder |
| Gitiles (Gerrit's code browser, `*.googlesource.com`) | `…/+/refs/heads/<ref>/<folder>`, `…/+/refs/tags/<ref>/<folder>`, `…/+/<ref>/<folder>` | branch, tag; folder |
| cgit (kernel.org, Launchpad) | `…/tree/<folder>?h=<ref>`, `…/log/?h=<ref>`, `…/commit/?id=<sha>` | branch, tag, commit; folder |
| Azure DevOps | `…/_git/<repo>?path=/<folder>&version=GB<branch>` (`GT` tag, `GC` commit) | branch, tag, commit; folder |
| Hugging Face Space or dataset | `huggingface.co/spaces/<org>/<name>`, `…/datasets/<org>/<name>`, with `…/tree/<ref>/<folder>` or `…/blob/<ref>/<file>` | branch, tag, commit; folder |

- A page URL naming a **file** reads the folder that holds it. A file page whose
  path is a folder reads that folder, and a folder page whose path is a file
  (Bitbucket, SourceHut, Forgejo and Gitiles write both alike) reads the folder
  holding the file.
- Where the ref is in the query (cgit, Azure DevOps) it is exact: it is not
  split from the folder, and a `?h=` or `?id=` after a cgit page name is the ref
  whatever the folder is called (`src`, `tree`), unless the path holds a GitLab
  (`-`) or Gitea (`src/commit|branch|tag`) marker, which makes the query stray. A query that names no ref
  (`?ref_type=heads`) is ignored, as before. An Azure DevOps `version` that does
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
  repository and is fetched like any other (Git LFS files stay pointers: Pitloom
  switches LFS off). A Space with no `pyproject.toml`, `setup.cfg` or `setup.py`
  has no Python project to read, and says so.
- Not read: hosts that need a login, `ssh://`, `git://`, `file://` and scp-style `user@host:path`
  addresses. These are refused with a message (see below).

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

## What it does and does not do

- **A downloaded repository is untrusted.** Its own `[tool.pitloom]` settings are
  ignored (an `INFO:` says so; `--config FILE` is yours and applies), and its
  build backend is never run: `--allow-build` is reported as having no effect.
- The clone is shallow, asks the server to leave out blobs over 10 MB (a server
  without partial clone sends them) and never follows a redirect on its own: Pitloom follows the Git server's redirect itself, one hop at a time
  (at most 5, 60 s for all probes), and a caller can check each hop first
  (`check_url=` in the Python API; Lumina uses it as its address guard).
- `git` has 10 minutes for all its calls together and 8 MiB of output (and of
  error text) per call. Ctrl-C stops `git` and what it started. `git` runs
  with only the http(s) transports, git-lfs off (a repository's LFS settings
  could name another host; LFS files are not downloaded) and without
  `GIT_DIR`-style variables of the calling environment.
- **Git LFS is a limitation, planned to be fixed in 0.22.0.** A file kept in LFS
  is a small pointer file in the checkout, because LFS is off. A pointer named
  like an AI model (`.onnx`, `.gguf`, ...) is recognised as a pointer and not
  read as a model, so the SBOM has no AI package for it. Any other file in LFS
  (a dataset, an image) is listed with the SHA-256 of the pointer text, not of
  the file, and no warning says so. Most model repositories on Hugging Face, and
  many on GitLab and Codeberg, keep their weights in LFS.
- **No size limit by default.** The command line sets none, so a very large
  repository is fetched in full (blobs over 10 MB excepted, on a server that
  supports partial clone). The library API can stop a fetch once the checkout
  takes more disk than a limit you give (`max_clone_bytes=`, error code
  `git.too-large`): [Python API](python-api.md).
- A symbolic link in the checkout that leads out of it is removed before the
  project is read (an `INFO:` counts them), so a host file is never read or
  hashed.
- A relative `--id-registry` is relative to where you run `loom`, not to the
  checkout.
- `--offline` forbids the fetch: it is an error, not a fallback.
- An empty repository is an error that says so.
- The output file is named from the project, as for a local one. `-o -` writes the
  SBOM to stdout.

## Messages

Every URL that is changed, refused or not followed is said, never silently:

| Level | Message | When |
| :---- | :------ | :--- |
| `INFO:` | `Git source: <url> redirected to <url>` | the server redirected: both URLs |
| `INFO:` | `Git source: <url> names repository <url>, branch <ref>, folder <path>` | the URL named more than a repository (or was cleaned) |
| `INFO:` | `Git source: <url> is not a repository; trying <url>` | a group called `src`/`tree`/`blob`: the whole URL is tried |
| `INFO:` | `Git source: <path> is a folder, not a file; reading it` | a file page whose path is a folder |
| `INFO:` | `Git source: <path> is a file, not a folder; reading the folder holding it` | a folder page whose path is a file |
| `INFO:` | `Git source: the server rejected the blob filter; fetching without it` | the server cannot leave out large blobs (Azure DevOps) |
| `INFO:` | `Git source: could not check <url> for a redirect (<reason>); asking git directly` | the redirect probe failed |
| `INFO:` | `Git source: $ git …` | each `git` call, credentials masked |
| `WARNING:` | `Git source: <url> redirected to <url>, which is not followed: <why>` | a redirect to another scheme, or to a page that is not a repository |
| `INFO:` | `Git source: <n> symbolic link(s) leading out of the repository were not followed` | links to host files were removed |
| `WARNING:` | `Git source: <reason>` | any refusal, as well as its `ERROR:`: an ssh, git, file or scp-style address, `--offline`, too many redirects, a redirect the caller's check refuses, an unknown ref or folder, a failed `git` call |
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
