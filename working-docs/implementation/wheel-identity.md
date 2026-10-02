---
Created: 2026-10-01
Last-Modified: 2026-10-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Wheel identity: implementation notes

See also: [archive-member-names.md](archive-member-names.md) (the member
names every wheel reader shares),
[wheel-embedding.md](wheel-embedding.md) (the embed flow),
[ai-model-scanning.md](ai-model-scanning.md) (the model scan skips the
wheel's own `.dist-info`),
[id-registry-followups.md](../design/id-registry-followups.md) (the
alternative to D2 below).

## Why

Registry v3 keys a package by name and version. For a wheel both come from
`read_wheel()`, so a wrong identity there is a wrong registry key on every
surface (`loom wheel`, `generate x.whl`, `wheel --embed`, `embed-wheel`,
`generate_wheel_sbom()`, `embed_wheel_sbom()`).

Real wheels (126 distinct local ones): every one has exactly one top-level
`.dist-info`, matching its file name after PEP 503 normalisation. Five carry
a vendored `METADATA`; `setuptools-82/83/84` were read as `zipp 3.23.0`
because `read_wheel` took the last `*.dist-info/METADATA` at any depth.

## Three rules became one

`read_wheel` (any depth, last wins), `_find_dist_info_prefix` (top level;
several: raw `startswith` on the file name's first segment) and the model
scan (top level, PEP 427 file name, PEP 503/440) now share
`pitloom.core.wheel_dist_info`. Only a top-level directory can be the
wheel's own. The scan keeps skipping exactly the directories the file name
names (`matching_dist_infos`), so a foreign `.dist-info` cannot hide a model.

## Decisions

- **D1** The file name names the directory (PEP 503 name, PEP 440 version).
  Where it names none: the only top-level `.dist-info`, silently when the
  file name is not a wheel name, with one `WARNING:` when it is and names
  another; none, or several: no metadata, one `WARNING:`. No user option:
  pip refuses a mismatched wheel, and an option would let users switch off
  the warning for a case never seen.
- **D2** A member that cannot be read (`MEMBER_READ_ERRORS`: damaged
  stream, bad CRC, encryption, unsupported compression, a name that is not
  UTF-8) refuses the whole wheel with one `ValueError`
  (`ARCHIVE=... ENTRY=...: could not read (<exception type>) -- wheel
  refused`; the type is bare for a builtin, qualified otherwise
  (`zlib.error`); exception text is never quoted). The CLI prints one
  `ERROR:`, exit 1, nothing written (a `wheel --embed -o` copy included: it
  is written after the embed); in an `embed-wheel` or `verify-wheel` batch
  the other wheels are still processed, exit 1. A member name that is not
  UTF-8 in the central directory fails `zipfile.ZipFile()` itself: the same
  shape without `ENTRY=`. Rejected: keep the file
  without a hash (the SBOM builder, the registry's (path, sha256) key and
  the Merkle root all assume a digest) and skip it (claims it is absent).
  The same guard covers `embed-wheel`'s rewrite and its `RECORD`/SBOM
  reads (a `RECORD` that is not UTF-8 too), `verify-wheel`'s `METADATA` and
  embedded-SBOM reads, `validate-wheel`'s embedded-SBOM read.
- **D3** `METADATA` is read for its headers only: reading stops at the first
  blank line, and the block is capped at 16 MiB (`MAX_METADATA_BYTES`, its
  own constant: real `METADATA` embeds READMEs) and 10,000 headers
  (`MAX_METADATA_HEADERS`). A byte cap alone did not bound memory: a 28 KB
  wheel inflating to 16 MiB of `X-A: b` lines is 2.4 million parsed headers,
  about 700 MB. Over a cap: one `WARNING:`, identity unknown, files still
  listed. The declared size is not trusted; the description after the
  headers may be any size. One function (`read_metadata_headers`) serves
  every `METADATA` reader. The identity `embed_wheel_sbom()` and `wheel
  --embed` already read (`wheel_identity()`, from `read_wheel`'s provenance)
  goes down to the embed (`identity=`), so it is not read and warned about
  twice; `embed-wheel --verify` and `verify-wheel` pass `report=` to say
  whether a `METADATA` that cannot be read is warned about (once per run).
- **DUP** A wheel holding one member name twice, exactly or once normalised
  (`a/M` and `a\M`), is refused (`ARCHIVE=... ENTRY=...: duplicate member
  name -- wheel refused`) by `wheel_members()`, which every wheel reader goes
  through. Warn-and-keep-the-last (`zip_file_members()`'s default, kept for
  sdists and `--allow-build`) let two readers disagree on one wheel: a
  `\METADATA` after the real one reported `evil 9` and was embedded.
- **One name list** Every reader picks the `.dist-info` from the same list
  (`wheel_members()`: names normalised, directory entries dropped). A raw
  `namelist()` counted an empty `extra.dist-info/` directory entry as a
  dist-info and a `\` name as not one, so `read_wheel` and the embed named
  different directories. `embed-wheel` refuses a wheel whose own `.dist-info`
  has a non-conforming member name (`./`, `\`): the rewrite matches raw
  names, so it would leave the old `RECORD` beside the new, or write `/`
  names next to `\` ones.
- **File name and directory name** The file name is parsed for name and
  version only (`wheel_name_version()`): `packaging`'s `parse_wheel_filename`
  also validates the tags, and 26.3 rejects tags 26.2 accepted, so the chosen
  directory would depend on the installed release. A directory matches when
  any `-` splits it into the canonical name and the version
  (`foo-bar-1.0`; `1-2` is `1.post2`). A wheel with no or several `.dist-info`
  is refused with the shared `PROBLEM_*` text, by every reader.
- **Cost** Each open wheel's member list is made once and passed down;
  directory ancestors are collected walking up and stopping at a known one
  (2000 members 1 to 2000 directories deep took 20 s, in the square of the
  depth).
- **verify-wheel** logs the D1 problem (it chose by `.dist-info`, not file
  name); the embed paths do not, as `read_wheel` already did. A refused
  wheel is one `ERROR:` and the batch goes on.
- **D1 wording** Several directories all matching the file name, a file name
  that is not a wheel name, and several none matching have their own text;
  none ends `; metadata not read`, which the AI-model skills read as a model
  bound (`... identity unknown` instead).

## Also changed

`read_wheel` sorts its files by `distribution_path`, as `get_wheel_files`
does: SPDX ids are minted in file order, so the same wheel written with its
members in another order gave different ids (present on main).

`--allow-build` reads its freshly built wheel with its own extractor, not
`read_wheel`; an unreadable member there keeps that path's documented
contract (`None` and one `WARNING:`, then static discovery).
