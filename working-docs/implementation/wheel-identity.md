---
Created: 2026-10-01
Last-Modified: 2026-10-01
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
  refused`; exception text is never quoted). The CLI prints one `ERROR:`,
  exit 1, nothing written; in an `embed-wheel` batch the per-wheel contract
  is unchanged (the others are processed, exit 1). Rejected: keep the file
  without a hash (the SBOM builder, the registry's (path, sha256) key and
  the Merkle root all assume a digest) and skip it (claims it is absent).
  The same guard covers `embed-wheel`'s rewrite and its `RECORD`/SBOM
  reads, `verify-wheel`'s `METADATA` and embedded-SBOM reads.
- **D3** `METADATA` is read in 8 KiB chunks up to 16 MiB
  (`MAX_METADATA_BYTES`, its own constant: real `METADATA` embeds READMEs).
  Over the cap: one `WARNING:`, identity unknown, files still listed. The
  declared size is not trusted.

## Also changed

`read_wheel` sorts its files by `distribution_path`, as `get_wheel_files`
does: SPDX ids are minted in file order, so the same wheel written with its
members in another order gave different ids (present on main).

`--allow-build` reads its freshly built wheel with its own extractor, not
`read_wheel`; an unreadable member there keeps that path's documented
contract (`None` and one `WARNING:`, then static discovery).
