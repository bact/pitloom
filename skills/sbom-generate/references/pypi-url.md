---
Created: 2026-11-10
Last-Modified: 2026-11-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Generating an SBOM from a PyPI URL

See also: [examples.md](examples.md), [git-url.md](git-url.md) (the same idea
for a repository); the Pitloom site page "SBOM from a PyPI URL"
(<https://bact.github.io/pitloom/pypi-urls/>). Pitloom 0.24.0 and later.

`loom wheel <url>` / `loom project <url>` / `loom generate <url> -o FILE` take
the `https` URL of a PyPI project page (`https://pypi.org/project/<name>/`,
the latest release) or release page (`.../<name>/<version>/`). Pitloom
downloads one file of the release into a temporary directory, checks its
SHA-256 against the one PyPI declares, reads it as it reads the file on disk,
and removes the directory. The command, not the URL, decides which file:

| Command | Reads | SBOM kind |
| :------ | :---- | :-------- |
| `loom wheel <url>` | the wheel that fits the running Python and platform | Analyzed SBOM |
| `loom project <url>` | the release's sdist | Source SBOM |
| `loom generate <url> -o FILE` | as `loom wheel`; an `INFO:` names `loom project <url>` for the sdist | Analyzed SBOM |

Rules to state to the user:

- Run a PyPI URL only with `uvx --from "pitloom>=0.24.0"` (or after `loom
  --version` shows 0.24.0 or later). The ephemeral recipe in `SKILL.md` pins
  an older floor, where a `pypi.org` URL is cloned as Git. On an older
  `loom`, do not run it; report that 0.24.0 is needed.
- A refusal prints `ERROR:` after a command prefix (`wheel command failed:`,
  `project command failed:` or `SBOM generation failed:`), then the
  condition, ending in the code in brackets. Key on that trailing `[code]`,
  not on the start of the line; the quoted `ERROR:` fragments below are the
  part after the prefix.

- There is no fallback between kinds. `loom wheel` never takes the sdist and
  `loom project` never takes a wheel. `loom generate` cannot ask for the
  sdist: use `loom project <url>`.
- The wheel is picked from the running environment (`sys_tags` order, ties by
  file name, a yanked wheel only when no unyanked one fits). The SBOM of the
  same URL can differ on another platform. No wheel, or none compatible, is an
  `ERROR:` (`[release-file-not-found]`, `[release-file-not-found/compatible-wheel]`)
  that names `loom project <url>`; no sdist is the mirror
  (`[release-file-not-found/sdist]`, naming `loom wheel <url>`). Offer the
  command the line names; do not run it unasked (non-interactively, report
  only). There is no flag yet to pick another platform's wheel.
- A URL without a version reads the latest release: a stable release that is
  not yanked, else a pre-release, else a yanked one (`[release-unpinned]`,
  `[release-unpinned/prerelease]`, `[release-unpinned/yanked]`; each an
  `INFO:` naming the version read). Recommend the versioned URL for a
  repeatable SBOM. The pick looks at the release first, so `loom project <url>`
  without a version fails with `[release-file-not-found/sdist]` when the
  latest release has no sdist, even if an older one has: give the versioned
  URL.
- A yanked file is read with an `INFO:` giving PyPI's reason
  (`[release-unusable]`); relay it, and say the choice to rely on it is the
  user's.
- Only `https`, only `pypi.org` for the URL and API and
  `files.pythonhosted.org` for files. Every redirect hop is checked.
  `http://`, a URL with a user name or password, another page of `pypi.org`
  `pypi.python.org` and another index (`test.pypi.org`, any `*.pypi.org`) are
  `[pypi-url-invalid]` with their own lines, never cloned as Git; a redirect or file URL on
  another host is `[url-unsafe]`. Do not fetch the target for the user.
- A SHA-256 that differs from the declared one is `[digest-invalid]`: nothing
  is read. Tell the user the file may have been altered; suggest running
  again, and reporting it to PyPI if it repeats.
- Nothing from the download is run (no build, no `setup.py`);
  `--allow-build` has no effect (a `WARNING:` says so) and an sdist's own
  `[tool.pitloom]` is ignored (`--config FILE` applies). `--offline` is an
  error, and `loom wheel <url> --embed` is refused.
- The file is capped at 512 MiB (`--max-download-bytes BYTES`, or
  `max-download-bytes` in a `--config` file). A larger one is
  refused with `FILE=<file>: ... ; not downloaded [over-cap]` and no SBOM. Tell the
  user about the flag and what it costs (disk, time, a hostile file); do not
  raise it for them (non-interactively, report only). The flag on any other
  target warns that it has no effect.
- The output is named as for a local file (`<wheel file name>.spdx3.json` for
  `loom wheel`, `<name>-<version>.spdx3.json` for `loom project`). No
  temporary path is in the SBOM or a message (`<download>` stands for it).

## What the SBOM records

The SBOM is the local file's, plus one provenance annotation on the main
package: the project page, the file's URL, the SHA-256 measured from the
bytes (`Evidence: measured_read`) and the one PyPI declared (`Evidence:
declared`), the version (a pinned URL: `Source: PyPI JSON API | Value: 1.0.0`, plus
`| Normalized-From: 1.0` if the URL spelled it differently; an unpinned one:
`Method: latest-release`), the
status when it is a pre-release or yanked, and for a wheel its tags and how
many other compatible wheels were skipped (`Method: running-environment`).
SPDX 3 has no property for these, so they are provenance text (a gap Pitloom
tracks for SPDX). Read them to explain why this wheel; never edit them. The
declared requirements (`Requires-Dist`) are listed, not a resolved
environment.

## Messages to relay

Read `messages.md` for each code above and relay its advice. A
`WARNING: PYPI=<name> FILE=<file>: ...; skipped` (`[pypi-response-invalid]`)
means a file of the release was left out of the choice because PyPI's entry
for it was not valid; it only narrows the choice, so report it. A network
failure (`[download-network-failed]`, `[download-timeout]`) is for the user to
retry; do not retry in a loop.
