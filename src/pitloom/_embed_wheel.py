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
import csv
import dataclasses
import email
import hashlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pitloom._wheel_sbom_location import _find_dist_info_prefix
from pitloom.core.creation import resolve_source_date_epoch
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.logging_config import configure_logging

_DEFAULT_FILE_ATTR = 0o644 << 16
_ZIP_EPOCH_FLOOR = datetime(1980, 1, 1, tzinfo=timezone.utc)
_INVALID_FILENAME_CHARS = frozenset({"/", "\\", "\x00"})


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
    clean = filename.strip()
    if (
        not clean
        or clean in (".", "..")
        or any(c in clean for c in _INVALID_FILENAME_CHARS)
    ):
        raise ValueError(f"Invalid SBOM filename: {filename!r}")


def _derive_wheel_sbom_filename(zf: zipfile.ZipFile, dist_info: str) -> str:
    """Derive default SBOM filename from wheel METADATA."""
    meta_name: str | None = None
    meta_version: str | None = None
    metadata_path = f"{dist_info}METADATA"
    if metadata_path in zf.namelist():
        content = zf.read(metadata_path).decode("utf-8", errors="replace")
        msg = email.message_from_string(content)
        meta_name = msg.get("Name")
        meta_version = msg.get("Version")
    if meta_name and meta_version:
        return f"{meta_name}-{meta_version}{SPDX3_JSONLD_EXTENSION}"
    prefix = dist_info.rstrip("/").removesuffix(".dist-info")
    return (
        f"{prefix}{SPDX3_JSONLD_EXTENSION}"
        if prefix
        else f"sbom{SPDX3_JSONLD_EXTENSION}"
    )


def _plan_embed(
    original_zf: zipfile.ZipFile,
    dist_info: str,
    sbom_filename: str | None,
    sbom_bytes: bytes,
) -> _EmbedPlan:
    """Resolve target arcname, updated RECORD, and timestamp for an embed."""
    target_name = (
        sbom_filename
        if sbom_filename is not None
        else _derive_wheel_sbom_filename(original_zf, dist_info)
    )
    _validate_sbom_filename(target_name)
    sbom_arcname = f"{dist_info}sboms/{target_name}"
    record_arcname = f"{dist_info}RECORD"
    sboms_prefix = f"{dist_info}sboms/"
    stale_arcnames = frozenset(
        name
        for name in original_zf.namelist()
        if name.startswith(sboms_prefix)
        and name.endswith(SPDX3_JSONLD_EXTENSION)
        and name != sbom_arcname
        and _looks_like_pitloom_sbom(original_zf.read(name))
    )

    record_info = None
    for info in original_zf.infolist():
        if info.filename == record_arcname:
            record_info = info
            break

    old_record_text = (
        original_zf.read(record_arcname).decode("utf-8") if record_info else ""
    )
    new_record_text = _update_record_lines(
        old_record_text,
        sbom_arcname,
        _calculate_record_hash(sbom_bytes),
        len(sbom_bytes),
        dist_info,
        stale_arcnames,
    )

    timestamp, timestamp_floored = _resolve_zip_timestamp(
        record_info.date_time if record_info else None
    )
    return _EmbedPlan(
        sbom_arcname=sbom_arcname,
        record_arcname=record_arcname,
        new_record_bytes=new_record_text.encode("utf-8"),
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
                with original_zf.open(info, "r") as src, new_zf.open(info, "w") as dst:
                    shutil.copyfileobj(src, dst)

            sbom_info = zipfile.ZipInfo(sbom_arcname, date_time=timestamp)
            sbom_info.compress_type = zipfile.ZIP_DEFLATED
            sbom_info.external_attr = _DEFAULT_FILE_ATTR
            new_zf.writestr(sbom_info, sbom_bytes)

            rec_info = zipfile.ZipInfo(record_arcname, date_time=timestamp)
            rec_info.compress_type = zipfile.ZIP_DEFLATED
            rec_info.external_attr = _DEFAULT_FILE_ATTR
            new_zf.writestr(rec_info, record_bytes)

        return temp_path
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def embed_sbom_in_wheel(
    wheel_path: Path | str,
    sbom_content: str | bytes,
    *,
    sbom_filename: str | None = None,
) -> tuple[Path, str, tuple[str, ...], bool]:
    """Embed an SPDX 3 SBOM into a built wheel archive (PEP 770)."""
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

    with zipfile.ZipFile(wheel_obj, "r") as original_zf:
        dist_info = _find_dist_info_prefix(original_zf, wheel_obj)
        plan = _plan_embed(original_zf, dist_info, sbom_filename, sbom_bytes)
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
