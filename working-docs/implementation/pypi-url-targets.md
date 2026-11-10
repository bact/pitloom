---
Created: 2026-11-07
Last-Modified: 2026-11-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# PyPI URL targets: `loom wheel <pypi-url>` and `loom project <pypi-url>`

See also: [roadmap.md](../design/roadmap.md) (the summary bullets),
[remote-source-ingestion.md](../design/remote-source-ingestion.md) (the wider
remote plan; its PyPI section is superseded by this page),
[pypi-urls.md](../../docs/pypi-urls.md) (the user-facing page),
[git-urls.md](../../docs/git-urls.md) (the built Git URL target this mirrors),
[message-catalogue-and-skills.md](../design/message-catalogue-and-skills.md)
(the codes used below), [evidence-levels.md](../design/evidence-levels.md) (how
the download is recorded) and [sbom-format-gaps.md](../design/sbom-format-gaps.md)
(FG-15, the provenance record).

Status: **built (iteration 1), 2026-11-10**, for 0.24.0. The design below is
kept as it was decided on 2026-11-07; [Amendments](#amendments-at-build-time-2026-11-10)
lists where the build departs from it, and wins where they differ. The first
iteration was meant to be small: **no prompts**, and (as designed) no new
flags; one flag was added (see the amendments). Hand-tested on one small package
(2026-10-20): `loom project <sdist>` and `loom wheel <wheel>` each wrote an SBOM
that `sbomcheck` read, so the work is the fetch, pick and verify steps, not the
readers.

First consumer: Lumina's *Generate & check* page (a PyPI URL beside a Git or
Hugging Face one), which would call this resolver rather than carry its own.

## Amendments at build time (2026-11-10)

Where the build differs from the design below:

1. **One new flag, `--max-download-bytes BYTES`** (user decision, 2026-11-09;
   the design said "no new flags"). Config key `max-download-bytes` (only via
   `--config` for a remote target, since a downloaded project's own config is
   never read), library `max_download_bytes=`; default 512 MiB; a positive
   integer, validated on every surface even where it has no effect, and an
   inert option (one `WARNING: Options:`) on every target but a PyPI URL.
   Over the cap: `ERROR:` `over-cap` (`DOWNLOAD_LINE`), no SBOM. The size PyPI
   declares never gates the read; the bytes received do. The design's
   "reuse the existing archive limits" was dropped: those bound what is read
   from an archive, not the archive.
2. **Several sdists in one old release**: the design said "at most one". Old
   releases can carry a `.zip` and a `.tar.gz`; the `.tar.gz` is preferred,
   then the file name, with an `INFO:` (`file-ambiguous`, `SDIST_PICK_LINE`).
3. **`check_url` on every URL**, not on redirect hops only: the JSON API URL,
   the file URL and each hop are given to the caller's check before the
   request (the Lumina address guard). `fetch_json` was not reused: it
   follows redirects unchecked; one hardened client
   (`extract/remote/_http_fetch.py`) serves the JSON API and the file, and
   `deps_pypi` builds its URL with the shared `pypi_json_url()`.
4. **The SBOM record is one provenance Annotation on the main package**, not
   native SPDX elements (user decision, 2026-11-09): the PyPI project URL, the
   file URL, the SHA-256 measured from the bytes and the declared one it
   matched (`Evidence: measured_read` / `declared`), the release version
   (pinned: `Source: PyPI JSON API | Value: 1.0.0`, plus
   `| Normalized-From: 1.0` when the URL spelled it differently; unpinned:
   `Method: latest-release`), the release status and yank
   reason, and for a wheel its tags and the number of other compatible wheels
   skipped (`Method: running-environment`). Built only through
   `provenance_source`/`provenance_segment`/`evidence_segment`. Rejected: the
   archive as a `software_File` with `hasDistributionArtifact` (structural
   drift from the local SBOM; a local wheel would want it too). The gap is
   FG-15 in [sbom-format-gaps.md](../design/sbom-format-gaps.md).
5. **JSON API answer cap**: 64 MiB and a nesting limit (the plan said 16 MiB);
   socket timeout 30 s, 2 minutes for the JSON answer, 30 minutes for the
   file; at most 5 redirects.
6. **An unpinned URL ignores the kind and the platform when it picks the
   release**: the release is chosen first (stable and unyanked, then
   pre-release, then yanked; it counts when it has a wheel or an sdist with a
   SHA-256), the file second. `loom project <pypi-url>` therefore fails with
   `release-file-not-found/sdist` when the latest release has no sdist even
   if an older one has; the workaround is the versioned URL. Making the pick
   look at the command is a later-iteration item.
7. **New catalogue families** (`since` 0.24.0): `pypi-url-invalid`,
   `url-unsafe`, `url-moved`, `query-no-effect`, `release-not-found`,
   `release-file-not-found` (with `/compatible-wheel` and `/sdist`),
   `digest-invalid`, `pypi-response-invalid`, `download-network-failed`,
   `download-timeout`, `temp-dir-unusable`, `release-unpinned` (with
   `/prerelease` and `/yanked`), `release-unusable` (a yanked file) and
   `file-ambiguous`; errors are `RemoteSourceError` codes `pypi.*`, each with
   its `pitloom_code`.
8. **PyPI is recognised before Git** on every surface (a PyPI URL passes
   `is_git_url`). `loom model <pypi-url>` is refused, naming `loom wheel` and
   `loom project`.
9. **`PypiDownload.unpinned` was replaced by `requested_version`.**
10. **The temporary directory** is `pitloom-pypi-XXXXXXXX`, masked as
   `<download>` by `mask_checkout`. It is made and removed by
   `core.temp_dirs.temp_dir` (`mkdtemp`, then `remove_temp_dir`: never raises;
   a leftover, such as a file still held open on Windows, is one `WARNING:`),
   not `TemporaryDirectory`, whose cleanup raises after the caller may have
   written its output. The Git route's checkout (`pitloom-git-XXXXXXXX`) moved
   to the same context manager in the same PR: before, the library route
   could write its SBOM and then fail on the cleanup, while the CLI wrote
   nothing. `rmtree_quietly` now retries once after making what is left
   writable (links skipped), as `TemporaryDirectory` does, since a Git pack
   file is read-only and Windows' rmtree leaves it. The Hatchling hook's
   staging directory had the same exposure (its `finalize()` runs after the
   wheel is written) and now uses `mkdtemp` and `remove_temp_dir` too. Left
   as `TemporaryDirectory`: setuptools' `egg_base` in
   `_models_wheel_setuptools.py` (removed before any output exists, so a
   failure there fails every surface alike) and the build work directory
   (`ignore_cleanup_errors=True` and a `WARNING:` already).
11. **`--allow-signed-wheel` is inert for a PyPI URL** (`WARNING: Options:
    ... has no effect without --embed`), not "the existing rule applies
    unchanged": `--embed` is refused for a URL (`pypi-url-unusable`), so no
    wheel is ever rewritten.
12. **Output file names follow the command**: `loom wheel <url>` writes
    `<wheel file name>.spdx3.json`, `loom project <url>`
    `<name>-<version>.spdx3.json` (or the `--config` `sbom-basename`), not one
    rule for both.
13. **The host family is recognised, not one host.** `is_pypi_url` takes
    `http` and `https` URLs on `pypi.org`, `www.pypi.org`, any `*.pypi.org`,
    `pypi.python.org` and `files.pythonhosted.org` (any case, a trailing dot
    dropped), so each is refused with a PyPI message (`pypi-url-invalid`) and
    never cloned. The file host joined the family on 2026-11-10: before, a
    direct file link reached the Git route and failed there. It is refused
    (`PYPI_FILE_LINK_LINE`, naming the release page to give); reading it as
    a file link is still the "file links" item under Deferred.
14. **One hardened HTTP client** (`_http_fetch.py`, `_http_watch.py`): https
    only, hosts allowlisted, no `Authorization`, no redirect handler of the
    standard library (hops followed by hand, at most 5, each checked and said),
    a byte cap on the bytes received (a `Content-Length` never gates a read,
    it only tells a cut body), and an overall deadline made of a timer that
    shuts every socket the fetch opened. The deadline does not cover the name
    lookup, the connect, a proxy `CONNECT` or the TLS handshake (a socket joins
    the watch when `connect()` returns); on Windows a shut socket does not end
    a pending read, which then ends at the per-operation timeout.
15. **Windows CI lessons** (PR #468's first Windows run): a test asserting
    `recv() == b""` after `shutdown(SHUT_RDWR)` blocked to its timeout, and a
    zero-second deadline read exactly 0 on the coarse Windows clock. Both are
    in [recurring-bug-patterns-platform-windows.md](recurring-bug-patterns-platform-windows.md);
    production already compared expiry as `<= 0`, the test did not.
16. **The dependency lookup shares the constant** `PYPI_JSON_API`
    (`Source: PyPI JSON API`, also the `Source` of a dependency's licence and
    originator), and `deps_pypi` builds its URL with `pypi_json_url()`; it does
    not pass through the caller's `check_url`.
17. **Library entry**: `generate_pypi_sbom_with_download()` returns
    `PypiSbom(sbom, download, metadata)`; `generate_pypi_sbom()` the SBOM
    alone; `generate()`, `generate_wheel_sbom()` and `generate_project_sbom()`
    take the URL string. `generate()` reads the wheel and says the library's
    sdist route in one `INFO:`.
18. **Surfaces**: the Hatchling hook does not apply. The GitHub Action is not
    extended: its inputs name a project directory, a wheel pattern or a model,
    not a URL. All three skills know the route (`sbom-generate`'s
    `references/pypi-url.md`, `sbom-enrich`'s `references/pypi-url-base.md`,
    a section in `sbom-validate`); see
    [skills-trigger-coverage.md](skills-trigger-coverage.md).

User-facing page: [pypi-urls.md](../../docs/pypi-urls.md).

## Decision

**Three commands accept a PyPI URL. The subcommand, not the URL, decides which
file is fetched.** The same URL gives a different file and a different SBOM
kind depending on the command:

| Command | Fetches | SBOM kind | If the release lacks that file |
| :------ | :------ | :-------- | :----------------------------- |
| `loom wheel <pypi-url>` | the one wheel that matches the running environment | Analyzed SBOM (payload only, as for a local wheel) | `ERROR:`, names `loom project <pypi-url>` |
| `loom project <pypi-url>` | the release's sdist | Source SBOM (as for a local sdist) | `ERROR:`, names `loom wheel <pypi-url>` |
| `loom generate <pypi-url>` | the same wheel as `loom wheel` (it routes to that path) | Analyzed SBOM | as `loom wheel`; an `INFO:` says `loom project <pypi-url>` gives the sdist |

Rules that follow from the table:

- There is **no fallback between kinds**. `loom wheel` never takes the sdist
  and `loom project` never takes a wheel, because the SBOM kind would change
  silently.
- `loom generate` has no way to ask for the sdist in iteration 1. Use
  `loom project <pypi-url>`.
- `loom wheel` and `loom generate` depend on the running environment for the
  wheel pick; `loom project` does not (a release has one sdist).
- The URL is the same in all three commands; only the command differs.

Why not `loom pypi` (the earlier sketch) or `loom source`: `wheel` and
`project` already mean "a built wheel" and "a project, directory or sdist". The
download is only a new way to obtain the file; after it the existing readers run
unchanged. A third name would split one job in two and need its own skill
trigger, docs page and `_matrix_plan.py` entry. This follows the Git URL
target, which `loom project` and `loom generate` both accept.

`loom generate` takes the wheel path because a wheel is what a user installs.

## Accepted URLs (iteration 1)

- `https://pypi.org/project/<name>/` -- the latest release (stable and unyanked first; see Resolution).
- `https://pypi.org/project/<name>/<version>/` -- that release.
- A direct file link on `files.pythonhosted.org` is a later step (a file link
  names a file, so no selection is needed; it stays out of iteration 1 to keep
  one resolver path).

Anything else on `pypi.org` (a user page, a search page) is refused with a
message. The name is read as a PEP 503 name and the version as PEP 440; both are
compared the ecosystem's way, never as raw strings. Other indexes
(`test.pypi.org`, a private index) are not iteration 1.

## Resolution

1. Ask the JSON API: `https://pypi.org/pypi/<name>/json` or
   `.../<name>/<version>/json`. Reuse the existing PyPI JSON lookup in
   `pitloom.assemble.spdx3.deps_pypi` (its `urlopen`/`json.loads` path already
   restricts the URL scheme); do not write a second client. (Superseded by
   amendment 3: one new client.)
2. No version: take the latest release that is neither a pre-release nor
   yanked and has at least one usable file. Say it: `INFO: PYPI=<name>
   VERSION=<ver>: no version given; using the latest release`. If no such
   release exists, take the newest one that has a usable file (a pre-release
   before a yanked one) and generate the SBOM anyway, with an `INFO:` naming
   which it is (`pre-release` or `yanked`, with the yank reason PyPI gives).
   A version the user names that is a pre-release or yanked is read the same way,
   with the same `INFO:`. The status is also recorded in the SBOM (below).
3. Pick the file (below), download it, verify it, hand it to the existing
   reader.

### Picking the wheel (`loom wheel`)

The wheel whose tags are compatible with the running interpreter and platform,
best-ranked first, using `packaging.tags.sys_tags()` (the order `pip` uses).
`packaging` is already a dependency.

- **One compatible wheel**: use it.
- **Several compatible wheels**: use the best-ranked one. An `INFO:` names the
  pick and the number of others skipped, so the choice is never silent.
- **No compatible wheel**: `ERROR:` listing the release's wheel filenames and
  saying that the running environment matches none. No fallback to another
  platform's wheel: a fallback would contradict the user's environment
  silently ("honour user intent"), and the payload differs per platform. The
  message points to `loom project <pypi-url>` for the sdist.
- **No wheel at all**: `ERROR:` pointing to `loom project <pypi-url>`.
- **Yanked files**: a yanked file is passed over while an unyanked wheel
  matches. If only yanked files match, the best-ranked one is used with the
  yanked `INFO:` above.

The sort must be a stable total order: a tie between two wheels of equal rank
breaks on filename, so the same release gives the same pick on the same
machine.

Matching the running environment means the SBOM depends on where it is built.
That is a documented property of this iteration, not a bug. The pick is named in
the `INFO:` line **and stated in the SBOM itself** (decided 2026-11-07): the
wheel filename and its tags, the number of compatible wheels skipped, and that
the choice followed the running environment, so a reader of the SBOM alone can
tell why this wheel. Pinning another platform needs a flag, deferred.

### Picking the sdist (`loom project`)

A release has at most one sdist, so there is no choice (superseded by
amendment 2: an old release can have two). No sdist: `ERROR:`
pointing to `loom wheel <pypi-url>`. (The sdist is never an implicit fallback
for `loom wheel`, nor the wheel for `loom project`: the two commands give
different SBOM kinds, and a quiet swap would change the kind.)

## Download and verification

The file is untrusted data.

- **Host**: only `files.pythonhosted.org`, the host the JSON API names. A file
  URL on any other host is refused and logged.
- **Caps** bound reading, never reporting (AGENTS.md): a size ceiling and a
  timeout on the download, chunked reads (`read(8192)`) into a temporary
  directory, never the whole file in memory. The ceiling reuses the existing
  archive limits of the wheel and sdist readers; the size PyPI declares is a
  declared value and never gates the read.
- **Digest**: the JSON API lists each file's SHA-256. Pitloom hashes the bytes
  it received. A mismatch is an `ERROR:` and no SBOM. A match is recorded
  with both levels: the digest *measured* from the bytes, and the source it was
  checked against (*declared* by the PyPI API).
- **Nothing runs**: no build, no `setup.py`, no `--allow-build`. The wheel and
  sdist readers already read archives without executing them.
- **`--offline`** is an error for a PyPI URL, as for a Git URL.
- **Temporary directory**: removed afterwards. Messages name the file by its
  PyPI filename and never the temporary path, so two runs print the same text.
- **Signed wheel**: (superseded by amendment 11) `--allow-signed-wheel` has
  no effect for a URL.

## What the SBOM says

- The subject is the downloaded file, named by its PyPI filename; the SBOM is
  what `loom wheel`/`loom project` writes for that local file today.
- Provenance records the PyPI project URL, the file URL and the verified
  SHA-256, built only through `provenance_source`/`provenance_segment`.
- The SBOM also states how the file was chosen (wheel only, see above) and the
  release status when it is a pre-release or yanked. A format that cannot hold
  these precisely goes in the gaps ledger below.
- The format has no property for "obtained from this URL" with a digest for a
  package file beyond `downloadLocation` and a hash; if the mapping stretches,
  add an entry to [sbom-format-gaps.md](../design/sbom-format-gaps.md) in the same
  change.
- Output file name: as the local command writes it (amendment 12); `-o -`
  works as for the local file.
- `--embed` (wheel) is **not** offered for a downloaded wheel: it would write
  into a temporary file. It is refused with a message, not ignored.

## Dependencies the SBOM lists

The SBOM states the release's **declared** requirements (`requires_dist`, as the
local reader already reads them from the file's own metadata), not a resolved
environment, and says so. Extras follow the local reader's rule for a wheel or
sdist (an extra edge is `hasOptionalDependency` with no scope).

## Surfaces

One resolver (`pitloom.extract.remote`, next to the Git and Hugging Face
code), used by every surface (AGENTS.md "usage surfaces"):

- CLI: `loom wheel`, `loom project` and `loom generate` recognise the URL.
- Library: `generate()` and the wheel/project APIs accept the URL string.
- Hatchling hook: not applicable (a build never fetches PyPI wheels).
- GitHub Action: inherits the CLI; check the `target` input handling.
- Skills: `sbom-generate` description lists "PyPI URL"; a combined "generate
  and enrich/validate" ask hands off as for other targets; a non-interactive
  fallback for every follow-up question. Grep `skills/` in the same change.
- Messages: new catalogue entries (`pypi/...` family) through
  `pitloom.messages`, `since` the next release, reference regenerated.
- `scripts/manual_cli_checks/_matrix_plan.py` entries for the new target
  forms; network checks marked `network`.

## Tests

- Resolver with a local loopback server standing in for the JSON API and the
  file host (marked `loopback`); the live check is a `network` test.
- `sys_tags` pick: patch the tag order, not the host, so the test is the same
  on Linux, macOS and Windows; a tie between equal ranks; no compatible wheel;
  yanked only; no version given; PEP 503 spelling variants of the name.
- Digest mismatch; a file URL on another host; an oversize body; a redirect to
  another host.
- Determinism: same release, same bytes, same SBOM; the clock pinned.
- A downloaded wheel and the same wheel passed as a local path give the same
  SBOM apart from the provenance (a drift guard).
- Dry-run on Windows (path and temporary directory handling).

## Deferred (after iteration 1)

- `--wheel-tag` / `--filename`: pick another platform's wheel (build first:
  Lumina needs it).
- `--list`: one `KEY=VALUE` line per candidate wheel, then exit.
- `--all-wheels`: one SBOM per wheel into an `-o` directory (never one merged
  document: platform wheels differ in payload).
- `--choose`: an interactive pick, only on a TTY and only when asked; never
  the default, because stdout is data only and the hook, CI and Action cannot
  answer.
- `name==version` and bare-name targets; `files.pythonhosted.org` file links;
  other indexes and credentials (shares the token rules in
  [remote-source-ingestion.md](../design/remote-source-ingestion.md)); a download cache.
- A private index with credentials (the token rules in
  [remote-source-ingestion.md](../design/remote-source-ingestion.md)).
- A no-download mode reading `requires_dist` from the JSON API alone: not
  planned, since the file's own metadata is the better source.

## Leftovers after PR #468 (2026-11-10)

Found while building or reviewing iteration 1 and left out of its scope; none
blocks it.

- **Deadline holes**: the name lookup, the TCP connect, a proxy `CONNECT`
  tunnel and the TLS handshake run before the socket joins the overall
  deadline (`_http_watch.Watch`), each bounded only by the per-operation
  timeout. Closing it needs `HTTPConnection._create_connection`, a private
  API.
- **Unpinned pick ignores the kind and the platform**: with no version, the
  latest release is chosen before its files are looked at, so `loom project`
  fails with `release-file-not-found/sdist` when that release has wheels only,
  and `loom wheel` with `.../compatible-wheel` when only an older release
  matches (pip would go back). The user gives the version today.
- **Refusal printed twice**: a refused PyPI or Git URL logs a `WARNING:`
  echoing the error, then the coded `ERROR:`; the Git route did so first.
- **`--offline` refusal has no code**: no catalogue family fits "network
  access is forbidden" (the Git route has the same gap).
- **Reader exceptions to a library caller**: masking of the temporary path
  (`mask_checkout`) happens in logging and `print_error` only, so an exception
  a wheel or sdist reader raises to a library caller may still name the
  `pitloom-pypi-`/`pitloom-git-` directory (as on the Git route).
- **Hatchling hook leftover name**: its "could not fully remove" warning names
  the real `pitloom-hatch-XXXXXXXX` directory, unmasked, as the build work
  directory's warning does.
- **Windows junctions**: `rmtree_quietly`'s writable retry skips symbolic
  links but not junctions (`os.path.islink` is false for one); neither a
  checkout nor a download holds one.
- **`verify-wheel`, `validate-wheel`, `embed-wheel` given a URL** print `not a
  .whl file: 'https:/pypi.org/...'`: the `Path` collapses `//`. They should
  say a URL is not read there.
- **GitHub Action**: its inputs name a directory, a wheel pattern or a model,
  not a URL; a PyPI (or Git) URL input is not offered.
- **Size limits**: `skills/sbom-generate/SKILL.md` body is 16,380 of 16,384
  bytes (the next addition moves text to `references/`);
  `core/_config_parse.py` is 505 lines; `docs/cli.md` and
  `working-docs/design/roadmap.md` were over the ~30 KB limit before this PR.
- **CLAUDE.md one-liners proposed**, for "Tests, platform and CI": Windows
  ends no `recv` on a socket shut for reading (spy the shutdown, keep the
  end-of-stream read POSIX-only); Windows' monotonic clock ticks about every
  15.6 ms, so compare a deadline's expiry as `<= 0`. Detail in
  [recurring-bug-patterns-platform-windows.md](recurring-bug-patterns-platform-windows.md).

## Decisions on the first open questions (2026-11-07)

1. **Only pre-releases or only yanked files**: generate the SBOM and say so with
   an `INFO:` (and in the SBOM); no error. See Resolution.
2. **Environment-dependent output**: the SBOM states which wheel was picked and
   why. See "Picking the wheel".
3. **`loom generate` with a release that has both kinds**: wheel by default, and
   an `INFO:` on stderr says that `loom project <pypi-url>` gives the sdist.
4. **Lumina** (first consumer) needs the sdist or the pure-Python wheel
   regardless of its server's platform; that needs `--wheel-tag`, so it is the
   first deferred item to build.

## Open questions

None left for iteration 1. For later iterations: whether extras are on or off by
default for a downloaded release, and whether a download cache is per user
(`~/.cache/pitloom/remote/<hash>`) or ephemeral (the same question as in
[remote-source-ingestion.md](../design/remote-source-ingestion.md)).
