---
Created: 2026-11-10
Last-Modified: 2026-11-13
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
  `http://`, a URL with a user name or password, another page of `pypi.org`,
  `pypi.python.org` and another index (`test.pypi.org`, any `*.pypi.org`) are
  `[pypi-url-invalid]` with their own lines, never cloned as Git; a redirect
  or file URL on another host is `[url-unsafe]`. A direct link to a file on
  `files.pythonhosted.org` is refused too (`URL=<url>: a file link is not
  read yet; give the project or release page
  https://pypi.org/project/<name>/<version>/` `[pypi-url-invalid]`): offer
  the release page the file belongs to (the name and version in the file
  name), and ask before running it. Do not fetch the target for the user.
- A SHA-256 that differs from the declared one is `[digest-invalid]`: nothing
  is read. Tell the user the file may have been altered; suggest running
  again, and reporting it to PyPI if it repeats.
- Nothing from the download is run (no build, no `setup.py`);
  `--allow-build` has no effect (a `WARNING:` says so) and an sdist's own
  `[tool.pitloom]` is ignored (`--config FILE` applies). `--offline` is an
  error (`[offline-unusable]`, as for a Git URL), and `loom wheel <url>
  --embed` is refused.
- The file is capped at 512 MiB (`--max-download-bytes BYTES`, or
  `max-download-bytes` in a `--config` file). A larger one is
  refused with `FILE=<file>: ... ; not downloaded [over-cap]` and no SBOM. Tell the
  user about the flag and what it costs (disk, time, a hostile file); do not
  raise it for them (non-interactively, report only). The same setting caps a
  Git URL's checkout (`git-url.md`); on any other target the flag warns that
  it has no effect.
- AI models in the downloaded wheel are gated as a Git URL's are: fastText,
  GGUF, HDF5, ONNX and PyTorch `.pt`/`.pth` models are listed with name,
  format and hash only, with one `INFO: FILE=<file>: AI models in these
  formats are listed without metadata ... [reader-unsafe/remote]`. Relay it;
  offer, never add unasked, `--trust-model-files` for a release the user
  trusts. `loom project <url>` does not scan the sdist for models (as for a
  local sdist), so the flag warns there that it has no effect.
- The output is named as for a local file (`<wheel file name>.spdx3.json` for
  `loom wheel`, `<name>-<version>.spdx3.json` for `loom project`). No
  temporary path is in the SBOM or a message (`<download>` stands for it).

## What the SBOM records

The SBOM is the local file's, plus one provenance annotation on the main
package: the project page, the file's URL, the SHA-256 measured from the
bytes (`Evidence: measured_read`) and the one PyPI declared (`Evidence:
declared`), the version (a pinned URL: `Source: PyPI JSON API | Value: 1.0.0`,
plus `| Normalized-From: 1.0` if the URL spelled it differently; an unpinned
one: `Method: latest-release`), the status when it is a pre-release or yanked,
and for a wheel its tags and how many other compatible wheels were skipped
(`Method: running-environment`). SPDX 3 has no property for these, so they are
provenance text (a gap Pitloom tracks for SPDX): an `Annotation` on the main
package (JSON, schema `https://pitloom.dev/provenance/fields/1`) and, with the
default format, the same entries in the package's `comment` after `Metadata
provenance:`. Read them to explain why this wheel; never edit them. The
declared requirements (`Requires-Dist`) are listed, not a resolved environment.

How to read the record to the user:

- `sha256` (`measured_read`) is the digest of the bytes Pitloom received;
  `sha256_declared` (`declared`) is what PyPI says it is. They are equal in
  every SBOM that exists (a mismatch is refused), so equal values are the
  normal case, not a finding. Neither is a hash property: the archive's digest
  is only here (the main package's `verifiedUsing` is a Merkle root over a
  wheel's payload files, and absent on an sdist).
- `release_version` with `Method: latest-release` means the URL named no
  version; `Normalized-From` means the URL's spelling differed (`1.0` for
  `1.0.0`). `release_status` `prerelease` or `yanked` is a fact about the
  release, not a defect of the SBOM; a yanked release is the user's choice to
  rely on.
- `wheel_tags` and `compatible_wheels_skipped` (`Method:
  running-environment`) explain why this wheel: the pick follows the Python
  and platform Pitloom ran on, so the SBOM of one URL differs per platform and
  per Python. Say so when the SBOM is shared or compared, and do not call a
  different payload on another platform a bug. An sdist SBOM does not depend
  on the platform.
- `download_location` and `project_url` are provenance text, not SPDX
  `downloadLocation`.

## Messages to relay

Find each code above in `messages.md`, read the page it links (`messages-pypi.md`
for most; `over-cap`, `url-unsafe` and the download codes are on others) and
relay its advice. A
`WARNING: PYPI=<name> FILE=<file>: ...; skipped` (`[pypi-response-invalid]`)
means a file of the release was left out of the choice because PyPI's entry
for it was not valid; it only narrows the choice, so report it. A network
failure (`[download-network-failed]`, `[download-timeout]`) is for the user to
retry; do not retry in a loop.

## Follow-ups: enrich, validate and combined asks

- **Validate** (`sbom-validate`): the SBOM is an ordinary SPDX 3 document;
  `loom fragment validate FILE` applies. A pass says nothing about completeness.
  `loom verify-wheel`, `validate-wheel` and `embed-wheel` take a local `.whl`
  file only, not a PyPI URL; to check a wheel's own embedded SBOM the user must
  have the wheel on disk (do not download it unasked).
- **Enrich** (`sbom-enrich`): `--enrich` and the lock-file, header and
  content-type flags have no effect on a PyPI URL (a `WARNING: Options:` line
  each): do not add them. The base is a wheel or sdist SBOM, so a fragment is
  never merged into it (`sbom-enrich`, "Where a fragment can be merged");
  the downloaded file is gone, so prose from the project means fetching again,
  which needs the user's consent.
- **Combined asks** ("generate an SBOM for https://pypi.org/project/x/ and
  validate it", "...and check it against CISA 2026"): generate with the
  command the ask implies (wheel unless it says sdist), then `sbom-validate`;
  for a named standard run `sbom-enrich`'s "Complete a standard's minimum
  elements" up to the gap report and hand over any drafted fragment unmerged.
  The reverse (asked to check or enrich "the SBOM of https://pypi.org/project/x/"
  with no file): `sbom-enrich`/`sbom-validate` hand back here to generate first.
- **Ask or fall back.** Which platform's wheel, whether to take the sdist after
  `[release-file-not-found...]`, whether to rely on a yanked release, or
  whether to raise `--max-download-bytes` are the user's call: ask; with nobody
  to ask, report the line and the command it names, and run nothing else.
