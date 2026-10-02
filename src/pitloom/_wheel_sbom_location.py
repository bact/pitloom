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
import email.message
import logging
import os
import zipfile
from pathlib import Path

from pitloom.core.wheel_dist_info import (
    PROBLEM_NONE,
    open_wheel_zip,
    read_metadata_headers,
    refusal,
    refuse_unreadable,
    resolve_own_dist_info,
    wheel_members,
)

log = logging.getLogger(__name__)


def _find_dist_info_prefix(
    zf: zipfile.ZipFile,
    wheel_path: Path,
    *,
    report: bool = False,
    members: list[tuple[str, zipfile.ZipInfo]] | None = None,
) -> str:
    """The wheel's own ``.dist-info`` prefix, as
    :func:`pitloom.core.wheel_dist_info.resolve_own_dist_info` selects it
    from :func:`~pitloom.core.wheel_dist_info.wheel_members` -- the member
    list :func:`pitloom.extract.wheel.read_wheel` selects from, so the two
    cannot name different directories for one wheel.

    *report* logs one ``WARNING:`` where the file name names no
    ``.dist-info`` of the wheel and another is used; a caller that has
    already read the wheel (``read_wheel`` says so) leaves it off. *members*
    is the wheel's :func:`~pitloom.core.wheel_dist_info.wheel_members`, where
    the caller has them already.

    Raises:
        ValueError: The wheel has no top-level ``.dist-info``, or several
            and not exactly one named by its file name, or two members
            share a name or one holds a NUL.
    """
    if members is None:
        members = wheel_members(zf, wheel_path.name)
    choice = resolve_own_dist_info(wheel_path.name, [name for name, _ in members])
    if choice.prefix is not None:
        if report and choice.problem:
            log.warning("ARCHIVE=%r: %s", wheel_path.name, choice.problem)
        return choice.prefix
    raise refusal(wheel_path.name, None, choice.problem or PROBLEM_NONE)


def read_wheel_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    """Member *info*'s bytes; an unreadable one refuses the wheel."""
    with refuse_unreadable(os.path.basename(zf.filename or ""), info.orig_filename):
        return zf.read(info)


@dataclasses.dataclass(frozen=True)
class EmbeddedSbomLocation:
    """A wheel's embedded SBOM, located under ``.dist-info/sboms/``."""

    arcname: str
    data: bytes


def name_version_from_email_message(
    msg: email.message.Message,
) -> tuple[str | None, str | None]:
    """Pull ``Name``/``Version`` out of an already-parsed METADATA message.

    The single source of truth for "what does the wheel declare as its own
    name/version" -- shared by :func:`read_wheel_name_version` below and by
    :func:`pitloom.extract.wheel._populate_metadata_from_email`, so the two
    can't silently disagree on this specific extraction (they still differ
    on what a *missing* header defaults to downstream: this function always
    returns ``None``, while `ProjectMetadata.name` separately defaults to
    the sentinel ``"unknown"`` when nothing overwrites it).
    """
    return msg.get("Name"), msg.get("Version")


def read_wheel_name_version(
    zf: zipfile.ZipFile,
    dist_info: str,
    *,
    members: list[tuple[str, zipfile.ZipInfo]] | None = None,
    report: bool = True,
) -> tuple[str | None, str | None]:
    """Read ``Name``/``Version`` from *dist_info*'s ``METADATA`` entry.

    Returns ``(None, None)`` if the entry is absent, or its headers are over
    a cap (see :func:`pitloom.core.wheel_dist_info.read_metadata_headers`:
    one ``WARNING:``, none with *report* false); either element may
    independently be ``None`` if the corresponding header is missing.

    Shared by :func:`pitloom._embed_wheel._derive_wheel_sbom_filename`
    (default-filename derivation) and `verify-wheel`'s name/version
    cross-check, so the two parses can't silently diverge.

    Raises:
        ValueError: The entry cannot be read (damaged, encrypted), two
            members of the wheel have one name, or a name holds a NUL.
    """
    archive = os.path.basename(zf.filename or "")
    if members is None:
        members = wheel_members(zf, archive)
    msg = read_metadata_headers(zf, members, dist_info, archive, report=report)
    return (None, None) if msg is None else name_version_from_email_message(msg)


def read_wheel_name_version_from_path(
    wheel_path: Path, *, report: bool = False
) -> tuple[str | None, str | None]:
    """Open *wheel_path*, resolve its ``.dist-info`` prefix, and read
    ``Name``/``Version`` from its ``METADATA`` entry -- the "just tell me
    the wheel's declared name/version" convenience both `verify-wheel`
    (`_check_one_wheel`) and `embed-wheel --verify`
    (`_warn_on_name_version_mismatch`) need, so the
    open/resolve-dist-info/read triplet isn't hand-copied at each call
    site. See :func:`read_wheel_name_version` for the lower-level,
    already-open-``ZipFile`` variant this wraps (used where a caller
    already has one open for another reason, e.g. `find_embedded_sbom`).
    *report* is :func:`_find_dist_info_prefix`'s, and also says whether a
    ``METADATA`` that cannot be read is warned about: a caller that reports
    the wheel's identity itself leaves it off.
    """
    with open_wheel_zip(wheel_path) as zf:
        members = wheel_members(zf, wheel_path.name)
        dist_info = _find_dist_info_prefix(
            zf, wheel_path, report=report, members=members
        )
        return read_wheel_name_version(zf, dist_info, members=members, report=report)


def find_embedded_sbom(
    wheel_path: Path, sbom_filename: str | None = None
) -> EmbeddedSbomLocation | None:
    """Locate the SBOM embedded in *wheel_path* under ``.dist-info/sboms/``.

    Format-neutral: only checks the PEP 770 packaging location, not the
    embedded file's content. Returns ``None`` when nothing is found
    (*sbom_filename* given but absent, or no ``sboms/`` entries at all).

    Raises:
        ValueError: The wheel's *content* is bad -- refused as a whole
            (:class:`~pitloom.core.wheel_dist_info.WheelRefused`: not a ZIP
            archive, a member that cannot be read, a duplicate or NUL name),
            missing/ambiguous ``.dist-info`` (see :func:`_find_dist_info_prefix`),
            or *sbom_filename* is unset and more than one file exists
            under ``sboms/`` (ambiguous -- caller must disambiguate
            explicitly).
        OSError: An *environment* problem reading *wheel_path* (missing
            file, permission denied, a transient I/O error) -- kept as
            its own exception type rather than folded into ``ValueError``
            (see :func:`pitloom.core.wheel_dist_info.open_wheel_zip`), so a
            caller can distinguish "this wheel is bad" from "try again."
    """
    with open_wheel_zip(wheel_path) as zf:
        listed = wheel_members(zf, wheel_path.name)
        dist_info = _find_dist_info_prefix(zf, wheel_path, members=listed)
        sboms_prefix = f"{dist_info}sboms/"
        members = dict(listed)
        if sbom_filename is not None:
            arcname = f"{sboms_prefix}{sbom_filename}"
            if arcname not in members:
                return None
            return EmbeddedSbomLocation(
                arcname=arcname, data=read_wheel_member(zf, members[arcname])
            )

        candidates = [
            name
            for name in members
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
                f"({sorted(candidates)}) -- pass --sbom-filename to disambiguate"
            )
        arcname = candidates[0]
        return EmbeddedSbomLocation(
            arcname=arcname, data=read_wheel_member(zf, members[arcname])
        )
