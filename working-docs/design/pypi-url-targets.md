---
Created: 2026-11-07
Last-Modified: 2026-11-07
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# PyPI URL targets: `loom wheel <pypi-url>` and `loom project <pypi-url>`

See also: [roadmap.md](roadmap.md) (the summary bullet),
[remote-source-ingestion.md](remote-source-ingestion.md) (the wider remote
plan; its PyPI section is superseded by this page),
[git-urls.md](../../docs/git-urls.md) (the built Git URL target this mirrors),
[message-catalogue-and-skills.md](message-catalogue-and-skills.md) (the codes
used below), and [evidence-levels.md](evidence-levels.md) (how the download is
recorded).

Status: design, 2026-11-07. Nothing built. The first iteration is deliberately
small: **no new flags and no prompts**. Hand-tested on one small package
(2026-10-20): `loom project <sdist>` and `loom wheel <wheel>` each wrote an SBOM
that `sbomcheck` read, so the work is the fetch, pick and verify steps, not the
readers.

First consumer: Lumina's *Generate & check* page (a PyPI URL beside a Git or
Hugging Face one), which would call this resolver rather than carry its own.

## Decision

Pitloom takes a PyPI URL through the subcommands that already name the
artefact kind, not through a new `loom pypi` subcommand:

| Command | Target | Fetches | SBOM |
| :------ | :----- | :------ | :--- |
| `loom wheel <pypi-url>` | wheel | the one wheel that matches the running environment | Analyzed SBOM (payload only, as for a local wheel) |
| `loom project <pypi-url>` | sdist | the release's sdist | Source SBOM (as for a local sdist) |
| `loom generate <pypi-url>` | -- | the dispatcher routes to `wheel` | as `wheel` |

Why not `loom pypi` (the earlier sketch) or `loom source`: `wheel` and
`project` already mean "a built wheel" and "a project, directory or sdist". The
download is only a new way to obtain the file; after it the existing readers run
unchanged. A third name would split one job in two and need its own skill
trigger, docs page and `_matrix_plan.py` entry.

`loom generate` takes a PyPI URL to the wheel path because a wheel is what a
user installs. Asking for the sdist is `loom project <pypi-url>`.

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
   restricts the URL scheme); do not write a second client.
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

A release has at most one sdist, so there is no choice. No sdist: `ERROR:`
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
- **Signed wheel**: the existing `--allow-signed-wheel` rule applies unchanged
  to a downloaded wheel (this iteration adds no flag).

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
  add an entry to [sbom-format-gaps.md](sbom-format-gaps.md) in the same
  change.
- Output file name: the existing rule (`<name>-<version>.spdx3.json`); `-o -`
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
  [remote-source-ingestion.md](remote-source-ingestion.md)); a download cache.
- A private index with credentials (the token rules in
  [remote-source-ingestion.md](remote-source-ingestion.md)).
- A no-download mode reading `requires_dist` from the JSON API alone: not
  planned, since the file's own metadata is the better source.

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
[remote-source-ingestion.md](remote-source-ingestion.md)).
