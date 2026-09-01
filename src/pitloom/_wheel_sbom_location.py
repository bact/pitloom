# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Locate an SBOM already embedded in a built wheel (PEP 770,
``.dist-info/sboms/``) -- read-only, format-neutral.

Shared by every command that needs to find where a wheel's SBOM lives,
not just the ones that write one: :func:`pitloom._embed_wheel.embed_sbom_in_wheel`
uses :func:`_find_dist_info_prefix` to plant a *new* entry; `verify-wheel`/
`validate-wheel` (`pitloom.cli.commands.verify_wheel`/`validate_wheel`) use
:func:`find_embedded_sbom` to read an *existing* one. See also
:mod:`pitloom._sbom_format` for format detection once an entry's bytes are
in hand.
"""

from __future__ import annotations

import dataclasses
import zipfile
from pathlib import Path


def _open_wheel_zip(wheel_path: Path) -> zipfile.ZipFile:
    """Open *wheel_path* for reading as a ZIP archive.

    Any non-``OSError`` exception (bad ZIP, unsupported feature) is
    normalized to ``ValueError`` -- caught generically so a future
    ``zipfile`` failure mode is normalized too, not left to leak its own
    type. ``OSError`` (missing file, permission denied, transient I/O)
    propagates unchanged, so a caller can retry it without string-matching
    a folded-in message. Scoped to this constructor call only -- an error
    from reading an entry afterward keeps its own exception type.
    """
    try:
        return zipfile.ZipFile(wheel_path, "r")
    except OSError:
        raise
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        raise ValueError(f"Invalid wheel archive {wheel_path.name}: {exc}") from exc


def _find_dist_info_prefix(zf: zipfile.ZipFile, wheel_path: Path) -> str:
    """Find the single .dist-info directory prefix in the wheel ZIP archive."""
    dist_infos: set[str] = set()
    for name in zf.namelist():
        parts = name.split("/")
        if len(parts) >= 2 and parts[0].endswith(".dist-info"):
            dist_infos.add(f"{parts[0]}/")

    if not dist_infos:
        raise ValueError(
            f"Invalid wheel archive {wheel_path.name}: no .dist-info directory found"
        )
    if len(dist_infos) > 1:
        stem_prefix = wheel_path.stem.split("-")[0]
        matching = [
            d
            for d in dist_infos
            if d.startswith(f"{stem_prefix}-") or d == f"{stem_prefix}.dist-info/"
        ]
        if len(matching) == 1:
            return matching[0]
        raise ValueError(
            f"Invalid wheel archive {wheel_path.name}: multiple .dist-info "
            f"directories found ({sorted(dist_infos)})"
        )
    return next(iter(dist_infos))


@dataclasses.dataclass(frozen=True)
class EmbeddedSbomLocation:
    """A wheel's embedded SBOM, located under ``.dist-info/sboms/``."""

    arcname: str
    data: bytes


def find_embedded_sbom(
    wheel_path: Path, sbom_basename: str | None = None
) -> EmbeddedSbomLocation | None:
    """Locate the SBOM embedded in *wheel_path* under ``.dist-info/sboms/``.

    Format-neutral: only checks the PEP 770 packaging location, not the
    embedded file's content. Returns ``None`` when nothing is found
    (*sbom_basename* given but absent, or no ``sboms/`` entries at all).

    Raises:
        ValueError: The wheel's *content* is bad -- not a valid ZIP archive
            or an unparseable one (see :func:`_open_wheel_zip`), missing/
            ambiguous ``.dist-info`` (see :func:`_find_dist_info_prefix`),
            or *sbom_basename* is unset and more than one file exists
            under ``sboms/`` (ambiguous -- caller must disambiguate
            explicitly).
        OSError: An *environment* problem reading *wheel_path* (missing
            file, permission denied, a transient I/O error) -- kept as
            its own exception type rather than folded into ``ValueError``
            (see :func:`_open_wheel_zip`), so a caller can distinguish
            "this wheel is bad" from "try again."
    """
    with _open_wheel_zip(wheel_path) as zf:
        dist_info = _find_dist_info_prefix(zf, wheel_path)
        sboms_prefix = f"{dist_info}sboms/"
        if sbom_basename is not None:
            arcname = f"{sboms_prefix}{sbom_basename}"
            if arcname not in zf.namelist():
                return None
            return EmbeddedSbomLocation(arcname=arcname, data=zf.read(arcname))

        candidates = [
            name
            for name in zf.namelist()
            if name.startswith(sboms_prefix)
            and name != sboms_prefix
            # Direct children of sboms/ only -- a nested entry like
            # sboms/extra/notes.txt isn't itself an embedded SBOM and
            # shouldn't trigger a false "multiple SBOMs" ambiguity.
            and "/" not in name[len(sboms_prefix) :]
        ]
        if not candidates:
            return None
        if len(candidates) > 1:
            raise ValueError(
                f"Multiple SBOMs found under {sboms_prefix} in {wheel_path.name} "
                f"({sorted(candidates)}) -- pass --sbom-basename to disambiguate"
            )
        arcname = candidates[0]
        return EmbeddedSbomLocation(arcname=arcname, data=zf.read(arcname))
