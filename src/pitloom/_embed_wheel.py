# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""ZIP archive manipulation and PEP 770 embedding for wheel files.

See also:
- :mod:`pitloom.embed` for full SBOM generation and embed coordination.
- :mod:`pitloom._wheel_sbom_location` for locating an *already*-embedded
  SBOM (read-only, shared with `verify-wheel`/`validate-wheel`) -- this
  module is about *writing* a new one.
"""

from __future__ import annotations

import base64
import contextlib
import csv
import dataclasses
import hashlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pitloom._wheel_sbom_location import (
    _find_dist_info_prefix,
    read_wheel_member,
    read_wheel_name_version,
)
from pitloom.core.creation import resolve_source_date_epoch
from pitloom.core.file_names import escape_file_name_part, is_plain_file_name
from pitloom.core.wheel_dist_info import (
    MAX_NAME_CHARS,
    RefusingReader,
    open_wheel_zip,
    refusal,
    refuse_unreadable,
    unreadable_member_error,
    wheel_members,
)
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.logging_config import configure_logging

_DEFAULT_FILE_ATTR = 0o644 << 16
_ZIP_EPOCH_FLOOR = datetime(1980, 1, 1, tzinfo=timezone.utc)


def _resolve_zip_timestamp(
    fallback: tuple[int, int, int, int, int, int] | None = None,
) -> tuple[tuple[int, int, int, int, int, int], bool]:
    """Resolve entry timestamp respecting SOURCE_DATE_EPOCH if set."""
    epoch_dt = resolve_source_date_epoch()
    if epoch_dt is not None:
        clamped = max(epoch_dt, _ZIP_EPOCH_FLOOR)
        return (
            (
                clamped.year,
                clamped.month,
                clamped.day,
                clamped.hour,
                clamped.minute,
                clamped.second,
            ),
            clamped != epoch_dt,
        )
    if fallback is not None:
        if fallback[0] >= 1980:
            return fallback, False
        return (1980, 1, 1, 0, 0, 0), True
    now = datetime.now(timezone.utc)
    return (now.year, now.month, now.day, now.hour, now.minute, now.second), False


def _calculate_record_hash(content: bytes) -> str:
    """Compute base64url SHA-256 digest without trailing padding (PEP 376)."""
    digest = hashlib.sha256(content).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _looks_like_pitloom_sbom(content: bytes) -> bool:
    """Check whether an SPDX 3 JSON-LD payload was created by Pitloom."""
    try:
        doc = json.loads(content)
    except (ValueError, UnicodeDecodeError):
        return False
    graph = doc.get("@graph") if isinstance(doc, dict) else None
    if not isinstance(graph, list):
        return False
    return any(
        isinstance(node, dict)
        and node.get("type") in ("Tool", "SoftwareAgent")
        and node.get("name") == "Pitloom"
        for node in graph
    )


def _update_record_lines(
    record_text: str,
    sbom_arcname: str,
    sbom_hash: str,
    sbom_size: int,
    dist_info_prefix: str,
    stale_arcnames: frozenset[str] = frozenset(),
) -> str:
    """Update or insert the SBOM entry in RECORD and ensure RECORD,, is intact."""
    rows: list[list[str]] = []
    reader = csv.reader(io.StringIO(record_text))
    found_sbom = False
    record_arcname = f"{dist_info_prefix}RECORD"

    for row in reader:
        if not row:
            continue
        if row[0] == sbom_arcname:
            rows.append([sbom_arcname, f"sha256={sbom_hash}", str(sbom_size)])
            found_sbom = True
        elif row[0] == record_arcname or row[0] in stale_arcnames:
            continue
        else:
            rows.append(row)

    if not found_sbom:
        rows.append([sbom_arcname, f"sha256={sbom_hash}", str(sbom_size)])

    rows.append([record_arcname, "", ""])

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerows(rows)
    return out.getvalue()


#: Files that sign the ``RECORD`` an embed rewrites: left in, they would sign
#: bytes that no longer exist. Removed, and reported (see
#: :func:`pitloom.cli.commands._embed_wheel_batch.report_embed_result`).
RECORD_SIGNATURES: tuple[str, ...] = ("RECORD.jws", "RECORD.p7s")


@dataclasses.dataclass(frozen=True)
class _EmbedPlan:
    """Everything :func:`embed_sbom_in_wheel` needs to rewrite the archive."""

    sbom_arcname: str
    record_arcname: str
    new_record_bytes: bytes
    stale_arcnames: frozenset[str]
    timestamp: tuple[int, int, int, int, int, int]
    timestamp_floored: bool


def _validate_sbom_filename(filename: str) -> None:
    """Guard against path traversal in an embedded SBOM filename (CWE-22)."""
    if not is_plain_file_name(filename):
        raise ValueError(f"Invalid SBOM filename: {filename!r}")


def _derive_wheel_sbom_filename(
    zf: zipfile.ZipFile,
    dist_info: str,
    identity: tuple[str | None, str | None] | None = None,
    members: list[tuple[str, zipfile.ZipInfo]] | None = None,
) -> str:
    """Derive default SBOM filename from wheel METADATA, or from *identity*,
    the name and version a caller already read from it (no second read, so
    no second warning). Control characters, whitespace, ``/``, ``\\`` and
    ``:`` are replaced in name and version
    (:func:`pitloom.core.file_names.escape_file_name_part`). Where the name
    would exceed ``MAX_NAME_CHARS`` characters (no file system installs
    it), the ``.dist-info`` directory's name is used, as with no name/version."""
    meta_name, meta_version = (
        identity
        if identity is not None
        else read_wheel_name_version(zf, dist_info, members=members)
    )
    if meta_name and meta_version:
        name = escape_file_name_part(meta_name)
        version = escape_file_name_part(meta_version)
        derived = f"{name}-{version}{SPDX3_JSONLD_EXTENSION}"
        if len(derived) <= MAX_NAME_CHARS:
            return derived
    prefix = escape_file_name_part(dist_info.rstrip("/").removesuffix(".dist-info"))
    return (
        f"{prefix}{SPDX3_JSONLD_EXTENSION}"
        if prefix
        else f"sbom{SPDX3_JSONLD_EXTENSION}"
    )


def _read_record(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo | None, archive: str
) -> str:
    """The text of ``RECORD`` (``""`` where the wheel has none).

    Raises:
        ValueError: ``RECORD`` cannot be read, or is not UTF-8.
    """
    if info is None:
        return ""
    try:
        return read_wheel_member(zf, info).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise unreadable_member_error(archive, info.orig_filename, exc) from exc


def _refuse_non_conforming_names(
    archive: str, dist_info: str, members: list[tuple[str, zipfile.ZipInfo]]
) -> None:
    """Refuse a wheel one of whose own ``.dist-info`` members is stored under
    a name that is not its install-location name."""
    for name, info in members:
        if name.startswith(dist_info) and info.orig_filename != name:
            raise refusal(archive, info.orig_filename, "non-conforming name")


def _refuse_signed_wheel(
    archive: str, dist_info: str, members: list[tuple[str, zipfile.ZipInfo]]
) -> None:
    """Refuse a wheel that carries a ``RECORD`` signature: the embed rewrites
    ``RECORD``, so the signature would stop verifying and is removed."""
    names = {name for name, _ in members}
    for signature in RECORD_SIGNATURES:
        if f"{dist_info}{signature}" in names:
            raise refusal(
                archive,
                f"{dist_info}{signature}",
                "embedding rewrites RECORD, so this signature would stop "
                "verifying; --allow-signed-wheel removes it (re-sign the "
                "wheel after)",
            )


def _plan_embed(
    original_zf: zipfile.ZipFile,
    dist_info: str,
    members: list[tuple[str, zipfile.ZipInfo]],
    sbom_filename: str | None,
    sbom_bytes: bytes,
    identity: tuple[str | None, str | None] | None = None,
) -> _EmbedPlan:
    """Resolve target arcname, updated RECORD, and timestamp for an embed.

    *members* are the wheel's
    :func:`~pitloom.core.wheel_dist_info.wheel_members`.

    Raises:
        ValueError: A member of the wheel's own ``.dist-info`` is stored
            under a non-conforming name (``./``, ``\\``): the rewrite matches
            raw names, so it would leave the old ``RECORD`` or SBOM beside
            its replacement, or write ``/`` names next to ``\\`` ones. Or
            ``RECORD`` is not UTF-8.
    """
    archive = os.path.basename(original_zf.filename or "")
    _refuse_non_conforming_names(archive, dist_info, members)
    members_by_name = dict(members)
    target_name = (
        sbom_filename
        if sbom_filename is not None
        else _derive_wheel_sbom_filename(original_zf, dist_info, identity, members)
    )
    _validate_sbom_filename(target_name)
    sbom_arcname = f"{dist_info}sboms/{target_name}"
    record_arcname = f"{dist_info}RECORD"
    stale_arcnames = frozenset(
        name
        for name, info in members_by_name.items()
        if name.startswith(f"{dist_info}sboms/")
        and name.endswith(SPDX3_JSONLD_EXTENSION)
        and name != sbom_arcname
        and _looks_like_pitloom_sbom(read_wheel_member(original_zf, info))
    ) | {
        f"{dist_info}{signature}"
        for signature in RECORD_SIGNATURES
        if f"{dist_info}{signature}" in members_by_name
    }
    record_info = members_by_name.get(record_arcname)
    new_record = _update_record_lines(
        _read_record(original_zf, record_info, archive),
        sbom_arcname,
        _calculate_record_hash(sbom_bytes),
        len(sbom_bytes),
        dist_info,
        stale_arcnames,
    ).encode("utf-8")
    timestamp, timestamp_floored = _resolve_zip_timestamp(
        record_info.date_time if record_info else None
    )
    return _EmbedPlan(
        sbom_arcname=sbom_arcname,
        record_arcname=record_arcname,
        new_record_bytes=new_record,
        stale_arcnames=stale_arcnames,
        timestamp=timestamp,
        timestamp_floored=timestamp_floored,
    )


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _rewrite_wheel_archive(
    wheel_path: Path,
    original_zf: zipfile.ZipFile,
    sbom_arcname: str,
    sbom_bytes: bytes,
    record_arcname: str,
    record_bytes: bytes,
    timestamp: tuple[int, int, int, int, int, int],
    stale_arcnames: frozenset[str] = frozenset(),
) -> Path:
    """Write updated entries to a temporary file."""
    temp_dir = wheel_path.parent
    with tempfile.NamedTemporaryFile(
        dir=temp_dir,
        delete=False,
        prefix=f"{wheel_path.stem}.",
        suffix=".tmp",
    ) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        with zipfile.ZipFile(
            temp_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as new_zf:
            for info in original_zf.infolist():
                if info.filename in (record_arcname, sbom_arcname):
                    continue
                if info.filename in stale_arcnames:
                    continue
                with refuse_unreadable(wheel_path.name, info.orig_filename):
                    source = original_zf.open(info, "r")
                with source, new_zf.open(info, "w") as dst:
                    shutil.copyfileobj(
                        RefusingReader(source, wheel_path.name, info.orig_filename),
                        dst,
                    )

            sbom_info = zipfile.ZipInfo(sbom_arcname, date_time=timestamp)
            sbom_info.compress_type = zipfile.ZIP_DEFLATED
            sbom_info.external_attr = _DEFAULT_FILE_ATTR
            new_zf.writestr(sbom_info, sbom_bytes)

            rec_info = zipfile.ZipInfo(record_arcname, date_time=timestamp)
            rec_info.compress_type = zipfile.ZIP_DEFLATED
            rec_info.external_attr = _DEFAULT_FILE_ATTR
            new_zf.writestr(rec_info, record_bytes)

        return temp_path
    except BaseException:
        with contextlib.suppress(OSError):
            temp_path.unlink(missing_ok=True)
        raise


def embed_sbom_in_wheel(
    wheel_path: Path | str,
    sbom_content: str | bytes,
    *,
    sbom_filename: str | None = None,
    identity: tuple[str | None, str | None] | None = None,
    allow_signed_wheel: bool = False,
) -> tuple[Path, str, tuple[str, ...], bool]:
    """Embed an SPDX 3 SBOM into a built wheel archive (PEP 770).

    A wheel carrying ``RECORD.jws``/``RECORD.p7s`` is refused unless
    *allow_signed_wheel*: the embed rewrites ``RECORD``, so the signature
    would no longer verify, and it is removed (the removed names are in the
    result, as for a stale SBOM).

    *identity* is the wheel's declared (name, version), where the caller has
    already read them from its ``METADATA``: the default file name is made
    from it, and ``METADATA`` is not read, or warned about, again.

    Raises:
        FileNotFoundError: *wheel_path* doesn't exist.
        ValueError: *sbom_content* is empty, or the wheel's content is bad
            (missing/ambiguous ``.dist-info``), or the wheel is refused
            (:class:`~pitloom.core.wheel_dist_info.WheelRefused`): not a ZIP
            archive, a member cannot be read (damaged, encrypted,
            unsupported, badly named), two members have one name or one
            holds a NUL, or a member of its own ``.dist-info`` has a
            non-conforming name, or it is signed and not *allow_signed_wheel*.
            The wheel is left as it was.
        OSError: An environment problem opening *wheel_path* (permission
            denied, a transient I/O error) -- kept as its own exception
            type, not folded into ``ValueError``.
    """
    configure_logging()
    wheel_obj = Path(wheel_path).resolve()
    if not wheel_obj.exists():
        raise FileNotFoundError(f"Wheel file not found: {wheel_obj}")

    sbom_bytes = (
        sbom_content.encode("utf-8") if isinstance(sbom_content, str) else sbom_content
    )
    if not sbom_bytes.strip():
        raise ValueError("SBOM content cannot be empty")

    orig_mode = wheel_obj.stat().st_mode if wheel_obj.exists() else None

    with open_wheel_zip(wheel_obj) as original_zf:
        members = wheel_members(original_zf, wheel_obj.name)
        dist_info = _find_dist_info_prefix(original_zf, wheel_obj, members=members)
        if not allow_signed_wheel:
            _refuse_signed_wheel(wheel_obj.name, dist_info, members)
        plan = _plan_embed(
            original_zf, dist_info, members, sbom_filename, sbom_bytes, identity
        )
        temp_path = _rewrite_wheel_archive(
            wheel_obj,
            original_zf,
            plan.sbom_arcname,
            sbom_bytes,
            plan.record_arcname,
            plan.new_record_bytes,
            plan.timestamp,
            plan.stale_arcnames,
        )

    try:
        os.replace(temp_path, wheel_obj)
        if orig_mode is not None:
            try:
                os.chmod(wheel_obj, orig_mode)
            except OSError:
                pass
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return (
        wheel_obj,
        plan.sbom_arcname,
        tuple(sorted(plan.stale_arcnames)),
        plan.timestamp_floored,
    )
