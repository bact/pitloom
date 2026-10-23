---
Created: 2026-10-21
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Remote Git ingestion: `loom project <url>`

See also: [remote-source-ingestion.md](../design/remote-source-ingestion.md)
(the design this builds part of), the user page `docs/git-urls.md`,
[roadmap.md](../design/roadmap.md), and the Lumina notes that led here
(`working-docs/design.md` in `bact/lumina`).

What was built (2026-10-21), why, and what was left out.

## Why it moved here

Lumina (the web checker) cloned Git URLs itself. A GitLab URL without `.git`
failed there (error 301), and page URLs (`.../-/tree/main/svc`) never worked.
A fix inside Lumina would have left the CLI, the library, the GitHub Action and
the agent skills each to fail the same way, so the URL logic is in Pitloom and
Lumina passes the URL (surface parity). Lumina keeps its policy only: an
address guard, the SBOM's author, the job and the log.

## What exists

| Module | Role |
| :----- | :--- |
| `extract/remote/git_url.py` | read a pasted URL: repository, page marker, branch/tag/commit and folder; pure |
| `extract/remote/_git_redirect.py` | follow the server's redirect hop by hop; each hop to the caller's `check_url` |
| `extract/remote/_git_run.py` | run `git` (no redirect, no prompt, shared deadline, output cap, process-group kill) |
| `extract/remote/_git_folder.py` | the folder to read (realpath containment), the monorepo hint |
| `extract/remote/git.py` | `fetch_git_project(url)`: a temporary checkout, `GitCheckout` |
| `assemble/_generators_git.py` | `generate_git_project_sbom(url, check_url=...)` |
| `cli/commands/project.py` | `loom project <url>` (shared with `loom generate <url>`) |

`generate()` classifies a URL as a Git target (`target_is_git_url`); a remote
address Pitloom does not fetch (`ssh://`, `git@host:path`, `file://`) is
classified the same way so it is refused with a message, not mistaken for a
missing directory.

## Decisions

- **Shallow `git` over smart HTTP, on every host.** The design doc planned a
  forge API tarball as the primary path (GitHub, GitLab) with git as the
  fallback. Checked on 2026-10-21 against GitLab (gitlab.com, ETSI, European
  Commission, German public sector, French education, Framagit, CERN), Forgejo
  (Codeberg, code.overheid.nl), Gitea, GitHub and Bitbucket: plain smart HTTP
  works the same everywhere, with no per-forge adapter. A tarball path stays an
  optimisation for later; it would need one adapter per forge and a token story.
- **The page syntax is read by path, not by host.** The same software has the
  same URLs on every instance, including the ones public bodies run, so no host
  list is kept. The branch/folder split comes from the server's refs
  (`ls-remote`, longest match), since a branch name may contain `/`.
- **Redirects are followed by Pitloom, not by `git`.** `git` runs with
  `http.followRedirects=false` so a redirect to an internal host cannot skip an
  address check; Pitloom follows each hop itself and calls the caller's
  `check_url` before asking it. A redirect to a scheme other than http(s), or to
  a page that is not a repository, is not followed and is a `WARNING:`.
- **The repository is untrusted.** Its `[tool.pitloom]` is ignored unless the
  caller supplies a config (a repository must not name host paths such as an
  ID registry or fragments); its build backend never runs (`--allow-build` is a
  `WARNING:` and has no effect).
- **Nothing is dropped silently.** A URL that is cleaned, redirected, retried
  as a whole repository, refused or not followed is an `INFO:` or `WARNING:`
  naming both URLs; a refused URL is also an error. See the table in
  `docs/git-urls.md`.
- **`RemoteSourceError` carries a code** (`git.clone-failed`, `git.timeout`,
  `git.ref-not-found`, `git.path-not-found`, `git.no-project`, ...), so a caller
  (Lumina) maps it to its own vocabulary without parsing text.
- **A size cap is the caller's.** `fetch_git_project(max_bytes=)` polls the
  checkout's size while `git` runs (every 0.25 s) and kills it past the cap
  (`git.too-large`), and checks once more when the call ends; bandwidth is
  spent before it stops, but disk and memory are not. The CLI sets none, as
  it sets no `check_url`.

## Problems the tests found

- A deadline killed only `git`, not `git-remote-https`, which held the output
  pipe open: the call hung until the child ended. `git` now runs in its own
  process group and the group is killed (`tests/extract/remote/test_git_edges.py`).
- A bare `.../src/...` or `.../tree/...` group before a `.git` repository was
  read as a page; a URL ending `.git` is now always a repository, and a page
  whose repository part is not a repository falls back to the whole URL.
- A redirect chain of exactly the limit was refused (off by one).
- A tag and a branch of one name: the branch was always taken; a `src/tag`
  page now takes the tag.

## Review round 2 (security)

Found by a fresh read-only review, reproduced, fixed, each with a test that fails
on the earlier tree (`tests/extract/remote/test_git_hardening.py`):

- git-lfs, if installed with its global filter, fetched from the address of the
  repository's own `.lfsconfig`, past the caller's URL check: LFS is now off
  (`filter.lfs.*`, `GIT_LFS_SKIP_SMUDGE`), and `GIT_ALLOW_PROTOCOL` is the
  allowed schemes.
- Server text in a failed `git` call reached stderr unescaped (a forged
  `ERROR:` line, a `::error::` workflow command, an escape sequence): reduced to
  one escaped line of `fatal:`/`error:`/`remote:` text, without the temporary
  path.
- A URL's credentials were echoed by the path and ref messages.
- Ctrl-C left `git` running (it has its own process group): the group is killed.
- stderr was uncapped on disk: drained with a cap.
- The retry with the whole URL hid TLS, DNS and sign-in failures: only a "not
  found" answer retries.
- A GitLab group called `src`/`tree` broke `/-/tree/` pages: the `/-/` marker is
  read first.
- A symlink in the repository to a host file was hashed into the SBOM: links
  leading out are removed (with an `INFO:`).
- `GIT_DIR` and friends of a calling git hook are removed from `git`'s
  environment.
- Several refusals were raised without a `WARNING:` (offline, too many
  redirects, the caller's check, an unknown ref): all are logged once, centrally,
  before the checkout is handed over (an error in the caller's own block is not).
- `hf.co` and `www.huggingface.co` were treated as Git repositories.
- The CLI named the random checkout path in the "option has no effect" warning
  and worded it differently from the library: it settles against the URL.

Left as they are: DNS rebinding between the caller's address check and git's own
lookup (as with the earlier Lumina code); no cap on the size of a clone beyond
the 10-minute deadline (the 10 MB blob filter is only a request to the server).

## Not built

- Tokens and private repositories (`GITHUB_TOKEN`, `--token`): `git`'s own
  credential helpers apply; nothing is prompted.
- `ssh://` and scp-style addresses.
- Provenance in the SBOM (`downloadLocation` with the commit, a `vcs`
  external reference, forge licence): the commit is logged, not recorded.
- Forge API tarballs; a persistent cache of fetches.
- A size cap for a CLI clone: only a library caller sets `max_bytes=` (#339);
  on the CLI the blob filter is a request, so only the 10-minute deadline
  bounds it.
- A reader for a project that declares its metadata only in an imperative
  `setup.py`; the error names the sub-projects it can read.
- DNS-rebinding protection between the caller's address check and git's own
  lookup.
- The GitHub Action takes a checkout in the workflow, not a URL.

## Bitbucket and SourceHut pages (2026-10-23)

Run against real servers (`zzzeek/sqlalchemy`, `~sircmpwn/scm.sr.ht`). Both
write a file page like a folder page (`src/<ref>/<file>`, `tree/<ref>/item/<file>`),
so a folder page whose path is a file reads the folder holding it, with an
`INFO:`. Bitbucket answers any path below a repository with the default branch,
so `/branch/<ref>`, `/commits/<sha>`, `/commits/branch/<ref>` and
`/commits/tag/<ref>` were cloned as the plain URL: the ref asked for was
dropped without a message. They are page markers now, as is SourceHut's
`/log/<ref>`. A short commit id in a Bitbucket URL is still refused (a server
cannot be asked for it).

## Other hosts (2026-10-23)

Run against real servers (see `docs/git-urls.md`). Findings:

- Azure DevOps answers a clone with `--filter=blob:limit=10m` with HTTP 400 but
  serves a plain shallow clone (and `blob:none`). `_checkout` retries once
  without the filter when the first attempt fails with `HTTP 400`; one `INFO:`
  says so. The retry is for that answer only, any other failure stands.
  `init` and `remote add` run once, before the first attempt (a second run
  fails with "remote origin already exists" and hid the server's answer). A
  failed filtered `fetch` still saves `remote.origin.partialclonefilter` in the
  repository config, which a plain `fetch` would send again, so the tag and
  commit route retries with `--no-filter`; the clone route has no such config.
  A fake runner that only looks at argv passed both mistakes: the test runner
  keeps the saved filter and refuses a second `init`/`remote add`, as git does.
- Azure DevOps and cgit carry the ref in the query (`GitPage.query_style`):
  `version=GB|GT|GC<ref>` and `path=` for Azure, `h=` or `id=` for cgit, with
  the folder in the path after the page name. The ref is exact, not split from
  the folder. Gitiles uses `/+/` with `refs/heads/` or `refs/tags/` in front of
  the ref; both are read like a path marker.
- A Hugging Face Space or dataset (`/spaces/...`, `/datasets/...`) is a Git
  repository, not a model: `is_git_url` accepts it, `parse_hf_model_id` refuses
  it, so `_classify_target` says `git` (before, `spaces/<org>` was read as a
  model id and `loom model` warned of 401s for a repository that does not
  exist). `loom project <model url>` and `loom model <git url>` each say to use
  the other command, in one `ERROR:` line, instead of a missing path.
- A folder page whose path is a file (Forgejo, Bitbucket, SourceHut, Gitiles
  write both alike) reads the folder holding the file.
- Not read, by choice: a cgit page with no `h=` or `id=` (it names the default
  branch, and its path cannot be told from a GitHub path).
- Tried, reverted: reading `?h=` as cgit's only when the path holds no GitHub
  style marker. A cgit folder called `src` or `tree` (`mesa/tree/src/gallium`)
  holds one, so it lost its ref. The query wins now; no forge puts `?h=` on its
  own page URLs.
- Path segments of query-style and Gitiles pages go through the same
  `..`/`.`/`\`/NUL check as every other page form, at parse time, before a clone
  (a NUL byte reached `os.path.realpath` after the clone and raised
  `ValueError`).
- Credentials: `sanitize_url_credentials` (free text, stops at whitespace) also
  masks, inside a URL only, a query or fragment parameter whose whole name (or
  ending: `_token`, `_key`, `_secret`, `_password`) says it is a secret, by name
  list and not by substring (`author`, `design`, `monkey` are kept); the name is
  capped at 64 characters, as a substring pattern was quadratic on a server's
  8 MiB stderr. `sanitize_url` is for a text that is one URL and masks a
  userinfo holding a newline or a space, also in the collapsed `https:/` form of
  a path. Every URL echoed by the Git source (the `$ git` line per argument,
  the build warnings) and by `loom model` and `loom project` goes through it. A
  secret in a parameter with another name is not recognised.
- A Hugging Face model id ends at `?` and `#`: a query token was part of the id
  and reached messages.
- A `?h=`/`?id=` after a GitLab `-` or Gitea `src/commit` marker is a stray
  query, not cgit's.

## Verification

- Unit and edge tests (`tests/extract/remote/test_git_*.py`), with a stand-in
  `git` for a hung, flooding or failing process.
- A local GitLab-style server over smart HTTP (`git http-backend`,
  `tests/_git_http_server.py`): the library, `generate()`, `loom project` and
  `loom generate` run against it, with surface parity (the same SBOM from each).
- Live tests of real platforms (`tests/extract/remote/test_git_platforms_live.py`,
  marked `network`), and the same server in Lumina's own end-to-end tests
  (the chain URL, Pitloom, checker, job API).
