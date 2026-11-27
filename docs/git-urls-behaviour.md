---
Created: 2026-11-26
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM from a Git URL, behaviour and messages

See also: [SBOM from a Git URL](git-urls.md) for the URL forms, the
verified platforms and model files, and [Credentials in
URLs](url-credentials.md).

What Pitloom does, and refuses to do, with a downloaded repository, and
every message the Git route prints.

## What it does and does not do

- **A downloaded repository is untrusted.** Its own `[tool.pitloom]` settings are
  ignored (`INFO: Git source: the repository's own [tool.pitloom] settings are
  ignored (untrusted) ... [config-unsafe]`; `--config FILE` is yours and
  applies), and `--allow-build` is reported as having no effect. A discovery
  failure shows only the exception type
  ("text not shown for a downloaded repository"), and a line of the
  repository's requirements file is replaced by `<a line of the downloaded
  repository, not shown>`.
- **The repository's own build-time code is not run** while its files are
  listed. In a clone, these settings are ignored, with one `WARNING:` naming
  the file and the settings ([`config-unsafe/build-code`](message-codes-targets.md#config-unsafebuild-code)):
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
- **Credentials in the URL** (`https://user:token@host/...`) never reach
  `git`'s command line, which any user of the machine can read, nor the
  clone's `.git/config`: Pitloom takes them out of the URL and hands them to
  `git` through a credential helper of its own, for that host alone, in the
  environment of the calls that contact the server. For such a URL every
  credential helper and ask-pass program of yours (a keychain, Git Credential
  Manager, `gh`, `~/.git-credentials`) is switched off: none is asked, and
  nothing is stored in one. A URL without credentials is fetched as `git
  clone` fetches it, with your own helpers or `.netrc`, the better place for a
  credential. `git` never prompts on the terminal (a private repository it
  cannot sign in to fails at once), and the `GIT_TRACE*` and
  `GIT_CURL_VERBOSE` variables of the calling environment, which can write
  what `git` sends, are not passed on. A secret in the URL's query or
  fragment (`?token=`, `?access_token=`, `#token=`) is never given to `git`:
  the query and fragment are dropped before the clone URL is built (`INFO: Git
  source: URL=<url>: the query and fragment have no effect; cut
  [query-no-effect]`), so `git` cannot sign in with one either.
  This is how the URL you give is
  fetched and shown (masked) in messages; it is not a rewrite of the SBOM: a
  URL field of the SBOM that holds a credential is warned of, or refused in
  the `refuse` mode, as on every target ([Credentials in URLs](url-credentials.md)).
  - A plain `http://` URL with credentials is fetched with them, and
    `WARNING: URL=<url>: credentials are sent in clear over http; use https
    [credentials-unsafe/http-clear]` says so once.
  - Credentials holding a line break (`%0A`, `%0D`) are not sent: the URL is
    fetched without them, with `WARNING: URL=<url>: credentials holding a line
    break are not sent to git [credentials-unsafe/git-line-break]`.
  - A URL whose user information `git` would read differently from Pitloom
    (an empty host after the `@`, for one) is refused before `git` runs:
    `ERROR: loom project: URL=https://***:***@/o/r: user information
    cannot be taken out of the git command line; not fetched
    [credentials-unsafe/git-userinfo]`. So is a user name or password
    holding a NUL (`%00`), which cannot be handed to `git`. A malformed host
    or port is refused as an invalid URL (`git.url-invalid`; for the port,
    `URL=<url>: the port is not a number; nothing fetched [git-url-invalid]`). Other control
    characters (a tab, an escape) are sent as typed.
  - A URL with a host and no path (`https://github.com/`, or a path such
    as `/./` or `/..` that collapses to the root) names no repository and
    is refused before any request:
    `URL=<url>: the URL names a host but no repository; nothing fetched
    [git-url-invalid]`. One path segment (`https://git.example.org/repo`)
    is handed to the server, which says whether it is a repository.
- The clone is shallow, asks the server to leave out blobs over 10 MiB that the
  checkout does not need (a server without partial clone sends them) and never
  follows a redirect on its own: Pitloom follows the Git server's redirect itself, one hop at a time
  (at most 5, 60 s for all probes), and a caller can check each hop first
  (`check_url=` in the Python API; Lumina uses it as its address guard).
- `git` has 10 minutes for all its calls together and 8 MiB of output (and of
  error text) per call. Ctrl-C stops `git` and what it started. `git` runs
  with only the http(s) transports, git-lfs off (a repository's LFS settings
  could name another host; LFS files are not downloaded) and without
  `GIT_DIR`-style variables of the calling environment, nor those that run
  another program or turn a check off (`GIT_EXEC_PATH`, `GIT_SSH`,
  `GIT_SSH_COMMAND`, `GIT_SSH_VARIANT`, `GIT_PROXY_COMMAND`,
  `GIT_TEMPLATE_DIR`, `GIT_SSL_NO_VERIFY`, `GIT_CONFIG`,
  `GIT_REDIRECT_STDIN`/`STDOUT`/`STDERR`). Your own configuration is read
  as `git clone` reads it (`HOME`, `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`,
  `GIT_CONFIG_NOSYSTEM` are kept), and so are your ask-pass programs
  (`GIT_ASKPASS`, `SSH_ASKPASS`, `core.askPass`) unless the URL carries
  credentials.
- **Git LFS files are pointers.** LFS is off, so a file kept in LFS is a small
  pointer file in the checkout, and Pitloom never fetches its content. The SBOM
  lists it with the pointer's `oid` as its SHA-256 (no SHA-512; the hash
  comment says the content was not read, and the file's provenance is `Method:
  lfs_pointer`), so the hash is the same after `git lfs pull`. The stated size
  is only recorded in that comment. A pointer named like an AI model (`.onnx`,
  `.gguf`, ...) is listed as a file only, with no AI package; a pointer named
  by its own URL is an error (see [Model files](git-urls.md#model-files)). No content type,
  licence or copyright comes from the pointer text. One `WARNING:` per SBOM
  names the first pointer (and, for more than one, the count): `clone with git
  lfs, then run on the directory`. Run `loom project` on that directory for
  the content. Most model repositories on Hugging Face, and many on GitLab
  and Codeberg, keep their weights in LFS.
- **512 MiB of disk by default.** The fetch is stopped once the checkout
  takes more disk than `--max-download-bytes BYTES` (`[tool.pitloom]
  max-download-bytes` from `--config`, library `max_download_bytes=`; the
  setting that caps a [PyPI download](pypi-urls.md#size-limit)): `ERROR: loom <command>: the
  repository is larger than the <limit>-byte max-download-bytes cap; git clone
  was stopped`, error code `git.too-large`, message code
  [`over-cap`](message-codes-files.md#over-cap), and no SBOM. The 10 MiB filter
  leaves out only large blobs the checkout does not need; a large file in the
  checked-out tree (a model of 12 MiB, say) is fetched and counts. Raise the
  cap for one run when you trust the repository.
- A cloned project's build file list (Hatchling `force-include`, setuptools
  `package-dir`, `packages.find.where` or `package-data` with an absolute or
  `..` path, say) keeps only files inside the repository. Such an entry is
  dropped before the files are discovered, one `WARNING:` per entry as written
  ([`file-unreadable/outside-repository`](message-codes-files.md#file-unreadableoutside-repository)),
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
  project`, `loom model` and `loom generate` alike (`URL=<url>: network
  access is forbidden (offline mode); nothing fetched`,
  [`offline-unusable`](message-codes-network.md#offline-unusable), the code a PyPI
  URL or a Hugging Face model refuses with too).
- A clone that cannot reach the server (a name that does not resolve, a
  refused, reset or timed-out connection, a TLS failure, an HTTP 5xx answer)
  ends `git <command> failed: <git's reason>; nothing fetched`
  ([`download-network-failed`](message-codes-network.md#download-network-failed));
  one that runs out of time, `git <command> did not finish within
  <duration>; stopped`
  ([`download-timeout`](message-codes-network.md#download-timeout)): the codes a
  PyPI or Hugging Face request that fails the same way carries. Any other
  git failure (a repository, branch or sign-in the server refused) is
  [`git-repository-unusable`](message-codes-git.md#git-repository-unusable):
  `git <command>: <git's reason>; nothing fetched`, with git's own `fatal:`,
  `error:` and `remote:` lines as the reason. Network failures are told from other git
  failures by git's own `fatal:` and `error:` lines (git runs with
  `LC_ALL=C`), never by a name, URL or server text inside them.
- An empty repository is an error that says so (`URL=<url>: an empty
  repository (no commits); nothing read [git-repository-unusable/empty]`).
- The output file is named from the project (or the model file), as for a
  local one, and written to the current directory. `-o -` writes the SBOM to
  stdout.

## Messages

Every URL that is changed, refused or not followed is said, never silently:

| Level | Message | When |
| :---- | :------ | :--- |
| `INFO:` | `Git source: URL=<url>: redirects to <target>; followed [url-moved]` | the server redirected: both URLs |
| `INFO:` | `Git source: URL=<url>: read as repository <target>, <ref-kind> <ref>, directory '<path>' [target-ambiguous/git-page]` | the URL named more than a repository (or was cleaned); the ref and the folder are left out of the line when the URL names none |
| `INFO:` | `Git source: URL=<url>: not a repository; read as repository <target> [target-ambiguous/git-page]` | a group called `src`/`tree`/`blob`: the whole URL is tried |
| `INFO:` | `Git source: URL=<url>: '<path>' is a directory, not a file; reading it [target-ambiguous/git-page]` | a file page whose path is a folder |
| `INFO:` | `Git source: URL=<url>: '<path>' is a file, not a directory; read as the file named [target-ambiguous/git-page]` | a folder page whose path is a file: the file is read as the one the URL named (a model file, or else its folder) |
| `INFO:` | `Git source: URL=<url>: the query and fragment have no effect; cut [query-no-effect]` | the URL held a query or fragment that names no ref |
| `INFO:` | `Git source: URL=<url>: the version names no branch, tag or commit; the default branch is read [query-no-effect]` | a page URL's version query (Azure DevOps) names none |
| `INFO:` | `FILE=<file>: not an AI model file; reading its directory` | the file URL named a file whose name no model has, and that is not a model or is missing (`loom generate`) |
| `INFO:` | `FILE=<file>: no Python project; reading this AI model file` | `loom generate` on a folder with no project and one model |
| `INFO:` | `FILE=<file>: the one AI model file; reading it` | `loom model` on a folder with one model |
| `INFO:` | `FILE=<file>: one of several AI model files`, then `ERROR:` `<url>: several AI model files (N files); name one file` | a folder holds several models (one line per file; `model-ambiguous`) |
| `INFO:` | `AI models from a Git URL in these formats are listed without metadata, their reader not being run on a downloaded file: <formats>; pass --trust-model-files for a repository you trust` | a model in a format whose reader is not run on a download |
| `ERROR:` | `'<path>': no Python project (pyproject.toml, setup.cfg or setup.py); Python projects are in subdirectories (<directories>); give the URL of one of them [project-not-found]` | the folder holds no project but folders below it do (`loom project`); a folder's line ends `Pitloom reads the directory in the URL only` instead |
| `ERROR:` | `<url>: no Python project (pyproject.toml, setup.cfg or setup.py) and no AI model file of a supported format; name a project directory or a model file` | neither a project nor a model (`project-or-model-not-found`; with subfolders that hold projects, the same hint as above) |
| `ERROR:` | `<file>: header is a Git LFS pointer, content not fetched (oid sha256:<oid>, size <size>); clone with git lfs, then run on the file` | the named model file is an LFS pointer |
| `INFO:` | `Git source: URL=<url>: the server rejected the blob filter; fetching without it [git-filter-unusable]` | the server cannot leave out large blobs (Azure DevOps) |
| `INFO:` | `Git source: URL=<url>: could not be checked for a redirect (<why>); git asked directly [git-redirect-unusable]` | the redirect probe failed |
| `INFO:` | `Git source: $ git ...` | each `git` call (a summary: no code); a URL's credentials are not among its arguments |
| `WARNING:` | `Git source: URL=<url>: redirects to <target>; not followed (<why>); the URL itself asked of git [url-unsafe]` | a redirect to another scheme, or to a page that is not a repository: git is run on the URL as given and follows no redirect |
| `INFO:` | `Git source: URL=<url>: <n> symbolic link(s) leading out of the repository, into its .git directory or to a directory; removed, not followed [git-link-unsafe]` | such links were removed |
| `ERROR:` | `URL=<url>: only http and https URLs are fetched (not ssh, git, file or scp-style addresses); nothing fetched [git-url-invalid]` | an ssh, git, file or scp-style address |
| `ERROR:` | `URL=<url>: the port is not a number; nothing fetched [git-url-invalid]` | a malformed port |
| `ERROR:` | `URL=<url>: a path part decodes to ., .., an empty part, a backslash, a NUL or .git; nothing fetched [git-url-invalid]` | a branch or path part that would leave the checkout or reach git's own files |
| `ERROR:` | `URL=<url>: network access is forbidden (offline mode); nothing fetched [offline-unusable]` | `--offline` |
| `ERROR:` | `URL=<url>: more than 5 redirects; not followed [url-unsafe]` | too many redirects (`git.too-many-redirects`) |
| `ERROR:` | `URL=<url>: no branch or tag <ref>; a commit needs its full 40 or 64 hex digits [git-ref-not-found]` | an unknown branch, tag or commit (`git.ref-not-found`) |
| `ERROR:` | `git is not installed or not on PATH; nothing fetched [git-missing]` | no `git` program (`git.not-found`) |
| `ERROR:` | `git <command>: <error>; nothing fetched [git-repository-unusable]` | a failed `git` call that was no network failure: the repository, branch or sign-in the server refused (`git.clone-failed`) |
| `ERROR:` | `URL=<url>: an empty repository (no commits); nothing read [git-repository-unusable/empty]` | a repository with no commits |
| `ERROR:` | `git <command> failed: <error>; nothing fetched [download-network-failed]` | the server could not be reached |
| `ERROR:` | `git <command> did not finish within <duration>; stopped [download-timeout]` | the 10-minute limit passed |
| `WARNING:` | `FILE=<file>: build-time code of the downloaded repository is not run; <settings> ignored [config-unsafe/build-code]` | a cloned project's build settings would run the repository's own code (once per SBOM) |
| `WARNING:` | `FILE=<entry>: outside the downloaded repository; not read [file-unreadable/outside-repository]` | a build file list entry, as written, names a path outside the repository (one line per entry) |
| `WARNING:` | `DIR=<dir>: larger than the 60-second file-discovery cap; file list not read [over-cap]` | file discovery in a clone ran over its time cap |
| `WARNING:` | `listed files outside the downloaded repository<count>; not read [file-unreadable/outside-repository]` | files found outside after discovery (counted, not named) |
| `WARNING:` | `Build: <url>: --allow-build has no effect for a remote repository ...` | a build flag (from the library, `BuildOptions.allow`) |
| `ERROR:` | `ERROR: loom <command>: ...` | the run could not finish (the command names itself; any Git `ERROR:` above, and any other) |

The `Git source: ` in front of an `INFO:` or `WARNING:` line is a frame: it
names the fetch that said the line and is no part of it (the line is what
follows, with its `URL=` and its code), and only the codes the Git route
says admit it. An `ERROR:` line never carries it: the command prints its own frame
(`ERROR: loom <command>: ...`) as for every error, and no `WARNING:` repeats it.

A URL or ref in a message is shown without credentials (`https://***:***@host`,
`***:***@host:path` for an scp-style address, and the value of each query or
fragment parameter named like a secret, as listed in
[Credentials in URLs](url-credentials.md):
`?private_token=***`, and an access token's shape anywhere: `ghp_***`)
and with control characters escaped. Another secret in a parameter with
another name is not recognised. What a server or `git` says
is reduced to one line (its `fatal:`, `error:` and `remote:` lines), so it
cannot add a tagged line of its own.

If the repository has no Python project at its root but has some in folders,
the error names them (up to five) and asks for the URL of one of them.
