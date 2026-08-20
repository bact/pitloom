# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Wheel file discovery and per-file metadata extraction helpers.

See also: :mod:`pitloom.core.models` for SPDX model identifiers and Merkle calculation.
"""

from __future__ import annotations

import hashlib
import operator
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.project import ProjectFile

if TYPE_CHECKING:
    from pitloom.extract._file_headers import FileHeaderMetadata


class _FileHeaderExtras(TypedDict):
    """Keyword arguments for :class:`ProjectFile`'s header/content-type fields."""

    copyright_text: str | None
    copyright_source: str | None
    file_contributors: list[str]
    file_type: str | None
    spdx_license_identifier: str | None
    content_type: str | None
    content_type_method: str | None


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _resolve_file_header_extras(
    raw_bytes: bytes,
    filename: str,
    distribution_path: str,
    parse_header: Callable[[bytes], FileHeaderMetadata | None] | None,
    detect_content: Callable[[bytes, str, str], tuple[str | None, str | None]] | None,
    content_type_overrides: tuple[ContentTypeOverride, ...],
    content_type_method: str,
) -> _FileHeaderExtras:
    """Resolve the optional per-file header/content-type fields for *raw_bytes*."""
    header = parse_header(raw_bytes) if parse_header else None
    content_type: str | None = None
    resolved_method: str | None = None
    if detect_content:
        override = None
        if content_type_overrides:
            # pylint: disable=import-outside-toplevel
            from pitloom.extract._file_headers import resolve_content_type_override

            override = resolve_content_type_override(
                distribution_path, content_type_overrides
            )
        if override is not None:
            content_type = override.content_type
            resolved_method = "config_override"
        else:
            content_type, resolved_method = detect_content(
                raw_bytes, filename, content_type_method
            )
    return _FileHeaderExtras(
        copyright_text=header.copyright_text if header else None,
        copyright_source=header.copyright_source if header else None,
        file_contributors=header.file_contributors if header else [],
        file_type=header.file_type if header else None,
        spdx_license_identifier=(header.spdx_license_identifier if header else None),
        content_type=content_type,
        content_type_method=resolved_method,
    )


# pylint: disable=too-many-locals
def get_wheel_files(
    project_dir: Path,
    *,
    scan_file_headers: bool = False,
    detect_content_type: bool = False,
    content_type_method: str = "auto",
    content_type_overrides: tuple[ContentTypeOverride, ...] = (),
) -> tuple[str | None, list[ProjectFile]]:
    """Get all files included in the wheel and compute their SHA-256 Merkle root.

    Uses hatchling's :class:`~hatchling.builders.wheel.WheelBuilder` to
    discover the exact file set -- respecting every include/exclude rule,
    ``force-include`` entry, and ``packages`` configuration from
    ``pyproject.toml``.
    """
    # pylint: disable=import-outside-toplevel,cyclic-import
    from hatchling.builders.wheel import WheelBuilder

    parse_header = None
    if scan_file_headers:
        from pitloom.extract._file_headers import parse_file_header

        parse_header = parse_file_header

    detect_content = None
    if detect_content_type:
        from pitloom.extract._file_headers import (
            guess_content_type,
            require_magika_available,
        )

        if content_type_method == "magika":
            require_magika_available()
        detect_content = guess_content_type

    try:
        builder = WheelBuilder(str(project_dir))
        project_files: list[ProjectFile] = []
        file_entries: list[tuple[str, bytes]] = []
        for included_file in builder.recurse_included_files():
            source = Path(included_file.path)
            if source.is_file():
                distribution_path = included_file.distribution_path.replace("\\", "/")
                raw_bytes = source.read_bytes()
                digest_bytes = hashlib.sha256(raw_bytes).digest()
                file_entries.append((distribution_path, digest_bytes))
                try:
                    rel_path = source.relative_to(project_dir).as_posix()
                except ValueError:
                    rel_path = source.as_posix()

                extras = _resolve_file_header_extras(
                    raw_bytes,
                    source.name,
                    distribution_path,
                    parse_header,
                    detect_content,
                    content_type_overrides,
                    content_type_method,
                )
                project_files.append(
                    ProjectFile(
                        physical_path=rel_path,
                        distribution_path=distribution_path,
                        digest_sha256=digest_bytes.hex(),
                        **extras,
                    )
                )
    # pylint: disable=broad-exception-caught
    except Exception:
        return None, []

    if not file_entries:
        return None, []

    file_entries.sort(key=operator.itemgetter(0))
    from pitloom.core.models import _build_merkle_tree

    merkle_root = _build_merkle_tree([digest for _, digest in file_entries])
    return merkle_root, project_files
