---
Created: 2026-10-21
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: an SBOM from a Git URL on any forge

See also: [README.md](README.md) (index of these notes),
[../remote-git-ingestion.md](../remote-git-ingestion.md) (what was built, PR
#317), [messages-and-surfaces.md](messages-and-surfaces.md) (one message per
event, surfaces that drift apart),
[../ai-model-scan-security-lessons.md](../ai-model-scan-security-lessons.md)
(hostile input), [process-lessons.md](process-lessons.md).

The trigger was a demo on 2026-10-20: `https://labs.etsi.org/rep/ocf/capif`
(a GitLab project with a URL prefix) failed in Lumina with `error: 301`. All
facts below were measured on 2026-10-21 with git 2.43 to 2.55, against real
servers or a local server that answers like GitLab. Each item has a "Do:" rule.

## 1. What a pasted URL is

- **GitLab answers a bare project URL with a 301 that git will not follow.**
  `GET <project>/info/refs?service=git-upload-pack` is redirected to
  `<project>.git/info/refs` (`gitlab.com`, `labs.etsi.org/rep`, `code.europa.eu`,
  `gitlab.opencode.de`, `forge.apps.education.fr`, `framagit.org`,
  `gitlab.cern.ch`). GitHub, Forgejo (`codeberg.org`, `code.overheid.nl`),
  Gitea (`gitea.com`) and Bitbucket serve the bare URL as it is. A tool that
  tested only GitHub never sees it, and one that disables redirects for safety
  (`http.followRedirects=false`, the right default) turns every GitLab link
  into `error: 301`.
  Do: probe `/info/refs` yourself, follow the redirect by hand, hop by hop,
  and clone the final URL with redirects still off.
- **People paste the page they were looking at, not a clone URL.** The syntax
  belongs to the software, not the host, so no host list is needed:
  GitLab `/-/tree/<ref>/<dir>` and `/-/blob/<ref>/<file>`; GitHub `/tree/`,
  `/blob/`; Gitea, Forgejo, Codeberg `/src/branch/<ref>/`, `/src/tag/<ref>/`,
  `/src/commit/<sha>/`; Bitbucket Cloud `/src/<ref>/<dir>`; SourceHut
  `/tree/<ref>/item/<dir>`. A GitLab instance under a prefix (`/rep`) and
  nested subgroups work because the repository is "the path before the marker".
  Do: read the URL by its path; keep the marker table in one place.
- **A branch name may contain `/`, so the split between ref and folder cannot
  be read from the URL.** `.../-/tree/feature/x/pkg` is branch `feature/x` and
  folder `pkg`, or branch `feature` and folder `x/pkg`. Ask the server:
  `git ls-remote --heads --tags --refs` and take the longest leading run of
  segments that is a ref. A name that is both a branch and a tag follows the
  page kind (`src/tag/` means the tag).
  Do: resolve ambiguity against the server's own refs, never guess.
- **A group called `src`, `tree` or `blob` breaks marker search.** For
  `.../g/sub/src/proj/-/tree/main/x` the first marker by position is `src`.
  Found by the second review round, not by a test; fixed by reading GitLab's
  unambiguous `/-/` marker first. A URL ending `.git` is always a repository.
  Do: look for the unambiguous marker before the positional ones.
- **A fallback must not hide the real failure.** Retrying the whole URL as a
  repository when `ls-remote` failed also swallowed TLS, DNS and sign-in
  errors, and the final message named a URL the user never meant. Retry only on
  "not found".
  Do: say which condition a fallback is for, and test the other conditions.
- **A full commit id is needed.** A server cannot be asked for an abbreviated
  id; a tag is fetched by `refs/tags/<ref>`; a 40 or 64 hex digit id by
  `init` + `fetch --depth 1` + `checkout FETCH_HEAD`.

## 2. Measured platform notes (2026-10-21)

| Platform | Result |
| :-- | :-- |
| GitLab (7 instances, two of them public bodies) | bare URL 301 followed; page URLs work |
| Forgejo (`codeberg.org`, `code.overheid.nl`), Gitea (`gitea.com`), GitHub | work, page URLs included |
| Bitbucket Cloud | `ls-remote` level only: no small Python repository found to clone (the one tried was 148 MB) |
| SourceHut | unreachable from the test host (HTTP 502); parsing is unit-tested only |
| GNU Savannah | the redirect leads to a host that does not resolve; reported, not followed |

A failure that is the tool's honest limit is a result: `labs.etsi.org/rep/ocf/capif`
now fails with a message that names its sub-projects, because the repository root
has no project and Pitloom does not read an imperative `setup.py`.
Do: list a host as "works" only after cloning a real repository from it, with
the date.

## 3. An untrusted repository and an untrusted server

The review found three high-severity holes after two earlier rounds had passed.
Each was reproduced first; each has a test that fails on the earlier tree.

- **git-lfs bypasses the address check.** With `git lfs install` in the user's
  config (the default on many machines and images) a checkout runs the smudge
  filter, and git-lfs sends `POST <url>/objects/batch` to the address in the
  repository's own `.lfsconfig`: a second network client, past `check_url` and
  past `http.followRedirects=false`. A legitimate LFS repository would download
  its objects without bound.
  Do: `-c filter.lfs.smudge= -c filter.lfs.process= -c filter.lfs.required=false`,
  `GIT_LFS_SKIP_SMUDGE=1`, and `GIT_ALLOW_PROTOCOL` set from the same constant
  as the scheme check. A check on the URL does not cover every client that
  the tool starts.
- **With LFS off, the pointer is the identity.** A pointer states the content's
  SHA-256 (`oid`), so a tool that never fetches can still name the file and
  keep the name across `git lfs pull`; an archive that ships the pointer text
  must keep the hash of those bytes, to match its `RECORD`. Parse the pointer
  strictly and probe the real `git lfs pointer --check` on a matrix of
  variants: git-lfs's decoder accepts forms it never writes (blank lines,
  `size +5`, upper-case hex). Pitloom is stricter and accepts nothing git-lfs
  refuses. See [git-lfs-pointers.md](../git-lfs-pointers.md).
- **Server text is attacker text.** A smart-HTTP server answered with the
  pkt-line `ERR boom\nERROR: forged line\n::error::x \x1b[31m`: the CLI printed
  a forged `ERROR:` line, a GitHub Actions workflow command and a terminal
  escape. Git's stderr is now reduced to its own `fatal:`, `error:` and
  `remote:` lines, one line, escaped, without credentials or the temporary path.
  Do: treat what a subprocess prints as data from the network.
- **A credential in a URL leaks through the error path, not the happy path.** The
  masking helper was applied to the echoed command but not to the "invalid
  path" and "no such ref" messages built from the raw URL.
  Do: mask where the message is built, and test every message with a URL
  that holds `user:SECRET@`.
- **A symlink in the repository is a read primitive.** A tracked `extra.py ->
  /etc/passwd` was hashed into a `software_File`. Links leading out of the
  checkout are removed, with one `INFO:` that counts them.
- **The caller's `GIT_DIR` reaches git.** From a git hook, `rev-parse HEAD`
  returned another repository's commit. Remove the variables that repoint git.
- **Killing git means killing its group.** `git` starts `git-remote-https`,
  which holds the pipe open: killing only the process left a 30-second hang
  (found by a stand-in `git` test) and Ctrl-C left it running (found by
  the review). `start_new_session` plus `os.killpg`, on timeout, output flood
  and `BaseException` alike. Cap stderr as well as stdout: a hostile server
  can fill the disk with `remote:` lines.
- **Redirects are a policy question.** The caller's address check (Lumina's SSRF
  guard) runs on every hop before the request; a redirect to a non-http scheme
  or to a page that is not `/info/refs` (a sign-in page) is not followed and
  says so in a `WARNING:`. The probe sends no credentials. Left open and written
  down: DNS rebinding between the check and git's own lookup, and no cap on
  clone size (a blob filter is a request to the server; a 20 MB blob was still
  fetched over HTTP).

## 4. Where the logic lives

The first fix was in Lumina (a redirect follower plus a page-URL parser, on two
Lumina branches, with review rounds). The user's question "the URL resolution should be at
the Pitloom level; Lumina gets the support naturally?" was right: the CLI, the
library and the next consumer would each have needed their own copy. Moved to
Pitloom in one PR, with Lumina reduced to policy (its address check, its error
codes). Parity across surfaces became a test (library, `generate()`, CLI
`project`, CLI `generate` write the same SBOM from one local server), and the
CLI first named the random checkout path in a warning the library worded
differently. Lumina's own end-to-end tests run against the same server and check its log
and notification path.
Do: put the resolution where every surface shares it; keep the consumer's
policy a callback.

## 5. Rejections must be said, and said once

"When a URL is rejected, log it and tell the user, don't be silent." Seven
refusals raised an error and logged nothing (offline, too many redirects, the
caller's check, an unknown ref, a bad port, a missing folder, a redirect with
no `Location`). One wrapper now logs every refusal before the checkout is
handed over; an error in the consumer's own `with` block is deliberately not
logged as a fetch problem. The same refusal is a `WARNING:` and the CLI's
`ERROR:`: deliberate, so a caller that only logs still shows it.

## 6. Test traps this feature found

- **A local server that answers like the real one beats a mock.** `git
  http-backend` behind a short handler gave GitLab's 301, smart HTTP, and a
  repository with branches containing `/`. All tests of redirect handling,
  ref splitting and the CLI ran against it, offline.
- **Python 3.14 reports a closed-late temporary file as an unraisable error.**
  `urllib.error.HTTPError` holds its response body in a temporary file; the
  probe read the status and dropped the error. With `filterwarnings = error`
  that failed 47 tests on 3.14 only (the rest of the matrix was green).
  `with exc:` closes it. The regression test calls `gc.collect()` inside the test
  so the finaliser runs there, not in some later test.
- **macOS answers `EPERM` where Linux answers `ESRCH`** when `os.killpg` targets
  the group of a process that exited and is not yet reaped. One test on one leg.
- **Windows:** a directory named `a@b:c` is invalid (the test of "an existing
  path is never an address" is POSIX-only); `file://D:\x` is not a URL; a
  `file://` clone test skips there.
- **Time:** a fixed `sleep` followed by an interrupt, a wall-clock bound on a
  slow server and a port that "nothing listens on" are three flakes waiting.
  Wait for the condition (a pid file, an event), assert the message not the
  duration, and take a free port by binding and closing.
- **A guard test is a free reviewer.** Adding a kind and a parameter surfaced
  three registries the compiler cannot see: the inert-options table (and its
  docs row), the cap-warning list, and the skill's description (1,024 characters)
  and body (24 KB) limits.
- **Lint that passes locally can fail in CI** if it runs from another directory:
  a docstring line of 114 characters, against a 100-character limit in Lumina's
  `pylintrc`, scored 10/10 locally.
