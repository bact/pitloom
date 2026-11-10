---
Created: 2026-11-10
Last-Modified: 2026-11-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: an SBOM from a PyPI URL

See also: [README.md](README.md) (index of these notes),
[../pypi-url-targets.md](../pypi-url-targets.md) (what was built, PR #468),
[remote-git-sources.md](remote-git-sources.md) (the Git URL counterpart),
[evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md)
(the evidence vocabulary),
[../recurring-bug-patterns-platform-windows.md](../recurring-bug-patterns-platform-windows.md)
(two Windows-only test failures from the same PR),
[remote-fetch-hardening.md](remote-fetch-hardening.md) (the fetch policy the
PyPI route shares with the Git and Hugging Face routes).

Facts checked on 2026-11-10 against the code of PR #468, a local server that
answers like the PyPI JSON API and file host, and `loom` runs on the same
tree. Each item has a "Do:" rule.

## 1. What a downloaded archive records

- **Two digests, one of them already compared.** The JSON API declares a
  SHA-256 per file; the tool hashes the bytes it receives as it streams them
  to disk. A mismatch refuses the file, so in every SBOM that exists the two
  are equal. Both are still written, as `sha256` with `Evidence:
  measured_read` and `sha256_declared` with `Evidence: declared` (and
  `Source: PyPI JSON API`): a later reader can see which was computed and
  which was claimed, and a future fetch can be compared with the claim.
  Do: record the measured and the declared value separately, each with its
  evidence level; never write one as the other.
- **The package hash is not the archive hash.** The SBOM of a wheel puts a
  Merkle root over its payload files in the package's `verifiedUsing`; an
  sdist's package has none. The archive's digest has no SPDX 3.0.1 home beside
  `downloadLocation`, which holds a URL only. It went into a provenance
  record (gap FG-15). Do: tell checkers' users that a "component hash" element
  is satisfied by the Merkle root, not by the digest of the file that was
  downloaded.
- **The version a URL spells is not always the version PyPI lists.** `1.0` and
  `1.0.0` are one PEP 440 release; the JSON API may list the second. The
  record keeps the listed spelling as the value and the URL's as
  `Normalized-From`; a URL with no version records `Method: latest-release`.
  Do: keep both spellings; a reader who compares raw strings finds a mismatch
  that is not one.

## 2. The same URL gives different SBOMs on different machines

- **A wheel is chosen for the interpreter that asks.** The candidates are the
  release's wheels whose tags appear in `packaging.tags.sys_tags()`; the best
  rank wins, a tie breaks on the file name, an unyanked file beats a yanked
  one. A pure-Python wheel is the same everywhere; a `manylinux`, `macosx` or
  `win_amd64` wheel is not, and neither is its payload. The SBOM records the
  tags, how many other compatible wheels were skipped and `Method:
  running-environment`, so a reader of the file alone knows why this wheel.
  Do: say that the output depends on the environment; offer the sdist when a
  platform-independent result is wanted; do not fall back to another
  platform's wheel silently.
- **Choosing the release first can fail the file second.** With no version in
  the URL the release is picked (stable and unyanked, then a pre-release, then
  a yanked one) before the kind is considered, so `loom project <url>` fails
  when the latest release has no sdist even though an older one has. Do:
  state the rule in the error and recommend the versioned URL; keep the
  pick-by-command refinement as a later, visible step.

## 3. Recognising the family of hosts

- **A recogniser must cover the family, not one host.** `pypi.org` alone left
  `test.pypi.org` and `pypi.python.org` to be cloned as Git repositories (the
  Git recogniser took every `http(s)` host that was not a Hugging Face
  model); the family test is `pypi.org`, `www.pypi.org`,
  any `*.pypi.org` and `pypi.python.org`, `http` and `https`, any case, a
  trailing dot dropped, and the PyPI route refuses what it does not read, with
  its own message. A direct link to a file on `files.pythonhosted.org` is not
  in the family and, found by probing on 2026-11-10, is still taken for a Git
  URL (`loom project <file link> --offline` reports "Git source: Cannot
  fetch"). Do: decide for every neighbouring host (file host, mirror, old
  address) whether it is refused, read or passed on, and test each.
- **Check the neighbour of a refusal.** The Git route also refuses a PyPI URL
  (`pypi-url-unusable`), for a library caller that reaches it without the
  command-line routing. Do: put the refusal where the dispatch is, and again
  at the entry that can be reached around it.

## 4. A deadline that is a socket shutdown

- A timeout on each socket operation does not bound a server that answers a
  byte at a time. A timer that shuts every socket the fetch opened at the
  deadline does, but a socket joins the watch only when `connect()` returns,
  so the name lookup, the TCP connect, a proxy `CONNECT` and the TLS handshake
  run outside it, bounded by the per-operation timeout alone. On Windows a
  shut socket does not end a pending read either (see the Windows file linked
  above), so the read ends at its timeout. Do: say what the deadline does
  not cover, in the code and in the user page, and bound the rest by the
  smaller timeout.
