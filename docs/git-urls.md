---
Created: 2026-10-21
Last-Modified: 2026-10-21
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
the SBOM. The directory is removed afterwards. It needs the `git` program.

```bash
loom project https://gitlab.com/group/project                  # the default branch
loom project https://github.com/owner/repo/tree/v1.2/src       # a tag and a folder
loom project https://codeberg.org/owner/repo/src/branch/main/svc/api
loom generate https://labs.etsi.org/rep/ocf/capif/-/tree/staging/services/register -o sbom.json
```

## Which URLs

Paste what you have: the clone URL, or the address of the page you were
looking at. The repository is the part of the path before the page marker, so a
URL prefix (`/rep` on ETSI's GitLab) and GitLab subgroups work. A branch name
may contain `/` (`feature/x`): the split between branch and folder is taken
from the server's own branches and tags, longest match first.

| Platform | Page URL read | Names |
| :------- | :------------ | :---- |
| GitLab | `…/-/tree/<ref>/<folder>`, `…/-/blob/<ref>/<file>` | branch, tag, commit; folder |
| GitHub | `…/tree/<ref>/<folder>`, `…/blob/<ref>/<file>` | branch, tag, commit; folder |
| Gitea, Forgejo, Codeberg | `…/src/branch/<ref>/…`, `…/src/tag/<ref>/…`, `…/src/commit/<sha>/…` | branch, tag, commit; folder |
| Bitbucket Cloud | `…/src/<ref>/<folder>` | branch, tag; folder |
| SourceHut | `…/tree/<ref>/item/<folder>` | branch, tag; folder |

- A page URL naming a **file** reads the folder that holds it. A file page whose
  path is a folder reads that folder.
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
- Hugging Face addresses (`huggingface.co`, `hf.co`, `www.` forms) are models,
  not Git repositories: `loom model` reads them.
- Not read: Azure DevOps page URLs (the folder is in a query string), hosts that
  need a login, `ssh://`, `git://`, `file://` and scp-style `user@host:path`
  addresses. These are refused with a message (see below).

## Verified platforms

Fetched with `loom` from a real server, on 2026-10-21 (the live tests in
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
| Forgejo | `codeberg.org` | bare URL, `/src/branch/` page |
| Forgejo | `code.overheid.nl` (Dutch government) | bare URL, `/src/branch/<branch>/<folder>` page |
| Gitea | `gitea.com` | `/src/branch/<branch>/<folder>`, `/src/tag/<tag>/<folder>` pages |
| GitHub | `github.com` | bare URL, `/tree/` page, `/blob/` page |

Also checked, with a narrower scope:

- **Bitbucket Cloud** (`bitbucket.org`): the repository is served as it is, and
  the `git ls-remote` that reads a page URL's branch works. A full fetch was not
  run: no small public Python repository was found, and the one tried is 148 MB.
- **SourceHut** (`git.sr.ht`): the page syntax is parsed (and tested); the server
  could not be reached from the test network, so no fetch was run.
- **cgit and GNU Savannah**: the redirect to another host is followed only
  when it leads to a repository; the one tried led to a host that does not
  resolve.

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
| `INFO:` | `Git source: could not check <url> for a redirect (<reason>); asking git directly` | the redirect probe failed |
| `INFO:` | `Git source: $ git …` | each `git` call, credentials masked |
| `WARNING:` | `Git source: <url> redirected to <url>, which is not followed: <why>` | a redirect to another scheme, or to a page that is not a repository |
| `INFO:` | `Git source: <n> symbolic link(s) leading out of the repository were not followed` | links to host files were removed |
| `WARNING:` | `Git source: <reason>` | any refusal, as well as its `ERROR:`: an ssh, git, file or scp-style address, `--offline`, too many redirects, a redirect the caller's check refuses, an unknown ref or folder, a failed `git` call |
| `WARNING:` | `Build: <url>: --allow-build has no effect for a remote repository …` | a build flag |
| `ERROR:` | `SBOM generation failed: …` | the run could not finish |

A URL or ref in a message is shown without credentials (`https://***:***@host`)
and with control characters escaped. What a server or `git` says is reduced to
one line (its `fatal:`, `error:` and `remote:` lines), so it cannot add a
tagged line of its own.

If the repository has no Python project at its root but has some in folders,
the error names them (up to five) and asks for the URL of one of them.
