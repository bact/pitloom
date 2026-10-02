---
Created: 2026-10-02
Last-Modified: 2026-10-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: package identity and archives

See also: [README.md](README.md) (index of these notes),
[wheel-identity.md](../wheel-identity.md),
[archive-member-names.md](../archive-member-names.md),
[wheel-embedding.md](../wheel-embedding.md),
[ai-model-scan-security-lessons.md](../ai-model-scan-security-lessons.md)
sections 3.3 (archives inside archives) and 3.8 (wheel identity bugs).

## 1. Package identity

- **Version equality is PEP 440, not string and not SemVer.**
  `Version("1.0") == Version("1.0.0") == Version("1.0.0.0")`, and
  `Version("1-2")` is `1.post2`. Two entries for one name in a lock file
  (one per marker branch) with `1.0` and `1.0.0` are the same release,
  not a conflict to warn about and drop. Prose must say "PEP 440
  equality": a reader hears "same version" as "compatible range"
  ([recurring-bug-patterns.md](../recurring-bug-patterns.md)).
  Do: compare every version through the ecosystem's parser, never `==`
  on strings.
- **Names are compared after PEP 503 canonicalisation.**
  `canonicalize_name("Foo.Bar_baz")` is `foo-bar-baz`. In a survey of 126
  distinct real wheels, 49 needed this normalisation for the file name to
  match its own `.dist-info` directory (`license_matcher-2.11.dist-info`
  inside `license-matcher-...whl`) (#266).
  Do: canonicalise both sides before any equality test or dict key.
- **A `.dist-info` directory name splits at any dash.** `foo-bar-1.0`
  has a hyphenated name, so the split point is not the first or last `-`;
  try each split that gives the canonical name plus a parseable version.
  Trying every dash is quadratic: a 64,000-dash name took 9 s, five of
  them in a 600 KB wheel 103 s. Pitloom caps the stem at 255 characters
  (one path component) before trying (#266).
  Do: bound any "try every split" by the longest legal value first.
- **Parse only the fields you need from a file name.** `packaging`'s
  `parse_wheel_filename` also validates the platform tags, and
  `packaging` 26.3 rejects tags 26.2 accepted, so the `.dist-info` chosen
  would have depended on which `packaging` release was installed. Pitloom
  parses name and version only, with its own rule (#266).
  Do: keep identity selection independent of a validating library's
  release.
- **Identity comes from the top-level `.dist-info` only.** Vendored
  libraries ship their own `METADATA`; setuptools 82-84 were reported as
  `zipp 3.23.0`. Numbers and the selector are in the lessons doc, 3.8
  (#266).
  Do: anchor "which metadata is mine" to the archive root and the file
  name, never "any member ending `METADATA`".
- **A URL requirement never yields a version.** `name @ https://.../
  archive/refs/tags/v2.31.0.zip` and pip's legacy `git+https://...#egg=x`
  look release-shaped, but PEP 508 defines a direct reference with no
  PEP 440 version; a tag may be `v2.31.0`, `stable` or anything. The legacy
  forms are not valid PEP 508 at all (`InvalidRequirement`). Every lock
  format skips path, VCS and URL entries the same way
  ([lock-file-cascade.md](../lock-file-cascade.md)).
  Do: report a direct reference as one, never derive a version from a URL.
- **An explicit pin beats the generator's own environment.** A version
  pinned by its own source (a lock file, an exact `==`/`===`) is final;
  introspecting the environment the generator runs in says nothing about
  the target project's. Environment data is a fallback for the unpinned
  case only (AGENTS.md design principle).
  Do: never let `importlib.metadata` of the tool's own process override a
  pin.
- **A lock hash describes one artifact, so check the version first.**
  A declared exact pin can override a conflicting locked version; the
  lock's SHA-256 then describes a different artifact. The direct
  dependency takes the lock hash only when its resolved version
  PEP 440-equals the locked one. A lock hash always beats a PyPI lookup,
  even online: the lock names what was really resolved (#212).
  Do: tie every hash to the exact (name, version) it was recorded for.

## 2. ZIP and tar realities

- **`ZipInfo.filename` depends on the OS that reads the archive.**
  CPython's `ZipInfo.__init__` replaces `os.sep` with `/` only where
  `os.sep != "/"`, so a member stored as `pkg\mod.py` reads as
  `pkg/mod.py` on Windows and `pkg\mod.py` on macOS and Linux (checked on
  macOS: both `filename` and `orig_filename` keep the backslash). One
  wheel, two SBOMs. `orig_filename` is unconverted on every OS (#251).
  Do: read `orig_filename`, then apply your own documented policy.
- **Pick one reading of `\` and apply it everywhere.** pip on POSIX
  installs `pkg\x` as one file named `pkg\x`; Windows sees a directory.
  Pitloom chose the Windows reading (`\` is a separator) so one archive
  gives one SBOM on every OS, and warns once per member:
  `ARCHIVE='x.whl' ENTRY='pkg\\mod.py': non-conforming name -- recorded
  as 'pkg/mod.py'` (#251).
  Do: make member-name normalisation one shared helper used by every
  reader.
- **Unsafe names are skipped, not rewritten.** A leading `/` (and UNC
  `//host`), a first segment with a drive (`C:`; also `a:b.py`, which is
  drive-relative on Windows), any `..` segment, a NUL, or nothing left
  after dropping empty and `.` segments. Kept, `../x` became a directory
  element named `..` and a registry key; rewritten, it would show a legal
  path the archive never installs to. pip and `installer` refuse such a
  wheel anyway (#251).
  Do: skip with one `WARNING:`; never invent an install location.
- **A file can also be a directory.** `pkg` plus `pkg/mod.py` in one
  archive: no installer can write both, and keeping both gave two SPDX
  elements named `pkg`, and failed extraction for `--allow-build`. The
  file is skipped (#251).
  Do: check every file name against the set of directory prefixes.
- **Directory detection differs by archive type.** `ZipInfo.is_dir()`
  reads `filename`, so `pkg\` was a directory on Windows only; `tarfile`
  retypes only a trailing `/`, so a regular tar member `pkg\` stayed a
  file. Pitloom decides from the raw name (ends in `/`, `\` or a `.`
  segment) and warns when a directory entry carries data (#251).
  Do: decide directory-ness from the raw name, in one place.
- **`./` is normal in tar, not in a wheel.** `tar -C dir -czf x .` writes
  `./pkg/...`, so one leading `./` in an sdist is dropped silently; a
  wheel has no such convention and warns (#251).
  Do: keep per-format conventions explicit rather than one lenient rule.
- **Duplicate names: the policy depends on what the archive is for.**
  Wheels are refused (`duplicate member name -- wheel refused`): two
  readers keeping different copies is how a scanner and an installer see
  different files. Sdists and build output keep the last, as unpacking
  in archive order would (#251, #266; NUL-truncated names are duplicates
  too, see the lessons doc 3.8).
  Do: refuse duplicates in anything an installer will consume.
- **A damaged member raises many exception types.** A corrupt deflate
  stream raises `zlib.error`; also `BadZipFile` (bad CRC), `EOFError`,
  `lzma.LZMAError`, `RuntimeError` (encrypted), `NotImplementedError`
  (compression method). Catching `BadZipFile` and `UnicodeDecodeError`
  only aborted a whole `verify-wheel` batch at a wheel declaring extract
  version 9.2. Pitloom refuses the wheel with one line naming the type
  (`could not read (zlib.error) -- wheel refused`), never quoting the
  exception text, and goes on with the batch (#266).
  Do: keep one tuple of member-read errors and use it at every read.
- **A non-UTF-8 member name fails before any member is read.** With the
  UTF-8 flag set and invalid bytes in the central directory,
  `zipfile.ZipFile()` itself raises; there is no member to name, so the
  message drops `ENTRY=` (#266).
  Do: wrap the archive open as well as each member read.
- **ZIP timestamps have a 1980 floor and 2-second resolution.**
  `ZipInfo(name, (1970, 1, 1, 0, 0, 0))` raises `ValueError: ZIP does not
  support timestamps before 1980`; a second of 59 is stored as 58 (DOS
  time keeps seconds / 2). `ZipInfo`'s default is 1980-01-01 00:00:00.
  `SOURCE_DATE_EPOCH=0` is a legitimate placeholder, so Pitloom floors
  only the ZIP entry, keeps the true value in the SBOM's `created`, and
  says so in one `INFO:` line rather than rewriting the SBOM (#148).
  Do: keep the SBOM's datetime and the container's timestamp separate.
- **An empty ZIP has no local header.** It is the 22-byte end record
  alone, starting `PK\x05\x06` (`np.savez(f)` with no array writes one);
  a sniff for `PK\x03\x04` alone calls it "not a ZIP" (#270).
  Do: accept both signatures when sniffing for a ZIP.
- **Archive sizes and counts lie.** `ZipInfo.file_size`, the declared
  entry count and nested archives are all attacker-controlled; see the
  lessons doc, 3.3, for the measured bombs and the `_EndRecData` fix.
  Do: count bytes as you copy; never trust a declared size.
- **Embedding into a wheel: RECORD is exact.** Each row is
  `<path>,sha256=<urlsafe base64, '=' padding stripped>,<size>`;
  `RECORD` lists itself as `<dist-info>/RECORD,,`. Pitloom writes a
  sibling `.whl.tmp` and `os.replace()`s it, streaming members across,
  and checks the result with `installer`'s `validate_record()` (#148).
  Do: validate with the installer's own checker, not your reader.
- **Find a stale SBOM by content, not by file name.** On re-embed,
  Pitloom removes an earlier SBOM only when its JSON-LD `@graph` names a
  `Tool`/`SoftwareAgent` "Pitloom"; a filename glob would delete another
  tool's SBOM. Each removal is one `INFO:` line (#148).
  Do: delete only what you can prove you wrote, and say so.
- **Member order must not reach identifiers.** `File-N` ids follow list
  order, so the same files zipped in another order gave another SBOM;
  `read_wheel` now sorts by install path (#266). The sdist reader still
  has it; see the lessons doc, 3.6.
  Do: sort archive members by normalised path before minting anything.
