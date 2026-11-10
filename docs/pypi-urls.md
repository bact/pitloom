---
Created: 2026-11-10
Last-Modified: 2026-11-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM from a PyPI URL

See also: [Command line](cli.md) for `loom wheel`, `loom project` and
`loom generate`,
[Python API: remote targets](python-api-remote.md) for `generate()` and `generate_pypi_sbom()`,
[SBOM from a Git URL](git-urls.md) for the same idea applied to a repository,
[Wheel SBOMs and PEP 770 embedding](wheel-sbom.md) for what is read from a
wheel, and [Configuration](configuration.md) for `max-download-bytes`.

Give `loom wheel`, `loom project` or `loom generate` the `https` URL of a
project or release page on `pypi.org`, and Pitloom downloads one file of the
release into a temporary directory, checks it against the SHA-256 that PyPI
declares for it, and reads it as it would read the same file on disk. The
directory is removed afterwards, and a message that would name it says
`<download>` instead, so two runs print the same text. Which file is
downloaded depends on the command, not on the URL.

```bash
loom wheel https://pypi.org/project/demo/1.0/ -o sbom.spdx3.json    # that release's wheel
loom project https://pypi.org/project/demo/1.0/                     # that release's sdist
loom generate https://pypi.org/project/demo/ -o sbom.spdx3.json     # latest release, its wheel
```

## Which URLs

| URL | Reads |
| :-- | :---- |
| `https://pypi.org/project/<name>/` | the latest release (see [Which release](#which-release)) |
| `https://pypi.org/project/<name>/<version>/` | that release |

- A trailing `/` is optional, and `www.pypi.org` and a capitalised host are
  accepted. The name is compared as PEP 503 does (`Foo_Bar` and `foo-bar` are
  one project) and the version as PEP 440 does (`1.0` and `1.0.0` are one
  release).
- `http://pypi.org/...` is refused, naming the `https` form; it is not
  upgraded silently. A URL with a user name or password is refused.
- A query or fragment is ignored, with one `INFO:` (`query-no-effect`).
- Any other page of `pypi.org` (a user page, a search page), another index
  (`test.pypi.org` or any other `*.pypi.org` host), `pypi.python.org`
  (PyPI's old address) and a direct link to a file on
  `files.pythonhosted.org` are not read; see [Not yet](#not-yet). Each is
  refused with its own line and is never cloned as Git; a file link's line
  names the release page to give instead. A trailing dot (`pypi.org.`) is
  accepted as `pypi.org`.
- A PyPI URL is never given to Git: `pypi.org`, every `*.pypi.org` host,
  `pypi.python.org` and `files.pythonhosted.org` are recognised before the
  Git rules on every surface, and the Git route refuses one itself
  (`pypi-url-unusable`). A private index on a host of its own is no PyPI URL;
  see [SBOM from a Git URL](git-urls.md#which-urls) for what the Git route
  reads.

With `--offline`, an invalid URL is reported first as `pypi-url-invalid`;
a valid one is then refused for `--offline`.

## What each command fetches

| Command | Fetches | SBOM kind | If the release lacks that file |
| :------ | :------ | :-------- | :----------------------------- |
| `loom wheel <url>` | the one wheel that fits the running Python and platform | Analyzed SBOM (the payload, as for a local wheel) | `ERROR:`, naming `loom project <url>` |
| `loom project <url>` | the release's sdist | Source SBOM (as for a local sdist) | `ERROR:`, naming `loom wheel <url>` |
| `loom generate <url>` | the same wheel as `loom wheel` | Analyzed SBOM | as `loom wheel`; an `INFO:` says `loom project <url>` reads the sdist |

There is **no fallback between kinds**: `loom wheel` never takes the sdist and
`loom project` never takes a wheel, because the SBOM kind would change without
a word. `loom generate` cannot ask for the sdist; use `loom project <url>`.
`loom model <url>` refuses a PyPI URL and names the two commands above. With
`generate()` and the wheel and project functions of the library, the URL is
given as a string; see [Python API: remote targets](python-api-remote.md).

## How the wheel is picked

`loom wheel` and `loom generate` depend on where they run, because the choice
follows the running interpreter and platform:

1. A wheel is a candidate when one of its tags is in the tag list of the running
   environment (`packaging.tags.sys_tags()`, the order `pip` uses).
2. The best-ranked candidate wins: the one whose best tag comes first in that
   list. A tie breaks on the file name, so one release gives one pick on one
   machine.
3. A yanked wheel is passed over while an unyanked one fits. If only yanked
   wheels fit, the best-ranked of them is read, with an `INFO:` naming the yank
   reason.
4. With more than one candidate, an `INFO:` names the pick and the number of
   candidates.
5. With no candidate, the read fails and lists the release's wheel files. There
   is **no fallback to another platform's wheel**: it would contradict the
   running environment, and the payload differs per platform. The error names
   `loom project <url>`, which reads the sdist.

The sdist is chosen by `loom project`: a release normally has one. Some old
releases have several (`.zip` and `.tar.gz`); the `.tar.gz` is preferred and
an `INFO:` says which was read.

A wheel or sdist whose entry in the PyPI answer is not valid (a name that is
not a bare ASCII file name, or is a Windows device name, a name that does not
belong to the release, no download URL, a name listed twice) is left out of the
choice, with one `WARNING:` per file. A file with no valid SHA-256 stays a
candidate: if it is the one picked, the run stops with
[`pypi-response-invalid`](message-codes.md#pypi-response-invalid) and does not
turn to the next file.

## Which release

Without a version, Pitloom asks the PyPI JSON API for the release list and takes
the newest release by PEP 440 order, in this order of preference:

1. a stable release that is not yanked;
2. else a pre-release that is not yanked;
3. else a yanked release.

A release counts only when it has a wheel or sdist with a SHA-256 digest.
Each choice beyond the first is said in an `INFO:` (see
[Messages](#messages)), and the `INFO:` for the first names the release too,
so a run is never silent about which version it read. Name the version in the
URL for a repeatable result.

A version named in the URL that is a pre-release or yanked is read all the
same: a yanked file gets an `INFO:` with PyPI's reason, a pre-release is
recorded in the SBOM only.

The version-less pick does not look at the command: it chooses the release
first and the file second. A latest release that has no sdist therefore fails
`loom project <url>` with `release-file-not-found/sdist` even when an older
release has one; give the versioned URL.

## Verification

The download is untrusted data:

- **https only.** The user URL, the JSON API URL and every redirect hop must be
  `https`.
- **Two hosts.** The URL host is `pypi.org`; the JSON API is
  `https://pypi.org/pypi/...`; files come from `files.pythonhosted.org` only.
  A file URL that PyPI names on another host is refused.
- **Every redirect hop is checked** before it is requested: scheme, host and
  user information, at most 5 hops, each said in an `INFO:`. A redirect to
  another host is refused, not followed. No `Authorization` header is ever
  sent. A library caller can check each URL first (`check_url=`).
- **The SHA-256 is compared.** Pitloom hashes the bytes it receives while it
  streams them to disk and compares the digest with the one the JSON API
  declares. A mismatch is an `ERROR:` and no SBOM; a file for which PyPI
  declares no digest is not downloaded at all.
- **Nothing is executed.** No build, no `setup.py`, no build backend, no
  `--allow-build` (a build flag has no effect and says so). The wheel and sdist
  readers read the archive without running it. An sdist's own
  `[tool.pitloom]` is never read; `--config FILE` is yours and applies.
- **The temporary directory is removed** on return, on an error too. No
  message and no SBOM names its path.
- **`--offline` is an error**, not a fallback, for every command (the flag, or
  `offline = true` from `--config`): nothing is requested.
- **`--embed` is refused** with `wheel <url>`: it would write into a temporary
  file.
- `--allow-signed-wheel` has no effect on a PyPI URL (a `WARNING:` says so):
  it concerns embedding, and `--embed` is refused for a URL.

## Size limit

A byte cap bounds reading, never reporting. The cap on the file is
`--max-download-bytes BYTES` (or `[tool.pitloom] max-download-bytes` from
`--config`, or `max_download_bytes=` in the library): **512 MiB** by default. A
positive integer; zero or a negative value is an error, not "unlimited". The
size PyPI declares for the file never gates the download: the bytes received do,
so a server that understates its size is stopped too.

```bash
loom wheel https://pypi.org/project/huge/1.0/ --max-download-bytes 2147483648
```

A file over the cap is not downloaded further: `ERROR:` with the catalogued
code [`over-cap`](message-codes.md#over-cap), and no SBOM. Raise the cap for one
run when you trust the project. The JSON API answer has its own fixed cap of
64 MiB (and a nesting limit). Timeouts: 30 seconds per socket read, 2 minutes
for the JSON answer, 30 minutes for the file. The deadline does not cover the
name lookup, the connection, a proxy `CONNECT` or the TLS handshake; each is
bounded by the per-operation timeout. On Windows a read stalled on a
connection ends at that timeout, not at the deadline.

On any other target `--max-download-bytes` has no effect and says so once; see
[Options with no effect](cli.md#options-with-no-effect).

## What the SBOM records

The SBOM is what `loom wheel` or `loom project` writes for the same file on
disk, plus **one provenance annotation on the main package** that says how the
file was obtained. SPDX 3 has no property for "obtained from URL X, archive
digest Y checked against Z, chosen because W", so the facts are carried as
provenance strings (gap FG-15 in the format-gap ledger, proposed for SPDX): an
`Annotation` whose JSON `statement` holds one entry per field below, and, with
the default `format = "both"`, the same entries in the package's `comment`
after `Metadata provenance:`. Every entry survives `detail = "minimal"`. How
provenance is written and what `Source`, `Method` and `Evidence` mean:
[Metadata provenance](metadata-provenance.md#the-download-record-a-file-read-from-a-pypi-url).
The fields of that record:

| Field | Meaning |
| :---- | :------ |
| `project_url` | the release page that was read |
| `download_location` | the file's URL on `files.pythonhosted.org`, with the file name |
| `sha256` | the SHA-256 measured from the downloaded bytes (`Evidence: measured_read`) |
| `sha256_declared` | the one the PyPI JSON API declared (`Evidence: declared`); equal to `sha256`, since a mismatch is refused |
| `release_version` | the version: for a pinned URL `Source: PyPI JSON API \| Value: 1.0.0`, with `\| Normalized-From: 1.0` when the URL spelled it differently; for an unpinned URL `Method: latest-release` |
| `release_status` | `prerelease` and/or `yanked`, with the yank reason; only when it applies |
| `wheel_tags` | the wheel's tags, from its file name (wheel only) |
| `compatible_wheels_skipped` | how many other compatible wheels were not read, and that the pick followed the running environment (wheel only) |

For example, for the latest release of a pure-Python project:

```text
project_url: Source: PyPI | Value: https://pypi.org/project/demo/1.0/
download_location: Source: PyPI | File: demo-1.0-py3-none-any.whl | Value: https://files.pythonhosted.org/packages/ab/cd/demo-1.0-py3-none-any.whl
sha256: Source: downloaded file | File: demo-1.0-py3-none-any.whl | Value: <64 hex digits> | Evidence: measured_read
sha256_declared: Source: PyPI JSON API | File: demo-1.0-py3-none-any.whl | Value: <64 hex digits> | Evidence: declared
release_version: Source: PyPI JSON API | Method: latest-release | Value: 1.0
wheel_tags: Source: wheel filename | File: demo-1.0-py3-none-any.whl | Value: py3-none-any
compatible_wheels_skipped: Source: PyPI JSON API | Method: running-environment | Value: 0
```

- The SBOM names the file by its PyPI file name and never by a temporary path.
  For a fixed creation time, one release read twice on one machine gives the
  same SBOM; the same URL on another platform can give another wheel, hence a
  different SBOM (see [How the wheel is picked](#how-the-wheel-is-picked)).
- The dependencies listed are the release's **declared** requirements
  (`Requires-Dist`, as the file's own metadata gives them), not a resolved
  environment.
- A wheel's contents are described as for any local wheel; an sdist's as for a
  local sdist. The output file name follows the command: `<wheel file
  name>.spdx3.json` for `loom wheel`, `<name>-<version>.spdx3.json` for
  `loom project`; `-o -` writes to stdout.

## Not yet

This is the first iteration. Not built:

- A flag to pick another platform's wheel (`--wheel-tag`), to list the candidate
  wheels (`--list`), to write one SBOM per wheel (`--all-wheels`) or to choose
  interactively (`--choose`). Today the wheel follows the running environment.
- A pick that looks at the command: `loom project <url>` without a version
  fails when the latest release has no sdist, even if an older one has; give
  the versioned URL.
- `name==version` and bare-name targets, links to files on
  `files.pythonhosted.org` (refused, naming the release page to give), other
  indexes (`test.pypi.org`, a private index) and credentials.
- A download cache: every run downloads again.

## Messages

Every decision and refusal is said, never silently. The level and code are
those of the [message catalogue](message-codes.md).

The CLI prints a refusal through its error handler, so the `ERROR:` text
follows a command prefix (`ERROR: wheel command failed: ...`, `ERROR: project
command failed: ...` or `ERROR: SBOM generation failed: ...`) and ends in the
code in brackets, for example `[pypi-url-invalid]`. A script or an agent should
key on that trailing code. The `ERROR:` rows below quote the part after the
prefix and before the code.

| Level | Message | When |
| :---- | :------ | :--- |
| `INFO:` | `PYPI=<name> VERSION=<version>: no version given; using the latest release` | the URL has no version ([`release-unpinned`](message-codes.md#release-unpinned)) |
| `INFO:` | `PYPI=<name> VERSION=<version>: no version given and no stable release that is not yanked; using the newest pre-release` | no stable, unyanked release ([`release-unpinned/prerelease`](message-codes.md#release-unpinnedprerelease)) |
| `INFO:` | `PYPI=<name> VERSION=<version>: no version given and every release is yanked; using the newest (yanked: <reason>)` | only yanked releases ([`release-unpinned/yanked`](message-codes.md#release-unpinnedyanked)) |
| `INFO:` | `PYPI=<name> VERSION=<version> FILE=<file>: the file is yanked (<reason>); reading it anyway` | the file read is yanked ([`release-unusable`](message-codes.md#release-unusable)) |
| `INFO:` | `PYPI=<name> VERSION=<version>: <n> wheels match this environment; using <file>, the best-ranked` | several wheels fit ([`file-ambiguous`](message-codes.md#file-ambiguous)) |
| `INFO:` | `PYPI=<name> VERSION=<version>: <n> sdists; using <file>` | several sdists ([`file-ambiguous`](message-codes.md#file-ambiguous)) |
| `INFO:` | `FILE=<file>: the downloaded sdist's own [tool.pitloom] settings are ignored (untrusted); --config or pitloom_config= applies` | `loom project <url>` read the sdist ([`config-unsafe`](message-codes.md#config-unsafe)) |
| `INFO:` | `URL=<url>: redirects to <target>; followed` | a followed redirect, each hop ([`url-moved`](message-codes.md#url-moved)) |
| `INFO:` | `URL=<url>: the query and fragment have no effect; cut` | the URL had a query or fragment ([`query-no-effect`](message-codes.md#query-no-effect)) |
| `INFO:` | `PYPI=<name>: loom generate reads the wheel; 'loom project <url>' reads the sdist` | `loom generate` read the wheel ([`file-ambiguous`](message-codes.md#file-ambiguous)) |
| `WARNING:` | `PYPI=<name> FILE=<file>: <why>; skipped` | a file of the release is not valid and left out ([`pypi-response-invalid`](message-codes.md#pypi-response-invalid)) |
| `WARNING:` | the refusal's own `ERROR:` text, repeated | any refusal, as well as its `ERROR:` |
| `ERROR:` | `URL=<url>: not a PyPI project or release page; give https://pypi.org/project/<name>/ or .../<name>/<version>/` | another page of `pypi.org` ([`pypi-url-invalid`](message-codes.md#pypi-url-invalid)) |
| `ERROR:` | `URL=<url>: PyPI is read over https only; give the https:// URL` | an `http` URL ([`pypi-url-invalid`](message-codes.md#pypi-url-invalid)) |
| `ERROR:` | `URL=<url>: holds user information; a PyPI URL is read without credentials` | a user name or password in the URL ([`pypi-url-invalid`](message-codes.md#pypi-url-invalid)) |
| `ERROR:` | `URL=<url>: <name> is not a valid project name` | a bad name ([`pypi-url-invalid`](message-codes.md#pypi-url-invalid)) |
| `ERROR:` | `URL=<url>: <version> is not a PEP 440 version` | a bad version ([`pypi-url-invalid`](message-codes.md#pypi-url-invalid)) |
| `ERROR:` | `PYPI=<name>: no such project on PyPI` | PyPI answers 404 ([`release-not-found`](message-codes.md#release-not-found)) |
| `ERROR:` | `PYPI=<name> VERSION=<version>: no such release on PyPI` | the version does not exist ([`release-not-found`](message-codes.md#release-not-found)) |
| `ERROR:` | `PYPI=<name>: no release has a wheel or sdist with a SHA-256 digest` | nothing to read ([`release-not-found`](message-codes.md#release-not-found)) |
| `ERROR:` | `PYPI=<name> VERSION=<version>: the release has no wheel; 'loom project <url>' reads its sdist` | `wheel` or `generate` on a release without wheels ([`release-file-not-found`](message-codes.md#release-file-not-found)) |
| `ERROR:` | `PYPI=<name> VERSION=<version>: no wheel matches this Python and platform (wheels: <files>); 'loom project <url>' reads its sdist` | wheels, none for this environment ([`release-file-not-found/compatible-wheel`](message-codes.md#release-file-not-foundcompatible-wheel)) |
| `ERROR:` | `PYPI=<name> VERSION=<version>: the release has no sdist; 'loom wheel <url>' reads a wheel` | `project` on a release without an sdist ([`release-file-not-found/sdist`](message-codes.md#release-file-not-foundsdist)) |
| `ERROR:` | `FILE=<file>: SHA-256 <measured> does not match <declared> declared by <source>; not read` | the download is not the file PyPI declared ([`digest-invalid`](message-codes.md#digest-invalid)) |
| `ERROR:` | `FILE=<file>: PyPI declares no SHA-256 digest; not downloaded` | no digest to check against ([`pypi-response-invalid`](message-codes.md#pypi-response-invalid)) |
| `ERROR:` | `PYPI=<name>: PyPI answered for project <other>; not read` | the answer is for another project ([`pypi-response-invalid`](message-codes.md#pypi-response-invalid)) |
| `ERROR:` | `PYPI=<name>: the PyPI JSON API answer has no valid <field>; not read` | the answer lacks a field ([`pypi-response-invalid`](message-codes.md#pypi-response-invalid)) |
| `ERROR:` | `URL=<url>: redirects to <target>; not followed (<why>)` | a redirect to another scheme or host ([`url-unsafe`](message-codes.md#url-unsafe)) |
| `ERROR:` | `URL=<url>: more than <n> redirects; not followed` | too many redirects ([`url-unsafe`](message-codes.md#url-unsafe)) |
| `ERROR:` | `FILE=<file>: download URL <target> is not on <hosts>; not fetched` | PyPI names a file on another host ([`url-unsafe`](message-codes.md#url-unsafe)) |
| `ERROR:` | `URL=<url>: <failure>; not read` | an HTTP status other than 404, a refused connection, a name that did not resolve ([`download-network-failed`](message-codes.md#download-network-failed)) |
| `ERROR:` | `URL=<url>: no complete answer within <seconds> seconds; not read` | a timeout ([`download-timeout`](message-codes.md#download-timeout)) |
| `ERROR:` | `URL=<url>: --embed writes into a wheel file, and a PyPI URL has none to keep; nothing fetched` | `loom wheel <url> --embed` ([`pypi-url-unusable`](message-codes.md#pypi-url-unusable)) |
| `ERROR:` | `URL=<url>: a PyPI page is not a model; 'loom wheel' reads its wheel, 'loom project' its sdist; nothing fetched` | `loom model <url>` ([`pypi-url-unusable`](message-codes.md#pypi-url-unusable)) |
| `ERROR:` | `FILE=<file>: could not be saved in the temporary directory (<failure>); not downloaded` | the disk is full or the temporary directory cannot be written ([`temp-dir-unusable`](message-codes.md#temp-dir-unusable)) |
| `ERROR:` | `FILE=<file>: <reason>; not downloaded` | the file is over `max-download-bytes` ([`over-cap`](message-codes.md#over-cap)) |

A temporary directory that cannot be fully removed on return is a `WARNING:`
(`PyPI source: could not fully remove temporary directory ...`), not an error:
the SBOM is already written.

Fragments for the refusals of other hosts (after the command prefix, before the
code):

- `URL=<url>: only pypi.org is read; another index is not supported yet` `[pypi-url-invalid]`
- `URL=<url>: pypi.python.org is PyPI's old address; give https://pypi.org/project/<name>/` `[pypi-url-invalid]`
- `URL=<url>: a file link is not read yet; give the project or release page https://pypi.org/project/<name>/<version>/` `[pypi-url-invalid]`
- `URL=<url>: a PyPI page is not a Git repository; generate_pypi_sbom(), 'loom wheel' or 'loom project' reads it; nothing fetched` `[pypi-url-unusable]` (the library Git route)
- `INFO: PYPI=<name>: generate() reads the wheel; generate_pypi_sbom('<url>', kind='sdist') reads the sdist` `[file-ambiguous]` (library `generate()`; the CLI line names `loom project <url>`)

A URL in a message is shown without credentials and with control characters
escaped, and what PyPI says (a file name, a yank reason) is reduced to one line,
so it cannot add a tagged line of its own.
